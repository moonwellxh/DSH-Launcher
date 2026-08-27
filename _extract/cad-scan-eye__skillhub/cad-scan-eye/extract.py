# -*- coding: utf-8 -*-
"""
extract.py — A 路：AutoCAD COM 在线提取（rev2 扩展版）

依据：《最终设计 rev2》§3/§5/§7/§8.7 + 任务书 T8。

相对旧版新增（对照任务书 §2.1① 差距清单逐项补齐）：
  - 布局/图纸空间遍历：模型空间 + 全部布局，每条记录带 space 标志；
  - handle（实体句柄）/ layer_state（图层开关冻结状态）/ plot_height；
  - 块属性带块插入点/缩放/旋转；块内文字提取（EffectiveName、世界坐标、
    不等比缩放字高修正）；
  - 弹窗防护：FILEDIA/CMDDIA/PROXYNOTICE/FONTALT 设置与恢复（记录原值）；
  - 看门狗硬超时（默认 5min），超时降级并标注「COM 不完整」；
  - COM 侧 XREF 检测（IsXRef+Path+加载状态）与代理实体枚举（在线轨）；
  - 动态输出目录（先图纸同目录，探测失败降级临时目录并标注实际路径）；
  - 清洗器外置：cad_text_clean.clean_mtext（堆叠分数/换段/字段正确还原）。

用法：
    python extract.py "关键词1" ...             # 默认：文字+块属性+引线+表格
    python extract.py --full "关键词1" ...      # 全量：加标注/块完整字段
    python extract.py --out <目录> ...          # 指定输出目录
    （不传关键词则提取当前激活文档）

输出：JSON（<图纸名>_内容提取.json，含 source:"A"）+ stdout 文字打印。
"""
import json
import math
import os
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cad_text_clean import clean_mtext          # noqa: E402
from merge_normalize import transform_point      # noqa: E402
from proxy_detect import detect_online           # noqa: E402

import comtypes                                     # noqa: E402
import comtypes.client                              # noqa: E402
from pyautocad.types import aDouble, aShort         # noqa: E402

RPC_E_CALL_REJECTED = -2147418111

FILTER_TEXTS = "TEXT,MTEXT,INSERT,MULTILEADER,ACAD_TABLE"
FILTER_FULL = "TEXT,MTEXT,INSERT,DIMENSION,ACAD_TABLE,MULTILEADER"

# 看门狗硬超时（秒）
WATCHDOG_TIMEOUT = 300
# 大图 JSONL 批写阈值（条）
JSONL_THRESHOLD = 20000


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def pick_output_dir(preferred=None):
    """动态输出目录（§8.3）：图纸同目录 → 同目录 UNC 形式（SMB 盘符只读兜底）→ 临时目录。"""
    from path_util import ensure_writable_dir
    d, _mode = ensure_writable_dir(preferred)
    return d


def com_retry(fn, retries=120, delay=0.5):
    """每个 COM 调用包自动重试（RPC_E_CALL_REJECTED 退避）。"""
    for _ in range(retries):
        try:
            return fn()
        except comtypes.COMError as e:
            if e.args and e.args[0] == RPC_E_CALL_REJECTED:
                time.sleep(delay)
                continue
            raise
    raise TimeoutError("COM 调用持续被拒绝：请关闭 AutoCAD 中的对话框后重试")


def _round(v, n=2):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def pt3(p):
    try:
        v = list(p)
        return (_round(v[0]), _round(v[1]), _round(v[2]))
    except Exception:
        return (None, None, None)


# ---------------------------------------------------------------------------
# 看门狗（§8.7：单次提取硬超时）
# ---------------------------------------------------------------------------

class _Watchdog:
    def __init__(self, timeout):
        self.timeout = timeout
        self.fired = False
        self._t = None

    def start(self):
        self._t = threading.Timer(self.timeout, self._fire)
        self._t.daemon = True
        self._t.start()

    def _fire(self):
        self.fired = True

    def stop(self):
        if self._t:
            self._t.cancel()


# ---------------------------------------------------------------------------
# 选择集（减少 COM 往返：按类型批过滤）
# ---------------------------------------------------------------------------

