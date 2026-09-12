#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1 triage.py —— 分诊（text/scanned/hybrid/退化探测/FR-A4 页内区域）
==================================================================
作用：读 PDF 前先分诊，输出 work/triage.json 供编排层逐页路由。
输入：pdf_path + cfg；输出：triage dict（{page_count, encrypted, locked,
      degraded, doc_verdict, pages:[{page,verdict,ratio,printable,cjk,
      layout_hint,skew_deg,dpi_ok,intra_regions}]}）。
复跑：python triage.py <pdf>（无参数即从 pdf_path 推断——实际由 orchestrator 调用函数）。
改造源：assets/pdf_text_probe.py（verdict 阈值 0.50/0.30 与可读率函数原样复用）。
设计锚点：详细技术设计（升级）§1；冻结详细技术设计 §6.1；需求书 FR-A1/A2/A4。
"""
import sys
from pathlib import Path

# assets/ 根入 path，复用 pdf_text_probe（阈值/可读率/verdict）
_ASSETS = Path(__file__).resolve().parents[1]
if str(_ASSETS) not in sys.path:
    sys.path.insert(0, str(_ASSETS))

import pdf_text_probe as ptp  # noqa: E402


class TriageError(Exception):
    """encrypted | locked | zero_page | open_failed —— 编排层据此退出码 3（FR-A1）。"""

    def __init__(self, kind, detail=""):
        self.kind = kind
        self.detail = detail
        super().__init__("TriageError(%s): %s" % (kind, detail))


def _page_lines_pt(page):
    """PyMuPDF 页 → pt 系行列表（供 FR-A4/intra_regions）。lines: [{box:[x1,y1,x2,y2], text}]"""
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
            by = max(s["bbox"][3] for s in spans)
            txt = "".join(s.get("text", "") for s in spans)
            if txt.strip():
                out.append({"box": [lx, ly, rx, by], "text": txt.strip()})
    return out


def triage(pdf_path, cfg=None):
    """PDF → triage dict。异常：TriageError。
    逐页探测（路由需要每页 verdict）。"""
    cfg = cfg or {}
    import pypdf
    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except Exception as e:  # open_failed
        raise TriageError("open_failed", str(e))
    encrypted, locked = False, False
    try:
        if getattr(reader, "is_encrypted", False):
            encrypted = True
            try:
                reader.decrypt("")
            except Exception:
                pass
    except Exception:
        pass
    try:
        n = len(reader.pages)
    except Exception:
        n = 0
        locked = True
    if locked or (encrypted and n == 0):
        raise TriageError("locked", "encrypted/locked 无密码不可读")
    if n == 0:
        raise TriageError("zero_page", "零页 PDF")

    result = {"file": str(Path(pdf_path).resolve()), "page_count": n,
              "encrypted": encrypted, "locked": locked,
              "degraded": {"zero_page": False, "blank_pages": []},
              "doc_verdict": None, "pages": []}

    import pymupdf as fitz
    doc = fitz.open(str(pdf_path))
    text_pages, nontext_pages = [], []
    for i, page in enumerate(doc, 1):
        t = page.get_text() or ""
        pr = ptp._printable_count(t)
        cjk = ptp._cjk_count(t)
        raw = len(t)
        ratio = round(pr / raw, 3) if raw else 0.0
        st = {"raw_len": raw, "printable": pr, "ratio": ratio}
        v = ptp.verdict(st) if raw else "image"     # raw==0 → image（verdict 同语义）
        rec = {"page": i, "verdict": v, "ratio": ratio, "printable": pr, "cjk": cjk,
               "layout_hint": _layout_hint(page),
               "skew_deg": 0.0,                     # 简化：0.0（FR-A3 deskew 前置留后续，含文本行估算接口）
               "dpi_ok": True, "intra_regions": []}
        if v == "text":
            text_pages.append(i)
            try:
                from textlayer import detect_intra_regions
                rec["intra_regions"] = detect_intra_regions(page, _page_lines_pt(page), cfg)  # 3 参（实物签名）
            except Exception:
                rec["intra_regions"] = []
        else:
            nontext_pages.append(i)
            if raw == 0:
                result["degraded"]["blank_pages"].append(i)
        result["pages"].append(rec)
    result["doc_verdict"] = ("text" if not nontext_pages
                             else ("scanned" if not text_pages else "hybrid"))
    return result


def _layout_hint(page):
    """单/双栏粗略判定（复用 textlayer._detect_columns 口径；6 元组 (y,x,x1,size,font,text)）。"""
    try:
        from textlayer import _detect_columns
        lines = _page_lines_pt(page)
        w = page.rect.width
        tups = [(ln["box"][1], ln["box"][0], ln["box"][2], 0.0, "", ln["text"])
                for ln in lines]                      # (y, x, x1, size, font, text)
        return _detect_columns(w, tups)
    except Exception:
        return "single"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python triage.py <pdf>")
        sys.exit(2)
    try:
        out = triage(sys.argv[1])
    except TriageError as e:
        print(str(e), file=sys.stderr)
        sys.exit(3)
    import json
    print(json.dumps(out, ensure_ascii=False, indent=1))
