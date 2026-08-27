# -*- coding: utf-8 -*-
"""
cad_guard.py — CAD 系统变量快照与崩溃兜底（崩溃/卡死时保证环境可恢复）。

背景（2026-08-18 用户要求）：skill 为防 COM 弹窗挂起，会临时设
FILEDIA/CMDDIA/PROXYNOTICE=0、FONTALT=兜底字体，完成后恢复。正常路径有
try/finally 保证恢复；但 Python 进程崩溃/被 kill 时 finally 不执行，
CAD 端变量残留在 0（用户 Ctrl+O 变命令行模式）。

本模块提供崩溃兜底：
  1. 设变量前把原值快照写入 %TEMP%/cad-scan-eye/guards_snapshot.json
     （若上次的快照残留未删，说明上次崩溃——本次仍覆盖，但保留旧档 *_stale.json）；
  2. 正常恢复后删除快照文件；
  3. 提供 has_stale_snapshot() 检测 + restore_from_snapshot() 一键恢复；
  4. extract.py / tz3_convert.py 支持 --restore-guards 选项；
     orchestrator 运行前自检，发现残留快照时打印告警与恢复命令。

红线：恢复失败不静默——写入 errors 或抛带原始报错的异常。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SNAP_DIR = Path(tempfile.gettempdir()) / "cad-scan-eye"
SNAP_FILE = SNAP_DIR / "guards_snapshot.json"
STALE_FILE = SNAP_DIR / "guards_snapshot_stale.json"

# skill 会临时设置的 CAD 系统变量（与 extract.py / tz3_convert.py 一致）
GUARD_VARS = ("FILEDIA", "CMDDIA", "PROXYNOTICE", "FONTALT")


def _write_json_atomic(path: Path, data: dict):
    """原子写 JSON（先 .tmp 再 rename），避免写一半被 kill 留坏档。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        # 跨设备 rename 失败兜底（理论上同目录不会发生）
        import shutil
        shutil.move(str(tmp), str(path))


def save_snapshot(doc, vars_set: dict):
    """把本次设置的原值快照写盘。vars_set = {变量名: 原值}。

    若已存在残留快照（上次崩溃未删），先备份为 *_stale.json 再覆盖。
    """
    try:
        if SNAP_FILE.exists():
            try:
                SNAP_FILE.replace(STALE_FILE)
            except OSError:
                pass
        _write_json_atomic(SNAP_FILE, {
            "created_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            "doc_name": _safe_str(lambda: doc.Name),
            "doc_path": _safe_str(lambda: doc.FullName),
            "vars": {k: _to_jsonable(v) for k, v in vars_set.items()},
        })
    except Exception as e:
        # 快照写失败不阻断主流程，但必须告知（红线：不静默）
        print(f"[cad_guard] 警告：快照写入失败（崩溃时将无法自动恢复）: "
              f"{type(e).__name__}: {e}", file=sys.stderr, flush=True)


def clear_snapshot():
    """正常恢复后删除快照文件。"""
    try:
        if SNAP_FILE.exists():
            SNAP_FILE.unlink()
    except Exception:
        pass


def has_stale_snapshot():
    """是否存在残留快照（= 上次提取崩溃/卡死未恢复）。"""
    return SNAP_FILE.exists()


def load_snapshot():
    """读快照；不存在返回 None。"""
    try:
        return json.loads(SNAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def restore_from_snapshot(verbose=True):
    """用快照恢复 CAD 系统变量。返回 (ok, detail_lines)。

    流程：连接 CAD → 逐变量 SetVariable 回快照值 → 删除快照文件。
    任何一步失败都记入 detail，不静默。
    """
    lines = []
    snap = load_snapshot()
    if not snap:
        lines.append("无残留快照，无需恢复")
        if verbose:
            for ln in lines:
                print(ln, flush=True)
        return True, lines

    vars_map = snap.get("vars") or {}
    if not vars_map:
        lines.append("快照内容为空，直接清理快照文件")
        clear_snapshot()
        if verbose:
            for ln in lines:
                print(ln, flush=True)
        return True, lines

    lines.append(f"快照时间: {snap.get('created_at')}")
    lines.append(f"涉及文档: {snap.get('doc_name')} ({snap.get('doc_path')})")

    try:
        import comtypes.client
    except Exception as e:
        lines.append(f"comtypes 不可用: {type(e).__name__}: {e}")
        if verbose:
            for ln in lines:
                print(ln, flush=True)
        return False, lines

    try:
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
    except Exception as e:
        lines.append(f"AutoCAD 未运行，无法恢复（请先打开 AutoCAD）: "
                     f"{type(e).__name__}")
        if verbose:
            for ln in lines:
                print(ln, flush=True)
        return False, lines

    doc = app.ActiveDocument
    ok = True
    for var, val in vars_map.items():
        try:
            doc.SetVariable(var, val)
            lines.append(f"  已恢复 {var} = {val}")
        except Exception as e:
            ok = False
            lines.append(f"  恢复 {var} 失败: {type(e).__name__}: {e}")

    if ok:
        clear_snapshot()
        lines.append("快照已清理")
    else:
        lines.append("部分变量恢复失败，快照保留以便重试")
    if verbose:
        for ln in lines:
            print(ln, flush=True)
    return ok, lines


def self_check_and_warn():
    """orchestrator 启动自检：发现残留快照则打印告警与恢复命令。返回是否干净。"""
    if not has_stale_snapshot():
        return True
    snap = load_snapshot() or {}
    print("=" * 60, flush=True)
    print("[cad_guard] 检测到上次提取可能崩溃/卡死：系统变量快照残留", flush=True)
    print(f"  快照时间: {snap.get('created_at', '?')}", flush=True)
    print(f"  涉及文档: {snap.get('doc_name', '?')}", flush=True)
    print("  影响：AutoCAD 的 FILEDIA/CMDDIA 可能停在 0（Ctrl+O 等不弹对话框）",
          flush=True)
    print("  恢复：先打开 AutoCAD，然后运行：", flush=True)
    print("    python \"<skill目录>/extract.py\" --restore-guards", flush=True)
    print("  或：", flush=True)
    print("    python \"<skill目录>/tz3_convert.py\" --restore-guards", flush=True)
    print("=" * 60, flush=True)
    return False


def _safe_str(fn):
    try:
        return str(fn())
    except Exception:
        return "?"


def _to_jsonable(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)


def main():
    argv = sys.argv[1:]
    if "--restore-guards" in argv or "--restore" in argv:
        ok, _ = restore_from_snapshot(verbose=True)
        sys.exit(0 if ok else 2)
    if "--check" in argv:
        sys.exit(0 if not has_stale_snapshot() else 1)
    print(__doc__)
    print("用法:")
    print("  python cad_guard.py --check            # 检测是否有残留快照")
    print("  python cad_guard.py --restore-guards   # 按快照恢复系统变量")


if __name__ == "__main__":
    main()
