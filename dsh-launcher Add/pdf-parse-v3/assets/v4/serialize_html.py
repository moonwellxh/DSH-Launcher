#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M13 serialize_html.py —— 自包含 HTML（FR-F3/F5；仅用户触发，Q3）
==================================================
自包含单页 HTML：表格原生渲染（带边框样式，避免"无边框误判为错"）+ 图片原位 + 溯源角标（页码/status，
默认开启可关，FR-F3）+ data 属性携带页码/status（FR-F5 溯源贯穿）。FR-E6-b 不可信角标：status∉{ok,fixed} 渲染 ⚠不可信。
"""
import html


def _esc(s):
    return html.escape(s or "")


def _escape_pipe(s):
    return _esc(s or "").replace("|", "\\|").replace("\n", "<br>")


def to_html(v4_json, badges=True):
    """v4 JSON → 自包含 HTML。badges=False 关闭溯源/不可信角标（FR-F3 可关）。"""
    parts = ["<html><head><meta charset='utf-8'><style>",
             "table{border-collapse:collapse;margin:8px 0;} "
             "td,th{border:1px solid #999;padding:4px 8px;}",
             ".badge{font-size:11px;color:#555;margin-left:6px;} "
             ".untrust{color:#c00;font-weight:bold;}",
             "</style></head><body>"]
    for chapter in v4_json.get("chapters", []):
        parts.append(f"<h1>{_esc(chapter.get('text', ''))}</h1>")
    for page in v4_json.get("pages", []):
        pno = page.get("page_number")
        for img in page.get("images", []):
            cap = _esc(img.get("caption") or img.get("id") or "image")
            parts.append(f"<figure><img src='{_esc(img.get('path'))}' alt='{cap}'>{badge(pno, badges)}</figure>")
        for tb in page.get("tables", []):
            cap = tb.get("caption")
            if cap:
                parts.append(f"<div>{_esc(cap)}</div>")
            status = tb.get("status", "ok") or "ok"
            b = _table_badge(pno, status, badges)
            parts.append(_html_table(tb) + b)
    parts.append("</body></html>")
    return "\n".join(parts)


def _table_badge(pno, status, badges):
    if not badges:
        return ""
    bad = "" if status in ("ok", "fixed") else f" <span class='untrust'>⚠不可信({status})</span>"
    return f"<span class='badge' data-page='{pno}' data-status='{status}'>p.{pno}</span>{bad}"


def badge(pno, badges):
    return f"<span class='badge' data-page='{pno}'>p.{pno}</span>" if badges else ""


def _html_table(table):
    g = table.get("grid", {})
    R, C = g.get("n_rows", 0), g.get("n_cols", 0)
    grid = [[{} for _ in range(C)] for _ in range(R)]
    for c in table.get("cells", []):
        for i in range(c["row"], min(c["row"] + c.get("rowspan", 1), R)):
            for j in range(c["col"], min(c["col"] + c.get("colspan", 1), C)):
                grid[i][j] = c
    out = ["<table>"]
    covered = set()
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
            txt = _escape_pipe(c.get("text", ""))
            out.append(f"    <{tag} rowspan={rowspan} colspan={colspan}>{txt}</{tag}>")
        out.append("  </tr>")
    out.append("</table>")
    return "\n".join(out)
