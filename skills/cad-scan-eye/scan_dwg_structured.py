# -*- coding: utf-8 -*-
"""
scan_dwg_structured.py — B 路：离线结构化提取（不依赖 AutoCAD）

依据：《最终设计 rev2》§3 + 任务书 T5。

技术链：LibreDWG dwg2dxf → DXF 预处理修复（LibreDWG BINARY 组码偶发奇长/
  非 hex 损坏行）→ ezdxf 解析核（修 MTEXT 组码 3/1 顺序 bug，获 handle/布局/
  块变换/正确拼接）。

提取范围（模型空间 + 全部布局）：
  TEXT / MTEXT / DIMENSION / INSERT（virtual_entities 展开块内文字，
  世界坐标已变换，含字高缩放修正）/ ATTRIB / ATTDEF / ACAD_TABLE /
  MULTILEADER（virtual_entities 中 MTEXT 子对象）；XREF 清单（flags&4）。

输出：JSON（含 handle / space / layer_state / source:"B" / filter_criteria）。

用法：
    python scan_dwg_structured.py --file "D:/xx.dwg" [--out <目录>]
    python scan_dwg_structured.py "关键词"          # 连 AutoCAD 拿磁盘路径（可选）
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proxy_detect import find_libredwg_dir   # noqa: E402
from cad_text_clean import clean_mtext      # noqa: E402
from merge_normalize import transform_point  # noqa: E402

# 每块 virtual_entities 展开上限（防超大块爆炸；LibreDWG 输出中模型主体
# 内容可能以「块插入」形式挂载，块内实体可上千，文字排后 → 需较大限额）
_VIRTUAL_LIMIT = 5000
# 总文字条数保护上限（异常图防御）
_MAX_TEXT = 500000


# ---------------------------------------------------------------------------
# 输出目录（设计 §8.3：动态探测，禁止硬编码用户目录）
# ---------------------------------------------------------------------------

def pick_output_dir(preferred=None):
    """动态输出目录（§8.3）：图纸同目录 → 同目录 UNC 形式（SMB 盘符只读兜底）→ 临时目录。"""
    from path_util import ensure_writable_dir
    d, _mode = ensure_writable_dir(preferred)
    return d


# ---------------------------------------------------------------------------
# DWG → DXF（LibreDWG，双命令兜底）
# ---------------------------------------------------------------------------

def dwg_to_dxf(dwg_path, out_dir):
    """dwg2dxf 转换；失败时 dwgread -O DXF 兜底。返回 DXF 路径。"""
    d = find_libredwg_dir()
    if d is None:
        raise FileNotFoundError("LibreDWG 未找到：请安装 LibreDWG 0.14 并设置 "
                                "LIBREDWG_DIR 或放入 ~/.workbuddy/bin/libredwg/")
    dxf_path = out_dir / (Path(dwg_path).stem + "_offline.dxf")

    exe = d / "dwg2dxf.exe"
    r = subprocess.run([str(exe), "-o", str(dxf_path), str(dwg_path)],
                       capture_output=True, timeout=600,
                       encoding="utf-8", errors="replace")
    if not dxf_path.exists() or dxf_path.stat().st_size == 0:
        # 兜底：dwgread -O DXF
        r = subprocess.run(
            [str(d / "dwgread.exe"), "-O", "DXF", "-o", str(dxf_path),
             str(dwg_path)],
            capture_output=True, timeout=600, encoding="utf-8",
            errors="replace")
    if not dxf_path.exists() or dxf_path.stat().st_size == 0:
        raise RuntimeError(f"DWG→DXF 转换失败: {(r.stderr or '')[:200]}")
    return dxf_path


# ---------------------------------------------------------------------------
# DXF 预处理修复（LibreDWG BINARY 组码损坏行）
# ---------------------------------------------------------------------------

_BINARY_FIX_RE = None


def fix_dxf(src_path, dst_path):
    """修复 LibreDWG 输出的两类缺陷，返回 (binary_fixes, truncated_sections)。

    1. BINARY 组码（310-319）畸形值行：奇长/非 hex → "00"（实测 LibreDWG
       偶发输出奇长 "0" 或 GBK 字节串混入，ezdxf 拒绝解析）；
    2. 段截断：LibreDWG 0.14 转大图时偶发在 BLOCKS 等段中间截断（无
       ENDSEC/EOF）→ 截断该未闭合段（丢弃其后内容）补 ENDSEC+EOF，
       ENTITIES 段数据完整保留，块内内容损失记入 errors（降级链原则）。
    """
    raw = open(src_path, "rb").read()
    text = raw.decode("gbk", errors="replace")
    lines = text.split("\n")
    hex_re = re.compile(r"^[0-9A-Fa-f]+$")
    out = []
    fixed = 0
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        out.append(line)
        try:
            code = int(s)
        except ValueError:
            code = None
        if code is not None and 310 <= code <= 319 and i + 1 < n:
            val = lines[i + 1].strip()
            if val:
                if not hex_re.match(val):
                    out.append("00")       # 非 hex（编码损坏串）→ 空字节
                    fixed += 1
                elif len(val) % 2 == 1:
                    out.append(val + "0")  # 奇长纯 hex → 右侧补 0（保持组码对结构）
                    fixed += 1
                else:
                    out.append(lines[i + 1])   # 合法偶长 hex
            else:
                out.append(lines[i + 1])   # 空值原样保留
            i += 2
            continue
        i += 1

    # 段配对检测：未闭合 SECTION → 截断
    trunc = []
    stack = []
    for idx, line in enumerate(out):
        s = line.strip()
        if s == "SECTION":
            stack.append(idx)
        elif s == "ENDSEC":
            if stack:
                stack.pop()
    if stack:
        cut_at = stack[0]   # 第一个未闭合段（嵌套时外层）
        secname = "?"
        for j in range(cut_at, min(cut_at + 5, len(out))):
            if out[j].strip() == "2":
                secname = out[j + 1].strip()
                break
        trunc.append(secname)
        # 保留截断点前已完整的块：找最后一个 ENDBLK 截断
        # （模型空间实体在 BLOCKS 段的 *Model_Space 块内，不能整段丢弃）
        last_endblk = -1
        for j in range(len(out) - 1, cut_at, -1):
            if out[j].strip() == "ENDBLK":
                last_endblk = j
                break
        if last_endblk > cut_at:
            cut_at = last_endblk + 1   # ENDBLK 之后截断（slice 不含组码 0 悬空行）
        elif cut_at >= 1 and out[cut_at - 1].strip() == "0":
            cut_at -= 1   # 无完整块：回退悬空组码 0 行
        # 尾部若已以 ENDSEC 结尾则只补 EOF，避免孤立 ENDSEC
        tail = [l for l in out[:cut_at] if l.strip()]
        if tail and tail[-1].strip() == "ENDSEC":
            out = out[:cut_at] + ["  0", "EOF", ""]
        else:
            out = out[:cut_at] + ["  0", "ENDSEC", "  0", "EOF", ""]

    with open(dst_path, "wb") as f:
        f.write("\n".join(out).encode("gbk"))
    return fixed, trunc


# ---------------------------------------------------------------------------
# ezdxf 解析
# ---------------------------------------------------------------------------

def _read_fixed_dxf(dxf_path, work_dir):
    """ezdxf 读取，失败则预处理修复后重试。返回 (doc, fixes, trunc)。"""
    import ezdxf
    try:
        return ezdxf.readfile(str(dxf_path)), 0, []
    except Exception as e1:
        fixed_path = work_dir / (dxf_path.stem + "_fixed.dxf")
        try:
            fixed, trunc = fix_dxf(dxf_path, fixed_path)
        except Exception as e2:
            raise RuntimeError(f"DXF 解析失败且预处理也失败: {e1} / {e2}")
        try:
            return ezdxf.readfile(str(fixed_path)), fixed, trunc
        except Exception as e3:
            raise RuntimeError(f"DXF 预处理后仍解析失败: {e3} (原始错误: {e1})")


def _layer_states(doc):
    """收集 LAYER 表状态：{name: on|off|frozen}。"""
    states = {}
    try:
        for layer in doc.layers:
            st = "on"
            if layer.is_frozen():
                st = "frozen"
            elif layer.is_off():
                st = "off"
            states[layer.dxf.name] = st
    except Exception:
        pass
    return states


def _round(v, n=2):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def _entity_xy(e):
    """实体插入点（2D）。"""
    try:
        p = e.dxf.insert
        return _round(p.x), _round(p.y)
    except Exception:
        return None, None


def _extract_xrefs(doc):
    """XREF 清单（rev2 §4.5 ①）：块记录 flags&4（bit4=XREF）+ 路径。"""
    xrefs = []
    try:
        for br in doc.blocks:
            b = br.block
            try:
                flags = int(b.dxf.flags)
            except Exception:
                continue
            if flags & 4:  # XREF
                xrefs.append({
                    "name": br.name,
                    "path": b.dxf.get("xref_path", None),
                    "insert": [_round(v) for v in
                               (b.dxf.get("base_point") or (0, 0, 0))],
                    "type": "overlay" if flags & 8 else "attach",
                })
    except Exception:
        pass
    return xrefs


def _safe(dxf, attr, default=None):
    """虚拟实体（virtual entities）的 dxf 属性访问受限，安全取值。"""
    try:
        return dxf.get(attr, default)
    except Exception:
        return default


def extract_doc(doc):
    """解析 ezdxf Document → 结构化结果 dict（未归并的扁平记录）。

    空间归属按块名规则判定（不依赖 ezdxf layouts 绑定——LibreDWG 输出
    块名大小写不一致（*MODEL_SPACE/*Model_Space）、布局块名为中文，
    会导致 ezdxf 的 modelspace 绑定失效）：
      - *MODEL_SPACE（忽略大小写）→ model
      - 块名与布局同名 → layout:<名>
      - *PAPER_SPACE* → 跳过（占位块）
      - 普通块定义 → 不直接提取（块内文字经 INSERT virtual_entities 展开）
    """
    texts = []
    dims = []
    attrs = []
    tables = []
    errors = []
    layer_states = _layer_states(doc)
    table_no = 0
    layout_names = {n.upper() for n in doc.layouts.names()}
    # 布局块记录名（经 LAYOUT 表关联的，如 *MODEL_SPACE/*PAPER_SPACE）
    br_layout_names = set()
    for ln in doc.layouts.names():
        try:
            br_layout_names.add(
                doc.layouts.get(ln).block_record_name.upper())
        except Exception:
            pass

    # 被 INSERT 引用的块（普通块定义，内容经 virtual_entities 展开，不直接提取）
    inserted = set()
    try:
        for br in doc.blocks:
            for e in br:
                if e.dxftype() == "INSERT":
                    try:
                        inserted.add(e.dxf.get("name", "").upper())
                    except Exception:
                        pass
    except Exception:
        pass

    for br in doc.blocks:
        bname = br.name
        uname = bname.upper()
        if uname == "*MODEL_SPACE":
            space = "model"
        elif uname in br_layout_names and uname not in ("*MODEL_SPACE",):
            space = f"layout:{bname}"
        elif "PAPER_SPACE" in uname.replace("*", ""):
            continue   # 图纸空间占位块
        elif uname not in inserted and uname not in layout_names \
                and not bname.startswith("*"):
            # 不被 INSERT 引用且无布局关联的含实体块（排除 *D/*U/*T 匿名块
            # 与 *A$ 组块）→ LibreDWG 丢失 LAYOUT 表关联的孤儿布局块
            #（布局内容直接显示，坐标即布局坐标）
            try:
                has_content = any(e.dxftype() in
                                  ("TEXT", "MTEXT", "DIMENSION", "INSERT",
                                   "ACAD_TABLE", "MULTILEADER")
                                  for e in br)
            except Exception:
                has_content = False
            if not has_content:
                continue
            space = f"layout:{bname}"
        else:
            continue   # 普通块定义：经 INSERT 展开

        for e in br:
            try:
                etype = e.dxftype()
                handle = e.dxf.get("handle", None)
                layer = e.dxf.get("layer", "")
                layer_state = layer_states.get(layer, "on")

                if etype == "TEXT":
                    content, is_field = clean_mtext(e.dxf.text)
                    x, y = _entity_xy(e)
                    texts.append({
                        "content": content, "type": "单行", "layer": layer,
                        "x": x, "y": y,
                        "height": _round(e.dxf.height, 2),
                        "plot_height": _round(e.dxf.height, 2),
                        "rotation": _round(e.dxf.get("rotation", 0.0), 2),
                        "handle": handle, "space": space,
                        "layer_state": layer_state, "source": "B",
                        "is_field": is_field,
                    })
                elif etype == "MTEXT":
                    content, is_field = clean_mtext(e.plain_text())
                    x, y = _entity_xy(e)
                    texts.append({
                        "content": content, "type": "多行", "layer": layer,
                        "x": x, "y": y,
                        "height": _round(e.dxf.char_height, 2),
                        "plot_height": _round(e.dxf.char_height, 2),
                        "rotation": _round(e.dxf.get("rotation", 0.0), 2),
                        "handle": handle, "space": space,
                        "layer_state": layer_state, "source": "B",
                        "is_field": is_field,
                    })
                elif etype == "DIMENSION":
                    m = e.dxf.get("actual_measurement", None)
                    ov = e.dxf.get("text", "")
                    dims.append({
                        "measurement": _round(m, 3),
                        "text_override": ov,
                        "is_overridden": bool(ov) and "<>" not in ov,
                        "layer": layer, "handle": handle, "space": space,
                        "layer_state": layer_state, "source": "B",
                    })
                elif etype == "INSERT":
                    bname2 = e.dxf.get("name", "?")
                    ins = e.dxf.get("insert", None)
                    if ins is not None:
                        ins2 = [_round(ins.x, 2), _round(ins.y, 2)]
                    else:
                        ins2 = [0.0, 0.0]
                    rot = _round(e.dxf.get("rotation", 0.0), 4)
                    sx = e.dxf.get("xscale", 1.0)
                    sy = e.dxf.get("yscale", 1.0)
                    n_virtual = 0
                    try:
                        for ve in e.virtual_entities():
                            n_virtual += 1
                            if n_virtual > _VIRTUAL_LIMIT:
                                break
                            vt = ve.dxftype()
                            if vt in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
                                vx, vy = _entity_xy(ve)
                                vh = _round(_safe(ve.dxf, "height", None), 2)
                                content, is_field = clean_mtext(
                                    ve.plain_text() if vt == "MTEXT"
                                    else ve.dxf.text)
                                rec = {
                                    "content": content,
                                    "type": {"TEXT": "单行", "MTEXT": "多行",
                                             "ATTRIB": "属性",
                                             "ATTDEF": "属性定义"}[vt],
                                    "layer": _safe(ve.dxf, "layer", layer),
                                    "x": vx, "y": vy, "height": vh,
                                    "plot_height": vh,
                                    "rotation": _round(
                                        _safe(ve.dxf, "rotation", 0.0), 2),
                                    "handle": _safe(ve.dxf, "handle", None),
                                    "space": space,
                                    "layer_state": layer_states.get(
                                        _safe(ve.dxf, "layer", layer), "on"),
                                    "source": "B", "is_field": is_field,
                                    "block_name": bname2,
                                    "block_insert": ins2,
                                    "block_scale": [_round(sx, 3),
                                                    _round(sy, 3)],
                                    "block_rotation": rot,
                                }
                                if vt in ("ATTRIB", "ATTDEF"):
                                    rec["tag"] = _safe(ve.dxf, "tag", "")
                                    attrs.append(rec)
                                else:
                                    texts.append(rec)
                    except Exception as e:
                        # 降级链：virtual_entities 对含代理实体等不可变换
                        # 对象的块会整块抛错 → 手动矩阵变换块定义内文字
                        errors.append(f"INSERT展开失败 {bname2}: "
                                      f"{type(e).__name__}")
                        try:
                            block_def = doc.blocks.get(bname2)
                        except Exception:
                            block_def = None
                        if block_def is not None:
                            rot_deg = math.degrees(rot or 0.0)
                            for be in block_def:
                                try:
                                    bt = be.dxftype()
                                    if bt not in ("TEXT", "MTEXT", "ATTRIB",
                                                  "ATTDEF"):
                                        continue
                                    bp = _safe(be.dxf, "insert", None)
                                    if bp is None:
                                        continue
                                    wx, wy = transform_point(
                                        bp.x, bp.y,
                                        (ins2[0] or 0.0, ins2[1] or 0.0),
                                        (sx, sy), rot_deg)
                                    wx, wy = _round(wx), _round(wy)
                                    content, is_field = clean_mtext(
                                        be.plain_text() if bt == "MTEXT"
                                        else be.dxf.text)
                                    bh = _round(_safe(be.dxf, "height",
                                                      None), 2)
                                    rec2 = {
                                        "content": content,
                                        "type": {"TEXT": "单行",
                                                 "MTEXT": "多行",
                                                 "ATTRIB": "属性",
                                                 "ATTDEF": "属性定义"}[bt],
                                        "layer": _safe(be.dxf, "layer",
                                                       layer),
                                        "x": wx, "y": wy,
                                        "height": (_round(bh * abs(sy), 3)
                                                   if bh else None),
                                        "plot_height": (_round(bh * abs(sy), 3)
                                                        if bh else None),
                                        "rotation": _round(
                                            _safe(be.dxf, "rotation", 0.0), 2),
                                        "handle": _safe(be.dxf, "handle",
                                                        None),
                                        "space": space,
                                        "layer_state": layer_states.get(
                                            _safe(be.dxf, "layer", layer),
                                            "on"),
                                        "source": "B", "is_field": is_field,
                                        "block_name": bname2,
                                        "block_insert": ins2,
                                        "block_scale": [_round(sx, 3),
                                                        _round(sy, 3)],
                                        "block_rotation": rot,
                                    }
                                    if bt in ("ATTRIB", "ATTDEF"):
                                        rec2["tag"] = _safe(be.dxf, "tag",
                                                            "")
                                        attrs.append(rec2)
                                    else:
                                        texts.append(rec2)
                                except Exception:
                                    continue
                elif etype == "ACAD_TABLE":
                    table_no += 1
                    cells = []
                    try:
                        for c in e.cells():
                            for cell in c:
                                try:
                                    v = clean_mtext(cell.text)[0]
                                    if v:
                                        cells.append(
                                            {"row": cell.row + 1,
                                             "col": cell.col + 1, "value": v})
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    if cells:
                        tables.append({"table_no": table_no,
                                       "handle": handle, "cells": cells,
                                       "space": space})
                elif etype == "MULTILEADER":
                    try:
                        for ve in e.virtual_entities():
                            if ve.dxftype() == "MTEXT":
                                content, is_field = clean_mtext(
                                    ve.plain_text())
                                vx, vy = _entity_xy(ve)
                                texts.append({
                                    "content": content, "type": "引线",
                                    "layer": layer, "x": vx, "y": vy,
                                    "height": _round(
                                        ve.dxf.get("char_height", None), 2),
                                    "plot_height": _round(
                                        ve.dxf.get("char_height", None), 2),
                                    "handle": handle, "space": space,
                                    "layer_state": layer_state, "source": "B",
                                    "is_field": is_field,
                                })
                    except Exception:
                        pass
            except Exception as e:
                errors.append(f"{etype}:{type(e).__name__}")
            if len(texts) + len(attrs) > _MAX_TEXT:
                errors.append("text limit reached, truncated")
                break

    return {"texts": texts, "dims": dims, "attrs": attrs, "tables": tables,
            "xrefs": _extract_xrefs(doc), "errors": errors}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def scan_file(dwg_path, out_dir=None):
    """对单个 DWG 执行完整离线提取。返回 (payload, output_json_path)。"""
    t0 = time.time()
    dwg_path = Path(dwg_path)
    if not dwg_path.exists():
        raise FileNotFoundError(f"文件不存在: {dwg_path}")

    out_dir = pick_output_dir(out_dir or dwg_path.parent)
    work_dir = pick_output_dir(None)  # DXF 中转一律临时目录（网络盘可读不可写时兜底）
    dxf_path = dwg_to_dxf(dwg_path, work_dir)
    doc, fixed, trunc = _read_fixed_dxf(dxf_path, work_dir)
    result = extract_doc(doc)
    if trunc:
        result["errors"].append(
            f"LibreDWG 输出在段 {trunc} 截断：该段内容已丢弃，"
            f"块内文字可能缺失（建议改用 COM 路或转 T3 后重试）")

    payload = {
        "dwg": dwg_path.name,
        "path": str(dwg_path),
        "mode": "offline_structured",
        "filter_criteria": ("type in [TEXT,MTEXT,DIMENSION,INSERT,ATTRIB,"
                            "ATTDEF,ACAD_TABLE,MULTILEADER] and content non-empty"),
        "total_entities": None,   # ezdxf 无轻量总数（遍历即统计）
        "filtered_entities": len(result["texts"]) + len(result["attrs"]),
        "elapsed_sec": round(time.time() - t0, 1),
        "dxf_fixes": fixed,
        "output_dir": str(out_dir),
        "texts": result["texts"], "dims": result["dims"],
        "attrs": result["attrs"], "tables": result["tables"],
        "xrefs": result["xrefs"],
        "proxy_report": [], "errors": result["errors"],
    }
    out = out_dir / f"{dwg_path.stem}_离线文字.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return payload, out


def main():
    args = sys.argv[1:]
    out_dir = None
    if "--out" in args:
        i = args.index("--out")
        out_dir = args[i + 1]
        args = args[:i] + args[i + 2:]

    if args and args[0] == "--file":
        paths = [Path(args[1])]
    else:
        # 连 AutoCAD 拿磁盘路径（CAD 未运行时抛提示）
        try:
            import comtypes.client
            app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                                  dynamic=True)
        except Exception:
            print("[未连接] AutoCAD 未运行。请用 --file <路径> 直读磁盘文件，"
                  "或先打开 AutoCAD。", flush=True)
            sys.exit(2)
        docs = app.Documents
        keywords = args
        if not keywords:
            paths = [Path(docs.Item(0).FullName)]
        else:
            paths = [Path(docs.Item(i).FullName) for i in range(docs.Count)
                     if any(k in docs.Item(i).Name for k in keywords)]

    for p in paths:
        print(f"\n[离线提取] {p.name}", flush=True)
        try:
            payload, out = scan_file(p, out_dir)
            print(f"  [文字] {len(payload['texts'])} 条 [属性] "
                  f"{len(payload['attrs'])} 条 [标注] {len(payload['dims'])} 条 "
                  f"[XREF] {len(payload['xrefs'])} 个 耗时"
                  f"{payload['elapsed_sec']}s", flush=True)
            if payload["dxf_fixes"]:
                print(f"  [修复] LibreDWG 损坏 BINARY 行 {payload['dxf_fixes']} 处",
                      flush=True)
            for t in payload["texts"][:8]:
                print(f"    [{t['type']}] {t['layer']} ({t['x']},{t['y']}) "
                      f"{t['content'][:50]!r}", flush=True)
            print(f"  [输出JSON] {out}", flush=True)
        except Exception as e:
            print(f"  [失败] {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
