#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent four-layer verification for the installed docx-comment-writer skill.

L1 imports, L2 probes, L3 the skill's own checks (which must be able to FAIL),
L4 an independent end-to-end smoke that does NOT reuse the skill's own test
logic: real Word-produced .docx, a synthetic fixture carrying w:tab/w:cr/w:pict,
text-fidelity and structure-fidelity assertions, and the error path.

Usage: python verify_skill.py <skill_dir> <real_fixture.docx> <workdir>
Prints ASCII lines, then one JSON object after a line reading '=== JSON ==='.
Exit 0 only when no BLOCKING check failed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{%s}' % W_NS
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

RESULTS = []


def check(layer, name, ok, detail='', blocking=True):
    ok = bool(ok)
    RESULTS.append({'layer': layer, 'name': name, 'ok': ok,
                    'blocking': bool(blocking), 'detail': str(detail)[:600]})
    tag = 'PASS' if ok else ('FAIL' if blocking else 'GAP ')
    print('[%s] L%d %-56s | %s' % (tag, layer, name, str(detail)[:200]), flush=True)
    return ok


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def para_texts(docx_path):
    import lxml.etree as LE
    with zipfile.ZipFile(docx_path) as z:
        root = LE.fromstring(z.read('word/document.xml'))
    return [''.join(t.text or '' for t in p.iter(W + 't')) for p in root.iter(W + 'p')]


def structure(docx_path):
    """Per paragraph, the ordered tags of every run child that is NOT plain text.
    Comparing this catches a lost OR duplicated tab/br/pict, independent of how
    the engine chose to re-split runs."""
    import lxml.etree as LE
    with zipfile.ZipFile(docx_path) as z:
        root = LE.fromstring(z.read('word/document.xml'))
    out = []
    for p in root.iter(W + 'p'):
        tags = []
        for child in p:
            if child.tag != W + 'r':
                continue
            for c in child:
                if c.tag in (W + 't', W + 'rPr', W + 'commentReference'):
                    continue
                tags.append(c.tag.split('}')[-1])
        out.append(tags)
    return out


def comments_info(docx_path):
    import lxml.etree as LE
    with zipfile.ZipFile(docx_path) as z:
        if 'word/comments.xml' not in z.namelist():
            return []
        root = LE.fromstring(z.read('word/comments.xml'))
    return [{'id': c.get(W + 'id'), 'author': c.get(W + 'author'),
             'date': c.get(W + 'date'), 'initials': c.get(W + 'initials')}
            for c in root.iter(W + 'comment')]


def pick_unique(text, frac, n=12):
    L = len(text)
    for width in (n, 10, 8, 6):
        base = int(L * frac)
        for start in range(base, max(0, base - 500), -3):
            cand = text[start:start + width]
            if len(cand) < width or not cand.strip() or cand.strip() != cand:
                continue
            if text.count(cand) == 1:
                return cand
    return None


def build_raw(path):
    """Minimal valid docx: one run holding text + tab + text + cr + text + pict,
    so the structural (non-text) preservation path is exercised exactly."""
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="%s"><w:body>'
           '<w:p><w:r>'
           '<w:t>\u7532\u65b9</w:t><w:tab/><w:t>\u4e59\u65b9</w:t><w:cr/>'
           '<w:t>\u4e19\u65b9</w:t><w:pict/>'
           '</w:r></w:p>'
           '<w:p><w:r><w:t>\u7b2c\u4e8c\u6761 \u4ed8\u6b3e\u65b9\u5f0f\uff1a'
           '\u5408\u540c\u7b7e\u8ba2\u540e\u652f\u4ed8\u767e\u5206\u4e4b\u4e09\u5341\u3002</w:t>'
           '</w:r></w:p>'
           '</w:body></w:document>') % W_NS
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="%s">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>') % CT_NS
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>') % REL_NS
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="%s"/>') % REL_NS
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)
        z.writestr('word/_rels/document.xml.rels', drels)
    return 'raw-ooxml'


def build_synthetic(path):
    try:
        import docx  # noqa: F401
    except Exception:
        return build_raw(path)
    import docx
    d = docx.Document()
    p = d.add_paragraph()
    r = p.add_run('\u7532\u65b9')
    r.add_tab()
    r.add_text('\u4e59\u65b9\u5e94\u5728\u4e09\u5341\u65e5\u5185\u5b8c\u6210')
    d.add_paragraph('\u7b2c\u4e8c\u6761 \u4ed8\u6b3e\u65b9\u5f0f\uff1a\u5408\u540c\u7b7e\u8ba2'
                    '\u540e\u652f\u4ed8\u767e\u5206\u4e4b\u4e09\u5341\u3002')
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = '\u5de5\u671f'
    t.cell(0, 1).text = '\u4e09\u5341\u4e2a\u5de5\u4f5c\u65e5'
    d.save(path)
    return 'python-docx'


