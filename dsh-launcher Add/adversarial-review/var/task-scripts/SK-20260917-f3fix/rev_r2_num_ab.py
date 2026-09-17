# -*- coding: utf-8 -*-
"""num_text / is_num_text / cell_auto 基线(pre-s1s2) vs 当前 的全量 A/B。"""
import sys

sys.path.insert(0, r'C:\Users\雍远\.agents\skills\fire-check-consolidation\scripts')
sys.path.insert(0, r'D:\DeepSeekS\My Projcet\.tmp_rev_r2')
import f3_base as base
import f3_register as cur

CASES = ['1572.60', '9190.24', '2022', '3020', '776.4400000000001', '7549.85', '0.751',
         '2007', '2000', '+2022', ' 2022 ', '１５７２', 'nan', 'NaN', 'inf', '-inf', 'Infinity',
         '-Infinity', '1e400', '-1e400', '12345678901234567890', '99999999999999999999',
         '1234567890123456', '123456789012345', '1000000000000000', '1e15', '1e16', '1.5e16',
         '1e-20', '0.0000000000000001', '  ', '', 'abc', '1,000', '0x10', '-0.0', '.5',
         '2007年建成，2023年改造', '2000年以前（具体年代不详）', '2018.0', '100.00']

print('%-26s %-22s %-22s %-9s %-9s %s' % ('输入', 'base.num_text', 'cur.num_text', 'base.num', 'cur.num', '差异'))
ndiff = cdiff = 0
for s in CASES:
    try:
        bn, cn = base.num_text(s), cur.num_text(s)
    except Exception as e:
        bn = cn = 'EXC %s' % e
    try:
        bi, ci = base.is_num_text(s), cur.is_num_text(s)
    except Exception as e:
        bi = ci = 'EXC %s' % e
    tag = []
    if bn != cn:
        tag.append('num_text')
        ndiff += 1
    if bi != ci:
        tag.append('is_num')
        cdiff += 1
        # 同时看归一化后的判定
        tag.append('(norm: base=%s cur=%s)' % (base.is_num_text(bn) if isinstance(bn, str) else '?',
                                               cur.is_num_text(cn) if isinstance(cn, str) else '?'))
    print('%-26r %-22r %-22r %-9s %-9s %s' % (s, bn, cn, bi, ci, ','.join(tag)))
print('\nnum_text 差异 %d 例；is_num_text 差异 %d 例' % (ndiff, cdiff))

print('\n=== 端到端写入形态差异（num_text -> cell_auto）===')
for s in CASES:
    try:
        b = base.cell_auto('X1', 0, base.num_text(s))
    except Exception as e:
        b = 'EXC %s' % e
    try:
        c = cur.cell_auto('X1', 0, cur.num_text(s))
    except Exception as e:
        c = 'EXC %s' % e
    b_num = '<v>' in b and 'inlineStr' not in b
    c_num = '<v>' in c and 'inlineStr' not in c
    if b_num != c_num or b != c:
        print('  DIFF %-24r base=%s  cur=%s' % (s, b[:60], c[:60]))
print('（只列差异）')
