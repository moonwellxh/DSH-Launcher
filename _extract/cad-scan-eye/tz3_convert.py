# -*- coding: utf-8 -*-
"""
tz3_convert.py — 自动转 T3（连接/启动 CAD → 打开图 → 发 TZ3 命令 → 轮询产物）

依据：《最终设计 rev2》§4.4「已装插件（全自动，无需用户确认）→ 自动转 T3」
      + 用户需求增强：不要求手动打开图纸/输命令。

流程：
  1. 连接 AutoCAD（运行中则复用；未运行则用 CreateObject 启动新实例）；
  2. 弹窗防护：设 FILEDIA/CMDDIA/PROXYNOTICE=0、FONTALT 兜底（完成后恢复）；
  3. 打开目标 DWG（已打开则复用，避免重复打开）；
  4. SendCommand("TZ3 ") 触发静默转 T3（原子写 _AiT3）；
  5. 轮询等待 原名_AiT3.dwg 生成（.tmp 残留视为失败重试）；
  6. 成功后写 sidecar 元数据 原名_AiT3.meta.json（mtime/size/快哈希三重增量用）；
  7. 恢复弹窗防护变量。

用法：
    python tz3_convert.py <dwg路径> [--timeout 600] [--close]

注意：需已运行 tz3_install.py --register 并重启 CAD（插件 demand-load 生效），
      或当次已 NETLOAD 对应 dll。TZ3 执行依赖天正环境（tch_kernal.arx 已加载）。
"""
import json
import math
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import t3_paths, quick_hash  # noqa: E402  (复用增量判定工具)

AIT3_SUFFIX = "_AiT3.dwg"
META_SUFFIX = "_AiT3.meta.json"
# 弹窗防护变量：仅 SendCommand 发命令时临时需要（防命令对话框挂起）
# 2026-08-18 优化：仅 CMDDIA 真正需要（FILEDIA 防的是用户手动 Ctrl+O 弹框，
# COM 路径下 Open/Save 不弹文件对话框；PROXYNOTICE 只影响代理提示弹窗）
GUARD_VARS = ("CMDDIA",)
# 主动兜底：设变量后若 N 秒内未恢复，看门狗线程强制恢复（缩小崩溃窗口期）
GUARD_WATCHDOG_SEC = 30


