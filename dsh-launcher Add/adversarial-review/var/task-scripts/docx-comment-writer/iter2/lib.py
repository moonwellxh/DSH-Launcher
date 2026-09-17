# -*- coding: utf-8 -*-
"""Shared helpers for the adversarial review of docx-comment-writer.

role : deterministic content signature / counting for docx packages
in   : path to .docx, or lxml root
out  : printed signatures; no assertions about expected values
rerun: python lib.py <file.docx>   (needs lxml)
"""
import os
import sys
import zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def q(t):
    return '{%s}%s' % (W, t)


SKIP_DESCEND = {
    q('drawing'): '<IMG>',
    q('pict'): '<PICTVML>',
    q('object'): '<OBJ>',
    q('txbxContent'): '<TXBX>',
}


def load_doc(path):
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read('word/document.xml'))


def load_part(path, name):
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read(name))


def sig(root):
    """Ordered render-relevant token stream of the body.

    descends into everything EXCEPT drawing/pict/object/txbxContent
    (emitted as a single placeholder token), so a text box is counted
    once and images are counted without pulling in their inner text.
    """
    out = []

    def walk(el):
        for c in el:
            tag = c.tag
            if tag in SKIP_DESCEND:
                out.append(SKIP_DESCEND[tag])
                continue
            if tag == q('t'):
                out.append(c.text or '')
                continue
            if tag == q('tab'):
                out.append('\t')
                continue
            if tag in (q('br'), q('cr')):
                out.append('\n')
                continue
            if tag in (q('commentRangeStart'), q('commentRangeEnd'),
                       q('commentReference')):
                continue
            if tag in (q('rPr'), q('pPr'), q('sectPr'), q('tblPr'),
                       q('trPr'), q('tcPr'), q('tblGrid')):
                continue
            if tag == q('p'):
                out.append('\n')
            walk(c)

    walk(root)
    return ''.join(out)


def counts(root):
    return {
        'tab': len(list(root.iter(q('tab')))),
        'br': len(list(root.iter(q('br')))),
        'cr': len(list(root.iter(q('cr')))),
        'drawing': len(list(root.iter(q('drawing')))),
        'pict': len(list(root.iter(q('pict')))),
        'txt': len(list(root.iter(q('t')))),
    }


def para_texts(root):
    return [''.join(t.text or '' for t in p.iter(q('t'))) for p in root.iter(q('p'))]


def part_names(path):
    with zipfile.ZipFile(path) as z:
        return sorted(z.namelist())


if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = load_doc(p)
        print('==', p)
        print('counts', counts(r))
        print('sig', repr(sig(r))[:1200])
