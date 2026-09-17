# -*- coding: utf-8 -*-
"""L0 probe: open every produced docx in real Microsoft Word and read back comments.

role : strongest available oracle (Word 16 via COM) - open + Comments.Count + Scope.Text
in   : D:\\DeepSeekS\\scratch\\review2\\work\\*.out.docx
out  : printed table; also builds round-2 append docs and a Word-authored comment doc
rerun: python t_word.py
"""
import os
import sys
import glob
import shutil
import zipfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
from docx_commenter import add_comments  # noqa: E402
import lib  # noqa: E402

try:
    import win32com.client as wc
except ImportError:
    print('pywin32 missing')
    sys.exit(2)

# ---------------------------------------------------------------- round 2
r2src = os.path.join(WORK, 'R2_r1.docx')
r2dst = os.path.join(WORK, 'R2_r2.docx')
mkc.build(os.path.join(WORK, 'R2_base.docx'),
          '<w:p><w:r><w:t>FIRSTTARGET here</w:t></w:r></w:p>'
          '<w:p><w:r><w:t>SECONDTARGET there</w:t></w:r></w:p>')
add_comments(os.path.join(WORK, 'R2_base.docx'), r2src,
             [{'anchor': 'FIRSTTARGET', 'text': 'round one'}],
             author='REV1', initials='R1')
lg, n = add_comments(r2src, r2dst, [{'anchor': 'SECONDTARGET', 'text': 'round two'}],
                     author='REV2', initials='R2')
print('round2 log=%s n=%d' % (lg, n))

# ------------------------------------------------- round 2 on Word's own comments
base = os.path.join(WORK, 'W_wordauthored.docx')
mkc.build(base, '<w:p><w:r><w:t>WORDMADE target text</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>OTHERTAIL line</w:t></w:r></w:p>')

app = wc.Dispatch('Word.Application')
app.Visible = False
try:
    app.DisplayAlerts = 0
except Exception:
    pass

wordauthored = None
try:
    d = app.Documents.Open(base)
    rng = d.Paragraphs(1).Range
    rng.MoveEnd(1, -1)
    d.Comments.Add(rng, 'word authored comment')
    d.SaveAs2(os.path.join(WORK, 'W_wordauthored_c.docx'), FileFormat=16)
    d.Close(False)
    wordauthored = os.path.join(WORK, 'W_wordauthored_c.docx')
    print('word-authored commented doc built: ok')
except Exception as exc:
    print('failed to build word-authored doc: %s' % exc)

if wordauthored:
    try:
        r = lib.load_doc(wordauthored)
        print('word-authored parts: %s' % [x for x in lib.part_names(wordauthored)
                                           if 'comment' in x.lower()])
        print('word-authored declared ids: %s' % [
            c.get(lib.q('id')) for c in r.iter(lib.q('comment'))])
    except Exception:
        pass
    try:
        lg2, n2 = add_comments(wordauthored, os.path.join(WORK, 'W_appended.docx'),
                               [{'anchor': 'OTHERTAIL', 'text': 'appended by engine'}],
                               author='REV', initials='RV')
        print('append-on-word-doc log=%s n=%d' % (lg2, n2))
    except Exception as exc:
        print('append-on-word-doc RAISED %s: %s' % (type(exc).__name__, exc))

targets = sorted(glob.glob(os.path.join(WORK, '*.out.docx')))
for extra in ('R2_r1.docx', 'R2_r2.docx', 'W_wordauthored_c.docx', 'W_appended.docx'):
    p = os.path.join(WORK, extra)
    if os.path.exists(p):
        targets.append(p)

print()
print('===== Word 16 read-back =====')
results = {}
for p in targets:
    name = os.path.basename(p)
    try:
        d = app.Documents.Open(p, ReadOnly=True)
        try:
            cnt = d.Comments.Count
            scopes = []
            for i in range(1, cnt + 1):
                try:
                    scopes.append(d.Comments(i).Scope.Text)
                except Exception as exc:
                    scopes.append('<scope err %s>' % exc)
            results[name] = (cnt, scopes)
            print('%-30s OPEN_OK comments=%d scopes=%s' % (name, cnt, scopes))
        finally:
            d.Close(False)
    except Exception as exc:
        results[name] = ('OPEN_FAIL', str(exc)[:200])
        print('%-30s OPEN_FAIL %s' % (name, str(exc)[:200]))

try:
    app.Quit()
except Exception:
    pass

with open(os.path.join(WORK, 'report_word.txt'), 'w', encoding='utf-8') as f:
    for k, v in results.items():
        f.write('%s\t%s\n' % (k, v))
print('written', os.path.join(WORK, 'report_word.txt'))
