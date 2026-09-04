#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resume/checkpoint test for rapid_ocr_pages.py.

Creates 2 tiny digit PNGs via PyMuPDF, OCRs them once (out.json written),
then re-runs: second run must skip already-done pages (prints 'resume: ...').
Usage: python tests/test_rapid_resume.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), 'assets')

FAILS = []


def check(name, cond, detail=''):
    if not cond:
        FAILS.append(name + ' ' + str(detail))
        print('FAIL %s %s' % (name, detail))
    else:
        print('PASS %s' % name)


def make_png(path, text):
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((40, 120), text, fontsize=72)
    pix = page.get_pixmap(dpi=72)
    pix.save(path)
    doc.close()


def run(args):
    return subprocess.run([sys.executable, '-u'] + args, capture_output=True, text=True, timeout=600)


def run_until_line(args, needle):
    """start process, stream stdout, kill it right after needle appears.
    returns (killed, stdout_so_far)"""
    p = subprocess.Popen([sys.executable, '-u'] + args, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    out = []
    try:
        for line in p.stdout:
            out.append(line)
            if needle in line:
                p.kill()
                break
        p.wait(timeout=60)
    except Exception:
        p.kill()
    return p.returncode is None or True, ''.join(out)


def main():
    with tempfile.TemporaryDirectory() as d:
        pngdir = os.path.join(d, 'png')
        os.makedirs(pngdir)
        make_png(os.path.join(pngdir, 'page_0001.png'), '24680')
        make_png(os.path.join(pngdir, 'page_0002.png'), '13579')
        out = os.path.join(d, 'out.json')
        cli = [os.path.join(ASSETS, 'rapid_ocr_pages.py'), pngdir, out]

        # crash simulation: kill after page 1 progress line -> 1 page persisted
        _, so1 = run_until_line(cli, 'page 1/2 ')
        with open(out, 'r', encoding='utf-8') as f:
            d1 = json.load(f)
        check('crash keeps partial (1 page on disk)', len(d1.get('pages', [])) == 1,
              str(len(d1.get('pages', []))))

        r2 = run(cli)
        check('second run resumes from 1', 'resume: 1 pages already done' in r2.stdout, r2.stdout[:200])
        check('second run per-page progress', 'page 2/2 ' in r2.stdout)
        check('second run done 2 pages', 'DONE pages=2' in r2.stdout, r2.stdout[-200:])
        with open(out, 'r', encoding='utf-8') as f:
            d2 = json.load(f)
        check('final two pages', len(d2.get('pages', [])) == 2)
        logp = out + '.log'
        if os.path.isfile(logp):
            lines = [l for l in open(logp, encoding='utf-8') if 'page ' in l]
            check('log has per-page lines', len(lines) >= 1)
    if FAILS:
        print('RESULT fail=%d' % len(FAILS))
        sys.exit(1)
    print('RESULT pass all')
    sys.exit(0)


if __name__ == '__main__':
    main()