def connect_acad(start=True, timeout=180):
    """连接 AutoCAD。返回 (app, started)。未运行时启动新实例。"""
    import comtypes.client
    try:
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
        return app, False
    except Exception:
        if not start:
            raise
    # 启动新实例（可能较慢，弹许可证/恢复会话对话框由弹窗防护缓解）
    app = comtypes.client.CreateObject("AutoCAD.Application", dynamic=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            _ = app.Version
            break
        except Exception:
            time.sleep(2)
    return app, True


def _retry(fn, retries=120, delay=0.5):
    from comtypes import COMError
    for _ in range(retries):
        try:
            return fn()
        except COMError as e:
            if e.args and e.args[0] == -2147418111:  # RPC_E_CALL_REJECTED
                time.sleep(delay)
                continue
            raise
    raise TimeoutError("COM 调用持续被拒绝")


class _GuardWatchdog:
    """主动兜底：设变量后 N 秒内未恢复则强制恢复（缩小崩溃窗口期）。

    后台线程定时器：到点若 _done 未置位，用快照强制恢复系统变量。
    正常路径 restore_guards 会置位并 cancel，不会触发。
    """

    def __init__(self, doc, saved, timeout=GUARD_WATCHDOG_SEC):
        import threading
        self._doc = doc
        self._saved = dict(saved)
        self._done = False
        self._timer = threading.Timer(timeout, self._fire)
        self._timer.daemon = True

    def start(self):
        self._timer.start()

    def done(self):
        self._done = True
        try:
            self._timer.cancel()
        except Exception:
            pass

    def _fire(self):
        if self._done:
            return
        try:
            for var, val in self._saved.items():
                self._doc.SetVariable(var, val)
            print(f"[主动兜底] {GUARD_WATCHDOG_SEC}s 未恢复，已强制恢复系统变量",
                  flush=True)
        except Exception as e:
            print(f"[主动兜底] 强制恢复失败: {type(e).__name__}: {e}",
                  flush=True)


def set_guards(doc):
    """设置弹窗防护变量（仅 CMDDIA），返回 (原值字典, 主动兜底看门狗)。

    崩溃兜底双保险：
    1. 写快照到 %TEMP%/cad-scan-eye/guards_snapshot.json（供 --restore-guards）；
    2. 启动主动兜底线程，N 秒未恢复则强制恢复（缩小窗口期）。
    """
    import cad_guard
    saved = {}
    for var in GUARD_VARS:
        try:
            saved[var] = doc.GetVariable(var)
            doc.SetVariable(var, 0)
        except Exception:
            pass
    cad_guard.save_snapshot(doc, saved)
    wd = _GuardWatchdog(doc, saved)
    wd.start()
    return saved, wd


def restore_guards(doc, saved, watchdog=None):
    """恢复弹窗防护变量原值，清除快照，并停掉主动兜底看门狗。"""
    import cad_guard
    if watchdog is not None:
        watchdog.done()
    for var, val in saved.items():
        try:
            doc.SetVariable(var, val)
        except Exception:
            pass
    cad_guard.clear_snapshot()


def open_document(app, dwg_path):
    """打开目标图（已打开则复用）。返回 doc。"""
    docs = app.Documents
    p = str(Path(dwg_path).resolve()).lower()
    for i in range(docs.Count):
        d = docs.Item(i)
        try:
            if str(d.FullName).lower() == p:
                return d, False
        except Exception:
            continue
    d = _retry(lambda: docs.Open(str(dwg_path)))
    return d, True


def write_meta(dwg_path, converter_version="TZ3-1.0"):
    """写 sidecar 元数据（供 orchestrator t3_valid 三重增量判定）。"""
    p = Path(dwg_path)
    _, meta = t3_paths(p)
    st = p.stat()
    meta.write_text(json.dumps({
        "src_path": str(p),
        "src_mtime": int(st.st_mtime),
        "src_size": st.st_size,
        "src_quick_hash": quick_hash(p),
        "converter_version": converter_version,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def convert(dwg_path, timeout=600, start_if_needed=True):
    """自动转 T3。返回 (ok, message)。"""
    p = Path(dwg_path)
    if not p.exists():
        return False, f"文件不存在: {p}"
    ait3, meta = t3_paths(p)
    tmp = Path(str(ait3) + ".tmp")

    app, started = connect_acad(start=start_if_needed)
    doc = None
    saved_guards = {}
    guard_wd = None
    try:
        doc, opened = open_document(app, p)
        saved_guards, guard_wd = set_guards(doc)

        # 源文件必须已保存（TZ3 读磁盘文件）
        if not _retry(lambda: doc.Saved):
            print("  [保存] 图纸有未保存修改，先保存...", flush=True)
            _retry(lambda: doc.Save())

        # 发 TZ3 命令（末尾空格 = 回车）
        print("  [命令] 发送 TZ3 ...", flush=True)
        _retry(lambda: doc.SendCommand("TZ3 "))

        # 轮询等待 _AiT3 生成（.tmp 残留视为失败，等待重转）
        t0 = time.time()
        last_size = -1
        while time.time() - t0 < timeout:
            if tmp.exists():
                print("  [等待] 发现 .tmp（转换中）...", flush=True)
                time.sleep(2)
                continue
            if ait3.exists():
                # 稳定检查：连续两次 size 不变视为写完成
                sz = ait3.stat().st_size
                if sz == last_size and sz > 0:
                    write_meta(p)
                    return True, f"转换成功: {ait3}"
                last_size = sz
            time.sleep(2)

        if ait3.exists():
            write_meta(p)
            return True, f"转换完成（超时前已生成）: {ait3}"
        return False, "超时未生成 _AiT3（TZ3 可能未加载，检查插件注册/天正环境）"
    finally:
        if doc is not None:
            restore_guards(doc, saved_guards, guard_wd)


def main():
    argv = sys.argv[1:]

    # 崩溃兜底：一键恢复上次崩溃残留的系统变量
    if "--restore-guards" in argv:
        import cad_guard
        ok, _ = cad_guard.restore_from_snapshot(verbose=True)
        sys.exit(0 if ok else 2)

    if not argv:
        print(__doc__)
        sys.exit(1)
    dwg = argv[0]
    timeout = 600
    if "--timeout" in argv:
        timeout = int(argv[argv.index("--timeout") + 1])
    ok, msg = convert(dwg, timeout=timeout)
    print(f"\n[{'成功' if ok else '失败'}] {msg}", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
