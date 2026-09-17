# -*- coding: utf-8 -*-
"""L0 probe: verify_comments robustness + dump_text guard + rels creation.

role : deterministic probing of the checker itself
in   : work/*.docx fixtures from earlier probes
out  : printed verdicts / exceptions
rerun: python t_misc.py    (run after t_integration.py)
"""
import os
import sys
import zipfile
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
import lib  # noqa: E402
from docx_commenter import dump_text, add_comments  # noqa: E402
from verify_comments import verify  # noqa: E402

print('===== 1. verify() on documents without any comments =====')
probe = os.path.join(WORK, 'V_nocomments.docx')
mkc.build(probe, '<w:p><w:r><w:t>NOC</w:t></w:r></w:p>')
try:
    p, s = verify(probe)
    print('   no comments.xml at all -> probs=%s stats=%s' % (p, s))
except Exception as exc:
    print('   no comments.xml at all -> RAISED %s: %s' % (type(exc).__name__, exc))

probe2 = os.path.join(WORK, 'V_emptycomments.docx')
mkc.build(probe2, '<w:p><w:r><w:t>NOC</w:t></w:r></w:p>',
          extra={'word/comments.xml':
                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<w:comments xmlns:w="%s"></w:comments>' % lib.W},
          extra_ct='<Override PartName="/word/comments.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
try:
    p, s = verify(probe2)
    print('   empty comments.xml     -> probs=%s stats=%s' % (p, s))
except Exception as exc:
    print('   empty comments.xml     -> RAISED %s: %s' % (type(exc).__name__, exc))

print()
print('===== 2. verify() on a docx with NO word/_rels/document.xml.rels =====')
probe3 = os.path.join(WORK, 'V_norels.docx')
mkc.build(probe3, '<w:p><w:r><w:t>NORELS</w:t></w:r></w:p>', with_rels=False,
          extra={'word/comments.xml':
                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<w:comments xmlns:w="%s"><w:comment w:id="1" w:author="a" '
                 'w:date="2020-01-01T00:00:00Z" w:initials="A">'
                 '<w:p><w:r><w:t>x</w:t></w:r></w:p></w:comment></w:comments>' % lib.W},
          extra_ct='<Override PartName="/word/comments.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
try:
    p, s = verify(probe3)
    print('   missing rels part      -> probs=%s stats=%s' % (p, s))
except Exception as exc:
    print('   missing rels part      -> RAISED %s: %s' % (type(exc).__name__, exc))

print()
print('===== 3. verify() on a doc with comments.xml but zero comments AND markers present =====')
probe4 = os.path.join(WORK, 'V_markernocomment.docx')
mkc.build(probe4,
          '<w:p><w:commentRangeStart w:id="1"/><w:r><w:t>M</w:t></w:r>'
          '<w:commentRangeEnd w:id="1"/><w:r><w:commentReference w:id="1"/></w:r></w:p>',
          extra={'word/comments.xml':
                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<w:comments xmlns:w="%s"></w:comments>' % lib.W},
          extra_ct='<Override PartName="/word/comments.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>',
          rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId9" '
               'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
               'Target="comments.xml"/></Relationships>')
try:
    p, s = verify(probe4)
    print('   markers w/o comment    -> probs=%s stats=%s' % (p, s))
except Exception as exc:
    print('   markers w/o comment    -> RAISED %s: %s' % (type(exc).__name__, exc))

print()
print('===== 4. dump_text same-path guard =====')
same = os.path.join(WORK, 'V_same.docx')
mkc.build(same, '<w:p><w:r><w:t>DT</w:t></w:r></w:p>')
before = open(same, 'rb').read()
try:
    dump_text(same, same)
    print('   dump_text(src, src) -> NO EXCEPTION (bad)')
except Exception as exc:
    print('   dump_text(src, src) -> %s: %s' % (type(exc).__name__, exc))
print('   bytes unchanged=%s' % (open(same, 'rb').read() == before))
# does dump_text leave a .dumptext residue on failure?
print('   dumptext residue=%s' % [f for f in os.listdir(WORK) if 'dumptext' in f])

print()
print('===== 5. rels / content-types written into K_norels.out.docx =====')
k = os.path.join(WORK, 'K_norels.out.docx')
if os.path.exists(k):
    with zipfile.ZipFile(k) as z:
        names = z.namelist()
        print('   rels present=%s' % ('word/_rels/document.xml.rels' in names))
        if 'word/_rels/document.xml.rels' in names:
            print('   rels=%s' % z.read('word/_rels/document.xml.rels').decode('utf-8'))
        print('   content-types has comments=%s' %
              (b'/word/comments.xml' in z.read('[Content_Types].xml')))
        print('   first entry=%s' % names[0])

print()
print('===== 6. overlapping anchors: real range geometry =====')
d = lib.load_doc(os.path.join(WORK, 'I_overlap.out.docx'))
seq = []
for e in d.iter():
    if e.tag in (lib.q('commentRangeStart'), lib.q('commentRangeEnd'), lib.q('t'),
                 lib.q('commentReference')):
        seq.append('%s%s' % (e.tag.split('}')[-1],
                             ('#' + (e.get(lib.q('id')) or '')) if e.get(lib.q('id')) else
                             (':' + (e.text or ''))))
print('   ' + ' | '.join(seq))

print()
print('===== 7. O_weirdids: declared vs marked ids =====')
with zipfile.ZipFile(os.path.join(WORK, 'O_weirdids.out.docx')) as z:
    cm = etree.fromstring(z.read('word/comments.xml'))
    dc = etree.fromstring(z.read('word/document.xml'))
print('   declared=%s' % [c.get(lib.q('id')) for c in cm.iter(lib.q('comment'))])
print('   marked  =%s' % sorted({e.get(lib.q('id')) for e in dc.iter(lib.q('commentRangeStart'))}))
print('   verify  =%s' % (verify(os.path.join(WORK, 'O_weirdids.out.docx')),))
