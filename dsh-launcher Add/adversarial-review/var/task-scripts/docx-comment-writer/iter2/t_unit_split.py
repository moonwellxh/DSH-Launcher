# -*- coding: utf-8 -*-
"""L0 unit probe: split_run bucketing + DocMap text collection.

role : deterministic input->output dump of split_run / DocMap (no expected values embedded)
in   : synthetic OOXML fragments built here
out  : for each case, the rebuilt XML and a render token stream
rerun: python t_unit_split.py
"""
import sys
import os
from lxml import etree

SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, SKILL)
from docx_commenter import split_run, DocMap, elem_text  # noqa: E402

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = ('xmlns:w="%s" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:v="urn:schemas-microsoft-com:vml"' % W)


def q(t):
    return '{%s}%s' % (W, t)


def parse_p(inner):
    return etree.fromstring(('<w:p %s>%s</w:p>' % (NS, inner)).encode('utf-8'))


def stream(el):
    """single-account render stream of a paragraph: text, \\t, \\n, <IMG>"""
    out = []

    def walk(e):
        for c in e:
            if c.tag in (q('drawing'), q('pict'), q('object'), q('txbxContent')):
                out.append('<IMG>')
                continue
            if c.tag == q('t'):
                out.append(c.text or '')
            elif c.tag == q('tab'):
                out.append('\\t')
            elif c.tag in (q('br'), q('cr')):
                out.append('\\n')
            elif c.tag in (q('commentRangeStart'), q('commentRangeEnd'),
                           q('commentReference'), q('rPr'), q('pPr')):
                continue
            else:
                walk(c)
    walk(el)
    return ''.join(out)


CASES = [
    # (name, run xml, lo, hi)
    ('C1 anchor covers last char, run ends with br',
     '<w:r><w:t>A B</w:t><w:br/></w:r>', 2, 3),
    ('C2 run = t(AB)+br, anchor=B',
     '<w:r><w:t>AB</w:t><w:br/></w:r>', 1, 2),
    ('C3 run = t(AB)+tab, anchor=B',
     '<w:r><w:t>AB</w:t><w:tab/></w:r>', 1, 2),
    ('C4 run = drawing+t(AB), anchor=A',
     '<w:r><w:drawing><wp:inline/></w:drawing><w:t>AB</w:t></w:r>', 0, 1),
    ('C5 run = t(AB)+drawing, anchor=B',
     '<w:r><w:t>AB</w:t><w:drawing><wp:inline/></w:drawing></w:r>', 1, 2),
    ('C6 run = t(AB)+br, anchor=full AB (early return)',
     '<w:r><w:t>AB</w:t><w:br/></w:r>', 0, 2),
    ('C7 run = tab,t(A),tab,t(B),tab  anchor=B',
     '<w:r><w:tab/><w:t>A</w:t><w:tab/><w:t>B</w:t><w:tab/></w:r>', 2, 3),
    ('C8 run = t(A),tab,t(B),tab,t(C)  anchor=B',
     '<w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:tab/><w:t>C</w:t></w:r>', 2, 3),
    ('C9 run = empty-t + t(AB), anchor=B',
     '<w:r><w:t></w:t><w:t>AB</w:t></w:r>', 1, 2),
    ('C10 run = t(A),rtl,t(B) anchor=B',
     '<w:r><w:t>A</w:t><w:rtl/><w:t>B</w:t></w:r>', 1, 2),
    ('C11 run = t(AB),rtl,t(C) anchor=BC (prefix lands on last char)',
     '<w:r><w:t>AB</w:t><w:rtl/><w:t>C</w:t></w:r>', 1, 3),
    ('C12 run = t(A),ptab,t(B) anchor=B',
     '<w:r><w:t>A</w:t><w:ptab w:alignment="left" w:relativeTo="margin" w:leader="none"/><w:t>B</w:t></w:r>', 1, 2),
    ('C13 run = t(A),lastRenderedPageBreak,t(B) anchor=B',
     '<w:r><w:t>A</w:t><w:lastRenderedPageBreak/><w:t>B</w:t></w:r>', 1, 2),
    ('C14 run = t(ABCD) anchor=BC',
     '<w:r><w:t>ABCD</w:t></w:r>', 1, 3),
    ('C15 run = t(A),t(B),t(C),t(D) anchor=BC',
     '<w:r><w:t>A</w:t><w:t>B</w:t><w:t>C</w:t><w:t>D</w:t></w:r>', 1, 3),
    ('C16 run = drawing,t(A),drawing,t(B),drawing anchor=B',
     '<w:r><w:drawing><wp:inline/></w:drawing><w:t>A</w:t>'
     '<w:drawing><wp:inline/></w:drawing><w:t>B</w:t>'
     '<w:drawing><wp:inline/></w:drawing></w:r>', 1, 2),
    ('C17 run = t(A),br,t(B) anchor=A (single char at start)',
     '<w:r><w:t>A</w:t><w:br/><w:t>B</w:t></w:r>', 0, 1),
    ('C18 run = t(A),br,t(BC) anchor=BC (anchor starts right after br)',
     '<w:r><w:t>A</w:t><w:br/><w:t>BC</w:t></w:r>', 1, 3),
    ('C19 run = rPr,t(A),br  anchor=A (hi==len)',
     '<w:r><w:rPr><w:b/></w:rPr><w:t>A</w:t><w:br/></w:r>', 0, 1),
    ('C20 run = rPr,t(AB),br  anchor=B',
     '<w:r><w:rPr><w:b/></w:rPr><w:t>AB</w:t><w:br/></w:r>', 1, 2),
]

