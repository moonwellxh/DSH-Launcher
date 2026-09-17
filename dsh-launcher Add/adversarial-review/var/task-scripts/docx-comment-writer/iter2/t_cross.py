# -*- coding: utf-8 -*-
"""L0 probe: cross-boundary ranges + failure-atomicity.

role : (1) range geometry across rows / cells / nested tables, (2) try/finally + atomic replace
in   : mkc.py
out  : work/XR_*.docx, work/AT_*.docx + printed geometry
rerun: python t_cross.py
"""
import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
from docx_commenter import add_comments  # noqa: E402
from verify_comments import verify  # noqa: E402
import lib  # noqa: E402

manifest = []


def geometry(path):
    d = lib.load_doc(path)
    out = []

    def walk(el, depth=0):
        for c in el:
            if c.tag == lib.q('commentRangeStart'):
                out.append(('S', c.get(lib.q('id'))))
            elif c.tag == lib.q('commentRangeEnd'):
                out.append(('E', c.get(lib.q('id'))))
            elif c.tag == lib.q('t'):
                out.append(c.text or '')
            elif c.tag == lib.q('tc'):
                out.append('|CELL|')
            elif c.tag == lib.q('tr'):
                out.append('|ROW|')
            walk(c, depth + 1)
    walk(d)
    return out


def run(tag, body, items):
    src = os.path.join(WORK, 'XR_%s.src.docx' % tag)
    dst = os.path.join(WORK, 'XR_%s.out.docx' % tag)
    mkc.build(src, body)
    try:
        lg, n = add_comments(src, dst, items, author='REV', initials='RV')
    except Exception as exc:
        print('%-14s RAISED %s: %s' % (tag, type(exc).__name__, exc))
        return
    print('%-14s log=%s' % (tag, lg))
    print('%-14s verify=%s' % (tag, verify(dst)[0]))
    print('%-14s geom=%s' % (tag, geometry(dst)))
    manifest.append((tag, dst))


TBL2 = ('<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>'
        '<w:tr><w:tc><w:tcPr/><w:p><w:r><w:t>R1CELL</w:t></w:r></w:p></w:tc></w:tr>'
        '<w:tr><w:tc><w:tcPr/><w:p><w:r><w:t>R2CELL</w:t></w:r></w:p></w:tc></w:tr>'
        '</w:tbl>')

# 1. last cell of row 1 -> first cell of row 2
run('row2row', TBL2, [{'anchor': 'R1CELLR2CELL', 'text': 'c1'}])

# 2. table cell -> following body paragraph
run('cell2body', TBL2 + '<w:p><w:r><w:t>AFTERBODY</w:t></w:r></w:p>',
    [{'anchor': 'R2CELLAFTERBODY', 'text': 'c1'}])

# 3. body paragraph -> table cell
run('body2cell', '<w:p><w:r><w:t>BEFOREBODY</w:t></w:r></w:p>' + TBL2,
    [{'anchor': 'BEFOREBODYR1CELL', 'text': 'c1'}])

# 4. nested table cell -> outer cell
NEST = ('<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="4000"/></w:tblGrid>'
        '<w:tr><w:tc><w:tcPr/><w:p><w:r><w:t>OUTER1</w:t></w:r></w:p>'
        '<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>'
        '<w:tr><w:tc><w:tcPr/><w:p><w:r><w:t>INNER</w:t></w:r></w:p></w:tc></w:tr>'
        '</w:tbl>'
        '<w:p><w:r><w:t>OUTER2</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
run('nested', NEST, [{'anchor': 'OUTER1INNEROUTER2', 'text': 'c1'}])

# 5. anchor that only MATCHES across a paragraph boundary (no explicit marker)
run('implicit_para', '<w:p><w:r><w:t>TAILWORD</w:t></w:r></w:p>'
                     '<w:p><w:r><w:t>HEADWORD</w:t></w:r></w:p>',
    [{'anchor': 'TAILWORDHEADWORD', 'text': 'c1'}])

# 6. occurrence beyond range
run('occ_oob', '<w:p><w:r><w:t>SAME SAME</w:t></w:r></w:p>',
    [{'anchor': 'SAME', 'occurrence': 5, 'text': 'c1'}])

print()
print('===== failure atomicity =====')
# malformed [Content_Types].xml -> parse error AFTER document.xml was already rewritten
bad = os.path.join(WORK, 'AT_bad.docx')
mkc.build(bad, '<w:p><w:r><w:t>ATOMIC</w:t></w:r></w:p>')
import zipfile
with zipfile.ZipFile(bad, 'a') as z:
    pass
tmpd = os.path.join(WORK, 'AT_repack')
shutil.rmtree(tmpd, ignore_errors=True)
with zipfile.ZipFile(bad) as z:
    z.extractall(tmpd)
with open(os.path.join(tmpd, '[Content_Types].xml'), 'w', encoding='utf-8') as f:
    f.write('<Types><broken>')
with zipfile.ZipFile(bad, 'w', zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk(tmpd):
        for fn in files:
            fp = os.path.join(base, fn)
            z.write(fp, os.path.relpath(fp, tmpd).replace('\\', '/'))
shutil.rmtree(tmpd, ignore_errors=True)

dst = os.path.join(WORK, 'AT_dst.docx')
mkc.build(dst, '<w:p><w:r><w:t>PREEXISTING</w:t></w:r></w:p>')
dst_before = open(dst, 'rb').read()
try:
    add_comments(bad, dst, [{'anchor': 'ATOMIC', 'text': 'c'}])
    print('   no exception (unexpected)')
except Exception as exc:
    print('   raised %s: %s' % (type(exc).__name__, str(exc)[:120]))
print('   dst bytes unchanged=%s' % (open(dst, 'rb').read() == dst_before))
print('   residue=%s' % [f for f in os.listdir(WORK)
                         if f.endswith('.tmpdir') or f.endswith('.ziping')])

# malformed document.xml -> failure before comments part
bad2 = os.path.join(WORK, 'AT_bad2.docx')
mkc.build(bad2, '<w:p><w:r><w:t>X</w:t></w:r></w:p>')
tmpd = os.path.join(WORK, 'AT_repack2')
shutil.rmtree(tmpd, ignore_errors=True)
with zipfile.ZipFile(bad2) as z:
    z.extractall(tmpd)
with open(os.path.join(tmpd, 'word', 'document.xml'), 'w', encoding='utf-8') as f:
    f.write('<w:document><broken>')
with zipfile.ZipFile(bad2, 'w', zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk(tmpd):
        for fn in files:
            fp = os.path.join(base, fn)
            z.write(fp, os.path.relpath(fp, tmpd).replace('\\', '/'))
shutil.rmtree(tmpd, ignore_errors=True)
try:
    add_comments(bad2, os.path.join(WORK, 'AT_out2.docx'), [{'anchor': 'X', 'text': 'c'}])
    print('   bad2 no exception (unexpected)')
except Exception as exc:
    print('   bad2 raised %s: %s' % (type(exc).__name__, str(exc)[:80]))
print('   residue=%s' % [f for f in os.listdir(WORK)
                         if f.endswith('.tmpdir') or f.endswith('.ziping')])

with open(os.path.join(WORK, 'manifest_cross.txt'), 'w', encoding='utf-8') as f:
    for name, p in manifest:
        f.write('%s\t%s\n' % (name, p))
print('manifest written')
