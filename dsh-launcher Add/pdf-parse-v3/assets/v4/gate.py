#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M7 gate.py —— 校验门四信号（FR-E1/E2/E3/E8），v2.3 分两层
================================================================
设计依据：详细技术设计 §7.2（§7.2.0 总编排 / §7.2.1a 结构 / §7.2.1 守恒 / §7.2.2 签名 /
§7.2.3 交叉对位 / §7.2.4 几何错位 / §7.2.5 信号缺失纪律）；需求书 FR-E1/E2/E3/E8、表 §13 术语。

信号分层（第三轮方向裁决）：
  gate-failure（否决） = 结构校验(FR-E1) + 守恒(FR-E2) + 缺陷签名(D1/D2) + 数值自洽(FR-E3)；
  hints（提示，不否决） = 交叉对位(信号3) + 几何错位(信号4)，仅引导第二意见抽样；D3 终裁在第二意见。
"""
import re
import unicodedata


NUM_TOK = re.compile(r"[0-9０-９]+(?:[.,][0-9]+)*%?")
_SIG_RE_CACHE = {}


def norm_num(s):
    s = unicodedata.normalize("NFKC", s or "")
    return s.replace(",", "").replace("，", "").strip()


def cluster_1d(vals, tol):
    vals = sorted(vals)
    clusters = []
    for v in vals:
        if clusters and v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def _sig_re(cfg):
    pat = cfg["adapter"]["defect_signature_re"]
    if pat not in _SIG_RE_CACHE:
        _SIG_RE_CACHE[pat] = re.compile(pat)
    return _SIG_RE_CACHE[pat]


# ---------------------------------------------------------------- 入口（§7.2.0）

def gate_check(table, ocr_lines, table_bbox, ocr_available, cfg, *, ocr_expected=True):
    """返回 {passed, failures, unavailable_signals, low_signal, hints}。
    failures = gate-failure（结构/守恒/签名/数值）；hints = D3 提示（信号3/4），不否决。
    ocr_expected=False 表示文字层确定性路径（method=textlayer）：信号3/4 为 N/A。"""
    failures, unavailable, hints = [], [], []
    # 入口守卫：退化 bbox 短路（MAJ-10：零宽/零高 bbox 不参与坐标信号）
    degenerate = not table_bbox or table_bbox[2] <= table_bbox[0] or table_bbox[3] <= table_bbox[1]
    failures += sig_structure(table)                          # gate-failure：结构（FR-E1）
    failures += sig_conservation(table)                       # gate-failure：守恒（FR-E2）
    failures += sig_defect_signature(table, cfg)              # gate-failure：签名（D1/D2）
    low_signal = False
    if ocr_expected and ocr_available and not degenerate:
        cc_hints, cc_low = sig_cross_check(table, ocr_lines, table_bbox, cfg)      # 信号3 → hints（KD4）
        geo_hints, geo_low = sig_geometry_misalign(table, ocr_lines, table_bbox, cfg)  # 信号4 → hints（KD9）
        hints += cc_hints + geo_hints
        low_signal = cc_low or geo_low
    elif not ocr_expected:
        pass                                   # 文字层路径：信号3/4 N/A，非低信号（MAJ-R3-2）
    else:
        unavailable += ["cross-check", "geometry-misalign"]
        low_signal = True                      # 扫描路径 OCR 不可用 → 低信号（§7.2.5）
    failures += check_numeric(table)                          # gate-failure：数值自洽（FR-E3）
    return {"passed": not failures, "failures": failures,
            "unavailable_signals": unavailable, "low_signal": low_signal,
            "hints": hints}


# ---------------------------------------------------------------- 信号0：结构校验（FR-E1；§7.2.1a）

def sig_structure(table):
    fails = []
    R, C = table["grid"]["n_rows"], table["grid"]["n_cols"]
    if R <= 0 or C <= 0:
        fails.append({"signal": "structure", "class": None,
                      "detail": f"空表：n_rows={R},n_cols={C}", "cells": []})
    if not any((cell["text"] or "").strip() for cell in table.get("cells", [])):
        fails.append({"signal": "structure", "class": None,
                      "detail": "非空行为 0", "cells": []})
    for cell in table.get("cells", []):
        for k in ("row", "col", "rowspan", "colspan"):
            if not isinstance(cell.get(k), int) or cell[k] < 0:
                fails.append({"signal": "structure", "class": None,
                              "detail": f"cell 字段非法 {k}={cell.get(k)}",
                              "cells": [[cell.get("row", -1), cell.get("col", -1)]]})
    return fails


# ---------------------------------------------------------------- 信号1：守恒（FR-E2；§7.2.1）

def sig_conservation(table):
    cells, R, C = table["cells"], table["grid"]["n_rows"], table["grid"]["n_cols"]
    seen, area, fails = set(), 0, []
    for cell in cells:
        r, c, rs, cs = cell["row"], cell["col"], cell["rowspan"], cell["colspan"]
        if r < 0 or c < 0 or r + rs > R or c + cs > C:
            fails.append({"signal": "conservation", "class": None,
                          "detail": f"越界({r},{c},{rs},{cs})", "cells": [[r, c]]})
            continue                                    # 越界格不再参与覆盖计算（MAJ-10）
        for i in range(r, r + rs):
            for j in range(c, c + cs):
                if (i, j) in seen:
                    fails.append({"signal": "conservation", "class": None,
                                  "detail": f"重叠({i},{j})", "cells": [[i, j]]})
                seen.add((i, j))
        area += rs * cs
    if area != R * C:
        fails.append({"signal": "conservation", "class": None,
                      "detail": f"不守恒 area={area}!={R}x{C}", "cells": []})
    return fails


# ---------------------------------------------------------------- 信号2：缺陷签名（D1 拼接 + D2 幻影；§7.2.2）

def sig_defect_signature(table, cfg):
    """D1 拼接签名 + D2 未解决过声明证据。归一化成功 → 表带 resolved issues、不带失败证据；
    归一化失败 → 表带 overdeclare_unresolved note，此处判 D2 失败（BLK-4）。"""
    sig_re = _sig_re(cfg)
    fails = []
    for cell in table["cells"]:
        if (cell["rowspan"] > 1 or cell["colspan"] > 1) and \
           sig_re.search(re.sub(r"\s", "", cell["text"])):
            fails.append({"signal": "signature", "class": "D1",
                          "detail": f"合并格内拼接 {cell['text'][:20]}",
                          "cells": [[cell["row"], cell["col"]]]})
    for note in table.get("adapter_notes", []):
        if note.startswith("overdeclare_unresolved"):
            fails.append({"signal": "signature", "class": "D2",
                          "detail": note, "cells": []})
    return fails


# ---------------------------------------------------------------- 信号3：交叉对位（KD4；hint；§7.2.3）

def sig_cross_check(table, ocr_lines, bbox, cfg):
    """返回 (hints, low_signal)。hint 的 class：被合并格覆盖的行带 → "D3"；否则 None（数值类）。"""
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return [], True
    R, C = table["grid"]["n_rows"], table["grid"]["n_cols"]
    col_w = (x2 - x1) / max(1, C)
    band_h = (y2 - y1) / max(1, R)
    merged_regions = []
    for cell in table["cells"]:
        if cell["rowspan"] > 1 or cell["colspan"] > 1:
            merged_regions.append((x1 + cell["col"] * col_w, y1 + cell["row"] * band_h,
                                   x1 + (cell["col"] + cell["colspan"]) * col_w,
                                   y1 + (cell["row"] + cell["rowspan"]) * band_h))
    merged_rows = {r for cell in table["cells"] if cell["rowspan"] > 1
                   for r in range(cell["row"], cell["row"] + cell["rowspan"])}

    def in_merged(xc, yc):
        return any(mx0 <= xc <= mx1 and my0 <= yc <= my1 for mx0, my0, mx1, my1 in merged_regions)

    rows_in = []
    for ln in ocr_lines:
        bx = ln["box"]
        yc = (bx[1] + bx[3]) / 2
        if not (y1 <= yc <= y2) or bx[2] <= bx[0]:
            continue
        overlap = max(0, min(bx[2], x2) - max(bx[0], x1))
        if overlap / (bx[2] - bx[0]) < cfg["gate"]["row_assign_overlap"]:
            continue
        if in_merged((bx[0] + bx[2]) / 2, yc):
            continue                                   # 空间豁免合并格（阻断-3）
        rows_in.append(ln)
    hdr = table["grid"].get("header_rows", 0)
    grid_rows = [[] for _ in range(R)]
    for cell in table["cells"]:
        if cell["rowspan"] != 1 or cell["colspan"] != 1:
            continue
        if not (0 <= cell["row"] < R):
            continue
        for tok in NUM_TOK.findall(norm_num(cell["text"])):
            grid_rows[cell["row"]].append(norm_num(tok))
    ocr_rows = [[] for _ in range(R)]
    for ln in rows_in:
        yc = (ln["box"][1] + ln["box"][3]) / 2
        b = min(R - 1, int((yc - y1) / band_h))         # 均分归带（阻断-2）
        for tok in NUM_TOK.findall(norm_num(ln["text"])):
            ocr_rows[b].append(norm_num(tok))
    hints, low = [], False
    for b in range(R):
        if b < hdr:
            continue
        g, o = sorted(grid_rows[b]), sorted(ocr_rows[b])
        if not g:
            continue
        if not o:
            low = True                                   # 网格有 token 而 OCR 空带：映射失稳，弃权（阻断-2）
            continue
        if g != o:
            cls = "D3" if b in merged_rows else None     # 未覆盖合并格 → 数值类（严重-3）
            hints.append({"signal": "cross-check", "class": cls,
                          "detail": f"行带{b} 数值不一致 OCR={o} GRID={g}",
                          "cells": [[b, -1]]})
    return hints, low


# ---------------------------------------------------------------- 信号4：几何错位（KD9；hint；§7.2.4）

def sig_geometry_misalign(table, ocr_lines, bbox, cfg):
    """纯几何（不读文本）。合并格 rs=k → 其余列取数值行 y 聚类，聚类数≠k 即 D3 hint。"""
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return [], True
    R, C = table["grid"]["n_rows"], table["grid"]["n_cols"]
    in_tab = [ln for ln in ocr_lines
              if y1 <= (ln["box"][1] + ln["box"][3]) / 2 <= y2]
    heights = sorted(ln["box"][3] - ln["box"][1] for ln in in_tab) or [1]
    med_h = heights[len(heights) // 2]
    tol_y = cfg["gate"]["geo_cluster_tol_line_h"] * med_h
    col_w = (x2 - x1) / max(1, C)
    band_h = (y2 - y1) / max(1, R)
    hints, low = [], False
    for cell in table["cells"]:
        if cell["rowspan"] <= 1:
            continue
        cx0, cx1 = x1 + cell["col"] * col_w, x1 + (cell["col"] + cell["colspan"]) * col_w
        gy0, gy1 = y1 + cell["row"] * band_h, y1 + (cell["row"] + cell["rowspan"]) * band_h
        ys = []
        for ln in in_tab:
            xc = (ln["box"][0] + ln["box"][2]) / 2
            yc = (ln["box"][1] + ln["box"][3]) / 2
            if cx0 <= xc <= cx1:
                continue                             # 排除合并格自身列（BLK-R2-1）
            if not NUM_TOK.search(norm_num(ln["text"])):
                continue                             # 只取含数值行
            if gy0 <= yc < gy1:
                ys.append(yc)
        if not ys:
            low = True                               # 无可计数数值行 → 低信号（轻微-1）
            continue
        k = len(cluster_1d(ys, tol_y))
        if k != cell["rowspan"]:
            hints.append({"signal": "geometry-misalign", "class": "D3",
                          "detail": f"合并格({cell['row']},{cell['col']}) rs={cell['rowspan']} 但数值列几何聚类行数={k}",
                          "cells": [[cell["row"], cell["col"]]]})
    return hints, low


# ---------------------------------------------------------------- gate-failure：数值自洽（FR-E3）

def check_numeric(table):
    """数值自洽（可解析时）：序号连续 + 合计行=分项和（容差 0.5%+0.01）+ 单位串位检测。
    不可解析不判负（不虚构失败，FR-E3 口径）。"""
    fails = []
    cells = table.get("cells", [])
    if not cells:
        return fails
    # 序号连续（第一列，跨数据行；可解析时）
    first_col_rows = {}
    for c in cells:
        if c.get("is_header"):
            continue
        m = re.match(r"\s*(\d+)\s*", c["text"] or "")
        if m and c["col"] == 0:
            first_col_rows[c["row"]] = int(m.group(1))
    seq = [first_col_rows[r] for r in sorted(first_col_rows) if r < table["grid"]["n_rows"]]
    if any(seq[i] + 1 != seq[i + 1] for i in range(len(seq) - 1)):
        fails.append({"signal": "numeric", "class": None,
                      "detail": f"序号不连续 {seq}",
                      "cells": [[r, 0] for r in sorted(first_col_rows)]})
    # 单位串位（同列单位词不一致）
    col_unit = {}
    for c in cells:
        if c.get("is_header") or c["row"] == 0:
            continue
        for unit in re.findall(r"[㎡m²°℃%‰]+", c["text"] or ""):
            col_unit.setdefault(c["col"], set()).add(unit)
    for col, units in col_unit.items():
        if len(units) > 1:
            fails.append({"signal": "numeric", "class": None,
                          "detail": f"列{col} 单位串位 {sorted(units)}",
                          "cells": [[c["row"], col] for c in cells
                                    if c.get("col") == col and not c.get("is_header")]})
    # 合计行=分项和（容差 0.5%+0.01；可解析时）
    total_row = _find_total_row(cells)
    if total_row is not None:
        total_vals = {c["col"]: _parse_float(c["text"]) for c in cells if c["row"] == total_row}
        for col, total_val in total_vals.items():
            if total_val is None:
                continue
            part_sum = 0.0
            has_part = False
            for c in cells:
                if c.get("is_header") or c["row"] >= total_row:
                    continue
                if "合计" in (c["text"] or "") or "总计" in (c["text"] or ""):
                    continue
                v = _parse_float(c["text"])
                if c["col"] == col and v is not None:
                    part_sum += v
                    has_part = True
            if has_part and abs(part_sum - total_val) > (0.005 * abs(total_val) + 0.01):
                fails.append({"signal": "numeric", "class": None,
                              "detail": f"列{col} 合计={total_val} ≠ 分项和={round(part_sum, 4)}",
                              "cells": [[total_row, col]]})
    return fails


def _find_total_row(cells):
    for c in cells:
        if "合计" in (c["text"] or "") or "总计" in (c["text"] or ""):
            return c["row"]
    return None


def _parse_float(s):
    m = re.match(r"-?\d+(?:\.\d+)?", (s or "").replace(",", "").strip())
    return float(m.group(0)) if m else None
