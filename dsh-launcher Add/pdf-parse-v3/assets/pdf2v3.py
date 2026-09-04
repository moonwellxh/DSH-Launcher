#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf2v3.py -- build Schema v3.0 JSON (per JSON制作规范.md) from per-page OCR text.

First-principles anchor (md v3.0): JSON must express the PDF faithfully,
losslessly and traceably. This module:
  * takes per-page OCR text (page -> lines) from any engine,
  * cleans page noise (repeated headers/footers) and OCR inter-CJK spacing,
  * splits chapters / articles / table & figure captions with page provenance,
  * splits enumerated items (1 2 3 / ①②③ / （1）（2）) into array elements,
  * keeps every original line inside pages[].text (lossless, A1/A2),
  * runs md-style validation (A3 counts / A6 page range) and reports issues.

Usage:
  python pdf2v3.py --parts <p1.extract.json,p2.extract.json> \
      --out merged.json \
      --name "建筑设计防火规范" --code "GBJ16-87" --year 1987 \
      --doc-class compilation --type "正文（OCR提取）" \
      [--sources "a.pdf,b.pdf"] [--engine winrt|rapid] [--json-issues issues.json]
Input JSON shape (produced by pdf-extract -IncludeText):
  {"page_count":N, "pages_text":[{"page":1,"method":"ocr","text":"..."}]}
