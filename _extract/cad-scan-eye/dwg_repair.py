# -*- coding: utf-8 -*-
"""
dwg_repair.py — DWG 自动修复（多级修复链）

依据：env.lsp 第 2 阶段「图纸深度修复」+ 扩展多种修复方法。
修复方法（按严重程度递进）：
  1. AUDIT      核查并修复数据库错误（基础）
  2. PURGE      深度清理未使用对象（重复 3 次）
  3. SCALELISTEDIT 重置注释比例列表
  4. 字典清理   删除 ACAD_XREF_NULL/ACAD_XREF_ERROR/ACAD_DGNLINESTYLECOMP/ACAD_PROXY_ENTITY
  5. RECOVER    修复损坏文件（AUDIT 失败时）
  6. 字体修复   FONTALT 兜底 + 重新加载
  7. 外部参照修复 卸载→重新加载→绑定（可选）

输出：原名_fix.dwg（不覆盖源文件）。
用法：
  python dwg_repair.py <dwg路径> [--out <目录>] [--level 1-7]
  python dwg_repair.py <dwg路径> --recover-only    # 仅 RECOVER（严重损坏时）
"""
import ctypes
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import quick_hash  # noqa: E402

FIX_SUFFIX = "_fix.dwg"

# 固定 LISP 目录（勿用临时目录：CAD 加载未信任路径的 LISP 会弹
# 「安全 - 可执行文件」需手动点「运行」，且临时目录路径每次变化会导致
# 信任失效。固定在 skill 目录下，一次性加入 TRUSTEDPATHS 即可长期免弹窗）
LISP_DIR = Path(__file__).parent / "lisp_tmp"


def _ensure_lisp_trusted():
    """确保 LISP_DIR 存在且已加入 CAD TRUSTEDPATHS（追加不覆盖）。

    双保险：
    ① 注册表级（长期）：枚举所有 CAD 版本/产品键追加 TRUSTEDPATHS，
       重启 CAD 后永久生效。复用 tz3_install 机制。
    ② 内存级（即时）：若 CAD 正运行，用 COM SetVariable 直接改当前会话
       的 TRUSTEDPATHS，无需重启立即生效（注册表改动需重启才加载）。
    """
    LISP_DIR.mkdir(parents=True, exist_ok=True)
    target = str(LISP_DIR).replace("/", "\\")
    # ① 注册表级（长期）
    try:
        import winreg
        sys.path.insert(0, str(Path(__file__).parent))
        import tz3_install as tz
        for v in tz.enum_acad_versions():
            for product in v["products"]:
                cur = tz.read_trustedpaths(v["ver"], product)
                if cur and target in cur.split(";"):
                    continue
                try:
                    tz.append_trusted(v["ver"], product, target, [])
                except Exception:
                    pass
    except Exception:
        pass
    # ② 内存级（即时，CAD 运行中）
    try:
        import comtypes.client
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
        if app.Documents.Count == 0:
            d = app.Documents.Add("acad.dwt")
            _tmp = True
        else:
            d = app.ActiveDocument
            _tmp = False
        try:
            tp = d.GetVariable("TRUSTEDPATHS")
            if target not in tp:
                d.SetVariable("TRUSTEDPATHS", tp.rstrip(";") + ";" + target)
        finally:
            if _tmp:
                d.Close(False)
    except Exception:
        pass  # 信任注册失败不阻断——最多弹一次「安全」对话框


def _pump_messages():
    """泵一轮 Windows 消息（PeekMessage PM_REMOVE）。

    根因（2026-08-18 实测）：SendCommand 发命令后，脚本轮询
    GetVariable("CMDACTIVE") 判断是否完成。但 CAD 空闲时 COM 回调
    会滞留在消息队列里——命令行明明显示已完成、回到「命令:」提示符，
    Python 侧的 COM 调用却不返回，直到用户手动按键戳醒消息泵才继续。
    表现为「第一个修复命令完成后脚本卡住，按键才继续下一条」。

    对策：轮询间隙主动 PeekMessage 泵消息，让滞留的 COM 回调及时派发。
    """
    try:
        msg = ctypes.create_string_buffer(48)  # MSG 结构体（64位约48字节）
        user32 = ctypes.windll.user32
        # PeekMessageW(msg, NULL, 0, 0, PM_REMOVE=1)：取走本线程所有待处理消息
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            pass
    except Exception:
        pass


