# -*- coding: utf-8 -*-
"""L0 probe: build integration fixtures, run the NEW engine, dump structure.

role : deterministic fixtures + engine run + structural dump (no expected values)
in   : mkc.py builder, installed engine
out  : work/*.docx and a structural report
rerun: python t_integration.py
"""
import os
import sys
import shutil
import zipfile
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SKILL = r'C:\Users\雍远\.agents\skills\docx-comment-writer\scripts'
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)

import mkc  # noqa: E402
from docx_commenter import add_comments, dump_text, DocMap  # noqa: E402
from verify_comments import verify  # noqa: E402
import lib  # noqa: E402

if os.path.exists(WORK):
    shutil.rmtree(WORK)
os.makedirs(WORK)

REPORT = []


def note(*a):
    line = ' '.join(str(x) for x in a)
    REPORT.append(line)
    print(line)


def parents_of_markers(path):
    d = lib.load_doc(path)
    out = []
    for tag in ('commentRangeStart', 'commentRangeEnd'):
        for e in d.iter(lib.q(tag)):
            par = e.getparent()
            out.append((tag, e.get(lib.q('id')), par.tag.split('}')[-1]))
    return out


def run_case(name, body, items, with_rels=True, extra=None, extra_ct=None):
    src = os.path.join(WORK, name + '.src.docx')
    dst = os.path.join(WORK, name + '.out.docx')
    mkc.build(src, body, with_rels=with_rels, extra=extra, extra_ct=extra_ct)
    r = lib.load_doc(src)
    ref_sig, ref_c = lib.sig(r), lib.counts(r)
    try:
        log, n = add_comments(src, dst, items, author='REV', initials='RV')
    except Exception as exc:
        note('--- %s  RAISED %s: %s' % (name, type(exc).__name__, exc))
        note('    leftovers=%s' % (sorted(f for f in os.listdir(WORK) if '.tmp' in f),))
        return src, dst, [], 0
    o = lib.load_doc(dst)
    out_sig, out_c = lib.sig(o), lib.counts(o)
    probs, stats = verify(dst)
    note('--- %s' % name)
    note('    log=%s' % (log,))
    note('    n_written=%d verify_probs=%s stats=%s' % (n, probs, stats))
    note('    content_sig_equal=%s ; counts src=%s dst=%s' % (ref_sig == out_sig, ref_c, out_c))
    note('    marker_parents=%s' % (parents_of_markers(dst),))
    note('    tmp_leftovers=%s' % (sorted(f for f in os.listdir(WORK) if '.tmp' in f),))
    return src, dst, log, n


# ---------- A baseline ----------
run_case('A_plain', '<w:p><w:r><w:t>ALPHA beta GAMMA</w:t></w:r></w:p>',
         [{'anchor': 'beta', 'text': 'c1'}])

# ---------- B cross-paragraph ----------
run_case('B_crosspara',
         '<w:p><w:r><w:t>FIRSTPART</w:t></w:r></w:p>'
         '<w:p><w:r><w:t>SECONDPART</w:t></w:r></w:p>',
         [{'anchor': 'FIRSTPARTSECONDPART', 'text': 'c1'}])

# ---------- C cross table cell ----------
run_case('C_crosscell',
         '<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>'
         '<w:tr><w:tc><w:tcPr/><w:p><w:r><w:t>CELLA</w:t></w:r></w:p></w:tc>'
         '<w:tc><w:tcPr/><w:p><w:r><w:t>CELLB</w:t></w:r></w:p></w:tc></w:tr></w:tbl>',
         [{'anchor': 'CELLACELLB', 'text': 'c1'}])

# ---------- D hyperlink ----------
run_case('D_hyperlink',
         '<w:p><w:r><w:t>PRE </w:t></w:r>'
         '<w:hyperlink r:id="rIdX"><w:r><w:t>LINKTARGET</w:t></w:r></w:hyperlink>'
         '<w:r><w:t> POST</w:t></w:r></w:p>',
         [{'anchor': 'LINKTARGET', 'text': 'c1'}])

# ---------- E w:ins ----------
run_case('E_ins',
         '<w:p><w:r><w:t>PRE </w:t></w:r>'
         '<w:ins w:id="11" w:author="a" w:date="2020-01-01T00:00:00Z">'
         '<w:r><w:t>INSTARGET</w:t></w:r></w:ins>'
         '<w:r><w:t> POST</w:t></w:r></w:p>',
         [{'anchor': 'INSTARGET', 'text': 'c1'}])

# ---------- F w:fldSimple ----------
run_case('F_fldsimple',
         '<w:p><w:r><w:t>PRE </w:t></w:r>'
         '<w:fldSimple w:instr=" REF bookmk \\h "><w:r><w:t>FIELDTARGET</w:t></w:r></w:fldSimple>'
         '<w:r><w:t> POST</w:t></w:r></w:p>',
         [{'anchor': 'FIELDTARGET', 'text': 'c1'}])

# ---------- G inline sdt ----------
run_case('G_sdt',
         '<w:p><w:r><w:t>PRE </w:t></w:r>'
         '<w:sdt><w:sdtPr><w:id w:val="1"/></w:sdtPr>'
         '<w:sdtContent><w:r><w:t>SDTTARGET</w:t></w:r></w:sdtContent></w:sdt>'
         '<w:r><w:t> POST</w:t></w:r></w:p>',
         [{'anchor': 'SDTTARGET', 'text': 'c1'}])

# ---------- H textbox-only anchor ----------
TXTBOX = ('<w:p><w:r><w:t>OUTSIDE</w:t></w:r><w:r><w:drawing><wp:inline>'
          '<a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>'
          '<w:p><w:r><w:t>INSIDEBOX</w:t></w:r></w:p>'
          '</w:txbxContent></wps:txbx></wps:wsp></a:graphicData>'
          '</a:graphic></wp:inline></w:drawing></w:r></w:p>')