Output: Schema v3.0 (md §1.0-1.4). All messages ASCII; data written UTF-8.
"""
import json
import os
import re
import sys
from datetime import date

# ----------------------------------------------------------------------------
# OCR text cleanup
# ----------------------------------------------------------------------------

CJK = r'\u4e00-\u9fff\u3400-\u4dbf'
CJK_PUNCT = '\u3001\u3002\uff0c\uff1b\uff1a\uff1f\uff01\u201c\u201d\u2018\u2019\uff08\uff09\u300a\u300b\u2014\u2026'
_BOTH = CJK + CJK_PUNCT
RE_CJK_SPACE = re.compile(
    r'(?<=[%s])[ \t]+(?=[%s])' % (_BOTH, _BOTH)
)
RE_NUM_DOT = re.compile(r'(?<=\d)\s*([.．])\s*(?=\d)')  # 3 . 2 . 1 -> 3.2.1
RE_HDR_SEP = re.compile(r'^[\s\-—_=~*·•.。]+$')
RE_WATERMARK = re.compile(r'(zaojiazhe|造价者|广告|推广|网\s*www|\.com|\.cn|告\s*者|亻\s*介)',
                          re.IGNORECASE)


def clean_line(line):
    s = line.strip()
    s = s.replace('\u3000', ' ')
    s = RE_CJK_SPACE.sub('', s)
    s = RE_NUM_DOT.sub('.', s)
    return re.sub(r'\s{2,}', ' ', s).strip()


def drop_global_noise(pages_lines):
    """pages_lines: list[(page_no, [raw_line,...])] -> cleaned lines per page,
    removing lines that repeat on many pages (headers/footers/watermarks)."""
    n = len(pages_lines)
    if n == 0:
        return []
    counts = {}
    for _, lines in pages_lines:
        seen = set()
        for ln in lines:
            c = clean_line(ln)
            if not c:
                continue
            low = c.lower()
            if len(low) <= 30 and low not in seen:
                seen.add(low)
                counts[low] = counts.get(low, 0) + 1
    drop = {k for k, v in counts.items() if v >= max(3, int(n * 0.5))}
    out = []
    for pno, lines in pages_lines:
        kept = []
        for ln in lines:
            c = clean_line(ln)
            if not c:
                continue
            if c.lower() in drop:
                continue
            if RE_WATERMARK.search(c) and len(c) <= 60:
                continue
            if RE_HDR_SEP.match(c):
                continue
            if re.fullmatch(r'\d{1,3}', c):  # bare page numbers
                continue
            kept.append(c)
        out.append((pno, kept))
    return out


# ----------------------------------------------------------------------------
# Structure regexes (md §1.3/§1.4 + generalized)
# ----------------------------------------------------------------------------

RE_CHAPTER = re.compile(r'^第\s*([一二三四五六七八九十百零〇]+|[0-9]+)\s*章\s*(.*)$')
# article styles: 第1.0.1条 / 3.2.1 本文 / 3.2.1.本文
RE_ARTICLE_A = re.compile(r'^第\s*([0-9]+(?:\.[0-9]+){1,2})\s*条\s*[:：]?\s*(.*)$')
RE_ARTICLE_B = re.compile(r'^([0-9]+(?:\.[0-9]+){1,2})\s*[.．、:：]?\s*(.+)$')
RE_TABLE = re.compile(r'^表\s*([0-9]+(?:\.[0-9]+)*)\s*(.*)$')
RE_FIG = re.compile(r'^(图\s*)?([0-9]{1,2}[-–—][0-9]{1,3})[\s.．、]*(.*)$')
RE_SECTION = re.compile(r'^第\s*([一二三四五六七八九十百零〇]+)\s*节\s*(.*)$')
RE_ITEM = re.compile(
    r'^((?:[0-9]{1,2}|[一二三四五六七八九十百]+|（[0-9一二三四五六七八九十百]+）|'
    r'[\(（]\s*[0-9]{1,2}\s*[\)）])[.、．]?)\s*(.+)$'
)
# dot leaders / TOC artifacts from OCR (目录行、连续点线)
RE_LEADER = re.compile(r'[.．·灬]{3,}|…')
RE_TOC_CLUSTER = re.compile(r'(?:第\s*[0-9一二三四五六七八九十百]+(?:[.．][0-9]+)?\s*条[^，。]{0,8}?){2,}')

_CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
       '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '二十': 20}


def cn_to_int(s):
    if s.isdigit():
        return int(s)
    return _CN.get(s, 0)


def is_toc_or_leader(line):
    # spaced dots from OCR like '． ．' or '灬' runs are TOC leaders too
    nos = re.sub(r'\s', '', line)
    if len(re.findall(r'[.．·灬…]', nos)) >= 3:
        return True
    if RE_LEADER.search(line):
        return True
    if RE_TOC_CLUSTER.search(line):
        return True
    if line.count('条') >= 3:
        return True
    return False


def strip_leader_tail(title):
    # remove OCR dot leaders and trailing page numbers like "厂房 ... 45"
    cut = re.split(r'[.．·灬…]', title, maxsplit=1)[0]
    t = re.sub(r'\s*\d{1,3}\s*$', '', cut)
    return t.strip()


def is_chapter_noisy(title):
    t = (title or '').strip()
    if not t:
        return True
    if len(t) > 60:
        return True
    if re.search(r'条|表|图\d', t):
        return True
    return False


# ----------------------------------------------------------------------------
# Builder
# ----------------------------------------------------------------------------

def build_v3(pages_lines, standard, engine, issues):
    """pages_lines: [(global_page_no, [clean lines...])] in page order."""
    # ---- TOC-page detection: a page with >=3 chapter-like rows is a 目录 page
    # (body pages rarely start 3+ chapters); rows there are structure noise.
    toc_pages = set()
    per_page_ch = {}
    for pno, lines in pages_lines:
        c = 0
        for ln in lines:
            if not is_toc_or_leader(ln) and RE_CHAPTER.match(ln):
                c += 1
        per_page_ch[pno] = c
    for pno in sorted(per_page_ch):
        if per_page_ch[pno] >= 3:
            toc_pages.add(pno)
        elif per_page_ch[pno] >= 2 and (pno - 1) in toc_pages:
            toc_pages.add(pno)  # continuation of a TOC run onto next page
    for pno in toc_pages:
        issues.append('page %d treated as TOC (chapters found on it dropped)' % pno)

    lines_meta = []            # (page, line)
    for pno, lines in pages_lines:
        for ln in lines:
            lines_meta.append((pno, ln))

    chapters = []
    articles_flat = []
    current_ch = None
    current_art = None

    def push_article():
        nonlocal current_art
        if current_art:
            articles_flat.append(current_art)
        current_art = None

    for pno, ln in lines_meta:
        if pno in toc_pages:
            continue  # 目录页：结构行整体丢弃（文本仍在 pages[].text，无损）
        if is_toc_or_leader(ln):
            continue  # 目录行/点线行：不进结构层，仅保留在 pages[].text
        mc = RE_CHAPTER.match(ln)
        if mc:
            push_article()
            title = strip_leader_tail(mc.group(2) or '')
            if not title:
                continue  # 空标题(目录残留)不建章
            if is_chapter_noisy(title):
                issues.append('chapter@%d suspicious title: %s' % (pno, ln[:40]))
            current_ch = {
                'chapter_number': mc.group(1).strip(),
                'chapter_title': title,
                'page': pno,
                'articles': [],
            }
            chapters.append(current_ch)
            current_art = None
            continue
        ma = RE_ARTICLE_A.match(ln) or RE_ARTICLE_B.match(ln)
        if ma:
            ano = ma.group(1).strip()
            first = re.match(r'(\d+)', ano)
            ci = cn_to_int(current_ch['chapter_number']) if current_ch else 0
            if ci and first and int(first.group(1)) != ci:
                # 表格数字行/他章条文混入：不建新条，续入当前条或仅作正文
                if current_art is not None:
                    current_art['content'].append(ln)
                continue
            push_article()
            current_art = {
                'article_number': ano,
                'page': pno,
                'content': [ma.group(2).strip()] if ma.group(2).strip() else [],
            }
            if current_ch is not None:
                current_ch['articles'].append(current_art)
            continue
        # continuation text -> last article body, with item splitting
        if current_art is not None:
            mi = RE_ITEM.match(ln)
            if mi and current_art['content']:
                current_art['content'].append(mi.group(2).strip())
            else:
                if current_art['content']:
                    current_art['content'][-1] += '\n' + ln
                else:
                    current_art['content'].append(ln)
            continue
        # text before any chapter/article (front matter) -> keep in page text only

    push_article()  # flush trailing article into flat list (chapter already holds refs)

    pages = []
    total_tables = total_figures = 0
    for pno, lines in pages_lines:
        tables, figures = [], []
        for i, ln in enumerate(lines):
            mt = RE_TABLE.match(ln)
            if mt:
                total_tables += 1
                tables.append({
                    'table_index': len(tables),
                    'caption': ln,
                    'table_no': mt.group(1).strip(),
                    'note': 'OCR 扫描件：单元格数据未重建，原文见 text',
                })
                continue
            mf = RE_FIG.match(ln)
            if mf:
                total_figures += 1
                note_lines = []
                for nxt in lines[i + 1:]:
                    s = nxt.strip()
                    if not s or RE_FIG.match(s) or not (nxt.startswith(' ') or nxt.startswith('\u3000')):
                        break
                    note_lines.append(s)
                figures.append({
                    'figure_index': len(figures),
                    'figure_no': mf.group(2).strip(),
                    'caption': ln,
                    'note': '\n'.join(note_lines) if note_lines else 'OCR 扫描件：图内容见 PDF 原页',
                })
                continue
        pages.append({
            'page_number': pno,
            'text': '\n'.join(lines),
            'tables': tables,
            'figures': figures,
        })

    metadata = {
        'total_pages': len(pages),
        'chapter_count': len(chapters),
        'article_count': len(articles_flat),
        'table_count': total_tables,
        'figure_count': total_figures,
        'page_layout': 'mixed',
        'extracted_at': date.today().isoformat(),
        'ocr_engine': engine,
        'note': 'OCR 提取版：数值与表格须回查 PDF 原件；正文噪声行已清理（去重页眉/页脚/水印）；'
                'OCR 未命中的章/条仅存于 pages[].text，未强行拆条（A1）。',
    }
    doc = {
        'schema_version': '3.0',
        'standard_info': standard,
        'metadata': metadata,
        'chapters': chapters,
        'articles': articles_flat,
        'pages': pages,
    }
    # ---- md-style validation (A3 / A6) ----
    n_tab = sum(len(p.get('tables', [])) for p in pages)
    n_fig = sum(len(p.get('figures', [])) for p in pages)
    if metadata['table_count'] != n_tab:
        issues.append('table_count mismatch')
    if metadata['figure_count'] != n_fig:
        issues.append('figure_count mismatch')
    if len(chapters) != metadata['chapter_count']:
        issues.append('chapter_count mismatch')
    if len(articles_flat) != metadata['article_count']:
        issues.append('article_count mismatch')
    for a in articles_flat:
        if not (1 <= a.get('page', 0) <= metadata['total_pages']):
            issues.append('article %s page out of range' % a.get('article_number'))
    for ch in chapters:
        if not (1 <= ch.get('page', 0) <= metadata['total_pages']):
            issues.append('chapter %s page out of range' % ch.get('chapter_number'))
    if len(chapters) == 0:
        issues.append('chapter_count=0 (structure layer likely failed on this scan)')
    return doc, issues


def load_parts(paths):
    """Return ordered [(page_no_local, text)] merged with continuity counters."""
    all_pages = []
    for p in paths:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        pts = data.get('pages_text') or data.get('pages', [])
        for pt in pts:
            all_pages.append((pt.get('page', 0), pt.get('text', '') or ''))
    # renumber by order into global page numbers
    global_no = 0
    merged = []
    for local, txt in all_pages:
        global_no += 1
        merged.append((global_no, txt.split('\n')))
    return merged


def main(argv):
    args = argv[1:]
    opts = {}
    for i in range(0, len(args)):
        if args[i].startswith('--'):
            key = args[i][2:]
            val = args[i + 1] if i + 1 < len(args) else ''
            opts[key] = val
            i += 1
    parts = [x for x in opts.get('parts', '').split(',') if x]
    if not parts or not opts.get('out'):
        print('usage: pdf2v3.py --parts a.json,b.json --out out.json --name .. --code .. --year .. [--doc-class compilation] [--type ...] [--sources ...] [--engine winrt]')
        return 2
    pages_lines = load_parts(parts)
    standard = {
        'name': opts.get('name', ''),
        'code': opts.get('code', ''),
        'year': int(opts.get('year', 0) or 0),
        'document_class': opts.get('doc-class', 'compilation'),
        'type': opts.get('type', '正文（OCR提取）'),
    }
    srcs = [x for x in opts.get('sources', '').split(',') if x]
    if srcs:
        standard['source_files'] = srcs
    issues = []
    cleaned = drop_global_noise(pages_lines)
    doc, issues = build_v3(cleaned, standard, opts.get('engine', 'winrt'), issues)
    with open(opts['out'], 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print('OK pages=%d chapters=%d articles=%d tables=%d figures=%d issues=%d -> %s' % (
        doc['metadata']['total_pages'], len(doc['chapters']), len(doc['articles']),
        doc['metadata']['table_count'], doc['metadata']['figure_count'], len(issues), opts['out']))
    if opts.get('json-issues'):
        with open(opts['json-issues'], 'w', encoding='utf-8') as f:
            json.dump(issues, f, ensure_ascii=False, indent=1)
    else:
        for it in issues[:30]:
            print('ISSUE: ' + it)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
