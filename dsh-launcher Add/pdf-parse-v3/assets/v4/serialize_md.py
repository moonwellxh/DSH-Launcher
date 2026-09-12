#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M13 serialize_md.py —— 分级 MD 序列化（FR-F1/F2；仅用户触发，Q3）
==================================================
设计依据：详细技术设计 §6.13、需求书 FR-F1（复杂度：rs>1/cs>1/多级表头/格内多行 → 复杂表；
简单→GFM 管道表+转义纪律；复杂→MD 内嵌 HTML <table>）FR-F2（图片原位 ![caption](path)，禁 base64）。
"""
import re


def classify_complex(table):
    g = table.get("grid", {})
    if g.get("header_rows", 0) > 1:
        return True
    for c in table.get("cells", []):
        if c.get("rowspan", 1) > 1 or c.get("colspan", 1) > 1:
            return True
        if "\n" in (c.get("text") or "") or "<br>" in (c.get("text") or ""):
            return True
    return False


def _escape_pipe(s):
    return (s or "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>").strip()


def _simple_pipe(table):
    g = table.get("grid", {})
    R = g.get("n_rows", 0)
    C = g.get("n_cols", 0)
    grid = [["" for _ in range(C)] for _ in range(R)]
    for c in table.get("cells", []):
        for i in range(c["row"], min(c["row"] + c.get("rowspan", 1), R)):
            for j in range(c["col"], min(c["col"] + c.get("colspan", 1), C)):
                grid[i][j] = _escape_pipe(c.get("text", ""))
    if not grid:
        return ""
    lines = ["| " + " | ".join(grid[0]) + " |",
             "| " + " | ".join(["---"] * C) + " |"]
    for row in grid[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _complex_html(table):
    g = table.get("grid", {})
    R = g.get("n_rows", 0)
    C = g.get("n_cols", 0)
    grid = [[{} for _ in range(C)] for _ in range(R)]
    for c in table.get("cells", []):
        for i in range(c["row"], min(c["row"] + c.get("rowspan", 1), R)):
            for j in range(c["col"], min(c["col"] + c.get("colspan", 1), C)):
                grid[i][j] = c
    out = ["<table>"]
    covered = set()          # 跨行合并覆盖区（rowspan 覆盖后续行）
    for i in range(R):
        out.append("  <tr>")
        for j in range(C):
            if (i, j) in covered:
                continue
            c = grid[i][j]
            if not c:
                continue
            rowspan, colspan = c.get("rowspan", 1), c.get("colspan", 1)
            covered.update((i2, j2) for i2 in range(i, i + rowspan) for j2 in range(j, j + colspan))
            tag = "th" if c.get("is_header") else "td"
            txt = (c.get("text") or "").replace("\n", "<br>")
            out.append(f"    <{tag} rowspan={rowspan} colspan={colspan}>{txt}</{tag}>")
        out.append("  </tr>")
    out.append("</table>")
    return "\n".join(out)


def to_md(v4_json):
    """v4 JSON → Markdown（分级）。图片原位 ![caption](path)，章节/条文/表/图按阅读序。"""
    parts = []
    for chapter in v4_json.get("chapters", []):
        parts.append(f"# {chapter.get('text', '')}")
    for page in v4_json.get("pages", []):
        for img in page.get("images", []):
            cap = img.get("caption") or img.get("id") or "image"
            parts.append(f"![{cap}]({img.get('path')})")
        for tb in page.get("tables", []):
            cap = tb.get("caption")
            if cap:
                parts.append(f"**{cap}**")
            if classify_complex(tb):
                parts.append(_complex_html(tb))
            else:
                parts.append(_simple_pipe(tb))
            parts.append("")
    return "\n\n".join(p for p in parts if p is not None)