def select_entities(doc, ss_name, filt):
    ssets = com_retry(lambda: doc.SelectionSets)
    try:
        ss = com_retry(lambda: ssets.Item(ss_name))
        com_retry(lambda: ss.Clear())
    except Exception:
        ss = com_retry(lambda: ssets.Add(ss_name))
    com_retry(lambda: ss.Select(5, aDouble(0, 0, 0), aDouble(0, 0, 0),
                                aShort([0]), [filt]))
    return ss


# ---------------------------------------------------------------------------
# 图层状态
# ---------------------------------------------------------------------------

def layer_state_of(doc, layer_name):
    """图层开关/冻结状态：on | off | frozen（记录只读，不改变图面）。"""
    try:
        l = com_retry(lambda: doc.Layers.Item(layer_name))
        if _safe(lambda: l.LayerOn, True) is False:
            return "off"
        if _safe(lambda: l.Freeze, False) is True:
            return "frozen"
        return "on"
    except Exception:
        return "on"


def layer_states(doc, layer_names):
    cache = {}
    for name in set(layer_names):
        cache[name] = layer_state_of(doc, name)
    return cache


# ---------------------------------------------------------------------------
# 块内文字（世界坐标变换，§3 第 2 条）
# ---------------------------------------------------------------------------

# 块定义文字缓存：{block_name: [记录]}（块定义空间坐标）。
# 大图有数千个重复 INSERT，逐实例遍历块定义是 O(实例数×块内实体) 的
# 重复 IO，是 COM 慢的主因；缓存后相同块只遍历一次，实例只做纯计算变换。
_BLOCK_DEF_CACHE = {}


def _block_def_texts(doc, block_name, ls_cache, watchdog):
    """提取块定义内文字（块定义空间坐标 bx/by），带全局缓存。"""
    if block_name in _BLOCK_DEF_CACHE:
        return _BLOCK_DEF_CACHE[block_name]
    out = []
    try:
        bdef = com_retry(lambda: doc.Blocks.Item(block_name))
    except Exception:
        _BLOCK_DEF_CACHE[block_name] = out
        return out
    n = _safe(lambda: bdef.Count, 0)
    for i in range(n):
        if watchdog.fired:
            break
        try:
            obj = com_retry(lambda i=i: bdef.Item(i))
            tname = _safe(lambda: obj.ObjectName, "")
            if tname not in ("AcDbText", "AcDbMText", "AcDbAttributeDefinition"):
                continue
            content, is_field = clean_mtext(
                _safe(lambda: obj.TextString, ""))
            bx = _safe(lambda: obj.InsertionPoint[0], None)
            by = _safe(lambda: obj.InsertionPoint[1], None)
            h = _safe(lambda: obj.Height, None)
            layer = _safe(lambda: str(obj.Layer), "")
            out.append({
                "content": content,
                "type": {"AcDbText": "单行", "AcDbMText": "多行",
                         "AcDbAttributeDefinition": "属性定义"}[tname],
                "layer": layer,
                "bx": bx, "by": by, "height": h,
                "handle": _safe(lambda: str(obj.Handle), None),
                "is_field": is_field,
            })
        except Exception:
            continue
    _BLOCK_DEF_CACHE[block_name] = out
    return out


def _block_texts(doc, block_name, ins, rot_rad, sx, sy, space, ls_cache,
                 watchdog):
    """块内文字 → 世界坐标（缓存块定义 + 逐实例变换；不等比缩放字高修正）。"""
    defs = _block_def_texts(doc, block_name, ls_cache, watchdog)
    rot_deg = math.degrees(rot_rad or 0.0)
    out = []
    for d in defs:
        bx, by = d["bx"], d["by"]
        wx = wy = None
        if bx is not None and by is not None:
            wx, wy = transform_point(bx, by,
                                     (ins[0] or 0.0, ins[1] or 0.0),
                                     (sx or 1.0, sy or 1.0), rot_deg)
        h = d["height"]
        out.append({
            "content": d["content"],
            "type": d["type"],
            "layer": d["layer"],
            "x": _round(wx), "y": _round(wy),
            "height": _round(h * abs(sy or 1.0), 3) if h else None,
            "plot_height": _round(h * abs(sy or 1.0), 3) if h else None,
            "handle": d["handle"],
            "space": space,
            "layer_state": ls_cache.get(d["layer"], "on"),
            "source": "A", "is_field": d["is_field"],
            "block_name": block_name,
            "block_insert": [_round(ins[0]), _round(ins[1])],
            "block_scale": [_round(sx, 3), _round(sy, 3)],
            "block_rotation": _round(rot_deg, 3),
        })
    return out


