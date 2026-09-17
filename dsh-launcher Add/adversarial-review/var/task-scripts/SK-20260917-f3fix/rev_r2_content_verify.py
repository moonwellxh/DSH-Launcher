# -*- coding: utf-8 -*-
import json
import re
import zipfile
from xml.dom.minidom import parseString

import openpyxl

D = r'D:\DeepSeekS\My Projcet\.tmp_rev_r2'
NEW = D + r'\e2e_out.xlsx'
cj = json.load(open(D + r'\e2e_computed.json', encoding='utf-8'))
ws = openpyxl.load_workbook(NEW)['Sheet1']
starts = [r for r in range(4, ws.max_row + 1) if ws.cell(r, 2).value]
blocks = []
for row in cj['rows']:
    if not blocks or blocks[-1][0] != row['name']:
        blocks.append([row['name'], []])
    blocks[-1][1].append(row)
print('xlsx 块起始行', starts, ' json 块数', len(blocks))
bad = 0
for (nm, rowsx), st in zip(blocks, starts):
    if ws.cell(st, 2).value != nm:
        print(' 块头不符', nm, ws.cell(st, 2).value)
        bad += 1
    for i, row in enumerate(rowsx):
        r = st + i
        for col, k in ((9, 'no'), (10, 'desc'), (11, 'zy'), (12, 'cat'), (13, 'clause'),
                       (14, 'nature'), (15, 'suggest')):
            if str(ws.cell(r, col).value) != str(row[k]):
                print('  行%d %s: xlsx=%r json=%r' % (r, k, ws.cell(r, col).value, row[k]))
                bad += 1
print('逐行内容不一致项 =', bad, ' 行数 xlsx=%d json=%d' % (ws.max_row - 3, len(cj['rows'])))
z = zipfile.ZipFile(NEW)
sh = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
parseString(sh)
print('sheet1.xml 良构 OK')
refs = re.findall(r'<c r="([A-Z]+\d+)"', sh)
print('c 引用数=%d 唯一=%d' % (len(refs), len(set(refs))))
print('I 列单元格=', re.findall(r'<c r="(I\d+)"', sh))
print('J 列首行=', re.findall(r'<c r="J\d+"[^>]*>', sh)[:2])