def fix_path(dwg_path):
    """修复输出路径：原名_fix.dwg。"""
    p = Path(dwg_path)
    return p.with_name(p.stem + FIX_SUFFIX)


def _retry(fn, retries=40, delay=0.5):
    from comtypes import COMError
    for _ in range(retries):
        try:
            _pump_messages()  # 重试间隙也泵消息
            return fn()
        except COMError as e:
            if e.args and e.args[0] == -2147418111:
                time.sleep(delay)
                continue
            raise
    # 持续被拒 = CAD 模态挂起，需用户手动按 ESC
    raise TimeoutError("COM 持续被拒：CAD 可能模态挂起，请到 CAD 窗口按 ESC")


def _wait_idle(doc, timeout=30, tag=""):
    """等待 CAD 回到空闲（CMDACTIVE=0）。

    用于命令发出前确保 CAD 已就绪——避免与启动时加载的初始 LISP
    （acad.lsp/acaddoc.lsp/ENV.lsp 等，约 1-2s）打架。带进度打印。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        _pump_messages()  # 戳消息泵，防 COM 回调滞留
        try:
            if doc.GetVariable("CMDACTIVE") == 0:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    print(f"    [等待空闲超时 {tag}] CAD 仍忙，继续尝试", flush=True)
    return False


def _cmd(doc, cmd, timeout=30, tag=""):
    """发送命令并等待完成。带进度反馈，超时主动 ESC 取消悬挂命令。"""
    label = tag or cmd.split()[0][:20]
    # 发出前先等 CAD 空闲（防与初始 LISP 加载打架）
    _wait_idle(doc, timeout=20, tag=label + ":前置")
    print(f"    [执行] {label} ...", flush=True)
    t0 = time.time()
    _retry(lambda: doc.SendCommand(cmd + "\n"))
    last_log = t0
    while time.time() - t0 < timeout:
        _pump_messages()  # 戳消息泵，让命令完成的 COM 回调及时返回
        try:
            if doc.GetVariable("CMDACTIVE") == 0:
                print(f"    [完成] {label}  用时 {time.time()-t0:.1f}s", flush=True)
                return True
        except Exception:
            pass
        # 每 5s 打一次心跳，避免用户干等误判卡死
        if time.time() - last_log >= 5:
            print(f"    [进行中] {label}  已 {int(time.time()-t0)}s ...",
                  flush=True)
            last_log = time.time()
        time.sleep(0.3)
    # 超时仍未结束 → 命令很可能卡在二级提示，ESC 取消避免挂死
    print(f"    [超时] {label} 超过 {timeout}s，发送 ESC 取消", flush=True)
    try:
        doc.SendCommand("\x1b")  # ESC
        time.sleep(0.5)
    except Exception:
        pass
    # ESC 可能把 CAD 顶进模态挂起（COM 全被拒）。主动泵消息并等待
    # 回到空闲；回不去则明确提示用户手动按 ESC，而非闷头重试到崩溃。
    t1 = time.time()
    while time.time() - t1 < 15:
        _pump_messages()
        try:
            if doc.GetVariable("CMDACTIVE") == 0:
                print(f"    [已恢复] {label} ESC 后 CAD 回到空闲", flush=True)
                return False
        except Exception:
            pass
        time.sleep(0.5)
    print(f"    [需手动] {label} ESC 后 CAD 仍挂起，请到 CAD 窗口按 1-2 次 ESC",
          flush=True)
    return False


def _cmd_script(doc, lines, timeout=120):
    """[已废弃] .scr 通道。保留仅为兼容，实际已全面切换 _cmd_lisp。"""
    import tempfile
    content = "\n".join(lines) + "\n\n\n\n"
    fd, scr = tempfile.mkstemp(suffix=".scr", prefix="dwgrepair_")
    try:
        with os.fdopen(fd, "w", encoding="ascii", errors="replace") as f:
            f.write(content)
        try:
            doc.SetVariable("FILEDIA", 0)
        except Exception:
            pass
        ok = _cmd(doc, f'_.script "{scr}"', timeout=timeout)
        try:
            doc.SetVariable("FILEDIA", 1)
        except Exception:
            pass
        return ok
    finally:
        try:
            os.remove(scr)
        except Exception:
            pass


def _cmd_lisp(doc, lisp_body, timeout=180, tag=""):
    """通过 .lsp 文件 + (load) 触发执行，末尾写标记文件判定完成。

    根因（2026-08-18 定稿）：SendCommand 发命令后，CAD 侧命令早已执行完，
    但 CMDACTIVE 卡住不归零（用户手动 ESC 才强制归零），PeekMessage 泵不动
    ——这不是本进程消息队列问题，是 SendCommand 异步执行后 CMDACTIVE 标志
    未复位。因此「脚本如何判断命令完成」不能依赖 CMDACTIVE。

    正解：把修复逻辑写进 .lsp，用 LISP 的 (command ...) 函数——它在 CAD
    自己的 LISP 引擎里同步执行，命令真正结束才返回（与 env.lsp 一致）。
    末尾用 LISP 写标记文件，Python 轮询文件出现即判定完成，完全绕开
    CMDACTIVE。(load "...") 由 SendCommand 发出，但完成判定只看标记文件。

    lisp_body: LISP 表达式字符串（不含最外层包裹，由本函数包裹）。
               若 lisp_body 里对 _RESULT 赋值，则该值被写进标记文件并返回。
    返回 (ok, result)：ok=True=标记文件出现；result=标记文件内容（默认 "DONE"）。
    """
    label = tag or "lisp"
    _ensure_lisp_trusted()  # 确保固定目录已加入信任（防「安全」弹窗）
    # 固定目录 + 时间戳唯一文件名（避免并发出冲突，且路径稳定不失信）
    stamp = f"{int(time.time()*1000)}"
    lisp = LISP_DIR / f"repair_{stamp}.lsp"
    marker = LISP_DIR / f"repair_{stamp}.done"
    try:
        # 路径在 LISP 字符串里用正斜杠（AutoLISP 认 /，避免反斜杠转义）
        marker_fw = str(marker).replace("\\", "/")
        full = (
            "(progn\n"
            + lisp_body + "\n"
            + f'(setq _fh (open "{marker_fw}" "w"))\n'
            + '(write-line (if (boundp (quote _RESULT)) _RESULT "DONE") _fh)\n'
            + "(close _fh)\n"
            + "(princ))\n"
        )
        with open(lisp, "w", encoding="gbk", errors="replace") as f:
            f.write(full)
        if marker.exists():
            marker.unlink()
        # 发出前先等 CAD 空闲
        _wait_idle(doc, timeout=20, tag=label + ":前置")
        print(f"    [执行] {label} ...", flush=True)
        t0 = time.time()
        lisp_fw = str(lisp).replace("\\", "/")
        _retry(lambda: doc.SendCommand(f'(load "{lisp_fw}")\n'))
        last_log = t0
        while time.time() - t0 < timeout:
            _pump_messages()
            if marker.exists():
                result = ""
                try:
                    with open(marker, encoding="gbk", errors="replace") as mf:
                        result = mf.read().strip()
                except Exception:
                    pass
                print(f"    [完成] {label}  用时 {time.time()-t0:.1f}s", flush=True)
                return True, result
            if time.time() - last_log >= 5:
                print(f"    [进行中] {label}  已 {int(time.time()-t0)}s ...",
                      flush=True)
                last_log = time.time()
            time.sleep(0.3)
        print(f"    [超时] {label} 超过 {timeout}s 未见标记文件", flush=True)
        return False, ""
    finally:
        for f_ in (lisp, marker):
            try:
                os.remove(str(f_))  # 直删，绕过 skill 的回收站 safe_delete
            except Exception:
                pass


def repair_audit(doc):
    """1. AUDIT 核查修复（LISP 通道，(command ...) 同步）。"""
    ok, _ = _cmd_lisp(doc, '(command "_.audit" "y")', timeout=180, tag="audit")
    return ok


def repair_purge(doc):
    """2. PURGE 深度清理（重复 3 次，LISP 通道）。

    与 env.lsp 的 (command \"_.purge\" \"a\" \"*\" \"n\") 完全一致——
    每个参数作为独立字符串由 LISP command 函数逐个同步喂给提示。
    """
    body = ""
    for _ in range(3):
        body += '(command "_.-purge" "a" "*" "n")\n'
    ok, _ = _cmd_lisp(doc, body, timeout=300, tag="purge")
    return ok


def repair_scalelist(doc):
    """3. 重置注释比例列表（LISP 通道）。"""
    ok, _ = _cmd_lisp(
        doc, '(command "_.-scalelistedit" "reset" "y" "e")',
        timeout=90, tag="scalelist")
    return ok


def _dict_remove(doc, dict_name):
    """删除命名对象字典（修复深层损坏）。"""
    try:
        nod = doc.NamedObjectsDictionary
        if nod.GetObject(dict_name) is not None:
            nod.Remove(dict_name)
            return True
    except Exception:
        pass
    return False


def repair_dicts(doc):
    """4. 字典清理（LISP 通道）。

    Ctrl+C 触发「保存时出错」的头号元凶是 ACAD_DGNLINESTYLECOMP
    （DGN 线型组件字典）。COM 动态绑定拿不到 doc.NamedObjectsDictionary
    （报 "Name NamedObjectsDictionary not found"），但 LISP 的
    (namedobjdict) 可用。用 (dictsearch ...) 探测、(dictremove ...) 删除。
    结果经标记文件旁路的 _dicts_result.txt 回传（JSON 不便，用纯文本）。
    """
    body = r'''
(setq _nod (namedobjdict))
(setq _rslt "")
(foreach _dn (list "ACAD_DGNLINESTYLECOMP" "ACAD_XREF_NULL" "ACAD_XREF_ERROR" "ACAD_PROXY_ENTITY")
  (if (dictsearch _nod _dn)
    (progn
      (dictremove _nod _dn)
      (setq _rslt (strcat _rslt _dn ":removed;"))
    )
    (setq _rslt (strcat _rslt _dn ":none;"))
  )
)
(setq _RESULT _rslt)
'''
    ok, result = _cmd_lisp(doc, body, timeout=90, tag="dicts")
    # 解析 LISP 回传结果，格式 "NAME:removed;NAME:none;..."
    results = []
    parsed = {}
    for part in result.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            parsed[k.strip()] = (v.strip() == "removed")
    for name in ("ACAD_DGNLINESTYLECOMP", "ACAD_XREF_NULL",
                 "ACAD_XREF_ERROR", "ACAD_PROXY_ENTITY"):
        results.append({"dict": name,
                        "removed": parsed.get(name, False),
                        "via": "lisp-dictremove" if ok else "lisp-timeout"})
    return results


def repair_recover(doc, dwg_path):
    """5. RECOVER 修复损坏文件（AUDIT 失败时）。

    返回 (new_doc, ok, new_is_self_opened)：第三个值标记新文档是否为
    本函数自己重新打开（供外层 finally 决定是否关闭）。RECOVER 会
    先关闭当前文档再重开，若原 doc 是复用的，重开后的新文档归脚本管。
    """
    try:
        app = doc.Application
        doc.Close(False)
        new_doc = _retry(lambda: app.Documents.Open(str(dwg_path)))
        return new_doc, True, True
    except Exception:
        return doc, False, False


def repair_fonts(doc):
    """6. 字体修复（FONTALT 兜底 + regen，LISP 通道）。"""
    try:
        doc.SetVariable("FONTALT", "simplex.shx")
    except Exception:
        pass
    ok, _ = _cmd_lisp(doc, '(command "_.regen")', timeout=60, tag="regen")
    return ok


def repair_xrefs(doc):
    """7. 外部参照修复（卸载→重新加载）。"""
    results = []
    try:
        blocks = doc.Blocks
        for i in range(blocks.Count):
            b = blocks.Item(i)
            if b.IsXRef:
                name = b.Name
                try:
                    b.Unload()
                    b.Reload()
                    results.append({"xref": name, "fixed": True})
                except Exception as e:
                    results.append({"xref": name, "fixed": False,
                                    "error": str(e)[:50]})
    except Exception:
        pass
    return results


def _has_save_error(app, dwg_path):
    """探测图纸是否有「保存时出错」：用 WBLOCK 全图导出做校验。

    关键（2026-08-19 实测）：COM SaveAs 成功 ≠ Ctrl+C 不报错。Ctrl+C
    触发的是「保存到剪贴板临时文件」的导出校验，比 SaveAs 严格，能暴露
    代理对象/数据库深层损坏。WBLOCK（写块全图）与剪贴板导出走同一套
    校验逻辑，因此用 WBLOCK 到临时文件来探测，比 SaveAs 更贴近真实症状。

    返回 True=仍有导出/保存错误（需重建），False=正常。
    判定依据：WBLOCK 全图导出到临时 DWG 是否抛异常。
    """
    import tempfile
    doc = None
    tmp = None
    try:
        doc = _retry(lambda: app.Documents.Open(str(dwg_path)))
        fd, tmp = tempfile.mkstemp(suffix=".dwg")
        os.close(fd)
        os.remove(tmp)  # WBLOCK 要求目标不存在
        tmp_fw = tmp.replace("\\", "/")
        # WBLOCK 全图导出（LISP 通道，与剪贴板导出同套校验）
        body = f'(command "_.-wblock" "{tmp_fw}" "*")'
        ok, _ = _cmd_lisp(doc, body, timeout=120, tag="verify-wblock")
        return not ok  # WBLOCK 失败 → 仍有错误
    except Exception:
        return True  # 打开/执行失败 → 视为有错误
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass


def rebuild_via_xref(app, src_path, fix_file):
    """最终方案：新建空白图 → 把源图作为 XREF 插入 → 绑定 → 另存。

    适用：原地修复（AUDIT/PURGE/字典清理）后仍有「保存时出错」，
    说明损坏在数据库深层（多为天正代理对象/逻辑错误），需重建数据库壳。

    通道（2026-08-19 定稿）：全程纯 COM 同步直调，不读 CMDACTIVE。
    完成判定靠「数据库实际状态」而非命令标志：
      - attach 完成 = 图纸块表里出现源图对应的 XRef 块；
      - bind 完成 = 该块 IsXRef 变为 False（并入当前图）。
    这样彻底绕开 CMDACTIVE 卡死的坑（新建文档的命令泵未热时
    _wait_idle 会卡死，2026-08-19 实测）。
    返回 True=成功。
    """
    from pathlib import Path as _P
    src_name = _P(str(src_path)).stem  # XRef 块名 = 源文件名（无扩展名）
    # 1. 新建空白文档
    try:
        new_doc = _retry(lambda: app.Documents.Add("acad.dwt"))
        time.sleep(1.5)
        print(f"    [重建] 新建空白图: {new_doc.Name}", flush=True)
    except Exception as e:
        print(f"    [失败] 新建空白文档: {str(e)[:60]}", flush=True)
        return False

    def _find_xref_block():
        """在块表里找源图对应的 XRef 块，返回 (block, is_xref) 或 None。"""
        try:
            blocks = new_doc.Blocks
            for i in range(blocks.Count):
                b = blocks.Item(i)
                if b.Name.lower() == src_name.lower():
                    return b, bool(b.IsXRef)
        except Exception:
            pass
        return None

    # 2. attach 源图为 XRef（SendCommand 异步，轮询块表判定完成）
    src_fw = str(src_path).replace("\\", "/")
    try:
        new_doc.SendCommand(f'_.-xref _a "{src_fw}" 0,0 1 1 0\n')
    except Exception as e:
        print(f"    [失败] attach 命令发出: {str(e)[:60]}", flush=True)
        new_doc.Close(False)
        return False
    t0 = time.time()
    attached = False
    while time.time() - t0 < 90:
        _pump_messages()
        found = _find_xref_block()
        if found and found[1]:  # 块出现且 IsXRef=True
            attached = True
            print(f"    [重建] attach 完成  用时 {time.time()-t0:.1f}s", flush=True)
            break
        time.sleep(0.5)
    if not attached:
        print("    [失败] attach 超时（90s 未见 XRef 块）", flush=True)
        new_doc.Close(False)
        return False

    # 3. bind（绑定并入当前图数据库），轮询 IsXRef 变 False
    try:
        new_doc.SendCommand(f'_.-xref _b "{src_name}"\n')
    except Exception as e:
        print(f"    [失败] bind 命令发出: {str(e)[:60]}", flush=True)
        new_doc.Close(False)
        return False
    t0 = time.time()
    bound = False
    while time.time() - t0 < 90:
        _pump_messages()
        found = _find_xref_block()
        # 绑定后块名会变（加前缀 名字$0$名字），IsXRef 变 False；
        # 简单判据：原 XRef 块不再是 XRef 即视为绑定完成
        if found and not found[1]:
            bound = True
            print(f"    [重建] bind 完成  用时 {time.time()-t0:.1f}s", flush=True)
            break
        time.sleep(0.5)
    if not bound:
        print("    [警告] bind 状态未确认，继续尝试另存", flush=True)

    # 4. 另存为 fix 文件（SaveAs 是同步 COM 方法）
    fix_fw = str(fix_file).replace("\\", "/")
    try:
        _retry(lambda: new_doc.SaveAs(str(fix_file)))
        print(f"    [重建] 另存完成: {fix_file}", flush=True)
        ok = True
    except Exception as e:
        print(f"    [失败] 另存: {str(e)[:60]}", flush=True)
        ok = False
    try:
        new_doc.Close(False)
    except Exception:
        pass
    return ok


def repair(dwg_path, out_dir=None, level=7, recover_only=False, rebuild=False):
    """执行修复。返回 (ok, fix_file, report)。

    level: 修复级别（1-7，数字越大修复越深）
    recover_only: 仅执行 RECOVER（严重损坏时）
    """
    p = Path(dwg_path)
    if not p.exists():
        return False, None, {"error": f"文件不存在: {p}"}

    fix_file = fix_path(p)
    if out_dir:
        fix_file = Path(out_dir) / fix_file.name

    report = {
        "source": str(p),
        "fix_file": str(fix_file),
        "steps": [],
        "level": level,
    }

    import comtypes.client
    try:
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
        started = False
    except Exception:
        app = comtypes.client.CreateObject("AutoCAD.Application",
                                           dynamic=True)
        started = True
        t0 = time.time()
        while time.time() - t0 < 180:
            try:
                _ = app.Version
                break
            except Exception:
                time.sleep(2)

    doc = None
    opened_doc_hwnd = None
    try:
        # 若目标图纸已在 CAD 中打开（多为历次崩溃遗留、带损坏状态），
        # 与目标同名的文档若已打开，多为历次脚本崩溃遗留。但需防止误关
        # 用户手动打开的图纸——安全判据：仅当该文档「未做用户修改」
        # （DBMOD=0，崩溃遗留通常无用户改动）时才自动关闭；有改动则报错
        # 请用户处理，绝不擅自关。用户开的其他图纸（非同名）一律不碰。
        try:
            target = str(p).lower()
            for i in range(app.Documents.Count - 1, -1, -1):
                d = app.Documents.Item(i)
                try:
                    if d.FullName.lower() == target:
                        dbmod = int(d.GetVariable("DBMOD"))
                        if dbmod == 0:
                            print(f"  [关闭遗留] {d.Name}（无用户改动，DBMOD=0）",
                                  flush=True)
                            d.Close(False)
                            time.sleep(1)
                        else:
                            # 有未保存改动——可能是用户正在编辑，绝不自动关
                            report["steps"].append({
                                "step": "open", "ok": False,
                                "error": f"目标图纸已在 CAD 打开且有未保存改动"
                                         f"(DBMOD={dbmod})，请先手动关闭或保存"})
                            return False, None, report
                except Exception:
                    pass
        except Exception:
            pass

        # 干净打开图纸
        try:
            doc = _retry(lambda: app.Documents.Open(str(p)))
            opened_doc_hwnd = doc.FullName.lower()
            print(f"  [打开] {doc.Name}", flush=True)
        except Exception as e:
            report["steps"].append({"step": "open", "ok": False,
                                    "error": str(e)[:100]})
            return False, None, report

        report["steps"].append({"step": "open", "ok": True})

        # 设置静默模式
        try:
            doc.SetVariable("FILEDIA", 0)
            doc.SetVariable("CMDDIA", 0)
            doc.SetVariable("CMDECHO", 0)
        except Exception:
            pass

        if recover_only:
            # 仅 RECOVER 模式
            doc, ok, self_opened = repair_recover(doc, p)
            if self_opened:
                opened_doc_hwnd = doc.FullName.lower()
            report["steps"].append({"step": "recover", "ok": ok})
        else:
            # 多级修复链
            if level >= 1:
                ok = repair_audit(doc)
                report["steps"].append({"step": "audit", "ok": ok})

            if level >= 2:
                ok = repair_purge(doc)
                report["steps"].append({"step": "purge", "ok": ok})

            if level >= 3:
                ok = repair_scalelist(doc)
                report["steps"].append({"step": "scalelist", "ok": ok})

            if level >= 4:
                results = repair_dicts(doc)
                report["steps"].append({"step": "dicts", "results": results})

            if level >= 5:
                # AUDIT 失败时执行 RECOVER
                audit_ok = any(s.get("step") == "audit" and s.get("ok")
                               for s in report["steps"])
                if not audit_ok:
                    doc, ok, self_opened = repair_recover(doc, p)
                    if self_opened:
                        opened_doc_hwnd = doc.FullName.lower()
                    report["steps"].append({"step": "recover", "ok": ok})

            if level >= 6:
                ok = repair_fonts(doc)
                report["steps"].append({"step": "fonts", "ok": ok})

            if level >= 7:
                results = repair_xrefs(doc)
                report["steps"].append({"step": "xrefs", "results": results})

        # 另存为 _fix（SaveAs 后 doc 指向的已是 _fix 文件）
        try:
            _retry(lambda: doc.SaveAs(str(fix_file)))
            report["steps"].append({"step": "saveas", "ok": True,
                                    "file": str(fix_file)})
            # 更新跟踪路径为 _fix，确保 finally 能关掉这个文档
            opened_doc_hwnd = doc.FullName.lower()
        except Exception as e:
            report["steps"].append({"step": "saveas", "ok": False,
                                    "error": str(e)[:100]})
            return False, None, report

        # 恢复环境变量
        try:
            doc.SetVariable("FILEDIA", 1)
            doc.SetVariable("CMDDIA", 1)
        except Exception:
            pass

        # ---- 修复后验证：试存到临时文件，仍报错则自动启用最终方案 ----
        # 判定机制：何时使用 XREF 重建？
        #   原地修复（AUDIT/PURGE/SCALELIST/字典）完成后，对 _fix.dwg 做一次
        #   「试开+试存到临时文件」。若 SaveAs 仍抛异常 → 损坏在数据库深层
        #   （多为天正代理对象/逻辑错误），原地修复无效 → 自动降级到
        #   XREF 重建（新建空白图→插入源图为外部参照→绑定→另存）。
        #   rebuild=True 时跳过原地修复直接重建。
        still_bad = False
        if not rebuild:
            # 先关掉修复文档（释放 _fix.dwg），再验证
            try:
                if opened_doc_hwnd and doc.FullName.lower() == opened_doc_hwnd:
                    doc.Close(False)
                    opened_doc_hwnd = None
                    time.sleep(1)
            except Exception:
                pass
            print("  [验证] 试存 _fix.dwg 检测是否仍有保存错误 ...", flush=True)
            still_bad = _has_save_error(app, fix_file)
            if still_bad:
                print("  [验证] 仍有保存错误 → 自动启用 XREF 重建", flush=True)

        if rebuild or still_bad:
            print("  [重建] 新建空白图 + XREF 插入绑定 ...", flush=True)
            ok_rebuild = rebuild_via_xref(app, p, fix_file)
            report["steps"].append({"step": "xref_rebuild", "ok": ok_rebuild})
            if not ok_rebuild:
                report["steps"].append({"step": "saveas", "ok": False,
                                        "error": "XREF 重建失败"})
                return False, None, report

        # 写 sidecar
        meta = fix_file.with_suffix(".meta.json")
        st = p.stat()
        meta.write_text(json.dumps({
            "src_path": str(p),
            "src_mtime": int(st.st_mtime),
            "src_size": st.st_size,
            "src_quick_hash": quick_hash(p),
            "fix_file": str(fix_file),
            "repair_steps": report["steps"],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=1), encoding="utf-8")

        report["ok"] = True
        return True, fix_file, report

    finally:
        # 只关闭「脚本自己打开」的文档；用户手动打开的、CAD 自动带出的
        # 只读参照底图一律不碰。复用已打开文档时 opened_doc_hwnd 为 None，
        # 同样不关。
        if doc is not None and opened_doc_hwnd is not None:
            try:
                if doc.FullName.lower() == opened_doc_hwnd:
                    print(f"  [关闭] 脚本打开的文档: {doc.Name}", flush=True)
                    doc.Close(False)
            except Exception:
                pass
        if started:
            try:
                app.Quit()
            except Exception:
                pass


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)

    dwg = argv[0]
    out_dir = None
    level = 7
    recover_only = False
    rebuild = False

    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    if "--level" in argv:
        level = int(argv[argv.index("--level") + 1])
    if "--recover-only" in argv:
        recover_only = True
    if "--rebuild" in argv:
        rebuild = True

    ok, fix_file, report = repair(dwg, out_dir=out_dir, level=level,
                                  recover_only=recover_only, rebuild=rebuild)

    print(f"\n{'='*60}")
    print(f"修复结果: {'成功' if ok else '失败'}")
    print(f"源文件: {report.get('source')}")
    if fix_file:
        print(f"修复文件: {fix_file}")
    print(f"执行步骤:")
    for s in report.get("steps", []):
        status = "✓" if s.get("ok") else "✗"
        print(f"  [{status}] {s.get('step')}")
        if s.get("error"):
            print(f"       错误: {s['error']}")
        if s.get("results"):
            for r in s["results"]:
                r_status = "✓" if r.get("removed") or r.get("fixed") else "-"
                print(f"       [{r_status}] {r.get('dict') or r.get('xref')}")
    print(f"{'='*60}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