run_case('H_textbox', TXTBOX, [{'anchor': 'INSIDEBOX', 'text': 'c1'},
                               {'anchor': 'OUTSIDE', 'text': 'c2'}])

# ---------- I overlapping anchors ----------
run_case('I_overlap', '<w:p><w:r><w:t>ABCDEFGH</w:t></w:r></w:p>',
         [{'anchor': 'BCDE', 'text': 'c1'}, {'anchor': 'DEFG', 'text': 'c2'}])

# ---------- J trailing tab after anchor (bug 2 regression) ----------
run_case('J_trailtab',
         '<w:p><w:r><w:t>LABEL</w:t><w:tab/><w:t>VALUE</w:t><w:tab/></w:r></w:p>',
         [{'anchor': 'VALUE', 'text': 'c1'}])

# ---------- K missing document.xml.rels ----------
run_case('K_norels', '<w:p><w:r><w:t>NORELS</w:t></w:r></w:p>',
         [{'anchor': 'NORELS', 'text': 'c1'}], with_rels=False)

# ---------- L src == dst ----------
same = os.path.join(WORK, 'L_same.docx')
mkc.build(same, '<w:p><w:r><w:t>SAMEPATH</w:t></w:r></w:p>')
before = open(same, 'rb').read()
try:
    add_comments(same, same, [{'anchor': 'SAMEPATH', 'text': 'c'}])
    note('--- L_srcdst  NO EXCEPTION (BAD)')
except Exception as exc:
    note('--- L_srcdst  raised %s: %s' % (type(exc).__name__, exc))
note('    bytes_unchanged=%s' % (open(same, 'rb').read() == before))

# ---------- M empty comments.xml -> verify ----------
empty_c = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:comments xmlns:w="%s"></w:comments>' % lib.W)
run_case('M_emptysrc', '<w:p><w:r><w:t>EMPTYSRC</w:t></w:r></w:p>',
         [{'anchor': 'EMPTYSRC', 'text': 'c1'}],
         extra={'word/comments.xml': empty_c},
         extra_ct='<Override PartName="/word/comments.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')

# ---------- N broken input: markers but no comments.xml ----------
run_case('N_brokeninput',
         '<w:p><w:commentRangeStart w:id="5"/><w:r><w:t>BROKEN</w:t></w:r>'
         '<w:commentRangeEnd w:id="5"/><w:r><w:commentReference w:id="5"/></w:r></w:p>',
         [{'anchor': 'BROKEN', 'text': 'c1'}])

# ---------- O non-contiguous / non-numeric existing ids ----------
existing = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:comments xmlns:w="%s" xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">'
            '<w:comment w:id="7" w:author="old" w:date="2020-01-01T00:00:00Z" w:initials="O">'
            '<w:p><w:r><w:t>old7</w:t></w:r></w:p></w:comment>'
            '<w:comment w:id="abc" w:author="old2" w:date="2020-01-01T00:00:00Z" w:initials="O">'
            '<w:p><w:r><w:t>oldabc</w:t></w:r></w:p></w:comment>'
            '</w:comments>' % lib.W)
run_case('O_weirdids',
         '<w:p><w:commentRangeStart w:id="7"/><w:r><w:t>KEEPME</w:t></w:r>'
         '<w:commentRangeEnd w:id="7"/><w:r><w:commentReference w:id="7"/></w:r></w:p>'
         '<w:p><w:r><w:t>NEWTARGET</w:t></w:r></w:p>',
         [{'anchor': 'NEWTARGET', 'text': 'c1'}],
         extra={'word/comments.xml': existing},
         extra_ct='<Override PartName="/word/comments.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')

print()
print('===== extra marker-placement cases =====')

# ---------- P anchor crossing a hyperlink boundary ----------
run_case('P_cross_hyperlink',
         '<w:p><w:r><w:t>PLAINTAIL</w:t></w:r>'
         '<w:hyperlink r:id="rIdX"><w:r><w:t>LINKHEAD</w:t></w:r></w:hyperlink></w:p>',
         [{'anchor': 'PLAINTAILLINKHEAD', 'text': 'c1'}])

# ---------- Q anchor crossing a tab between two runs ----------
run_case('Q_cross_tab',
         '<w:p><w:r><w:t>AARUN</w:t></w:r><w:r><w:tab/></w:r>'
         '<w:r><w:t>BBRUN</w:t></w:r></w:p>',
         [{'anchor': 'AARUNBBRUN', 'text': 'c1'}])

# ---------- R three anchors same paragraph, adjacent ----------
run_case('R_adjacent',
         '<w:p><w:r><w:t>ONE TWO THREE</w:t></w:r></w:p>',
         [{'anchor': 'ONE', 'text': 'c1'}, {'anchor': 'TWO', 'text': 'c2'},
          {'anchor': 'THREE', 'text': 'c3'}])

# ---------- S anchor = single char at very start / very end ----------
run_case('S_edges',
         '<w:p><w:r><w:t>HEAD middle TAIL</w:t></w:r></w:p>',
         [{'anchor': 'HEAD', 'text': 'c1'}, {'anchor': 'TAIL', 'text': 'c2'}])

print()
print('===== residue scan =====')
allf = sorted(os.listdir(WORK))
note('work dir entries: %s' % allf)
note('tmpdir/ziping residue: %s' % [f for f in allf if f.endswith('.tmpdir') or f.endswith('.ziping')])

print()
print('===== report tail =====')
with open(os.path.join(WORK, 'report_integration.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(REPORT))
print('written', os.path.join(WORK, 'report_integration.txt'))
