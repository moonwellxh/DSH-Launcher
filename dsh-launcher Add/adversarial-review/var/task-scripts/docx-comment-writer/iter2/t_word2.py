# -*- coding: utf-8 -*-
"""L0 probe: Word-only questions.

(a) markers placed INSIDE <w:r> - does Word 16 really refuse?
(b) Word round-trip (SaveAs) of engine output - does Word keep the comments?
(c) a Word-authored comment anchored in a HEADER (header part) -> engine append + verify
role : oracle tests; each Word open is done in-process but with a fresh instance
in   : work/
out  : printed verdicts
rerun: python t_word2.py
"""
import os
import sys
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
import lib  # noqa: E402
from docx_commenter import add_comments  # noqa: E402
from verify_comments import verify  # noqa: E402

COMMENTS_PART = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<w:comments xmlns:w="%s">'
                 '<w:comment w:id="1" w:author="m" w:date="2020-01-01T00:00:00Z" w:initials="M">'
                 '<w:p><w:r><w:t>manual</w:t></w:r></w:p></w:comment></w:comments>' % lib.W)
CT_OVERRIDE = ('<Override PartName="/word/comments.xml" '
               'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
RELS_C = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          '<Relationship Id="rId9" '
          'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
          'Target="comments.xml"/></Relationships>')


def one(path):
    import win32com.client as wc
    app = wc.Dispatch('Word.Application')
    app.Visible = False
    try:
        app.DisplayAlerts = 0
    except Exception:
        pass
    try:
        d = app.Documents.Open(path, ReadOnly=True)
        try:
            cnt = d.Comments.Count
            return 'OPEN_OK comments=%d scopes=%s' % (
                cnt, [d.Comments(i).Scope.Text for i in range(1, cnt + 1)])
        finally:
            d.Close(False)
    except Exception as exc:
        return 'OPEN_FAIL %s' % str(exc)[:150].replace('\n', ' ').replace('\r', ' ')
    finally:
        try:
            app.Quit()
        except Exception:
            pass


print('===== (a) markers placed INSIDE <w:r> =====')
inner = os.path.join(WORK, 'RW_inner.docx')
mkc.build(inner,
          '<w:p><w:r><w:t>PRE </w:t>'
          '<w:commentRangeStart w:id="1"/>'
          '<w:t>TARGET</w:t>'
          '<w:commentRangeEnd w:id="1"/>'
          '<w:commentReference w:id="1"/></w:r>'
          '<w:r><w:t> POST</w:t></w:r></w:p>',
          extra={'word/comments.xml': COMMENTS_PART},
          extra_ct=CT_OVERRIDE, rels=RELS_C)
print('   markers-in-run : %s' % one(inner))

outer = os.path.join(WORK, 'RW_outer.docx')
mkc.build(outer,
          '<w:p><w:r><w:t>PRE </w:t></w:r>'
          '<w:commentRangeStart w:id="1"/>'
          '<w:r><w:t>TARGET</w:t></w:r>'
          '<w:commentRangeEnd w:id="1"/>'
          '<w:r><w:commentReference w:id="1"/></w:r>'
          '<w:r><w:t> POST</w:t></w:r></w:p>',
          extra={'word/comments.xml': COMMENTS_PART},
          extra_ct=CT_OVERRIDE, rels=RELS_C)
print('   markers-at-p   : %s' % one(outer))

print()
print('===== (b) Word round-trip (SaveAs) of engine output =====')
import win32com.client as wc  # noqa: E402

for name in ('HL_HL_ext.out.docx', 'HL_INS.out.docx', 'HL_SDT.out.docx',
             'B_crosspara.out.docx', 'C_crosscell.out.docx', 'I_overlap.out.docx',
             'R_adjacent.out.docx', 'J_trailtab.out.docx'):
    p = os.path.join(WORK, name)
    if not os.path.exists(p):
        continue
    rt = os.path.join(WORK, 'RT_' + name)
    app = wc.Dispatch('Word.Application')
    app.Visible = False
    try:
        app.DisplayAlerts = 0
    except Exception:
        pass
    try:
        d = app.Documents.Open(p)
        try:
            before = d.Comments.Count
            d.SaveAs2(rt, FileFormat=16)
            d.Close(False)
            print('   %-26s saved; reopened check below' % name)
        except Exception as exc:
            print('   %-26s SaveAs failed %s' % (name, str(exc)[:100]))
            try:
                d.Close(False)
            except Exception:
                pass
    except Exception as exc:
        print('   %-26s open failed %s' % (name, str(exc)[:120]))
    finally:
        try:
            app.Quit()
        except Exception:
            pass
    if os.path.exists(rt):
        print('   %-26s -> %s' % ('roundtrip', one(rt)))
        with __import__('zipfile').ZipFile(rt) as z:
            r = __import__('lxml.etree', fromlist=['x']).fromstring(z.read('word/document.xml'))
        mk = [(e.tag.split('}')[-1], e.get(lib.q('id')), e.getparent().tag.split('}')[-1])
              for e in r.iter() if e.tag in (lib.q('commentRangeStart'), lib.q('commentRangeEnd'))]
        print('   %-26s markers=%s' % ('roundtrip', mk))

print()
print('===== (c) Word-authored comment in a HEADER =====')
base = os.path.join(WORK, 'HD_base.docx')
mkc.build(base, '<w:p><w:r><w:t>BODYTEXT here</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>SECONDLINE</w:t></w:r></w:p>')
app = wc.Dispatch('Word.Application')
app.Visible = False
try:
    app.DisplayAlerts = 0
except Exception:
    pass
hd = os.path.join(WORK, 'HD_word.docx')
try:
    d = app.Documents.Open(base)
    sec = d.Sections(1)
    hdr = sec.Headers(1)
    hdr.Range.Text = 'HEADERTEXT'
    hr = hdr.Range
    hr.MoveEnd(1, -1)
    d.Comments.Add(hr, 'header comment')
    d.SaveAs2(hd, FileFormat=16)
    d.Close(False)
    print('   header-comment doc built')
except Exception as exc:
    print('   build failed: %s' % str(exc)[:160])
try:
    app.Quit()
except Exception:
    pass

if os.path.exists(hd):
    print('   parts=%s' % [x for x in lib.part_names(hd) if 'comment' in x or 'header' in x])
    with __import__('zipfile').ZipFile(hd) as z:
        cm = __import__('lxml.etree', fromlist=['x']).fromstring(z.read('word/comments.xml'))
        names = z.namelist()
        for n in names:
            if n.startswith('word/header'):
                hx = __import__('lxml.etree', fromlist=['x']).fromstring(z.read(n))
                mk = sorted({e.get(lib.q('id')) for e in hx.iter(lib.q('commentRangeStart'))})
                print('   %s markers=%s' % (n, mk))
    print('   comments.xml ids=%s' % [c.get(lib.q('id')) for c in cm.iter(lib.q('comment'))])
    print('   engine append ->')
    out = os.path.join(WORK, 'HD_appended.docx')
    try:
        lg, n = add_comments(hd, out, [{'anchor': 'SECONDLINE', 'text': 'appended'}],
                             author='REV', initials='RV')
        print('      log=%s n=%d' % (lg, n))
        print('      verify=%s' % (verify(out),))
        print('      word=%s' % one(out))
    except Exception as exc:
        print('      RAISED %s: %s' % (type(exc).__name__, exc))
    print('   verify(src header doc)=%s' % (verify(hd),))