print('### split_run unit probe')
for name, xml, lo, hi in CASES:
    p = parse_p(xml)
    run = p[0]
    txt = elem_text(run)
    before = stream(p)
    try:
        b, t, a = split_run(run, lo, hi)
        same = (t is run)
        after = stream(p)
        ok = 'IDENTITY' if same else 'SPLIT'
        print('%-62s txt=%-6r lo=%d hi=%d %s' % (name, txt, lo, hi, ok))
        print('    before=%s' % before.__repr__())
        print('    after =%s' % after.__repr__())
        print('    xml   =%s' % etree.tostring(p, encoding='unicode')[len('<w:p %s>' % NS):])
    except Exception as exc:
        print('%-62s EXC %s: %s' % (name, type(exc).__name__, exc))
    print()

print('### DocMap text collection probes')
DM_CASES = [
    ('D1 hyperlink',
     '<w:p %s><w:r><w:t>pre</w:t></w:r><w:hyperlink r:id="rId9" '
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
     '<w:r><w:t>LINKTEXT</w:t></w:r></w:hyperlink><w:r><w:t>post</w:t></w:r></w:p>'),
    ('D2 w:ins / w:del',
     '<w:p %s><w:ins w:id="1" w:author="a"><w:r><w:t>INSTEXT</w:t></w:r></w:ins>'
     '<w:del w:id="2" w:author="a"><w:r><w:delText>DELTEXT</w:delText></w:r></w:del></w:p>'),
    ('D3 w:fldSimple',
     '<w:p %s><w:fldSimple w:instr=" REF x "><w:r><w:t>FIELDTEXT</w:t></w:r></w:fldSimple></w:p>'),
    ('D4 w:sdt inline',
     '<w:p %s><w:sdt><w:sdtPr/><w:sdtContent><w:r><w:t>SDTTEXT</w:t></w:r>'
     '</w:sdtContent></w:sdt></w:p>'),
    ('D5 textbox in drawing (DrawingML)',
     '<w:p %s><w:r><w:drawing><wp:inline><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
     '<w:txbxContent><w:p><w:r><w:t>BOXONCE</w:t></w:r></w:p></w:txbxContent>'
     '</a:graphic></wp:inline></w:drawing></w:r><w:r><w:t>BODY</w:t></w:r></w:p>'),
    ('D6 textbox duplicated by mc:AlternateContent Choice+Fallback',
     '<w:p %s><w:r><mc:AlternateContent><mc:Choice Requires="wps">'
     '<w:drawing><wp:inline><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
     '<w:txbxContent><w:p><w:r><w:t>BOXDUP</w:t></w:r></w:p></w:txbxContent>'
     '</a:graphic></wp:inline></w:drawing></mc:Choice>'
     '<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>'
     '<w:p><w:r><w:t>BOXDUP</w:t></w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict>'
     '</mc:Fallback></mc:AlternateContent></w:r><w:r><w:t>BODY</w:t></w:r></w:p>'),
    ('D7 sdt block wrapping paragraphs + nested table',
     '<w:body %s><w:sdt><w:sdtPr/><w:sdtContent><w:p><w:r><w:t>SDTPARA</w:t></w:r></w:p>'
     '</w:sdtContent></w:sdt>'
     '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>CELL1</w:t></w:r></w:p>'
     '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>NEST</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
     '</w:tc></w:tr></w:tbl>'
     '<w:altChunk r:id="rIdX" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
     '</w:body>'),
    ('D8 paragraph inside textbox has ancestor p too (nested)',
     '<w:body %s><w:p><w:r><w:drawing><wp:inline>'
     '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
     '<w:txbxContent><w:p><w:r><w:t>IN1</w:t></w:r></w:p>'
     '<w:p><w:r><w:t>IN2</w:t></w:r></w:p></w:txbxContent>'
     '</a:graphic></wp:inline></w:drawing></w:r><w:r><w:t>OUT</w:t></w:r></w:p>'
     '<w:p><w:r><w:t>SECOND</w:t></w:r></w:p></w:body>'),
]

for name, xml in DM_CASES:
    doc = etree.fromstring((xml % NS).encode('utf-8'))
    dm = DocMap(doc)
    print('%-56s text=%r' % (name, dm.text))
    for needle in ('BOXDUP', 'BOXONCE', 'LINKTEXT', 'INSTEXT', 'DELTEXT',
                   'FIELDTEXT', 'SDTTEXT', 'SDTPARA', 'CELL1', 'NEST',
                   'IN1', 'IN2', 'OUT', 'SECOND', 'BODY'):
        loc = dm.locate(needle, 0)
        if loc is not None:
            print('        locate(%-10s) -> %s' % (needle, loc))
    print('        occurrences: BOXDUP=%d BOXONCE=%d IN1=%d' % (
        dm.text.count('BOXDUP'), dm.text.count('BOXONCE'), dm.text.count('IN1')))
    print()
