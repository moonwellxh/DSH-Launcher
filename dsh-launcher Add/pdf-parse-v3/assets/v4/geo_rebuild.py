#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M14 geo_rebuild.py —— 表格几何重建（FR-C2/C4；研究报告附录A 原型工程化）
====================================================================
设计依据：详细技术设计 §7.5（§7.5.1 线框表 / §7.5.2 无框表）；需求书 FR-C2/C4。
GLM 主路线中的离线确定性兜底与校验手段，产出同样过校验门（FR-D3）。
失败不硬猜（FR-C4）→ 返回 None 升缺陷阶梯。
"""
import cv2
import numpy as np


def cluster_lines(lines, axis, tol):
    """线段坐标聚类（axis=0 竖线 x、axis=1 横线 y）。返回聚类中心列表。"""
    if not lines:
        return []
    vals = sorted(lines)
    clusters = []
    for v in vals:
        if clusters and v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def cluster_1d(vals, tol):
    vals = sorted(vals)
    clusters = []
    for v in vals:
        if clusters and v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def line_center(line):
    box = line["box"]
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def median_line_w(lines):
    ws = sorted(line["box"][2] - line["box"][0] for line in lines) or [1]
    return ws[len(ws) // 2]


def median_line_h(lines):
    hs = sorted(line["box"][3] - line["box"][1] for line in lines) or [1]
    return hs[len(hs) // 2]


def row_pitch_cv(ys):
    if len(ys) < 2:
        return 0.0
    ys = sorted(ys)
    pitches = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    if not pitches:
        return 0.0
    mean = sum(pitches) / len(pitches)
    if mean == 0:
        return 0.0
    var = sum((p - mean) ** 2 for p in pitches) / len(pitches)
    return round((var ** 0.5) / mean, 4)


def segment_exists(lines, y, x0, x1, tol=4):
    """横线 y 上是否存在覆盖 [x0,x1] 的线段。"""
    for (yy, xx0, xx1) in lines:
        if abs(yy - y) <= tol and (xx0 <= x0 + tol and xx1 >= x1 - tol):
            return True
    return False


def _openings_grid(hz_lines, vt_lines, grid_x, grid_y, tol):
    """由线段存在性推断合并。hz=水平线段 [(y,x0,x1)]，vt=[(x,y0,y1)]。
    返回 rs_map/ cs_map：{'open_down'/'open_right'}。"""
    R = len(grid_y) - 1
    C = len(grid_x) - 1
    rs_map, cs_map = {}, {}
    for r in range(R):
        for c in range(C):
            if not _h_seg(hz_lines, grid_y[r + 1], grid_x[c], grid_x[c + 1], tol):
                rs_map[(r, c)] = "open_down"
            if not _v_seg(vt_lines, grid_x[c + 1], grid_y[r], grid_y[r + 1], tol):
                cs_map[(r, c)] = "open_right"
    return rs_map, cs_map


def _h_seg(hz_lines, y, x0, x1, tol=4):
    return any(abs(yy - y) <= tol and (xx0 <= x0 + tol and xx1 >= x1 - tol) for (yy, xx0, xx1) in hz_lines)


def _v_seg(vt_lines, x, y0, y1, tol=4):
    return any(abs(xx - x) <= tol and (yy0 <= y0 + tol and yy1 >= y1 - tol) for (xx, yy0, yy1) in vt_lines)


def build_cells_from_openings(R, C, rs_map, cs_map):
    """合并推断：并查集合并开放边 → 网格 cell 列表（row/col/rowspan/colspan/text/bbox/is_header）。"""
    parent = {}
    def find(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for (r, c), kind in rs_map.items():
        if kind == "open_down" and (r + 1, c) in _allcells(R, C):
            union((r, c), (r + 1, c))
    for (r, c), kind in cs_map.items():
        if kind == "open_right" and (r, c + 1) in _allcells(R, C):
            union((r, c), (r, c + 1))
    groups = {}
    for r in range(R):
        for c in range(C):
            groups.setdefault(find((r, c)), []).append((r, c))
    cells = []
    for group in groups.values():
        rows = [g[0] for g in group]
        cols = [g[1] for g in group]
        r0, c0 = min(rows), min(cols)
        rs = max(rows) - r0 + 1
        cs = max(cols) - c0 + 1
        cells.append({"row": r0, "col": c0, "rowspan": rs, "colspan": cs,
                      "text": "", "bbox": None, "is_header": False})
    return cells


def _allcells(R, C):
    return {(r, c) for r in range(R) for c in range(C)}


def assign_lines(cells, ocr_lines, grid_x, grid_y):
    """行 box 中心归格；被覆盖格路由回锚点。"""
    R = len(grid_y) - 1
    C = len(grid_x) - 1
    if not cells:
        return cells
    for cell in cells:
        lo_c, hi_c = cell["col"], cell["col"] + cell["colspan"]
        lo_r, hi_r = cell["row"], cell["row"] + cell["rowspan"]
        xc0, xc1 = grid_x[lo_c], grid_x[min(hi_c, C)]
        yc0, yc1 = grid_y[lo_r], grid_y[min(hi_r, R)]
        texts = []
        for ln in ocr_lines:
            cx, cy = line_center(ln)
            if (xc0 <= cx <= xc1) and (yc0 <= cy <= yc1):
                texts.append(ln["text"])
        cell["text"] = " ".join(texts).strip()
    return cells


def conservation_ok(grid):
    R = grid["grid"]["n_rows"]
    C = grid["grid"]["n_cols"]
    seen, area = set(), 0
    for cell in grid["cells"]:
        r, c, rs, cs = cell["row"], cell["col"], cell["rowspan"], cell["colspan"]
        if r < 0 or c < 0 or r + rs > R or c + cs > C:
            return False
        for i in range(r, r + rs):
            for j in range(c, c + cs):
                if (i, j) in seen:
                    return False
                seen.add((i, j))
        area += rs * cs
    return area == R * C


def lines_to_grid(ocr_lines, row_clusters, col_bands, header_rows=0):
    """无框表 → 全 1×1 网格（行/列聚类带；行级输入）。返回 M6 规范表形状。"""
    row_centers = [sum(c) / len(c) for c in row_clusters]
    col_centers = [sum(c) / len(c) for c in col_bands]
    grid = {"n_rows": len(row_centers), "n_cols": len(col_centers), "header_rows": header_rows}
    cells = []
    for ln in ocr_lines:
        cx, cy = line_center(ln)
        r = min(range(len(row_centers)), key=lambda i: abs(row_centers[i] - cy)) if row_centers else 0
        c = min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - cx)) if col_centers else 0
        cells.append({"row": r, "col": c, "rowspan": 1, "colspan": 1, "text": ln["text"],
                      "bbox": None, "is_header": False})
    return {"grid": grid, "cells": cells, "adapter_notes": [], "issues": []}


# ---------------------------------------------------------------- §7.5.1 线框表（FR-C2）

def rebuild_wired(png_path, ocr_lines, cfg):
    """形态学线段检测→网格聚类→缺失线段=合并推断→行 box 中心归格。返回 grid dict 或 None。"""
    img = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    bininv = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    k = cfg["rebuild"]["wired_kernel_px"]
    hz = cv2.morphologyEx(bininv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    vt = cv2.morphologyEx(bininv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))
    tol = cfg["rebuild"]["line_cluster_tol_px"]
    hz_lines, vt_lines = [], []
    for y in range(hz.shape[0]):
        row = np.where(hz[y] > 0)[0]
        if row.size > 0:
            hz_lines.append((y, row.min(), row.max()))
    for x in range(vt.shape[1]):
        col = np.where(vt[:, x] > 0)[0]
        if col.size > 0:
            vt_lines.append((x, col.min(), col.max()))
    grid_x = cluster_lines([l[0] for l in vt_lines], axis=0, tol=tol)
    grid_y = cluster_lines([l[0] for l in hz_lines], axis=1, tol=tol)
    if len(grid_x) < 2 or len(grid_y) < 2:
        return None
    R, C = len(grid_y) - 1, len(grid_x) - 1
    rs_map, cs_map = _openings_grid(hz_lines, vt_lines, grid_x, grid_y, tol)
    cells = build_cells_from_openings(R, C, rs_map, cs_map)
    cells = assign_lines(cells, ocr_lines, grid_x, grid_y)
    table = {"grid": {"n_rows": R, "n_cols": C, "header_rows": 0},
             "cells": cells, "adapter_notes": [], "issues": []}
    return table if conservation_ok(table) else None   # 产出必过守恒（FR-C2 验收）


# ---------------------------------------------------------------- §7.5.2 无框表（FR-C4）

def rebuild_borderless(ocr_lines, cfg):
    """三线表等：x 聚类列带、y 聚类行带（行级输入）。不足判据显式（FR-C4 不硬猜）。"""
    if len(ocr_lines) < 2:
        return None
    xs = [line_center(l)[0] for l in ocr_lines]
    ys = [line_center(l)[1] for l in ocr_lines]
    col_bands = cluster_1d(xs, tol=cfg["rebuild"]["col_tol_word_ratio"] * median_line_w(ocr_lines))
    row_clusters = cluster_1d(ys, tol=cfg["rebuild"]["row_tol_word_ratio"] * median_line_h(ocr_lines))
    row_centers = [sum(c) / len(c) for c in row_clusters]
    # CV 用行聚类中心（去重），避免同一行重复 y 致 pitch=0 拉高 CV
    if len(col_bands) < 2 or row_pitch_cv(row_centers) > cfg["rebuild"]["row_pitch_cv_max"]:
        return None
    grid = lines_to_grid(ocr_lines, row_clusters, col_bands)
    return grid if conservation_ok(grid) else None