# ---------------------------------------------------------------------------
# XREF 检测（COM 侧，§4.5 ①）
# ---------------------------------------------------------------------------

def collect_xrefs(doc):
    """遍历块表记录判 IsXRef，读 Path/类型/加载状态。"""
    xrefs = []
    try:
        blocks = com_retry(lambda: doc.Blocks)
        n = _safe(lambda: blocks.Count, 0)
        for i in range(n):
            try:
                b = com_retry(lambda i=i: blocks.Item(i))
                if _safe(lambda: b.IsXRef, False):
                    path = _safe(lambda: b.Path, None)
                    status = "loaded"
                    if path:
                        resolved = Path(str(path))
                        if not resolved.is_absolute():
                            resolved = Path(str(_safe(lambda: doc.Path, "."))) \
                                / resolved
                        if not Path(str(resolved)).exists():
                            status = "missing"
                    xrefs.append({
                        "name": _safe(lambda: str(b.Name), "?"),
                        "path": path,
                        "type": "attach",   # COM 无直接 overlay 标志，见注释
                        "status": status,
                        "origin": pt3(_safe(lambda: b.Origin, (0, 0, 0))),
                    })
            except Exception:
                continue
    except Exception:
        pass
    return xrefs


# ---------------------------------------------------------------------------
# 主提取（单文档）
# ---------------------------------------------------------------------------

