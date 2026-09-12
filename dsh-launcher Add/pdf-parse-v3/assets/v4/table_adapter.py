#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M6 table_adapter.py —— GLM HTML→网格确定性转换（FR-C1/C5/C6）+ 过声明归一化 + 跨页续表合并
==========================================================================================
设计依据：详细技术设计 §7.1（§7.1.1 展开 / §7.1.2 过声明判定 / §7.1.3 归一化 / §7.1.4 续表合并）、
§6.6（M6 职责与输出契约演进：issues/header_rows/adapter_notes）、§2.4（FR-E9 缺陷登记）、
需求书 FR-C1/C5/C6、FR-E2（守恒）。

命名澄清（设计书 J-5）：本模块 `expand_table` 返回的 `issues` 为**结构便签**（kind/at：
placeholder_dropped/overlap/holes）；落盘时转记到 `adapter_notes`（结构诊断，不混入 FR-E9 issues[]）。
`html_to_grid` 输出的 `issues` 为 **FR-E9 缺陷登记**（defect_class/detected_by/resolution/status），
仅当归一化成功修复 D2 过声明时写入一条 resolved 记录。

契约（设计书 §6.6 演进口径）：
    html_to_grid(html_str, cfg) -> [{
        "grid": {"n_rows":int, "n_cols":int, "header_rows":int},
        "cells": [{"row","col","rowspan","colspan","text","bbox":None,"is_header":bool}],
        "issues": [...FR-E9...],
        "adapter_notes": [...结构便签/归一化便签...],
        "caption": str|None, "context_before": str|None   # 供续表合并
    }]
