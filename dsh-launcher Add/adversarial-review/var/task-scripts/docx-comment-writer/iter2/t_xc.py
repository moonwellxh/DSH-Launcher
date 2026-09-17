# -*- coding: utf-8 -*-
"""L0 probe: valid cross-container ranges (hyperlink <-> plain paragraph).

role : closes the last gap left by the invalid D/P fixtures
in   : mkc.py
out  : work/XC_*.docx
rerun: python t_xc.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
from docx_commenter import add_comments  # noqa: E402
from verify_comments import verify  # noqa: E402
import lib  # noqa: E402

RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdX" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.com/" TargetMode="External"/>'
        '<Relationship Id="rIdY" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.org/" TargetMode="External"/>'
        '</Relationships>')

CASES = [
    ('link_to_plain',
     '<w:p><w:hyperlink r:id="rIdX"><w:r><w:t>LINKHEAD</w:t></w:r></w:hyperlink>'
     '<w:r><w:t>PLAINTAIL</w:t></w:r></w:p>', 'LINKHEADPLAINTAIL'),
    ('plain_to_link',
     '<w:p><w:r><w:t>PLAINHEAD</w:t></w:r>'
     '<w:hyperlink r:id="rIdX"><w:r><w:t>LINKTAIL</w:t></w:r></w:hyperlink></w:p>',
     'PLAINHEADLINKTAIL'),
    ('link_to_link',
     '<w:p><w:hyperlink r:id="rIdX"><w:r><w:t>LINKONE</w:t></w:r></w:hyperlink>'
     '<w:r><w:t>MID</w:t></w:r>'
     '<w:hyperlink r:id="rIdY"><w:r><w:t>LINKTWO</w:t></w:r></w:hyperlink></w:p>',
     'LINKONEMIDLINKTWO'),
    ('ins_to_plain',
     '<w:p><w:ins w:id="11" w:author="a" w:date="2020-01-01T00:00:00Z">'
     '<w:r><w:t>INSHEAD</w:t></w:r></w:ins><w:r><w:t>PLAINTAIL</w:t></w:r></w:p>',
     'INSHEADPLAINTAIL'),
    ('fld_to_sdt',
     '<w:p><w:fldSimple w:instr=" REF x "><w:r><w:t>FLD</w:t></w:r></w:fldSimple>'
     '<w:r><w:t>MID</w:t></w:r>'
     '<w:sdt><w:sdtPr><w:id w:val="1"/></w:sdtPr>'
     '<w:sdtContent><w:r><w:t>SDT</w:t></w:r></w:sdtContent></w:sdt></w:p>',
     'FLDMIDSDT'),
]

for tag, body, anchor in CASES:
    src = os.path.join(WORK, 'XC_%s.src.docx' % tag)
    dst = os.path.join(WORK, 'XC_%s.out.docx' % tag)
    mkc.build(src, body, rels=RELS)
    lg, n = add_comments(src, dst, [{'anchor': anchor, 'text': 'c1'}],
                         author='REV', initials='RV')
    d = lib.load_doc(dst)
    mk = [(e.tag.split('}')[-1], e.get(lib.q('id')), e.getparent().tag.split('}')[-1])
          for e in d.iter() if e.tag in (lib.q('commentRangeStart'), lib.q('commentRangeEnd'))]
    print('%-14s log=%s verify=%s markers=%s' % (tag, lg, verify(dst)[0], mk))
