# -*- coding: utf-8 -*-
"""L0 probe: valid hyperlink / textbox / ins / sdt fixtures, src vs engine output.

role : build Word-valid fixtures then hand each file to word_check.py in a fresh process
in   : mkc.py
out  : pairs (src, out) written to work/, plus a manifest for external Word checking
rerun: python t_hl.py
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
from docx_commenter import add_comments  # noqa: E402
import lib  # noqa: E402

os.makedirs(WORK, exist_ok=True)

RELS_HL = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
           '<Relationship Id="rIdX" '
           'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
           'Target="https://example.com/" TargetMode="External"/>'
           '</Relationships>')

TXBOX = (
    '<w:p><w:r><w:t>OUTSIDE</w:t></w:r><w:r><w:drawing>'
    '<wp:inline distT="0" distB="0" distL="0" distR="0">'
    '<wp:extent cx="1828800" cy="914400"/>'
    '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
    '<wp:docPr id="1" name="TextBox 1"/>'
    '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
    '<wps:wsp><wps:cNvSpPr txBox="1"/><wps:spPr>'
    '<a:xfrm><a:off x="0" y="0"/><a:ext cx="1828800" cy="914400"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr>'
    '<wps:txbx><w:txbxContent>'
    '<w:p><w:r><w:t>INSIDEBOX</w:t></w:r></w:p>'
    '</w:txbxContent></wps:txbx>'
    '<wps:bodyPr/></wps:wsp>'
    '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')

CASES = [
    ('HL_ext', '<w:p><w:r><w:t>PRE </w:t></w:r>'
               '<w:hyperlink r:id="rIdX"><w:r><w:t>LINKTARGET</w:t></w:r></w:hyperlink>'
               '<w:r><w:t> POST</w:t></w:r></w:p>', RELS_HL, 'LINKTARGET'),
    ('HL_anchor', '<w:p><w:bookmarkStart w:id="1" w:name="bm"/>'
                  '<w:r><w:t>PRE </w:t></w:r>'
                  '<w:hyperlink w:anchor="bm"><w:r><w:t>LINKTARGET</w:t></w:r></w:hyperlink>'
                  '<w:r><w:t> POST</w:t></w:r></w:p>', None, 'LINKTARGET'),
    ('TXBOX', TXBOX, None, 'OUTSIDE'),
    ('INS', '<w:p><w:r><w:t>PRE </w:t></w:r>'
            '<w:ins w:id="11" w:author="a" w:date="2020-01-01T00:00:00Z">'
            '<w:r><w:t>INSTARGET</w:t></w:r></w:ins>'
            '<w:r><w:t> POST</w:t></w:r></w:p>', None, 'INSTARGET'),
    ('SDT', '<w:p><w:r><w:t>PRE </w:t></w:r>'
            '<w:sdt><w:sdtPr><w:id w:val="1"/></w:sdtPr>'
            '<w:sdtContent><w:r><w:t>SDTTARGET</w:t></w:r></w:sdtContent></w:sdt>'
            '<w:r><w:t> POST</w:t></w:r></w:p>', None, 'SDTTARGET'),
]

manifest = []
for name, body, rels, anchor in CASES:
    src = os.path.join(WORK, 'HL_%s.src.docx' % name)
    out = os.path.join(WORK, 'HL_%s.out.docx' % name)
    mkc.build(src, body, rels=rels)
    try:
        lg, n = add_comments(src, out, [{'anchor': anchor, 'text': 'c1'}],
                             author='REV', initials='RV')
    except Exception as exc:
        lg, n = [('RAISED', type(exc).__name__, str(exc))], -1
    manifest.append((name, src, out, lg, n))
    print('%-10s log=%s n=%s' % (name, lg, n))
    d = lib.load_doc(out if os.path.exists(out) else src)
    mk = []
    for tag in ('commentRangeStart', 'commentRangeEnd'):
        for e in d.iter(lib.q(tag)):
            mk.append((tag.replace('commentRange', ''), e.get(lib.q('id')),
                       e.getparent().tag.split('}')[-1]))
    print('           markers=%s' % (mk,))
    print('           text=%r' % (lib.sig(d),))

with open(os.path.join(WORK, 'manifest_hl.txt'), 'w', encoding='utf-8') as f:
    for name, src, out, lg, n in manifest:
        f.write('%s\t%s\n%s\t%s\n' % (name, src, name + '_OUT', out))
print('manifest written')
