#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M9 structurer.py —— 章节条文结构化 + v4.0 JSON 组装（§5 / 设计书 §6.9）
========================================================
把管线中间产物（triage/glm/ocr/textlayer/gate/ladder/figures）组装为收口 v4.0 JSON：
  chapters/articles（章条结构化，启发式沿用 pdf2v3.py）、pages[]（text/lines/blocks/tables/images/缺陷登记）、
  metadata（routing/transform_registry_ref/defect_ledger_ref/token_ledger_ref/table_status_counts/reader_notice/
  locatable_default）。
设计书 §6.9：章条拆分启发式（目录页剔除、章号前缀过滤、拆条失败留原文）原样复用；输入换干净文本，
准确率只升不降。结构化失败不强行拆条，原文在 pages[].text（A1）；FR-B3 旧 JSON lines[] 缺失 → locatable=false 走整页回退。
"""
import re
import json
from datetime import datetime

SCHEMA_VERSION = "4.0"


# ---------------------------------------------------------------- 章条结构化（启发式，简化自 pdf2v3.py）

_CAPTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*[、.．]?\s*(.*)$")
_ARTICLE_RE = re.compile(r"^([\d一二三四五六七八九十百]+(?:\.\d+)*)\s*[条条款款]")
_TOC_LINE_RE = re.compile(r"^\s*([\d一二三四五六七八九十]+)\s+[^\s].*\d+\s*$")


def split_chapters(lines):
    """把页文本行 → chapters/articles。目录行/页眉页脚剔除；拆条失败留原文（A1）。"""
    chapters, articles = [], []
    cur_chap = None
    for line in lines:
        s = (line or "").strip()
        if not s:
            continue
        if _is_toc_or_header_footer(s):
            continue
        m_c = _CAPTION_RE.match(s)
        m_a = _ARTICLE_RE.match(s)
        if m_c and not m_a:
            cur_chap = {"number": m_c.group(1), "title": m_c.group(2).strip(), "text": s}
            chapters.append(cur_chap)
        elif m_a:
            # 章号前缀过滤：仅当条文号所属章与当前章号匹配（防表格数字行误判）
            prefix = m_a.group(1).split(".")[0]
            if cur_chap and not _chap_matches(cur_chap["number"], prefix):
                continue
            art = {"number": m_a.group(1), "text": s}
            articles.append(art)
            if cur_chap is not None:
                cur_chap.setdefault("articles", []).append(art)
    return chapters, articles


def _is_toc_or_header_footer(s):
    # 目录行：一行 ≥3 个整数跨度 → 判目录；页眉页脚特征行
    if re.fullmatch(r"[\d\s\.·、，,]+", s) and len(s) > 4:
        return True
    return bool(_TOC_LINE_RE.match(s))


def _chap_matches(chap_no, art_prefix):
    if "." in chap_no:
        return chap_no.split(".")[0] == art_prefix
    return chap_no == art_prefix


# ---------------------------------------------------------------- v4 组装

def _reader_notice():
    return ("凡 status ∉ {ok,fixed} 的表（格），下游不得将其数值当事实；引用必须声明不可信。")


def _table_status_counts(pages):
    counts = {"ok": 0, "fixed": 0, "uncertain": 0, "unreadable": 0}
    for page in pages:
        for tb in page.get("tables", []):
            st = tb.get("status")
            counts[st] = counts.get(st, 0) + 1 if st in counts else 0
    return counts


def assemble_v4(*, pages_parts, standard_info, transform_registry_ref=None,
                defect_ledger_ref=None, token_ledger_ref=None, note=None):
    """pages_parts: list of {page_number,text,lines,blocks,tables,images,routing,...}（各通道产物）。
    返回 v4.0 JSON（design 书 §5）。"""
    pages = []
    for part in pages_parts:
        page = {
            "page_number": part.get("page_number", part.get("page")),
            "text": part.get("text", ""),                      # 原文保留，任何环节不覆盖（A1/A2, FR-G2）
            "lines": part.get("lines", []),
            "blocks": part.get("blocks", []),
            "tables": part.get("tables", []),
            "images": part.get("images", []),
        }
        pages.append(page)
    # 章条结构化（输入=各页文本行拼接）
    all_lines = []
    for p in pages:
        all_lines += [ln.get("text", "") for ln in p.get("lines", [])]
    chapters, articles = split_chapters(all_lines)
    # 全页原文 fallback 备查
    text_all = "\n".join(p["text"] for p in pages if p["text"])
    routing = [r for part in pages_parts for r in part.get("routing", [])]  # FR-A2/A4 留痕聚合
    metadata = {
        "total_pages": len(pages),
        "chapter_count": len(chapters),
        "article_count": len(articles),
        "table_count": sum(len(p.get("tables", [])) for p in pages),
        "figure_count": sum(len(p.get("images", [])) for p in pages),
        "page_layout": None,
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "routing": routing,
        "transform_registry_ref": transform_registry_ref,
        "defect_ledger_ref": defect_ledger_ref,
        "token_ledger_ref": token_ledger_ref,
        "table_status_counts": _table_status_counts(pages),
        "reader_notice": _reader_notice(),
        "locatable_default": any(p.get("lines") for p in pages),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "standard_info": standard_info or {},
        "metadata": metadata,
        "chapters": chapters,
        "articles": articles,
        "pages": pages,
    }


def page_out_of(pages_json, page_number):
    """按 page_number 取 page（溯源）。"""
    for p in pages_json.get("pages", []):
        if p.get("page_number") == page_number:
            return p
    return None


def to_data_grid(table):
    """data[][] 退化导出视图（§5.5；旧读取方兼容，新文件不生成）。"""
    R = table["grid"]["n_rows"]
    C = table["grid"]["n_cols"]
    grid = [["" for _ in range(C)] for _ in range(R)]
    for cell in table.get("cells", []):
        for i in range(cell["row"], min(cell["row"] + cell["rowspan"], R)):
            for j in range(cell["col"], min(cell["col"] + cell["colspan"], C)):
                grid[i][j] = cell.get("text", "")
    return grid
