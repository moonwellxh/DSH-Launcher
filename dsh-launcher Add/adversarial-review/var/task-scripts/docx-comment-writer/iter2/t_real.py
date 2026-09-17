# -*- coding: utf-8 -*-
"""L0 probe: real Word materials + old-engine reproduction of the reported bugs.

role : end-to-end on the user's real docx (read-only source) and OLD-engine replay
in   : C:\\Users\\雍远\\WorkBuddy\\2026-09-11-00-08-02\\洪泽湖监狱消防查验\\04_记录表（分专业）\\*.docx (read only)
out  : work/real_*.docx, work/OLD_*.docx + manifest for external Word checking
rerun: python t_real.py
"""
import os
import sys
import glob
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
NEW = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
OLD = r'C:\Users\雍远\.agents\skills\_backup\docx-comment-writer_prefix_20260917-032952\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, NEW)

import lib  # noqa: E402
from docx_commenter import add_comments, dump_text  # noqa: E402
from verify_comments import verify  # noqa: E402

REAL = (r'C:\Users\雍远\WorkBuddy\2026-09-11-00-08-02\洪泽湖监狱消防查验'
        r'\04_记录表（分专业）\01 建筑\消防安全隐患问题排查-现场记录表（洪泽湖监狱-1号厂房-建筑）.docx')

manifest = []

print('===== 1. real document inventory =====')
print('   exists=%s size=%d' % (os.path.exists(REAL), os.path.getsize(REAL)))
with zipfile.ZipFile(REAL) as z:
    names = z.namelist()
print('   parts=%s' % names)
doc = lib.load_doc(REAL)
for tag in ('p', 'tbl', 'tr', 'tc', 'drawing', 'pict', 'txbxContent', 'hyperlink',
            'ins', 'fldSimple', 'sdt', 'tab', 'br', 'sectPr'):
    n = len(list(doc.iter(lib.q(tag))))
    if n:
        print('   count %-12s = %d' % (tag, n))

text = dump_text(REAL)
print('   dump_text len=%d' % len(text))
print('   first 200=%r' % text[:200])
with open(os.path.join(WORK, 'real_dump.txt'), 'w', encoding='utf-8') as f:
    f.write(text)

# choose two anchors that must exist verbatim in the dumped text
cands = []
for probe in ('消防安全隐患', '建筑', '序号', '排查'):
    i = text.find(probe)
    if i >= 0:
        cands.append((probe, i))
print('   anchor candidates=%s' % cands)

items = []
for probe, i in cands[:2]:
    items.append({'anchor': probe, 'text': 'REVIEW:%s' % probe})
real_out = os.path.join(WORK, 'real_out.docx')
log, n = add_comments(REAL, real_out, items, author='复审', initials='RV')
print('   log=%s n=%d' % (log, n))
print('   verify=%s' % (verify(real_out),))
r0, r1 = lib.load_doc(REAL), lib.load_doc(real_out)
print('   sig_equal=%s counts_src=%s counts_dst=%s' % (
    lib.sig(r0) == lib.sig(r1), lib.counts(r0), lib.counts(r1)))
manifest.append(('real_out', real_out))

print()
print('===== 2. OLD engine replay: round 2 on an already-commented doc =====')
import importlib
for m in ('docx_commenter',):
    sys.modules.pop(m, None)
sys.path.insert(0, OLD)
old = importlib.import_module('docx_commenter')
sys.path.remove(OLD)

base = os.path.join(WORK, 'OLDBASE.docx')
import mkc  # noqa: E402
mkc.build(base, '<w:p><w:r><w:t>ALPHATARGET text</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>BETATARGET text</w:t></w:r></w:p>')
o1 = os.path.join(WORK, 'OLD_r1.docx')
o2 = os.path.join(WORK, 'OLD_r2.docx')
lg1, n1 = old.add_comments(base, o1, [{'anchor': 'ALPHATARGET', 'text': 'one'}],
                           author='A', initials='A')
lg2, n2 = old.add_comments(o1, o2, [{'anchor': 'BETATARGET', 'text': 'two'}],
                           author='B', initials='B')
print('   old r1 log=%s n=%d' % (lg1, n1))
print('   old r2 log=%s n=%d' % (lg2, n2))
with zipfile.ZipFile(o2) as z:
    from lxml import etree
    cm = etree.fromstring(z.read('word/comments.xml'))
    dc = etree.fromstring(z.read('word/document.xml'))
print('   OLD r2 declared=%s marked=%s' % (
    [c.get(lib.q('id')) for c in cm.iter(lib.q('comment'))],
    sorted({e.get(lib.q('id')) for e in dc.iter(lib.q('commentRangeStart'))})))
manifest.append(('OLD_r1', o1))
manifest.append(('OLD_r2', o2))

print()
print('===== 3. NEW engine, same scenario =====')
for m in ('docx_commenter',):
    sys.modules.pop(m, None)
sys.path.insert(0, NEW)
import docx_commenter as newc
importlib.reload(newc)
n1p = os.path.join(WORK, 'NEW_r1.docx')
n2p = os.path.join(WORK, 'NEW_r2.docx')
l1, c1 = newc.add_comments(base, n1p, [{'anchor': 'ALPHATARGET', 'text': 'one'}],
                           author='A', initials='A')
l2, c2 = newc.add_comments(n1p, n2p, [{'anchor': 'BETATARGET', 'text': 'two'}],
                           author='B', initials='B')
print('   new r1 log=%s n=%d' % (l1, c1))
print('   new r2 log=%s n=%d' % (l2, c2))
with zipfile.ZipFile(n2p) as z:
    from lxml import etree
    cm = etree.fromstring(z.read('word/comments.xml'))
    dc = etree.fromstring(z.read('word/document.xml'))
print('   NEW r2 declared=%s marked=%s' % (
    [c.get(lib.q('id')) for c in cm.iter(lib.q('comment'))],
    sorted({e.get(lib.q('id')) for e in dc.iter(lib.q('commentRangeStart'))})))
manifest.append(('NEW_r2', n2p))

print()
with open(os.path.join(WORK, 'manifest_real.txt'), 'w', encoding='utf-8') as f:
    for name, p in manifest:
        f.write('%s\t%s\n' % (name, p))
print('manifest written: %s' % os.path.join(WORK, 'manifest_real.txt'))
