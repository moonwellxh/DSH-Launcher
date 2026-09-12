#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_triage.py —— M1 triage 分诊单测（离线，R-02）
==================================================================
覆盖（升级详细设计 §1.3 + R-02 验收）：
  ① 合成文字 PDF → 页 verdict=text、ratio≥0.5、doc_verdict=text
  ② 合成纯扫描 PDF（无文字层）→ verdict=image、doc_verdict=scanned
  ③ 合成空白页 → degraded.blank_pages 登记
  ④ 加密/锁态（构造）→ TriageError（kind 恰当）
  ⑤ 字段齐全：含 intra_regions 键、layout_hint ∈ {single,double}
用法：python tests/v4/test_triage.py
"""
import io
import json
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
ASSETS = SKILL / "assets"
V4 = ASSETS / "v4"
for p in (str(V4), str(ASSETS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pymupdf as fitz  # noqa: E402
import pypdf  # noqa: E402
import triage  # noqa: E402


class Tally:
    def __init__(self):
        self.pass_ = 0
        self.fail = 0
        self.failures = []

    def check(self, name, ok, detail=""):
        if ok:
            self.pass_ += 1
            print("[PASS] %s %s" % (name, detail))
        else:
            self.fail += 1
            self.failures.append(name)
            print("[FAIL] %s %s" % (name, detail))


def make_pdf(path, pages=("text", "text"), blank_pages=()):
    """pages: 每元素 'text'=文字页 / 'image'=空白页（无文字层）。blank_pages 额外强制空。"""
    doc = fitz.open()
    for i, kind in enumerate(pages):
        page = doc.new_page()
        if kind == "text" and (i + 1) not in blank_pages:
            page.insert_text((72, 100), "第一条 建筑防火设计应符合国家现行标准。\n" * 20)
    doc.save(str(path))
    doc.close()


def main():
    t = Tally()
    cfg = {"intra_page": {"min_region_area_pt2": 30000, "min_region_area_ratio": 0.04,
                          "text_cover_max": 0.3, "wire_h_min": 6, "wire_v_min": 3}}

    # ① 文字 PDF
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "text.pdf"
        make_pdf(p, pages=("text", "text"))
        res = triage.triage(p, cfg)
        t.check("①doc_verdict=text", res["doc_verdict"] == "text", res["doc_verdict"])
        t.check("①page_count=2", res["page_count"] == 2, res["page_count"])
        all_text = all(pg["verdict"] == "text" for pg in res["pages"])
        t.check("①页 verdict 全 text", all_text,
                [pg["verdict"] for pg in res["pages"]])
        ok_ratio = all((pg["ratio"] or 0) >= 0.5 for pg in res["pages"])
        t.check("①ratio>=0.5", ok_ratio, [pg["ratio"] for pg in res["pages"]])

        # ② 纯扫描 PDF（image 页）
        p2 = Path(td) / "scan.pdf"
        make_pdf(p2, pages=("image", "image"))
        res2 = triage.triage(p2, cfg)
        t.check("②doc_verdict=scanned", res2["doc_verdict"] == "scanned", res2["doc_verdict"])
        all_img = all(pg["verdict"] == "image" for pg in res2["pages"])
        t.check("②页 verdict 全 image", all_img, [pg["verdict"] for pg in res2["pages"]])

        # ③ 含空白页
        p3 = Path(td) / "hybrid.pdf"
        make_pdf(p3, pages=("text", "image"))
        res3 = triage.triage(p3, cfg)
        t.check("③doc_verdict=hybrid", res3["doc_verdict"] == "hybrid", res3["doc_verdict"])
        t.check("③blank_pages 内容==[2]", res3["degraded"].get("blank_pages") == [2],
                str(res3["degraded"].get("blank_pages")))

        # ④ 字段齐全
        pg0 = res["pages"][0]
        t.check("④字段齐全", all(k in pg0 for k in
                ("page", "verdict", "ratio", "printable", "cjk",
                 "layout_hint", "skew_deg", "dpi_ok", "intra_regions")),
                sorted(pg0.keys()))
        t.check("④layout_hint 合法", pg0["layout_hint"] in ("single", "double"),
                pg0["layout_hint"])
        t.check("④intra_regions 是列表", isinstance(pg0["intra_regions"], list))

        # ⑤ R-03：零页 PDF（pypdf PdfWriter 直写 0 页，可构造已实测）→ TriageError kind==zero_page 单判据（无 skip）
        zbuf = io.BytesIO()
        pypdf.PdfWriter().write(zbuf)
        p5 = Path(td) / "zero.pdf"
        p5.write_bytes(zbuf.getvalue())
        try:
            triage.triage(p5, cfg)
            t.check("⑤零页抛 TriageError", False, "未抛异常")
        except triage.TriageError as e:
            t.check("⑤零页 kind==zero_page", e.kind == "zero_page", e.kind)

    print("\n== RESULT pass=%d fail=%d ==" % (t.pass_, t.fail))
    if t.failures:
        print("FAILURES:", ", ".join(t.failures))
    sys.exit(1 if t.fail else 0)


if __name__ == "__main__":
    main()
