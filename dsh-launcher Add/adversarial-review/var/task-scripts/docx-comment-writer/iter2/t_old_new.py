# -*- coding: utf-8 -*-
"""L0 probe: OLD (pre-fix snapshot) vs NEW engine, same synthetic inputs.

role : deterministic old/new comparison (no expected values embedded)
in   : backup snapshot dir + installed skill
out  : per-case DocMap text and split_run stream for both engines
rerun: python t_old_new.py
"""
import sys
import importlib
from lxml import etree

OLD = r'C:\Users\雍远\.agents\skills\_backup\docx-comment-writer_prefix_20260917-032952\scripts'
NEW = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = ('xmlns:w="%s" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:v="urn:schemas-microsoft-com:vml"' % W)


def q(t):
    return '{%s}%s' % (W, t)


def load(path):
    for m in ('docx_commenter',):
        if m in sys.modules:
            del sys.modules[m]
    sys.path.insert(0, path)
    try:
        return importlib.import_module('docx_commenter')
    finally:
        sys.path.remove(path)


def stream(el):
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
    ('D5 textbox in drawing',
     '<w:p %s><w:r><w:drawing><wp:inline><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
     '<w:txbxContent><w:p><w:r><w:t>BOXONCE</w:t></w:r></w:p></w:txbxContent>'
     '</a:graphic></wp:inline></w:drawing></w:r><w:r><w:t>BODY</w:t></w:r></w:p>'),
    ('D6 textbox dup via mc:AlternateContent',
     '<w:p %s><w:r><mc:AlternateContent><mc:Choice Requires="wps">'
     '<w:drawing><wp:inline><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
     '<w:txbxContent><w:p><w:r><w:t>BOXDUP</w:t></w:r></w:p></w:txbxContent>'
     '</a:graphic></wp:inline></w:drawing></mc:Choice>'
     '<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>'
     '<w:p><w:r><w:t>BOXDUP</w:t></w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict>'
     '</mc:Fallback></mc:AlternateContent></w:r><w:r><w:t>BODY</w:t></w:r></w:p>'),
    ('D8 nested textbox paragraphs',
     '<w:body %s><w:p><w:r><w:drawing><wp:inline>'
     '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
     '<w:txbxContent><w:p><w:r><w:t>IN1</w:t></w:r></w:p>'
     '<w:p><w:r><w:t>IN2</w:t></w:r></w:p></w:txbxContent>'
     '</a:graphic></wp:inline></w:drawing></w:r><w:r><w:t>OUT</w:t></w:r></w:p>'
     '<w:p><w:r><w:t>SECOND</w:t></w:r></w:p></w:body>'),
]

SNIP_CASES = [
    ('S1 t(AB)+br, anchor=B', '<w:r><w:t>AB</w:t><w:br/></w:r>', 1, 2),
    ('S2 t(A),tab,t(B),tab,t(C), anchor=B',
     '<w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:tab/><w:t>C</w:t></w:r>', 1, 2),
    ('S3 tab,t(A),tab,t(B),tab anchor=B',
     '<w:r><w:tab/><w:t>A</w:t><w:tab/><w:t>B</w:t><w:tab/></w:r>', 1, 2),
    ('S4 t(A),t(B),t(C),t(D) anchor=BC',
     '<w:r><w:t>A</w:t><w:t>B</w:t><w:t>C</w:t><w:t>D</w:t></w:r>', 1, 3),
    ('S5 t(A),br,t(B) anchor=A', '<w:r><w:t>A</w:t><w:br/><w:t>B</w:t></w:r>', 0, 1),
    ('S6 t(A),br,t(BC) anchor=BC', '<w:r><w:t>A</w:t><w:br/><w:t>BC</w:t></w:r>', 1, 3),
]

for label, path in (('OLD', OLD), ('NEW', NEW)):
    m = load(path)
    print('##### %s : %s' % (label, m.__file__))
    for name, xml in DM_CASES:
        doc = etree.fromstring((xml % NS).encode('utf-8'))
        dm = m.DocMap(doc)
        print('  %-40s text=%r' % (name, dm.text))
    for name, xml, lo, hi in SNIP_CASES:
        p = etree.fromstring(('<w:p %s>%s</w:p>' % (NS, xml)).encode('utf-8'))
        run = p[0]
        try:
            r = m.split_run(run, lo, hi)
            ident = 'IDENTITY' if r[1] is run else 'SPLIT'
            print('  %-40s %s stream=%r' % (name, ident, stream(p)))
            print('      %s' % etree.tostring(p, encoding='unicode').split('>', 1)[1])
        except Exception as exc:
            print('  %-40s EXC %s: %s' % (name, type(exc).__name__, exc))
    print()
