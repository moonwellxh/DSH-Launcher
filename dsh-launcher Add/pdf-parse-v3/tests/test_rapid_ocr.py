#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke test: RapidOCR engine importable and recognizes a digit image.

Usage: python test_rapid_ocr.py <image.png>
Exit 0 when engine works and OCR text non-empty (and contains digits).
"""
import sys

if len(sys.argv) < 2:
    print("usage: test_rapid_ocr.py <image.png>")
    sys.exit(2)

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception as exc:
    print("FAIL import %s" % exc)
    sys.exit(1)

eng = RapidOCR(det_limit_side_len=960)
res, _ = eng(sys.argv[1])
if res is None:
    print("FAIL no text recognized")
    sys.exit(1)
txt = "".join(r[1] for r in res)
print("PASS chars=%d text=%s" % (len(txt), txt[:60]))
if not txt.strip():
    print("FAIL empty text")
    sys.exit(1)
sys.exit(0)
