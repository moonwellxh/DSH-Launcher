#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF text-layer probe using pypdf.

Outputs a JSON document (ASCII-safe, ensure_ascii=True) to stdout with:
  - metadata: page_count, encrypted, producer/creator hints
  - pages[]: per-page stats {page, raw_len, printable, cjk, ratio}

Usage:
  python pdf_text_probe.py <pdf_path> [--all] [--samples N] [--outdir DIR]

If --all: stats for EVERY page (used before extraction routing).
Default: stats only for sampled pages (first 5, middle, last; <=8 unique).
If --outdir DIR is given with --all, per-page extracted text is written as
page_NNN.txt (UTF-8) into DIR for the text layer path.

Classification helpers (kept in Python so PS stays dumb):
  verdict(page): 'text' | 'image' | 'pseudo'  based on thresholds below.
"""
import json
import os
import re
import sys
import unicodedata

try:
    from pypdf import PdfReader
except Exception as exc:  # pragma: no cover
    print(json.dumps({"error": "pypdf_missing: %s" % exc}))
    sys.exit(2)

TEXT_MIN_PRINTABLE = 5      # tiny floor: short pages (covers/titles) stay text when ratio is high
TEXT_MIN_RATIO = 0.50       # printable / raw ratio required (CJK or latin)
PSEUDO_MIN_RATIO = 0.30     # printable / raw ratio below this => garbage text layer


def _printable_count(s):
    n = 0
    for ch in s:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            n += 1
            continue
        if o < 128:
            if 32 <= o <= 126 or o in (9, 10, 13):
                n += 1
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N") or cat in ("Po", "Pd", "Ps", "Pe", "Pc", "Sm"):
            n += 1
    return n


def _cjk_count(s):
    n = 0
    for ch in s:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF:
            n += 1
    return n


def verdict(st):
    raw = st["raw_len"]
    if raw == 0:
        return "image"
    ratio = st["ratio"]
    if ratio < PSEUDO_MIN_RATIO:
        return "pseudo"  # text layer exists but is garbage -> treat as image
    if st["printable"] >= TEXT_MIN_PRINTABLE and ratio >= TEXT_MIN_RATIO:
        return "text"
    return "image"


def main():
    args = [a for a in sys.argv[1:]]
    pdf_path = None
    all_pages = False
    outdir = None
    samples = 5
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--all":
            all_pages = True
        elif a == "--samples" and i + 1 < len(args):
            samples = int(args[i + 1]); i += 1
        elif a == "--outdir" and i + 1 < len(args):
            outdir = args[i + 1]; i += 1
        elif not a.startswith("-"):
            pdf_path = a
        i += 1

    if not pdf_path or not os.path.isfile(pdf_path):
        print(json.dumps({"error": "no_pdf_file"}))
        sys.exit(2)

    result = {"file": pdf_path, "pages": []}
    try:
        reader = PdfReader(pdf_path)
    except Exception as exc:
        print(json.dumps({"error": "open_failed: %s" % exc}))
        sys.exit(2)

    encrypted = False
    locked = False
    try:
        if getattr(reader, "is_encrypted", False):
            encrypted = True
            try:
                reader.decrypt("")
            except Exception:
                pass
    except Exception:
        pass
    result["encrypted"] = encrypted

    # pypdf raises FileNotDecryptedError when touching pages of a locked file;
    # report it cleanly instead of crashing.
    try:
        n = len(reader.pages)
    except Exception:
        n = 0
        locked = True
    result["page_count"] = n
    result["locked"] = locked or (encrypted and n == 0)

    try:
        info = reader.metadata
        result["producer"] = (info.get("/Producer") if info else None) or ""
        result["creator"] = (info.get("/Creator") if info else None) or ""
    except Exception:
        result["producer"] = ""
        result["creator"] = ""

    if locked:
        # cannot read pages without password; report and stop quietly
        print(json.dumps(result, ensure_ascii=True))
        sys.exit(0)

    if all_pages:
        wanted = list(range(1, n + 1))
    else:
        wanted = []
        for p in range(1, min(samples, n) + 1):
            wanted.append(p)
        if n > samples + 1:
            wanted.append((n + 1) // 2)
        if n > samples and n not in wanted:
            wanted.append(n)
        wanted = sorted(set(wanted))

    texts = {}
    for pno in wanted:
        try:
            t = reader.pages[pno - 1].extract_text() or ""
        except Exception:
            t = ""
        texts[pno] = t
        pr = _printable_count(t)
        st = {
            "page": pno,
            "raw_len": len(t),
            "printable": pr,
            "cjk": _cjk_count(t),
            "ratio": round(pr / len(t), 3) if t else 0.0,
        }
        st["verdict"] = verdict(st)
        result["pages"].append(st)

    if outdir and all_pages:
        os.makedirs(outdir, exist_ok=True)
        for pno, t in texts.items():
            with open(os.path.join(outdir, "page_%04d.txt" % pno), "w", encoding="utf-8") as f:
                f.write(t)

    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
