# -*- coding: utf-8 -*-
"""L0 probe: CONTROL test - are the hyperlink/textbox fixtures themselves Word-valid?

role : separates fixture invalidity from engine-caused corruption
in   : freshly built src/out pairs
out  : Word open verdict for src vs out of each pair
rerun: python t_control.py
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
import lib  # noqa: E402
import win32com.client as wc  # noqa: E402

REL_EXT = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rIdX" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/" TargetMode="External"/>
</Relationships>'''

CASES = {}

# 1. external hyperlink with a REAL relationship present
CASES['HL_valid'] = (
    '<w:p><w:r><w:t>PRE </w:t></w:r>'
    '<w:hyperlink r:id="rIdX"><w:r><w:t>LINKTARGET</w:t></w:r></w:hyperlink>'
    '<w:r><w:t> POST</w:t></w:r></w:p>', REL_EXT)

# 2. internal (anchor) hyperlink - no relationship needed
CASES['HL_anchor'] = (
    '<w:p><w:bookmarkStart w:id="1" w:name="bm"/><w:r><w:t>PRE </w:t></w:r>'
    '<w:hyperlink w:anchor="bm"><w:r><w:t>LINKTARGET</w:t></w:r></w:hyperlink>'
    '<w:r><w:t> POST</w:t></w:r></w:p>', None)

# 3. textbox with a fully-specified drawing (graphicData uri + wp:inline attrs)
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
CASES['TXBOX_valid'] = (TXBOX, None)

# 4. w:ins with a proper w:ins wrapping the run
CASES['INS_valid'] = (
    '<w:p><w:r><w:t>PRE </w:t></w:r>'
    '<w:ins w:id="11" w:author="a" w:date="2020-01-01T00:00:00Z">'
    '<w:r><w:t>INSTARGET</w:t></w:r></w:ins>'
    '<w:r><w:t> POST</w:t></w:r></w:p>', None)

# 5. sdt inline
CASES['SDT_valid'] = (
    '<w:p><w:r><w:t>PRE </w:t></w:r>'
    '<w:sdt><w:sdtPr><w:id w:val="1"/></w:sdtPr>'
    '<w:sdtContent><w:r><w:t>SDTTARGET</w:t></w:r></w:sdtContent></w:sdt>'
    '<w:r><w:t> POST</w:t></w:r></w:p>', None)

pairs = []
for name, (body, rels) in CASES.items():
    src = os.path.join(WORK, 'CTL_%s.src.docx' % name)
    out = os.path.join(WORK, 'CTL_%s.out.docx' % name)
    mkc.build(src, body)
    if rels:
        with __import__('zipfile').ZipFile(src, 'a') as z:
            z.writestr('word/_rels/document.xml.rels', rels)
    pairs.append((name, src, out, body))

app = wc.Dispatch('Word.Application')
app.Visible = False
try:
    app.DisplayAlerts = 0
except Exception:
    pass


def verdict(path):
    try:
        d = app.Documents.Open(path, ReadOnly=True)
        try:
            cnt = d.Comments.Count
            scopes = [d.Comments(i).Scope.Text for i in range(1, cnt + 1)]
            return 'OK comments=%d scopes=%s' % (cnt, scopes)
        finally:
            d.Close(False)
    except Exception as exc:
        return 'FAIL %s' % str(exc)[:140]


ANCHORS = {'HL_valid': 'LINKTARGET', 'HL_anchor': 'LINKTARGET',
           'TXBOX_valid': 'OUTSIDE', 'INS_valid': 'INSTARGET',
           'SDT_valid': 'SDTTARGET'}

print('===== control: source fixture validity vs engine output =====')
for name, src, out, body in pairs:
    v_src = verdict(src)
    print('%-14s SRC  %s' % (name, v_src))
    try:
        lg, n = add_comments(src, out, [{'anchor': ANCHORS[name], 'text': 'c1'}],
                             author='REV', initials='RV')
    except Exception as exc:
        print('%-14s ENGINE RAISED %s: %s' % (name, type(exc).__name__, exc))
        continue
    print('%-14s log=%s' % (name, lg))
    print('%-14s OUT  %s' % (name, verdict(out)))

# also: markers placed INSIDE a hyperlink by hand, to isolate the cause
manual = os.path.join(WORK, 'CTL_manual_inlink.docx')
mkc.build(manual,
          '<w:p><w:r><w:t>PRE </w:t></w:r>'
          '<w:hyperlink w:anchor="bm">'
          '<w:commentRangeStart w:id="1"/>'
          '<w:r><w:t>LINKTARGET</w:t></w:r>'
          '<w:commentRangeEnd w:id="1"/>'
          '<w:r><w:commentReference w:id="1"/></w:r>'
          '</w:hyperlink>'
          '<w:r><w:t> POST</w:t></w:r></w:p>',
          extra={'word/comments.xml':
                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<w:comments xmlns:w="%s"><w:comment w:id="1" w:author="m" '
                 'w:date="2020-01-01T00:00:00Z" w:initials="M">'
                 '<w:p><w:r><w:t>manual</w:t></w:r></w:p></w:comment></w:comments>' % lib.W},
          extra_ct='<Override PartName="/word/comments.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
print('%-14s MANUAL-IN-HYPERLINK %s' % ('manual', verdict(manual)))

# and: markers inside w:ins, by hand
manual2 = os.path.join(WORK, 'CTL_manual_inins.docx')
mkc.build(manual2,
          '<w:p><w:r><w:t>PRE </w:t></w:r>'
          '<w:ins w:id="11" w:author="a" w:date="2020-01-01T00:00:00Z">'
          '<w:commentRangeStart w:id="1"/>'
          '<w:r><w:t>INSTARGET</w:t></w:r>'
          '<w:commentRangeEnd w:id="1"/>'
          '<w:r><w:commentReference w:id="1"/></w:r>'
          '</w:ins>'
          '<w:r><w:t> POST</w:t></w:r></w:p>',
          extra={'word/comments.xml':
                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<w:comments xmlns:w="%s"><w:comment w:id="1" w:author="m" '
                 'w:date="2020-01-01T00:00:00Z" w:initials="M">'
                 '<w:p><w:r><w:t>manual</w:t></w:r></w:p></w:comment></w:comments>' % lib.W},
          extra_ct='<Override PartName="/word/comments.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
print('%-14s MANUAL-IN-INS %s' % ('manual2', verdict(manual2)))

app.Quit()
