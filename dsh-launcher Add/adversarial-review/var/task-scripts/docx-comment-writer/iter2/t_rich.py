# -*- coding: utf-8 -*-
"""L0 probe: rich Word-authored document -> engine -> Word, fidelity check.

role : build a feature-rich docx with real Word, run the engine, compare
in   : Word COM (creates the fixture)
out  : work/RC_*.docx and a fidelity report
rerun: python t_rich.py
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import lib  # noqa: E402
from docx_commenter import add_comments, dump_text  # noqa: E402
from verify_comments import verify  # noqa: E402
import win32com.client as wc  # noqa: E402

rc = os.path.join(WORK, 'RC_word.docx')
app = wc.Dispatch('Word.Application')
app.Visible = False
try:
    app.DisplayAlerts = 0
except Exception:
    pass

def step(label, fn):
    try:
        fn()
        print('  ok   %s' % label)
    except Exception as exc:
        print('  FAIL %s -> %s' % (label, str(exc)[:120]))


try:
    d = app.Documents.Add()
    d.Content.Text = ''
    rng = d.Content
    rng.InsertAfter('RICHDOC first paragraph with ANCHORONE inside.\r')
    rng2 = d.Content
    rng2.Collapse(0)
    d.Paragraphs.Add()
    d.Paragraphs(2).Range.InsertAfter('Second paragraph with ANCHORTWO here.\r')
    d.Paragraphs.Add()
    d.Paragraphs(3).Range.InsertAfter('Third line for spacing.\r')

    step('table', lambda: (lambda t: (
        setattr(t.Cell(1, 1).Range, 'Text', 'TBL11'),
        setattr(t.Cell(1, 2).Range, 'Text', 'TBL12'),
        setattr(t.Cell(2, 1).Range, 'Text', 'TBL21'),
        setattr(t.Cell(2, 2).Range, 'Text', 'TBL22')))(
            d.Tables.Add(d.Paragraphs(4).Range, 2, 2)))

    def addlink():
        hp = d.Paragraphs.Add()
        hp.Range.InsertAfter('Linkline example link text\r')
        hr = d.Range(hp.Range.Start + 9, hp.Range.Start + 9 + len('example link text'))
        d.Hyperlinks.Add(hr, 'https://example.com/', None, 'EXAMPLELINK',
                         'example link text')
    step('hyperlink', addlink)

    step('header', lambda: setattr(d.Sections(1).Headers(1).Range, 'Text', 'MYHEADER'))
    step('footer', lambda: setattr(d.Sections(1).Footers(1).Range, 'Text', 'MYFOOTER'))

    def addtb():
        tb = d.Shapes.AddTextbox(1, 50, 50, 200, 80)
        tb.TextFrame.TextRange.Text = 'TEXTBOXTEXT'
    step('textbox', addtb)

    def addfn():
        a = d.Paragraphs(1).Range
        a.Collapse(0)
        d.Footnotes.Add(a, 'FOOTNOTETEXT')
    step('footnote', addfn)

    def addcmt():
        cr = d.Paragraphs(3).Range
        cr.MoveEnd(1, -1)
        d.Comments.Add(cr, 'word own comment')
    step('comment', addcmt)

    d.SaveAs2(rc, FileFormat=16)
    d.Close(False)
    print('rich fixture built: %s' % rc)
except Exception as exc:
    print('build failed: %s' % str(exc)[:300])
finally:
    try:
        app.Quit()
    except Exception:
        pass

if not os.path.exists(rc):
    sys.exit(1)

print()
print('=== parts ===')
print([n for n in lib.part_names(rc)])
r0 = lib.load_doc(rc)
print('counts src=%s' % lib.counts(r0))
for tag in ('drawing', 'pict', 'txbxContent', 'hyperlink', 'footnoteReference',
            'tbl', 'tc', 'fldSimple', 'fldChar', 'instrText', 'sectPr'):
    n = len(list(r0.iter(lib.q(tag))))
    if n:
        print('   src %-18s = %d' % (tag, n))

text = dump_text(rc)
print('dump_text=%r' % text[:400])
print('contains TEXTBOXTEXT in dump=%s' % ('TEXTBOXTEXT' in text))
print('contains ANCHORONE=%s ANCHORTWO=%s' % ('ANCHORONE' in text, 'ANCHORTWO' in text))

out = os.path.join(WORK, 'RC_out.docx')
try:
    lg, n = add_comments(rc, out, [{'anchor': 'ANCHORONE', 'text': 'rev one'},
                                   {'anchor': 'ANCHORTWO', 'text': 'rev two'},
                                   {'anchor': 'TEXTBOXTEXT', 'text': 'must MISS'}],
                         author='REV', initials='RV')
    print('log=%s n=%d' % (lg, n))
except Exception as exc:
    print('RAISED %s: %s' % (type(exc).__name__, exc))
    raise SystemExit(1)

print('verify=%s' % (verify(out),))
r1 = lib.load_doc(out)
print('counts dst=%s' % lib.counts(r1))
print('sig_equal=%s' % (lib.sig(r0) == lib.sig(r1)))
if lib.sig(r0) != lib.sig(r1):
    a, b = lib.sig(r0), lib.sig(r1)
    import difflib
    print(''.join(difflib.unified_diff([a], [b])))
with zipfile.ZipFile(out) as z:
    names = set(z.namelist())
d = lib.load_doc(out)
for tag in ('drawing', 'pict', 'txbxContent', 'hyperlink', 'footnoteReference',
            'tbl', 'tc', 'fldSimple', 'fldChar', 'instrText', 'sectPr'):
    n = len(list(d.iter(lib.q(tag))))
    if n:
        print('   dst %-18s = %d' % (tag, n))
mk = [(e.tag.split('}')[-1], e.get(lib.q('id')), e.getparent().tag.split('}')[-1])
      for e in d.iter() if e.tag in (lib.q('commentRangeStart'), lib.q('commentRangeEnd'))]
print('markers=%s' % mk)
print('dump_text(dst) == dump_text(src): %s' % (dump_text(out) == text))

print()
print('=== xml header/footer preserved ===')
with zipfile.ZipFile(rc) as z:
    h0 = [n for n in z.namelist() if 'header' in n or 'footer' in n]
    c0 = {n: z.read(n) for n in h0}
with zipfile.ZipFile(out) as z:
    h1 = [n for n in z.namelist() if 'header' in n or 'footer' in n]
    c1 = {n: z.read(n) for n in h1}
print('src=%s dst=%s identical=%s' % (h0, h1, c0 == c1))