"""
import re
import copy
from bs4 import BeautifulSoup


# ---------------------------------------------------------------- 守恒

def conservation_ok(table) -> bool:
    """Σ(rowspan×colspan)==n_rows×n_cols 且无越界/重叠（FR-E2）。"""
    R = table["grid"]["n_rows"]
    C = table["grid"]["n_cols"]
    seen = set()
    area = 0
    for cell in table["cells"]:
        r, c = cell["row"], cell["col"]
        rs, cs = cell["rowspan"], cell["colspan"]
        if r < 0 or c < 0 or r + rs > R or c + cs > C:
            return False
        for i in range(r, r + rs):
            for j in range(c, c + cs):
                if (i, j) in seen:
                    return False
                seen.add((i, j))
        area += rs * cs
    return area == R * C


# ---------------------------------------------------------------- §7.1.1 展开（含占位空 td 丢弃）

def expand_table(table_tag):
    """HTML <table> → 展开网格。返回 dict(grid_text, cells, issues, n_rows, n_cols, header_rows)。
    占位规则（架构思考 §1-D4）：空格目标区全被上方合并覆盖 → 丢弃；空格落自由区 → 正常放置；
    非空格落入已覆盖区 → 记 overlap（真实错误）。"""
    trs = table_tag.find_all("tr")
    thead = table_tag.find("thead")
    header_rows = len(thead.find_all("tr")) if thead else 0
    grid, cells, issues = [], [], []
    for r, tr in enumerate(trs):
        while len(grid) <= r:
            grid.append([])
        c = 0
        for td in tr.find_all(["td", "th"]):
            while c < len(grid[r]) and grid[r][c] is not None:
                c += 1
            rs = max(1, int(td.get("rowspan", 1) or 1))
            cs = max(1, int(td.get("colspan", 1) or 1))
            text = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
            if not text:
                occupied = sum(
                    1 for i in range(r, r + rs) if i < len(grid)
                    for j in range(c, min(c + cs, len(grid[i])))
                    if grid[i][j] is not None)
                if occupied == rs * cs:
                    issues.append({"kind": "placeholder_dropped", "at": [r, c]})
                    continue                      # 纯占位格，丢弃
            cells.append({"row": r, "col": c, "rowspan": rs, "colspan": cs,
                          "text": text, "bbox": None,
                          "is_header": bool(td.name == "th" or (header_rows and r < header_rows))})
            for i in range(r, r + rs):
                while len(grid) <= i:
                    grid.append([])
                while len(grid[i]) < c + cs:
                    grid[i].append(None)
                for j in range(c, c + cs):
                    if grid[i][j] is not None:
                        issues.append({"kind": "overlap", "at": [i, j]})
                    grid[i][j] = text
            c += cs
    n_rows = len(grid)
    n_cols = max((len(row) for row in grid), default=0)
    holes = sum(1 for row in grid for v in row if v is None) \
          + sum(n_cols - len(row) for row in grid)
    if holes:
        issues.append({"kind": "holes", "count": holes})
    return {"grid_text": grid, "cells": cells, "issues": issues,
            "n_rows": n_rows, "n_cols": n_cols, "header_rows": header_rows}


# ---------------------------------------------------------------- §7.1.2 D2 过声明判定

def overdeclare_info(table_tag):
    """过声明信息：dict(header_rows, col_D, row_over)。
    列向 D2：col_D = 表头格最大声明 rowspan − 表头 tr 数；
    行向 D2：row_over = 声明 rowspan 超出「锚行之后剩余 tr 数」的格清单。"""
    trs = table_tag.find_all("tr")
    max_tr = len(trs)
    thead = table_tag.find("thead")
    header_rows = len(thead.find_all("tr")) if thead else 0
    col_D = 0
    if header_rows:
        declared = [max(1, int(th.get("rowspan", 1) or 1))
                    for th in thead.find_all(["th", "td"])]
        col_D = max(declared, default=1) - header_rows
    row_over = []
    for r, tr in enumerate(trs):
        for td in tr.find_all(["td", "th"]):
            rs = max(1, int(td.get("rowspan", 1) or 1))
            avail = max_tr - r
            if rs > avail:
                row_over.append({"tr": r, "declared": rs, "available": avail})
    return {"header_rows": header_rows, "col_D": col_D, "row_over": row_over}


# ---------------------------------------------------------------- §7.1.3 过声明归一化（幻影行/列坍缩）

def normalize_overdeclare(table_tag, cfg):
    """在深拷贝的 tag 上归一化 rowspan（保留原始 rs 证据，不就地变异）。
    返回 (expanded, notes)。notes 含 overdeclare_unresolved 前缀 = 归一化后仍不守恒。"""
    tag = copy.deepcopy(table_tag)
    trs = tag.find_all("tr")
    max_tr = len(trs)
    thead = tag.find("thead")
    header_rows = len(thead.find_all("tr")) if thead else 0
    notes = []
    # 1) 列向：表头格 rs 收缩到 header_rows
    if header_rows:
        for th in thead.find_all(["th", "td"]):
            rs = max(1, int(th.get("rowspan", 1) or 1))
            if rs > header_rows:
                th["rowspan"] = str(header_rows)
                notes.append(f"rowspan_overdeclare_col: {rs}→{header_rows}")
    # 2) 行向：任何格 rs 收缩到 max_tr − tr_index
    for r, tr in enumerate(trs):
        for td in tr.find_all(["td", "th"]):
            rs = max(1, int(td.get("rowspan", 1) or 1))
            avail = max_tr - r
            if rs > avail:
                td["rowspan"] = str(avail)
                notes.append(f"rowspan_overdeclare_row: tr{r} {rs}→{avail}")
    neo = expand_table(tag)
    if any(i["kind"] in ("holes", "overlap") for i in neo["issues"]):
        notes.append("overdeclare_unresolved: normalize 后仍不守恒")
    return neo, notes


# ---------------------------------------------------------------- M6 输出组装

def _grid_from_neo(neo):
    return {"n_rows": neo["n_rows"], "n_cols": neo["n_cols"], "header_rows": neo["header_rows"]}


def _structure_notes(neo_issues):
    """展开过程的结构便签（kind/at）→ adapter_notes 字符串（设计书 J-5：不混入 FR-E9 issues[]）。"""
    out = []
    for it in neo_issues or []:
        if it["kind"] == "placeholder_dropped":
            out.append(f"placeholder_dropped@{it['at']}")
        elif it["kind"] == "overlap":
            out.append(f"overlap@{it['at']}")
        elif it["kind"] == "holes":
            out.append(f"holes@{it.get('count', 0)}")
    return out


def html_to_grid(html_str, cfg):
    """GLM 的 md_results 中所有 <table> → 网格表（FR-C1/C6）。含占位丢弃 + 过声明归一化
    + 表头推断（处理遗留 R-15：无 <thead> 的规范性表格/旋转表，判据 1 序号行＋判据 2 属性词行）。
    返回表输出列表。异常表（解析失败）→ 抛 AdapterError(parse_failed)。"""
    if not html_str or "<table" not in html_str:
        return []
    soup = BeautifulSoup(html_str, "html.parser")
    tables = soup.find_all("table")
    out = []
    for tag in tables:
        cap_tag = tag.find_previous("p") or tag.find_previous(string=True)
        caption = _caption_of(tag)
        ovd = overdeclare_info(tag)
        if ovd["col_D"] > 0 or ovd["row_over"]:
            neo, notes = normalize_overdeclare(tag, cfg)
            issues = []
            resolved_d2 = bool(ovd["col_D"] > 0 or ovd["row_over"])
            if not any(n.startswith("overdeclare_unresolved") for n in notes):
                # 归一化成功且守恒 → 登记修复（设计书 §7.1.3）
                issues.append({"defect_class": "D2", "detected_by": ["signature"],
                               "resolution": "phantom-collapse", "status": "resolved",
                               "detail": ";".join(n for n in notes if n.startswith("rowspan_overdeclare"))})
            tb = {"grid": _grid_from_neo(neo), "cells": neo["cells"],
                  "issues": issues, "adapter_notes": notes + _structure_notes(neo["issues"]),
                  "caption": caption, "context_before": cap_tag}
        else:
            exp = expand_table(tag)
            tb = {"grid": {"n_rows": exp["n_rows"], "n_cols": exp["n_cols"],
                           "header_rows": exp["header_rows"]},
                  "cells": exp["cells"],
                  "issues": [], "adapter_notes": _structure_notes(exp["issues"]),
                  "caption": caption, "context_before": cap_tag}
        _trim_empty_cols(tb)                 # R-16 纯空列修剪（幽灵列消洞，先于表头推断）
        _infer_header_rows(tag, tb)          # R-15 表头推断（无 thead 表）
        out.append(tb)
    return out


# ---------------------------------------------------------------- R-15 表头推断（无 thead 表）

# 属性词表（语义表头识别，相对严；含 项次/层数——与 probe_header_precision 实测词表一致，防 0040/0043 漏标）
_HEADER_ATTR_WORDS = ("熔点", "沸点", "密度", "比重", "闪点", "自燃点", "爆炸", "备注", "名称", "单位",
                      "规格", "尺寸", "面积", "数量", "序号", "编号", "等级", "类别", "上限", "下限",
                      "厚度", "宽度", "高度", "间距", "温度", "压力", "材质", "型号", "部位", "项次", "层数")


# ---------------------------------------------------------------- R-16 纯空列修剪（幽灵列消洞）

def _col_has_text(tb, c):
    """列 c 是否有任何 cell 文本非空（含 colspan 扩展到该列）。"""
    for cl in tb.get("cells", []):
        lo, hi = cl["col"], cl["col"] + cl.get("colspan", 1)
        if lo <= c < hi and (cl.get("text") or "").strip():
            return True
    return False


def _recount_and_overwrite_holes(tb):
    """R-16 G-2：基于修剪后 cells 重建覆盖计数未覆盖格（holes），并覆写 adapter_notes 的 holes@N 便签（0 则删）。"""
    g = tb["grid"]
    R, C = g["n_rows"], g["n_cols"]
    covered = [[False] * C for _ in range(R)]
    for cl in tb.get("cells", []):
        r0, c0 = cl["row"], cl["col"]
        rs, cs = cl.get("rowspan", 1), cl.get("colspan", 1)
        for r in range(r0, min(r0 + rs, R)):
            for c in range(c0, min(c0 + cs, C)):
                if 0 <= r < R and 0 <= c < C:
                    covered[r][c] = True
    holes = sum(1 for r in range(R) for c in range(C) if not covered[r][c])
    notes = [n for n in (tb.get("adapter_notes") or []) if not n.startswith("holes@")]
    if holes:
        notes.append("holes@%d" % holes)
    tb["adapter_notes"] = notes


def _trim_empty_cols(tb):
    """R-16：整列全空（无任何 cell 文本）的幽灵列修剪；全空表保护；colspan>1 且横跨保留/空列边界 → 整表跳过。
    修剪：区间⊆空列集的 cell 删除；其余按 old→new 映射左移；n_cols 更新；重算并覆写 holes 便签。"""
    g = tb["grid"]
    C = g["n_cols"]
    if C <= 1:
        return False
    empty = [c for c in range(C) if not _col_has_text(tb, c)]
    if not empty:
        return False
    nonempty = [c for c in range(C) if c not in empty]
    if not nonempty:                       # 全空表保护（不退化到 0 列）
        return False
    for cl in tb.get("cells", []):
        if cl.get("colspan", 1) > 1:
            lo, hi = cl["col"], cl["col"] + cl["colspan"]
            cross_keep = any(lo <= c < hi for c in nonempty)
            cross_empty = any(lo <= c < hi for c in empty)
            if cross_keep and cross_empty:   # 横跨保留+空列边界 → 保守跳过整表
                return False
    mapping = {}
    j = 0
    for c in range(C):
        if c in empty:
            continue
        mapping[c] = j
        j += 1
    new_cells = []
    for cl in tb.get("cells", []):
        lo, hi = cl["col"], cl["col"] + cl.get("colspan", 1)
        if all(c in empty for c in range(lo, hi)):   # 区间 ⊆ 空列集 → 删除（文本必空）
            continue
        cl["col"] = mapping[cl["col"]]
        new_cells.append(cl)
    tb["cells"] = new_cells
    g["n_cols"] = len(nonempty)
    _recount_and_overwrite_holes(tb)
    return True


def _row_attr_hits(tr_cells):
    """该行命中属性词的**单元格个数**（允许同一词多格重复，按格计数——R-15 复审轻微4）。"""
    n = 0
    for c in tr_cells:
        if any(w in c["text"] for w in _HEADER_ATTR_WORDS):
            n += 1
    return n


def _row_is_seq(tr_cells):
    """序号行：该行非空文本全为纯正整数且数 ≥3（判据 1 前置）。"""
    ts = [c["text"].strip() for c in tr_cells if c["text"].strip()]
    return len(ts) >= 3 and all(re.fullmatch(r"\d+", t) for t in ts)


def _infer_header_rows(tag, tb):
    """无 <thead> 表（现 header_rows==0）的表头推断：
    判据 2（属性词行，按格 ≥ max(3,⌈C×0.4⌉)）或 判据 1（序号行 且 下一行命中判据 2）→ 连续表头行计 header_rows，
    并对表头区格 is_header=True。已有 thead/header_rows>0 的表跳过（不叠加）。"""
    if tb["grid"].get("header_rows", 0) > 0 or tag.find("thead") is not None:
        return
    rows = []
    for tr in tag.find_all("tr"):
        rows.append([{"text": td.get_text(" ", strip=True)} for td in tr.find_all(["td", "th"])])
    header_rows = 0
    for i, r in enumerate(rows):
        if not r:
            continue
        thr = max(3, -(-len(r) * 4 // 10))            # ⌈0.4×该行单元格数⌉（R-15 设计：C=该行 len——修正页0027 类大分列表漏标）
        hit_attr = _row_attr_hits(r) >= thr
        hit_seq = _row_is_seq(r) and (i + 1 < len(rows)) and _row_attr_hits(rows[i + 1]) >= max(3, -(-len(rows[i + 1]) * 4 // 10))
        if hit_seq or hit_attr:
            header_rows += 1
        else:
            break
    if header_rows > 0:
        tb["grid"]["header_rows"] = header_rows
        for c in tb["cells"]:
            if c.get("row") < header_rows:
                c["is_header"] = True


def _caption_of(table_tag):
    """近邻表题：table 前文本节点或上一非空文本（尽力而为）。"""
    prev = table_tag.find_previous(string=True)
    prev_sib = table_tag.find_previous_sibling()
    for cand in (prev, prev_sib.get_text() if prev_sib else None):
        if cand and isinstance(cand, str):
            t = re.sub(r"\s+", " ", cand).strip()
            if t and ("表" in t or "table" in t.lower() or len(t) >= 4):
                return t
    return None


# ---------------------------------------------------------------- §7.1.4 跨页续表合并（FR-C5）

def _norm_txt(s):
    return re.sub(r"\s+", "", s or "")


def col_sim(prev_hdr, nxt_hdr):
    """表头行文本逐列归一化 LCS 相似度（0..1）。"""
    if not prev_hdr or not nxt_hdr:
        return 0.0
    k = min(len(prev_hdr), len(nxt_hdr))
    if k == 0:
        return 0.0
    same = sum(1 for a, b in zip(prev_hdr[:k], nxt_hdr[:k]) if _norm_txt(a) == _norm_txt(b))
    return round(same / k, 4)


def _seq_of(row_texts):
    """从一行文本提取首个数字序号（int）或 None。"""
    for t in row_texts:
        m = re.search(r"(\d+)", _norm_txt(t))
        if m:
            return int(m.group(1))
    return None


def seq_contiguous(prev, nxt):
    """prev 末行序号 +1 == nxt 首行序号（可解析时）。"""
    prev_rows = sorted({c["row"] for c in prev["cells"]})
    nxt_rows = sorted({c["row"] for c in nxt["cells"]})
    if not prev_rows or not nxt_rows:
        return False
    prev_last = [c["text"] for c in prev["cells"] if c["row"] == prev_rows[-1]]
    nxt_first = [c["text"] for c in nxt["cells"] if c["row"] == nxt_rows[0]]
    a, b = _seq_of(prev_last), _seq_of(nxt_first)
    return a is not None and b is not None and (a + 1) == b


def seq_not_parseable(prev, nxt):
    """序号不可解析（视为通过，不硬猜——FR-C4 同纪律）。"""
    prev_rows = sorted({c["row"] for c in prev["cells"]})
    nxt_rows = sorted({c["row"] for c in nxt["cells"]})
    if not prev_rows or not nxt_rows:
        return True
    return _seq_of([c["text"] for c in prev["cells"] if c["row"] == prev_rows[-1]]) is None \
        or _seq_of([c["text"] for c in nxt["cells"] if c["row"] == nxt_rows[0]]) is None


def _unit_row(prev):
    """假单位行 = 表头行（含'单位'字样的行）的逐列文本。"""
    for c in prev["cells"]:
        if c.get("is_header") and "单位" in c["text"]:
            row = c["row"]
            return [cc["text"] for cc in prev["cells"] if cc.get("row") == row]
    return None


def unit_row_match(prev, nxt):
    """S5 单位行复现（设计书 §7.1.4）：双方均有单位行且逐列相同，或双方均无（视为通过）。"""
    pu, nu = _unit_row(prev), _unit_row(nxt)
    if pu is None and nu is None:
        return True
    if pu is None or nu is None:
        return False
    return [ _norm_txt(x) for x in pu ] == [ _norm_txt(x) for x in nu ]


def try_merge_continuation(prev, nxt, page_pair, cfg):
    """prev/nxt 为相邻页各一张候选表（适配层输出）。返回合并后表或 None（S1–S5 任一不满足即放弃）。"""
    ctx = (nxt.get("context_before") or "")[-cfg["continuation"]["context_chars"]:]
    s1 = ("续表" in ctx) or bool(re.match(r"^续\s*表", nxt.get("caption") or ""))
    s2 = prev["grid"]["n_cols"] == nxt["grid"]["n_cols"]
    nxt_hdr = [c["text"] for c in nxt["cells"] if c.get("is_header")]
    prev_hdr = [c["text"] for c in prev["cells"] if c.get("is_header")]
    s3 = (not nxt_hdr) or col_sim(prev_hdr, nxt_hdr) >= cfg["continuation"]["header_sim_min"]
    s4 = seq_contiguous(prev, nxt) or seq_not_parseable(prev, nxt)
    s5 = unit_row_match(prev, nxt)
    if not (s1 and s2 and s3 and s4 and s5):
        return None
    h_n = nxt["grid"].get("header_rows", 0)
    non_hdr = [c["row"] for c in nxt["cells"] if not c.get("is_header")]
    if non_hdr:
        h_n = max(h_n, min(non_hdr))                     # th-only 首行无 thead：header_rows=0 但首行实为表头（MIN-R3-3）
    data = [c for c in nxt["cells"] if c["row"] >= h_n]  # 数据行（去其重复表头）
    base = prev["grid"]["n_rows"]
    merged_cells = prev["cells"] + [{**c, "row": c["row"] - h_n + base} for c in data]
    n_data_rows = len({c["row"] for c in data})
    merged = {"grid": {"n_rows": base + n_data_rows,
                       "n_cols": prev["grid"]["n_cols"],
                       "header_rows": prev["grid"].get("header_rows", 0)},
              "cells": merged_cells}
    prev_cont = prev.get("continuation") or {}
    prev_src = prev_cont.get("source_pages") or [page_pair[0]]
    merged["continuation"] = {"group_id": prev_cont.get("group_id") or f"tbl-{page_pair[0]}",
                              "role": prev_cont.get("role", "head"),
                              "source_pages": sorted(set(list(prev_src) + list(page_pair)))}
    return merged if conservation_ok(merged) else None   # 合并必过守恒（FR-C5 验收）


# ---------------------------------------------------------------- AdapterError

class AdapterError(Exception):
    def __init__(self, kind, detail=""):
        self.kind = kind          # parse_failed | collapse_failed
        self.detail = detail
        super().__init__(f"[{kind}] {detail}")
