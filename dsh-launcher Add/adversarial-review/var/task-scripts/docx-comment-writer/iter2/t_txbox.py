# -*- coding: utf-8 -*-
"""L0 probe: OLD vs NEW dump_text on a REAL Word-authored doc containing a text box.

role : decisive evidence for the 'text box counted twice' claim
in   : work/RC_word.docx (created by Word 16, has both w:drawing and w:pict text boxes)
out  : printed occurrence counts
rerun: python t_txbox.py
"""
import os
import sys
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
NEW = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
OLD = r'C:\Users\雍远\.agents\skills\_backup\docx-comment-writer_prefix_20260917-032952\scripts'

rc = os.path.join(WORK, 'RC_word.docx')

for label, path in (('OLD', OLD), ('NEW', NEW)):
    sys.modules.pop('docx_commenter', None)
    sys.path.insert(0, path)
    m = importlib.import_module('docx_commenter')
    sys.path.remove(path)
    t = m.dump_text(rc)
    print('%s  len(dump)=%d  count(TEXTBOXTEXT)=%d  count(ANCHORONE)=%d'
          % (label, len(t), t.count('TEXTBOXTEXT'), t.count('ANCHORONE')))
    print('     locate(TEXTBOXTEXT)=%s locate(FOOTNOTETEXT)=%s'
          % (m.DocMap.__module__ and '', ''))
    from lxml import etree
    import zipfile
    with zipfile.ZipFile(rc) as z:
        root = etree.fromstring(z.read('word/document.xml'))
    dm = m.DocMap(root)
    print('     DocMap.text=%r' % dm.text[:200])
    print('     locate(TEXTBOXTEXT)=%s' % (dm.locate('TEXTBOXTEXT', 0),))
