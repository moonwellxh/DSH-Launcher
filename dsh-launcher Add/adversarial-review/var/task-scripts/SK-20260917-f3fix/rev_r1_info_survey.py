# -*- coding: utf-8 -*-
import openpyxl, glob, os
pats = {r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\基础信息.xlsx'}
for pat in (r'D:\W\2026.0909 监狱消防查验\**\*基础信息*.xlsx', r'D:\W\2026.0909 监狱消防查验\**\*建筑基础*.xlsx'):
    pats |= set(glob.glob(pat, recursive=True))
print('找到基础信息表:', len(pats))
for p in sorted(pats):
    print('==', p)
    try:
        wb = openpyxl.load_workbook(p, data_only=True)
    except Exception as e:
        print('   读取失败', e); continue
    for ws in wb.worksheets:
        print('  sheet', ws.title, ws.max_row, ws.max_column)
        for r in ws.iter_rows(min_row=2, values_only=True):
            if any(x is not None and str(x).strip() != '' for x in r):
                print('   ', '|'.join(('' if x is None else ('%r' % x)) for x in r))
