#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_layout.py -- layout engine for text-layer PDFs (PyMuPDF char/line coords).

First-principles pairing (JSON制作规范.md content model + engine decision):
  PDF page content is either text objects (readable, has geometry) or images
  (scanned -> OCR engines). This module is the TEXT-OBJECT engine: it extracts
  every line with its box/font/size from the PDF itself (no OCR), producing
  layout-aware reading order that plain text dump cannot guarantee.

Output JSON (UTF-8):
  {"engine":"layout","page_count":N,"page_layout":"single|double|mixed",
   "pages":[{"page":1,
             "lines":[{"y":..,"x":..,"x1":..,"size":..,"font":"..","text":".."}],
             "text":"line1\nline2"}]}
  * per-page lines already in reading order (column-aware when page_layout
    detected double),
  * header/footer lines that repeat across >=50% pages are dropped (flagged in
    "dropped_noise" counts) - page geometry makes this far more reliable than
    text heuristics.

Usage: python pdf_layout.py <pdf> <out.json>
"""
import json
import os
import re
import sys

HEADER_BAND = 0.09   # top 9% / bottom 9% of page height = header/footer band


def norm_noise(text):
    """normalize a potential header/footer line: strip whitespace and
    trailing page markers like '第1页' / '— 12 —' / '-3-'."""
    t = re.sub(r'\s+', '', text)
    t = re.sub(r'(第?\d+页?|[—–\-_]?\d{1,3}[—–\-_]?)$', '', t)
    return t


PG = '#page-no#'


def noise_key(txt, in_band):
    low = norm_noise(txt)
    if in_band and not low:
        return PG   # pure page-number header/footer
    return low


def _collect(page):
    """-> (h, [ (y0,x0,x1,size,font,text) ordered by dict traversal ])"""
    h = page.rect.height
    out = []
    d = page.get_text('dict')
    for block in d.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            if not spans:
                continue
            lx = min(s['bbox'][0] for s in spans)
            ly = min(s['bbox'][1] for s in spans)
            rx = max(s['bbox'][2] for s in spans)
            size = spans[0].get('size', 0)
            fonts = sorted({s.get('font', '') for s in spans})
            txt = ''.join(s.get('text', '') for s in spans)
            if txt.strip():
                out.append((round(ly), round(lx), round(rx), round(size, 1),
                            fonts[0] if len(fonts) == 1 else '|'.join(fonts[:2]), txt))
    return h, out


def _detect_columns(page_w, lines, h):
    """crude single/double detection by x-start histogram."""
    n = len(lines)
    if n == 0:
        return 'single'
    starts = [x for (_, x, _, _, _, _) in lines]
    mids = [x for x in starts if page_w * 0.35 < x < page_w * 0.65]
    left = [x for x in starts if x <= page_w * 0.35]
    right = [x for x in starts if x >= page_w * 0.65]
    # double when many lines begin on right half (two justified columns)
    if right and len(right) >= max(3, n * 0.3) and len(left) >= len(right) * 0.5:
        return 'double'
    return 'single'


def _order_lines(lines, layout, page_w):
    if layout == 'double':
        mid = page_w / 2.0
        left = sorted([l for l in lines if l[1] < mid], key=lambda l: (round(l[0] / 8.0), l[1]))
        right = sorted([l for l in lines if l[1] >= mid], key=lambda l: (round(l[0] / 8.0), l[1]))
        return left + right
    return sorted(lines, key=lambda l: (round(l[0] / 8.0), l[1]))


def main():
    if len(sys.argv) < 3:
        print('usage: pdf_layout.py <pdf> <out.json>')
        sys.exit(2)
    pdf_path, out_json = sys.argv[1], sys.argv[2]
    import pymupdf as fitz
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    pages_raw = [_collect(doc[p]) for p in range(page_count)]
    # repeated header/footer (any band line whose text repeats on >=50% pages)
    n = page_count
    freq = {}
    band_lines = []
    for (h, lines) in pages_raw:
        seen = set()
        for (y, x, x1, size, font, txt) in lines:
            in_band = (y < h * HEADER_BAND) or (y > h * (1 - HEADER_BAND))
            low = noise_key(txt, in_band)
            if not low or len(low) > 40:
                continue
            if in_band and low not in seen:
                seen.add(low)
                freq[low] = freq.get(low, 0) + 1
    drop = {t for t, c in freq.items() if n >= 2 and c >= max(2, int(n * 0.5))}

    layouts = []
    pages_out = []
    for pno in range(page_count):
        h, lines = pages_raw[pno]
        w = doc[pno].rect.width
        lay = _detect_columns(w, lines, h)
        layouts.append(lay)
        kept = [l for l in lines if noise_key(l[5], (l[0] < h * HEADER_BAND) or (l[0] > h * (1 - HEADER_BAND))) not in drop]
        ordered = _order_lines(kept, lay, w)
        page_lines = [{'y': l[0], 'x': l[1], 'x1': l[2], 'size': l[3], 'font': l[4], 'text': l[5].strip()}
                      for l in ordered]
        text = '\n'.join(pl['text'] for pl in page_lines)
        pages_out.append({'page': pno + 1, 'lines': page_lines, 'text': text})
    layout_all = 'mixed' if len(set(layouts)) > 1 else (layouts[0] if layouts else 'single')
    result = {
        'engine': 'layout',
        'page_count': page_count,
        'page_layout': layout_all,
        'dropped_noise_lines': sorted(drop),
        'pages': pages_out,
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print('OK pages=%d layout=%s text_pages=%d noise_dropped=%d -> %s' % (
        page_count, layout_all,
        sum(1 for p in pages_out if p['text'].strip()), len(drop), out_json))


if __name__ == '__main__':
    main()
