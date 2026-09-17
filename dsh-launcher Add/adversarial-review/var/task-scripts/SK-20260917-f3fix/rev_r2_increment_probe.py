# -*- coding: utf-8 -*-
"""增量反例探针：_as_idx / num_text / is_num_text / resolve_name / find_info / A2。"""
import math
import os
import re
import sys

sys.path.insert(0, r'C:\Users\雍远\.agents\skills\fire-check-consolidation\scripts')
sys.path.insert(0, r'C:\Users\雍远\.agents\skills\fire-check-consolidation\.rollback\SK-20260917-f3fix')
import f3_register as f3

print('=== find_info(info=None/非dict) ===')
for bad in (None, {}, [], 'x', 0, {'_norm': {}}):
    try:
        r = f3.find_info(bad, '监舍楼')
        print('  info=%-14r -> %r' % (bad, r))
    except Exception as e:
        print('  info=%-14r -> EXC %s: %s' % (bad, type(e).__name__, e))

print('\n=== _as_idx ===')
for a in ['²', '１２', '3 ', '3', '1\n', '٣', '0', '-1', '', None, 3, '3.0', '⑶', '½']:
    try:
        print('  %-8r isdigit=%s -> %r' % (a, (a.isdigit() if isinstance(a, str) else 'n/a'), f3._as_idx(a)))
    except Exception as e:
        print('  %-8r -> EXC %s: %s' % (a, type(e).__name__, e))

print('\n=== parse_info 对 ²/全角/带空格 A 列的行 ===')
import openpyxl
import tempfile
wb = openpyxl.Workbook()
ws = wb.active
rows = [
    ('²', '上标二行'), ('１２', '全角十二行'), ('3 ', '带空格三行'), ('3', '正常三行'),
    ('3.0', '小数三行'), ('⑶', '带圈三行'), ('5', '重复五行A'), ('5', '重复五行B'),
]
for i, (a, c) in enumerate(rows, 1):
    ws.cell(i, 1, a)
    ws.cell(i, 3, c)
p = os.path.join(tempfile.gettempdir(), '_rev2_info_probe.xlsx')
wb.save(p)
info = f3.parse_info(p)
print('  键:', [k for k in info if not k.startswith('_')])
print('  _norm:', info['_norm'])

print('\n=== num_text / is_num_text ===')
cases = ['1572.60', '9190.24', '2022', '2007年建成，2023年改造', '776.4400000000001', 'nan', 'NaN',
         'inf', '-inf', 'Infinity', '1e400', '-1e400', '12345678901234567890', '1234567890123456',
         '123456789012345', '0.0000000000000001', '1e-20', '.5', '1.', '1,000', '0x10', '1d5',
         ' 2022 ', '', '0', '-0.0', '1e15', '99999999999999999999', '  ', '１５７２']
for s in cases:
    try:
        nt = f3.num_text(s)
    except Exception as e:
        nt = 'EXC %s: %s' % (type(e).__name__, e)
    try:
        isn = f3.is_num_text(s)
    except Exception as e:
        isn = 'EXC %s: %s' % (type(e).__name__, e)
    try:
        cell = f3.cell_auto('X1', 0, nt)
    except Exception as e:
        cell = 'EXC %s: %s' % (type(e).__name__, e)
    print('  %-24r num_text=%-24r is_num=%-5s cell=%s' % (s, nt, isn, cell[:70]))

print('\n=== resolve_name 反例 ===')
infos = {
    'empty{}': {},
    'None': None,
    'norm_only': {'_norm': {}},
    'dup_norm': {'备勤楼（原小学）': {'idx': 15, 'cname': '备勤楼（原小学）'},
                 '备勤楼（原幼儿园）': {'idx': 16, 'cname': '备勤楼（原幼儿园）'},
                 '_norm': {'备勤楼': ['备勤楼（原小学）', '备勤楼（原幼儿园）']}},
    'multi_prefix': {'家属区1#楼': {'idx': 1, 'cname': '家属区1#楼'},
                     '家属区2#楼': {'idx': 2, 'cname': '家属区2#楼'},
                     '_norm': {'家属区1#楼': ['家属区1#楼'], '家属区2#楼': ['家属区2#楼']}},
    'nonstr_keys': {'1': 'notadict', '_norm': {}},
}
names = ['3-劳动改造用房', '备勤楼', '家属区', '1-招待所-2005', '17-家属区', '监舍楼（1号）', '1号监舍楼', '铁门']
for tag, inf in infos.items():
    for nm in names:
        try:
            r = f3.resolve_name(inf, nm)
            print('  [%-12s] %-16r -> (%r, %s)' % (tag, nm, r[0], (r[1] or {}).get('cname') if isinstance(r[1], dict) else r[1]))
        except Exception as e:
            print('  [%-12s] %-16r -> EXC %s: %s' % (tag, nm, type(e).__name__, e))
