# -*- coding: utf-8 -*-
"""端到端产物校验：openpyxl 合法性 + 单元格类型 + 与交付件逐格比对。"""
import json
import os
import re
import sys
import zipfile

import openpyxl

NEW = r'D:\DeepSeekS\My Projcet\.tmp_rev_r2\e2e_out.xlsx'
DELIV = r'D:\W\2026.0909 监狱消防查验\2026.0907_连云港监狱查验\05_汇总（记录表与登记表）\消防隐患联合排查整治行动情况登记表（连云港监狱-建筑专业）.xlsx'
COMP = r'D:\DeepSeekS\My Projcet\.tmp_rev_r2\e2e_computed.json'

for tag, p in (('新产物', NEW), ('交付件', DELIV)):
    print('== %s ==' % tag, p)
    try:
        wb = openpyxl.load_workbook(p)          # 严格模式（不传 data_only/read_only）
        ws = wb['Sheet1']
        print('  openpyxl 读通 dims=%s max_row=%d max_col=%d' % (ws.dimensions, ws.max_row, ws.max_column))
    except Exception as e:
        print('  openpyxl 拒读: %s: %s' % (type(e).__name__, e))
        continue
    z = zipfile.ZipFile(p)
    sh = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    # 所有数值单元格 <v> 必须能 float()，且不能含 nan/inf
    bad = []
    for m in re.finditer(r'<c r="([A-Z]+\d+)"([^>]*)>(?:<v>([^<]*)</v>)?', sh):
        ref, attrs, v = m.group(1), m.group(2), m.group(3)
        if v is None:
            continue
        if 'inlineStr' in attrs:
            continue
        try:
            f = float(v)
        except Exception:
            bad.append((ref, v, 'not-float'))
            continue
        if f != f or f in (float('inf'), float('-inf')):
            bad.append((ref, v, 'nonfinite'))
    print('  非法数值单元格 = %d %s' % (len(bad), bad[:5]))
    # E/F/G 单元格类型
    types = {}
    for r in range(4, ws.max_row + 1):
        for col in ('E', 'F', 'G'):
            c = ws['%s%d' % (col, r)]
            types.setdefault(col, set()).add(type(c.value).__name__)
    print('  E/F/G 值类型分布:', types)
    # 抖动：L/N 下拉 sqref
    dv = re.search(r'<dataValidations[\s\S]*?</dataValidations>', sh)
    print('  dataValidations sqref:', re.findall(r'sqref="([^"]+)"', dv.group(0)) if dv else None)
    print('  mergeCells:', re.search(r'<mergeCells count="(\d+)"', sh).group(1))
    print('  dimension:', re.search(r'<dimension ref="([^"]+)"', sh).group(1))
    print('  pageSetup:', re.search(r'<pageSetup[^>]*/>', sh).group(0))

# 交付件 vs 新产物 逐格比对
def grid(p):
    wb = openpyxl.load_workbook(p)
    ws = wb['Sheet1']
    g = {}
    for r in range(1, ws.max_row + 1):
        for c in range(1, 18):
            v = ws.cell(r, c).value
            if v is not None and str(v) != '':
                g['%s%d' % (openpyxl.utils.get_column_letter(c), r)] = str(v)
    return g

a, b = grid(NEW), grid(DELIV)
only_a = {k: v for k, v in a.items() if b.get(k) != v}
only_b = {k: v for k, v in b.items() if a.get(k) != v}
print('\n== 新产物 vs 交付件 逐格比对 ==')
print('  新产物非空格 %d，交付件非空格 %d' % (len(a), len(b)))
print('  不一致（在新产物）:', len(only_a))
for k in sorted(only_a, key=lambda x: (x[-1], x))[:20]:
    print('    %s 新=%r 交付=%r' % (k, only_a[k], b.get(k)))
print('  不一致（在交付件）:', len(only_b))
for k in sorted(only_b, key=lambda x: (x[-1], x))[:20]:
    print('    %s 交付=%r 新=%r' % (k, only_b[k], a.get(k)))

# 与 computed JSON 比对
if os.path.exists(COMP):
    cj = json.load(open(COMP, encoding='utf-8'))
    wb = openpyxl.load_workbook(NEW)
    ws = wb['Sheet1']
    mism = 0
    for i, row in enumerate(cj['rows']):
        r = 4 + i
        got = {'name': ws.cell(r, 2).value, 'no': ws.cell(r, 9).value, 'desc': ws.cell(r, 10).value,
               'zy': ws.cell(r, 11).value, 'cat': ws.cell(r, 12).value, 'clause': ws.cell(r, 13).value,
               'nature': ws.cell(r, 14).value, 'suggest': ws.cell(r, 15).value,
               'D': ws.cell(r, 4).value, 'area': ws.cell(r, 5).value, 'foot': ws.cell(r, 6).value,
               'year': ws.cell(r, 7).value}
        for k in ('name', 'no', 'desc', 'zy', 'cat', 'clause', 'nature', 'suggest', 'D', 'area', 'foot', 'year'):
            exp = row[k]
            g = got[k]
            if k in ('no',):
                exp = int(exp)
            if k in ('area', 'foot', 'year') and exp not in ('', None):
                try:
                    if float(g) == float(exp):
                        continue
                except Exception:
                    pass
            if str(g) != str(exp):
                mism += 1
                print('  行%d %s: 表=%r json=%r' % (r, k, g, exp))
    print('\n== 与 --computed-json 比对 == 不一致 %d 项（共 %d 行）' % (mism, len(cj['rows'])))
    # 打印楼块头
    print('\n楼块（B 列非空行）:')
    for r in range(4, ws.max_row + 1):
        if ws.cell(r, 2).value:
            print('  行%-3d B=%-28s C=%-10s D=%-12s E=%-10s F=%-8s G=%-16s H=%s' % (
                r, str(ws.cell(r, 2).value)[:28], str(ws.cell(r, 3).value)[:10], str(ws.cell(r, 4).value)[:12],
                str(ws.cell(r, 5).value)[:10], str(ws.cell(r, 6).value)[:8], str(ws.cell(r, 7).value)[:16],
                str(ws.cell(r, 8).value or '')[:18]))
