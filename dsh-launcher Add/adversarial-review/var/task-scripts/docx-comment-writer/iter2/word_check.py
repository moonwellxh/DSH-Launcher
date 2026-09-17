# -*- coding: utf-8 -*-
"""L0 probe: open ONE docx in a fresh Word instance and read comments back.

role : crash-isolated Word 16 oracle (one process per document)
in   : argv[1] = docx path
out  : single line verdict on stdout
rerun: python word_check.py <file.docx>
"""
import sys

path = sys.argv[1]
try:
    import win32com.client as wc
    app = wc.Dispatch('Word.Application')
except Exception as exc:
    print('NOWORD %s' % exc)
    sys.exit(0)

app.Visible = False
try:
    app.DisplayAlerts = 0
except Exception:
    pass

verdict = ''
try:
    d = app.Documents.Open(path, ReadOnly=True)
    try:
        cnt = d.Comments.Count
        scopes = []
        for i in range(1, cnt + 1):
            try:
                scopes.append(d.Comments(i).Scope.Text)
            except Exception as exc:
                scopes.append('<err %s>' % exc)
        verdict = 'OPEN_OK comments=%d scopes=%s' % (cnt, scopes)
    finally:
        try:
            d.Close(False)
        except Exception:
            pass
except Exception as exc:
    verdict = 'OPEN_FAIL %s' % str(exc)[:180].replace('\n', ' ').replace('\r', ' ')

try:
    app.Quit()
except Exception:
    pass
print(verdict)