def main():
    skill_dir = os.path.abspath(sys.argv[1])
    fixture_in = os.path.abspath(sys.argv[2])
    workdir = os.path.abspath(sys.argv[3])
    scripts = os.path.join(skill_dir, 'scripts')
    os.makedirs(workdir, exist_ok=True)

    def sha256(path):
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    src = os.path.join(workdir, 'real_source.docx')
    shutil.copy2(fixture_in, src)
    origin_hash, copy_hash = sha256(fixture_in), sha256(src)

    # ---------------- L1 ----------------
    import lxml.etree as letree
    check(1, 'lxml import', True, 'lxml.etree %s' % letree.__version__)
    sys.path.insert(0, scripts)
    import docx_commenter as dc
    inside = os.path.abspath(dc.__file__).lower().startswith(scripts.lower() + os.sep)
    check(1, 'engine imported from the INSTALLED skill copy', inside, dc.__file__)

    # ---------------- L2 ----------------
    text = dc.dump_text(src)
    check(2, 'dump_text(real docx) returns text', len(text) > 50, 'chars=%d' % len(text))
    p = run([sys.executable, os.path.join(scripts, 'docx_commenter.py'), src])
    check(2, 'engine CLI prints body text', p.returncode == 0 and len(p.stdout) > 20,
          'exit=%d stdout=%d' % (p.returncode, len(p.stdout)))
    dm = dc.DocMap(dc.etree.fromstring(zipfile.ZipFile(src).read('word/document.xml')))
    check(2, 'dump_text equals the DocMap anchor space, no U+FFFD',
          dm.text == text and '\ufffd' not in text,
          'replacement_chars=%d locate=%s' % (text.count('\ufffd'), dm.locate(text[80:100]) is not None))

    # ---------------- L3: the skill's own checks, must be falsifiable ----------
    vc = os.path.join(scripts, 'verify_comments.py')
    neg = run([sys.executable, vc, src])
    check(3, 'verify_comments FAILS on a comment-free docx (not a fake green)',
          neg.returncode == 1 and '[FAIL]' in (neg.stdout or ''), 'exit=%d' % neg.returncode)

    st = os.path.join(scripts, 'selftest.py')
    if os.path.isfile(st):
        s = run([sys.executable, st, '--work', os.path.join(workdir, 'selftest')])
        blob = (s.stdout or '') + (s.stderr or '')
        tail = [l for l in blob.splitlines() if '\u81ea\u68c0\u7ed3\u679c' in l or 'PASS' in l or 'FAIL' in l or 'SKIP' in l]
        n_fail = blob.count('[FAIL]')
        n_pass = blob.count('[PASS]')
        n_skip = blob.count('[SKIP]')
        check(3, 'bundled selftest.py runs and reports no failures',
              s.returncode == 0 and n_fail == 0, 'exit=%d pass=%d fail=%d skip=%d' % (s.returncode, n_pass, n_fail, n_skip))
        check(3, 'bundled selftest.py actually executed checks (not vacuous)',
              n_pass >= 6, 'pass=%d' % n_pass)
    else:
        check(3, 'bundled selftest.py present', False, 'missing %s' % st)

    # ---------------- L4: independent end-to-end ----------------
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    picks = []
    for frac in (0.3, 0.55, 0.75, 0.2, 0.45, 0.65, 0.85, 0.1):
        if len(picks) >= 2:
            break
        a = pick_unique(text, frac)
        if not a:
            continue
        probe_dst = os.path.join(workdir, 'probe_%d.docx' % len(picks))
        log, cnt = dc.add_comments(src, probe_dst, [{'anchor': a, 'occurrence': 0,
                                                     'text': '\u5192\u70df\u6279\u6ce8'}],
                                   author='\u5192\u70df\u6d4b\u8bd5', initials='SM')
        if cnt == 1 and all(x[0] == 'OK' for x in log):
            picks.append(a)
    check(4, 'auto-picked >=2 unique anchors the engine resolves', len(picks) >= 2,
          'picked=%d' % len(picks))

    dst = os.path.join(workdir, 'real_annotated.docx')
    items = [{'anchor': a, 'occurrence': 0, 'text': '\u5192\u70df\u6279\u6ce8 %d' % (i + 1)}
             for i, a in enumerate(picks[:2])]
    log, cnt = dc.add_comments(src, dst, items, author='\u5192\u70df\u6d4b\u8bd5', initials='SM')
    check(4, 'real docx: MISS == 0', not [x for x in log if x[0] != 'OK'],
          'miss=%d' % len([x for x in log if x[0] != 'OK']))
    check(4, 'real docx: comment count matches request', cnt == len(items),
          'written=%d requested=%d' % (cnt, len(items)))
    check(4, 'source never modified: user original and copy byte-identical',
          sha256(fixture_in) == origin_hash and sha256(src) == copy_hash,
          'sha256=%s' % copy_hash[:16])
    check(4, 'real docx: paragraph text identical to source',
          para_texts(src) == para_texts(dst),
          'paras=%d' % len(para_texts(src)))
    check(4, 'real docx: global plain text identical (no loss, no duplication)',
          dc.dump_text(src) == dc.dump_text(dst), 'chars=%d' % len(text))
    check(4, 'real docx: non-text run structure identical',
          structure(src) == structure(dst),
          'groups=%d' % len(structure(src)))
    v = run([sys.executable, vc, dst])
    check(4, 'real docx: structural self-check reports PASS',
          v.returncode == 0 and '[PASS]' in (v.stdout or ''), 'exit=%d' % v.returncode)
    ci = comments_info(dst)
    check(4, 'real docx: timestamps are real runtime UTC (not a hardcoded fake date)',
          bool(ci) and all((c['date'] or '').startswith(today) for c in ci),
          'dates=%s today=%s' % ([c['date'] for c in ci][:2], today))
    check(4, 'real docx: author/initials carried through',
          bool(ci) and all(c['author'] == '\u5192\u70df\u6d4b\u8bd5' and c['initials'] == 'SM' for c in ci),
          'n=%d' % len(ci))

    # ---- synthetic fixtures: structural children must survive a split ----
    for label, builder in (('raw-ooxml', build_raw), ('python-docx', build_synthetic)):
        syn = os.path.join(workdir, 'syn_%s.docx' % label)
        how = builder(syn)
        syn_dst = os.path.join(workdir, 'syn_%s_annotated.docx' % label)
        slog, scnt = dc.add_comments(syn, syn_dst, [{'anchor': '\u7532\u65b9', 'occurrence': 0,
                                                     'text': '\u7ed3\u6784\u4fdd\u771f\u6d4b\u8bd5'}],
                                     author='\u5192\u70df\u6d4b\u8bd5', initials='SM')
        check(4, '%s: comment written on the structural run (split exercised)' % label,
              scnt == 1 and all(x[0] == 'OK' for x in slog), 'builder=%s written=%d' % (how, scnt))
        check(4, '%s: paragraph text identical (no loss, no duplication)' % label,
              para_texts(syn) == para_texts(syn_dst))
        check(4, '%s: non-text structure identical' % label,
              structure(syn) == structure(syn_dst),
              'src=%s dst=%s' % (structure(syn)[0], structure(syn_dst)[0]))
        sv = run([sys.executable, vc, syn_dst])
        check(4, '%s: structural self-check PASS' % label, sv.returncode == 0, 'exit=%d' % sv.returncode)

    # w:tab specific regression (the defect that was silently corrupting text)
    syn = os.path.join(workdir, 'syn_raw-ooxml.docx')
    syn_dst = os.path.join(workdir, 'syn_raw-ooxml_annotated.docx')
    if os.path.isfile(syn_dst):
        for tag in ('tab', 'cr'):
            a = zipfile.ZipFile(syn).read('word/document.xml').count(('<w:%s' % tag).encode())
            b = zipfile.ZipFile(syn_dst).read('word/document.xml').count(('<w:%s' % tag).encode())
            check(4, 'regression: <w:%s/> count preserved across the split' % tag, a == b,
                  'src=%d dst=%d' % (a, b))

    # ---- error path (reported honestly; not silently passed) ----
    e1 = run([sys.executable, os.path.join(scripts, 'docx_commenter.py'),
              os.path.join(workdir, '__missing__.docx')])
    blob = (e1.stdout or '') + (e1.stderr or '')
    friendly = e1.returncode != 0 and 'Traceback' not in blob
    check(4, 'error path: missing file gives a friendly error (no traceback)',
          friendly, 'exit=%d traceback=%s' % (e1.returncode, 'Traceback' in blob),
          blocking=False)
    e2 = run([sys.executable, os.path.join(scripts, 'docx_commenter.py')])
    check(4, 'error path: no arguments does not crash',
          e2.returncode == 0 and 'Traceback' not in ((e2.stdout or '') + (e2.stderr or '')),
          'exit=%d' % e2.returncode, blocking=False)

    blocking_failed = [r for r in RESULTS if r['blocking'] and not r['ok']]
    gaps = [r for r in RESULTS if not r['blocking'] and not r['ok']]
    print('=== JSON ===')
    print(json.dumps({'total': len(RESULTS), 'blockingFailed': len(blocking_failed),
                      'gaps': len(gaps), 'results': RESULTS}, ensure_ascii=True))
    return 1 if blocking_failed else 0


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('usage: python verify_skill.py <skill_dir> <real_fixture.docx> <workdir>')
        sys.exit(2)
    sys.exit(main())