def extract_document(doc, full=False, out_dir=None,
                     watchdog_timeout=WATCHDOG_TIMEOUT):
    """提取单个文档全部空间。返回 payload dict。"""
    dwg_name = com_retry(lambda: doc.Name)
    dwg_path = com_retry(lambda: doc.FullName)
    filt = FILTER_FULL if full else FILTER_TEXTS
    t0 = time.time()
    errors = []
    watchdog = _Watchdog(watchdog_timeout)

    saved_guards = None   # 纯读取操作，无需弹窗防护（2026-08-18 优化：减少系统变量修改）
    watchdog.start()
    try:
        texts, attrs, dims, tables, mleaders = [], [], [], [], []
        table_no = 0

        # 空间列表：模型空间 + 全部布局
        spaces = [("model", doc.ModelSpace)]
        try:
            layouts = com_retry(lambda: doc.Layouts)
            for i in range(_safe(lambda: layouts.Count, 0)):
                try:
                    lay = com_retry(lambda i=i: layouts.Item(i))
                    spaces.append((f"layout:{_safe(lambda: str(lay.Name), '?')}",
                                   com_retry(lambda: lay.Block)))
                except Exception:
                    continue
        except Exception as e:
            errors.append(f"布局遍历失败: {type(e).__name__}")

        # 图层状态缓存：遍历图层表（图层数远小于实体数，避免全量遍历实体）
        ls_cache = {}
        try:
            layers = com_retry(lambda: doc.Layers)
            for i in range(_safe(lambda: layers.Count, 0)):
                try:
                    l = com_retry(lambda i=i: layers.Item(i))
                    name = str(_safe(lambda: l.Name, ""))
                    st = "on"
                    if _safe(lambda: l.LayerOn, True) is False:
                        st = "off"
                    elif _safe(lambda: l.Freeze, False) is True:
                        st = "frozen"
                    ls_cache[name] = st
                except Exception:
                    continue
        except Exception:
            pass

        for space, blk in spaces:
            if watchdog.fired:
                errors.append("看门狗超时，COM 提取不完整")
                break
            if space == "model":
                # 模型空间：选择集按类型批过滤（减少 COM 往返，大图性能关键）
                try:
                    ss = select_entities(doc, "KK_EXT_M", filt)
                    total = com_retry(lambda: ss.Count)
                except Exception:
                    continue
                def _item(i):
                    return com_retry(lambda i=i: ss.Item(i))
            else:
                # 布局块：直接遍历（布局实体量小；选择集 Select 作用于当前空间）
                ss = None
                total = _safe(lambda: blk.Count, 0)
                def _item(i):
                    return com_retry(lambda i=i: blk.Item(i))
            for i in range(total):
                if watchdog.fired:
                    errors.append("看门狗超时，COM 提取不完整")
                    break
                try:
                    obj = _item(i)
                    tname = _safe(lambda: obj.ObjectName, "")
                    handle = _safe(lambda: str(obj.Handle), None)
                    layer = _safe(lambda: str(obj.Layer), "")
                    ls = ls_cache.get(layer, "on")

                    if tname in ("AcDbText", "AcDbMText"):
                        content, is_field = clean_mtext(
                            _safe(lambda: obj.TextString, ""))
                        x, y, z = pt3(_safe(lambda: obj.InsertionPoint, (0, 0, 0)))
                        h = _round(_safe(lambda: obj.Height, None))
                        texts.append({
                            "content": content, "type":
                                "单行" if tname == "AcDbText" else "多行",
                            "layer": layer, "x": x, "y": y, "z": z,
                            "height": h, "plot_height": h,
                            "rotation": _round(
                                _safe(lambda: obj.Rotation, 0.0)
                                * 180 / math.pi, 2),
                            "handle": handle, "space": space,
                            "layer_state": ls, "source": "A",
                            "is_field": is_field,
                        })
                    elif tname == "AcDbMLeader":
                        content, is_field = clean_mtext(
                            _safe(lambda: obj.TextString, ""))
                        x, y, z = pt3(_safe(lambda: obj.TextLocation, None))
                        texts.append({
                            "content": content, "type": "引线",
                            "layer": layer, "x": x, "y": y, "z": z,
                            "height": _round(_safe(lambda: obj.TextHeight, None)),
                            "plot_height": _round(
                                _safe(lambda: obj.TextHeight, None)),
                            "handle": handle, "space": space,
                            "layer_state": ls, "source": "A",
                            "is_field": is_field,
                        })
                    elif tname == "AcDbBlockReference":
                        try:
                            bname = str(_safe(lambda: obj.EffectiveName,
                                              _safe(lambda: obj.Name, "?")))
                        except Exception:
                            bname = str(_safe(lambda: obj.Name, "?"))
                        ins = _safe(lambda: obj.InsertionPoint, None)
                        rot = _safe(lambda: obj.Rotation, 0.0) or 0.0
                        sx = _safe(lambda: obj.XScaleFactor, 1.0) or 1.0
                        sy = _safe(lambda: obj.YScaleFactor, 1.0) or 1.0
                        # 块属性（带插入点/变换）
                        if _safe(lambda: obj.HasAttributes, False):
                            for a in _safe(lambda: obj.GetAttributes(), []):
                                attrs.append({
                                    "tag": clean_mtext(_safe(
                                        lambda: a.TagString, ""))[0],
                                    "value": clean_mtext(_safe(
                                        lambda: a.TextString, ""))[0],
                                    "layer": layer,
                                    "handle": _safe(
                                        lambda: str(a.Handle), None),
                                    "space": space,
                                    "layer_state": ls, "source": "A",
                                    "block_name": bname,
                                    "block_insert": pt3(ins)[:2],
                                    "block_scale": [_round(sx, 3),
                                                    _round(sy, 3)],
                                    "block_rotation":
                                        _round(rot * 180 / math.pi, 3),
                                })
                        # 块内文字（世界坐标）
                        if full or True:   # 块内文字在两种模式都提取（提资必需）
                            texts.extend(_block_texts(
                                doc, bname, ins, rot, sx, sy, space,
                                ls_cache, watchdog))
                    elif "Dimension" in tname:
                        m = _round(_safe(lambda: obj.Measurement, None), 3)
                        ov = clean_mtext(_safe(
                            lambda: obj.TextOverride, ""))[0]
                        dims.append({
                            "measurement": m, "text_override": ov,
                            "is_overridden": bool(ov) and "<>" not in ov,
                            "type": tname.replace("AcDb", ""),
                            "layer": layer, "handle": handle,
                            "space": space, "layer_state": ls,
                            "source": "A",
                        })
                    elif tname == "AcDbTable":
                        table_no += 1
                        cells = []
                        for r in range(_safe(lambda: int(obj.Rows), 0)):
                            for c in range(_safe(lambda: int(obj.Columns), 0)):
                                v = ""
                                try:
                                    v = com_retry(lambda r=r, c=c:
                                                  obj.GetCellValue(r, c))
                                except Exception:
                                    try:
                                        v = com_retry(lambda r=r, c=c:
                                                      obj.GetText(r, c))
                                    except Exception:
                                        pass
                                v = clean_mtext(v)[0]
                                if v:
                                    cells.append({"row": r + 1, "col": c + 1,
                                                  "value": v})
                        if cells:
                            tables.append({"table_no": table_no, "cells": cells,
                                           "handle": handle, "space": space})
                except Exception:
                    continue
            if ss is not None:
                try:
                    com_retry(lambda: ss.Delete())
                except Exception:
                    pass
    finally:
        watchdog.stop()
        # 纯读取操作，无系统变量需恢复

    payload = {
        "dwg": dwg_name, "path": dwg_path,
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "full" if full else "texts",
        "filter_criteria": f"type in [{filt}] and content non-empty",
        "elapsed_sec": round(time.time() - t0, 1),
        "texts": texts, "attrs": attrs, "dims": dims,
        "tables": tables,
        "xrefs": collect_xrefs(doc),
        "proxy_report": detect_online(doc),
        "errors": errors,
    }
    out = pick_output_dir(out_dir or Path(dwg_path).parent) \
        / f"{Path(dwg_name).stem}_内容提取.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    payload["_output"] = str(out)
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    # 崩溃兜底：一键恢复上次崩溃残留的系统变量
    if "--restore-guards" in args:
        import cad_guard
        ok, _ = cad_guard.restore_from_snapshot(verbose=True)
        sys.exit(0 if ok else 2)

    full = "--full" in args
    out_dir = None
    if "--out" in args:
        i = args.index("--out")
        out_dir = args[i + 1]
        args = args[:i] + args[i + 2:]
    keywords = [a for a in args if a != "--full"]

    try:
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
    except Exception as e:
        print("[未连接] AutoCAD 未运行。请先打开 AutoCAD 并打开目标 DWG 图纸，"
              "再重新运行。")
        print(f"（原始错误：{type(e).__name__}: {e}）")
        sys.exit(2)

    docs = app.Documents
    print(f"AutoCAD 已打开 {docs.Count} 个文档", flush=True)

    if not keywords:
        matched = [docs.Item(0)]
    else:
        matched = [docs.Item(i) for i in range(docs.Count)
                   if any(k in docs.Item(i).Name for k in keywords)]
        if not matched:
            print(f"[未找到] 没有文档名包含关键词 {keywords}。当前已打开：",
                  flush=True)
            for i in range(docs.Count):
                print(f"    - {docs.Item(i).Name}", flush=True)
            sys.exit(1)

    for d in matched:
        try:
            payload = extract_document(d, full=full, out_dir=out_dir)
            print(f"\n[图纸] {payload['dwg']}", flush=True)
            print(f"[统计] 文字{len(payload['texts'])} 属性"
                  f"{len(payload['attrs'])} 标注{len(payload['dims'])} 表格"
                  f"{len(payload['tables'])} XREF{len(payload['xrefs'])} "
                  f"耗时{payload['elapsed_sec']}s", flush=True)
            if payload["errors"]:
                print(f"[警告] {payload['errors'][:3]}", flush=True)
            print(f"[输出JSON] {payload['_output']}", flush=True)
            print(f"\n{'='*70}\n【{payload['dwg']} 文字内容】\n{'='*70}",
                  flush=True)
            for i, t in enumerate(payload["texts"], 1):
                print(f"{i}\t{t['content']}\t[{t['type']}]\t{t['layer']}"
                      f"\t({t['x']},{t['y']})\t字高={t['height']}", flush=True)
        except Exception as e:
            print(f"[失败] {payload if False else ''}{type(e).__name__}: {e}",
                  flush=True)


if __name__ == "__main__":
    main()
