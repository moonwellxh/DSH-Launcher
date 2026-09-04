#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit test for pdf_layout.py using a synthesized CJK text-layer PDF.

Run: python tests/test_layout.py   (exit 0 = pass)
Creates 2 pages via PyMuPDF (SimSun font):
  header repeated on both pages (must be dropped), body lines with 章/条,
  a repeated footer. Verifies layout fields, reading order and noise removal.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ASSETS = os.path.join(SKILL, 'assets')

FAILS = []


def check(name, cond, detail=''):
    if not cond:
        FAILS.append(name + ' ' + str(detail))
        print('FAIL %s %s' % (name, detail))
    else:
        print('PASS %s' % name)


def find_cjk_font():
    cands = [r'C:\Windows\Fonts\simsun.ttc', r'C:\Windows\Fonts\msyh.ttc',
             r'C:\Windows\Fonts\simhei.ttf']
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def make_pdf(path):
    import pymupdf as fitz
    fontfile = find_cjk_font()
    doc = fitz.open()
    for pno in range(2):
        page = doc.new_page(width=595, height=842)
        if fontfile:
            page.insert_font(fontname='cjk', fontfile=fontfile)
            fn = 'cjk'
        else:
            fn = 'helv'
        page.insert_text((72, 60), '测试规范 第%d页' % (pno + 1), fontname=fn, fontsize=14)  # header
        page.insert_text((72, 200), '第一章 总则', fontname=fn, fontsize=16)
        page.insert_text((72, 240), '第1.0.1条 为了预防火灾，制定本规范。', fontname=fn, fontsize=12)
        page.insert_text((100, 280), '1 厂房、仓库', fontname=fn, fontsize=12)
        page.insert_text((100, 310), '2 民用建筑', fontname=fn, fontsize=12)
        page.insert_text((72, 360), '第二章 术语', fontname=fn, fontsize=16)
        page.insert_text((72, 400), '2.1.1 高层建筑：建筑高度大于27m的住宅建筑。', fontname=fn, fontsize=12)
        page.insert_text((72, 800), '— %d —' % (pno + 1), fontname=fn, fontsize=10)  # footer
    doc.save(path)


def main():
    with tempfile.TemporaryDirectory() as d:
        pdf = os.path.join(d, 'sample.pdf')
        out = os.path.join(d, 'layout.json')
        make_pdf(pdf)
        r = subprocess.run([sys.executable, os.path.join(ASSETS, 'pdf_layout.py'), pdf, out],
                           capture_output=True, text=True)
        check('layout runs', r.returncode == 0, r.stdout + r.stderr)
        with open(out, 'r', encoding='utf-8') as f:
            data = json.load(f)
        check('engine=layout', data.get('engine') == 'layout')
        check('pages=2', data.get('page_count') == 2)
        p1 = data['pages'][0]
        line = p1['lines'][0]
        check('line has geometry', all(k in line for k in ('y', 'x', 'x1', 'size', 'font', 'text')))
        t1 = p1['text']
        check('header dropped', '测试规范' not in t1, t1[:80])
        t2 = data['pages'][1]['text']
        check('footer dropped', '—' not in t1 and '—' not in t2)
        order_ok = (t1.find('第一章') < t1.find('第1.0.1条') < t1.find('1 厂房') < t1.find('2 民用建筑'))
        check('reading order page1', order_ok, t1)
        check('page1 text content', '第一章 总则' in t1 and '第1.0.1条' in t1)
        check('page2 text content', '第二章 术语' in t2 and '2.1.1' in t2)
    if FAILS:
        print('RESULT fail=%d' % len(FAILS))
        sys.exit(1)
    print('RESULT pass all')
    sys.exit(0)


if __name__ == '__main__':
    main()
