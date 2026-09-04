#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rapid_ocr_pages.py -- OCR a folder of page images with RapidOCR.

Usage:
  python rapid_ocr_pages.py <png_dir> <out.json> [det_limit_side_len]

Reads page_NNNN.png files (4-digit), OCRs each with RapidOCR (zh),
orders lines top->bottom (then left->right), writes:
  {"pages_text":[{"page":N,"method":"rapid","chars":C,"text":"..."}]}
All console output ASCII; JSON UTF-8.
"""
import glob
import json
import os
import re
import sys
import time


def sort_key(box):
    y0 = min(p[1] for p in box)
    x0 = min(p[0] for p in box)
    return (round(y0 / 12.0), x0)


def main():
    if len(sys.argv) < 3:
        print("usage: rapid_ocr_pages.py <png_dir> <out.json> [det_limit_side_len]")
        sys.exit(2)
    # line-buffer stdout so per-page progress appears live even without -u
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    png_dir, out_json = sys.argv[1], sys.argv[2]
    det_lim = int(sys.argv[3]) if len(sys.argv) > 3 else 960
    log_file = out_json + '.log'

    # resume support: existing out_json is loaded; pages already present are
    # skipped; a checkpoint is written every 10 pages (crash-safe).
    done = {}
    if os.path.isfile(out_json):
        try:
            with open(out_json, 'r', encoding='utf-8') as fh:
                prev = json.load(fh)
            for p in prev.get('pages', []):
                done[p['page']] = p
            print('resume: %d pages already done in %s' % (len(done), out_json))
        except Exception as exc:
            print('resume warn: cannot read existing out (%s); starting fresh' % exc)

    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR(det_limit_side_len=det_lim)

    files = glob.glob(os.path.join(png_dir, 'page_*.png'))
    files.sort(key=lambda p: int(re.search(r'page_(\d+)\.png$', p).group(1)))
    pages = list(done.values())
    t_all = time.time()
    processed = 0

    def log_line(i, pages_done, last_elapsed):
        eta = (last_elapsed / pages_done) * (len(files) - pages_done) if pages_done else 0
        line = 'page %d/%d done %ds eta~%ds (checkpoint %d pages)' % (
            i, len(files), int(last_elapsed), int(eta), len(pages))
        print(line)
        try:
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(line + '\n')
        except Exception:
            pass

    for i, f in enumerate(files, 1):
        pno = int(re.search(r'page_(\d+)\.png$', f).group(1))
        if pno in done:
            continue
        processed += 1
        try:
            res, _ = eng(f)
        except Exception as exc:
            print('FAIL page %d %s' % (pno, exc))
            res = None
        if res is None:
            txt = ''
        else:
            lines = sorted(res, key=lambda r: sort_key(r[0]))
            txt = '\n'.join(r[1] for r in lines)
        pages.append({'page': pno, 'method': 'rapid', 'chars': len(txt), 'text': txt})
        # checkpoint EVERY page so any interruption loses at most the current
        # page; progress line is printed every page (visible, proves not stuck)
        pages.sort(key=lambda p: p['page'])
        with open(out_json, 'w', encoding='utf-8') as fh:
            json.dump({'engine': 'rapidocr_onnxruntime', 'det_limit_side_len': det_lim,
                       'pages': pages}, fh, ensure_ascii=False)
        log_line(i, len(pages), time.time() - t_all)
    pages.sort(key=lambda p: p['page'])
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump({'engine': 'rapidocr_onnxruntime', 'det_limit_side_len': det_lim,
                   'pages': pages}, fh, ensure_ascii=False)
    print('DONE pages=%d total=%.0fs -> %s' % (len(pages), time.time() - t_all, out_json))


if __name__ == '__main__':
    main()
