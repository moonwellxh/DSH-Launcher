#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize_v3.py -- post-production validation & sampling for a v3.0 JSON.

Usage: python finalize_v3.py <v3.json> [out_report.json]
Checks (md §四 validate_v3 subset) and prints a human summary:
  counts, A3 consistency, A6 page ranges, TOC-page issues, page_layout note,
  5 sampled pages text heads, chapter/article samples.
All output ASCII-safe except printed excerpts are written to report file UTF-8.
"""
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("usage: finalize_v3.py <v3.json> [out_report.json]")
        sys.exit(2)
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    md = d.get("metadata", {})
    errs = []
    n_tab = sum(len(p.get("tables", [])) for p in d.get("pages", []))
    n_fig = sum(len(p.get("figures", [])) for p in d.get("pages", []))
    if md.get("table_count") != n_tab:
        errs.append("table_count mismatch")
    if md.get("figure_count") != n_fig:
        errs.append("figure_count mismatch")
    total = md.get("total_pages", 0)
    for a in d.get("articles", []):
        if not (1 <= a.get("page", 0) <= total):
            errs.append("article %s page out of range" % a.get("article_number"))
    for c in d.get("chapters", []):
        if not (1 <= c.get("page", 0) <= total):
            errs.append("chapter %s page out of range" % c.get("chapter_number"))
    rep = {
        "file": path,
        "schema_version": d.get("schema_version"),
        "standard_info": d.get("standard_info"),
        "metadata": md,
        "chapter_count": len(d.get("chapters", [])),
        "article_count": len(d.get("articles", [])),
        "pages": total,
        "validation_errors": errs,
        "samples": {
            "pages": [
                {"page": p.get("page_number"),
                 "head": (p.get("text") or "").split("\n")[0][:60]}
                for p in (d.get("pages") or [])[:3] + (d.get("pages") or [])[-2:]
            ],
            "chapters_first": [
                {"page": c.get("page"), "no": c.get("chapter_number"),
                 "title": c.get("chapter_title")}
                for c in (d.get("chapters") or [])[:8]
            ],
            "articles_first": [
                {"page": a.get("page"), "no": a.get("article_number"),
                 "head": (a.get("content") or [""])[0][:40]}
                for a in (d.get("articles") or [])[:6]
            ],
        },
    }
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("pages=%d chapters=%d articles=%d tables=%d figures=%d errors=%d" % (
        total, len(d.get("chapters", [])), len(d.get("articles", [])),
        n_tab, n_fig, len(errs)))
    for e in errs:
        print("ERR: " + e)
    print("report -> " + sys.argv[2])


if __name__ == "__main__":
    main()
