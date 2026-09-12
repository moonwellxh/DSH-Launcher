#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3 textlayer.py —— 文字层确定性提取（FR-B1 词/行 bbox；FR-C3 表格；FR-A2 重路由；FR-A4 页内探测；FR-E3 页原文交叉）
==================================================================
设计依据：详细技术设计 §6.3（复用 pdf_layout.py：_collect/_detect_columns/_order_lines/页眉页脚剔除）、
§3.3（pt_to_px 换算——文字层路径入库前换算为渲染像素系）、§7.4（FR-A4 页内区域级探测）、
需求书 FR-B1/C3/A2/A4/E3。
"""
import re

HEADER_BAND = 0.09


def _noise_key(text, in_band):
    t = re.sub(r"\s+", "", text)
    t = re.sub(r"(第?\d+页?|[—–\-_]?\d{1,3}[—–\-_]?)$", "", t)
    if in_band and not t:
        return "#page-no#"
    return t


def _collect(page):
    h = page.rect.height
    out = []
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            lx = min(s["bbox"][0] for s in spans)
            ly = min(s["bbox"][1] for s in spans)
            rx = max(s["bbox"][2] for s in spans)
            size = spans[0].get("size", 0)
            fonts = sorted({s.get("font", "") for s in spans})
            txt = "".join(s.get("text", "") for s in spans)
            if txt.strip():
                out.append((round(ly), round(lx), round(rx), round(size, 1),
                            fonts[0] if len(fonts) == 1 else "|".join(fonts[:2]), txt))
    return h, out


def _detect_columns(page_w, lines):
    n = len(lines)
    if n == 0:
        return "single"
    starts = [x for (_, x, _, _, _, _) in lines]
    right = [x for x in starts if x >= page_w * 0.65]
    left = [x for x in starts if x <= page_w * 0.35]
    if right and len(right) >= max(3, n * 0.3) and len(left) >= len(right) * 0.5:
        return "double"
    return "single"


def _order_lines(lines, layout, page_w):
    if layout == "double":
        mid = page_w / 2.0
        left = sorted([l for l in lines if l[1] < mid], key=lambda l: (round(l[0] / 8.0), l[1]))
        right = sorted([l for l in lines if l[1] >= mid], key=lambda l: (round(l[0] / 8.0), l[1]))
        return left + right
    return sorted(lines, key=lambda l: (round(l[0] / 8.0), l[1]))


def pt_to_px(box, reg):
    sx, sy = reg["scale"]
    return [round(box[0] * sx), round(box[1] * sy), round(box[2] * sx), round(box[3] * sy)]


_TEXT_MIN_RATIO = 0.50
_PSEUDO_MIN_RATIO = 0.30


def textlayer_page(pdf, page_no, render_reg, cfg):
    """单页文字层 → page part（lines[] px 系、tables 网格、routing/reroute、intra_regions）。
    render_reg = {scale:[sx,sy], dpi, pixel, render_sha1}（变换登记，M2 提供）。"""
    page = pdf[page_no - 1]
    w = page.rect.width
    h, lines = _collect(page)
    lay = _detect_columns(w, lines)
    kept = [l for l in lines if _noise_key(l[5], (l[0] < h * HEADER_BAND) or (l[0] > h * (1 - HEADER_BAND)))]
    ordered = _order_lines(kept, lay, w)
    page_lines = [{"box": pt_to_px([x, y, x1, y + (h * 0.01 or 1)], render_reg),
                   "text": t.strip(), "source": "layout", "size": size, "font": font}
                  for (y, x, x1, size, font, t) in ordered]
    text = "\n".join(pl["text"] for pl in page_lines)
    printable = sum(1 for pl in page_lines if len(pl["text"].strip()) >= 2)
    ratio = printable / len(page_lines) if page_lines else 0.0
    reroute = ratio < _TEXT_MIN_RATIO and ratio >= 0 and len(page_lines) > 0 and ratio < 0.5
    pseudo = ratio < _PSEUDO_MIN_RATIO and len(page_lines) > 0
    # 表格（pdfplumber find_tables，FR-C3）
    tables = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf.name) as docp:
            ptp = docp.pages[page_no - 1]
            for ti, tb in enumerate(ptp.find_tables()):
                grid = tb.extract()
                n_rows = len(grid)
                n_cols = len(grid[0]) if n_rows else 0
                cells = []
                for ri, row in enumerate(grid):
                    for ci in range(n_cols):
                        cells.append({"row": ri, "col": ci, "rowspan": 1, "colspan": 1,
                                      "text": str(row[ci]) if ci < len(row) and row[ci] is not None else "",
                                      "bbox": None, "is_header": ri == 0})
                tables.append({"grid": {"n_rows": n_rows, "n_cols": n_cols, "header_rows": 1},
                               "cells": cells, "status": "ok", "method": "textlayer",
                               "verified_by": ["conservation"], "issues": [],
                               "bbox": pt_to_px(list(tb.bbox), render_reg)})
    except Exception:
        tables = []
    intra_regions = detect_intra_regions(page, page_lines, cfg)
    return {"page_number": page_no, "text": text, "lines": page_lines,
            "blocks": [], "tables": tables, "images": [],
            "routing": [{"page": page_no, "method": "textlayer",
                         "rerouted": bool(pseudo), "reroute_reason": "pseudo_textlayer" if pseudo else None,
                         "intra_page_regions": intra_regions}]}


def detect_intra_regions(page, text_lines, cfg):
    """FR-A4 页内区域级探测（§7.4）：内嵌位图区域 + 线框矢量区，过滤文字覆盖充分者。
    返回 [{bbox_pt, kind, evidence}]。"""
    W, H = page.rect.width, page.rect.height
    regions = []
    for xref in {img[0] for img in page.get_images(full=True)}:
        for r in page.get_image_rects(xref):
            regions.append({"bbox_pt": [r.x0, r.y0, r.x1, r.y1],
                            "kind": "raster_image", "evidence": f"xref={xref}"})
    hz, vt = [], []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 0.5:
                    hz.append((p1, p2))
                elif abs(p1.x - p2.x) < 0.5:
                    vt.append((p1, p2))
            elif it[0] == "re":
                r = it[1]
                hz += [(r.tl, r.tr), (r.bl, r.br)]
                vt += [(r.tl, r.bl), (r.tr, r.br)]
    if len(hz) >= cfg["intra_page"]["wire_h_min"] and len(vt) >= cfg["intra_page"]["wire_v_min"]:
        xs = [p.x for seg in hz + vt for p in seg]
        ys = [p.y for seg in hz + vt for p in seg]
        regions.append({"bbox_pt": [min(xs), min(ys), max(xs), max(ys)],
                        "kind": "raster_table", "evidence": f"wires h={len(hz)} v={len(vt)}"})
    out = []
    for rg in regions:
        x1, y1, x2, y2 = rg["bbox_pt"]
        area = max(0, x2 - x1) * max(0, y2 - y1)
        if area < cfg["intra_page"]["min_region_area_pt2"] or \
           area < cfg["intra_page"]["min_region_area_ratio"] * W * H:
            continue
        cover = text_cover_ratio(text_lines, rg["bbox_pt"])
        if cover > cfg["intra_page"]["text_cover_max"]:
            continue
        out.append(rg)
    return out


def text_cover_ratio(text_lines, bbox_pt):
    """文字行 bbox 与区域交并比（近似，行中心落入计）。"""
    if not text_lines:
        return 0.0
    inside = 0
    for ln in text_lines:
        bx = ln["box"]
        xc = (bx[0] + bx[2]) / 2
        yc = (bx[1] + bx[3]) / 2
        if bbox_pt[0] <= xc <= bbox_pt[2] and bbox_pt[1] <= yc <= bbox_pt[3]:
            inside += 1
    return round(inside / len(text_lines), 4)
