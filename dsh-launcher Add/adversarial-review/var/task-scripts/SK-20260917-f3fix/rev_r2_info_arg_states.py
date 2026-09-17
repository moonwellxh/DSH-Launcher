# -*- coding: utf-8 -*-
"""A2 探针：--info 的 5 种输入形态（不存在/目录/空工作簿/相对路径错 cwd/不传）。"""
import json
import os
import subprocess
import sys
import tempfile

import openpyxl

PY = r'C:\Users\雍远\AppData\Local\Programs\Python\Python312\python.exe'
F3 = r'C:\Users\雍远\.agents\skills\fire-check-consolidation\scripts\f3_register.py'
CP = r'D:\DeepSeekS\My Projcet\.tmp_rev_r2\corpus_same_names'
TPL = r'D:\W\2026.0909 监狱消防查验\02_内部标准\消防隐患联合排查整治行动情况登记表-模板.xlsx'
OUTD = r'D:\DeepSeekS\My Projcet\.tmp_rev_r2'
INFO_OK = r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\基础信息.xlsx'

td = tempfile.mkdtemp(prefix='_rev2_a2_')
empty = os.path.join(td, 'empty.xlsx')
wb = openpyxl.Workbook()
wb.save(empty)
print('空工作簿:', empty, os.path.getsize(empty))

# 有表头无数据
hdr = os.path.join(td, 'hdr_only.xlsx')
wb = openpyxl.Workbook()
ws = wb.active
for i, t in enumerate(['序号', 'B', '建筑名称', '用途', '现状', '面积', '占地', '年份', '手续'], 1):
    ws.cell(1, i, t)
wb.save(hdr)


def run(tag, args, cwd=None):
    cmd = [PY, '-X', 'utf8', F3, '--prison', '连云港', '--unit', '连云港监狱',
           '--docdir', CP, '--template', TPL, '--no-lo', '-o',
           os.path.join(OUTD, 'a2_%s.xlsx' % tag)] + args
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       cwd=cwd, timeout=600)
    out = (r.stdout or '').strip().replace('\n', ' | ')
    err = (r.stderr or '').strip().splitlines()
    print('\n--- %s ---' % tag)
    print('  rc=%s' % r.returncode)
    print('  stdout: %s' % out[:200])
    print('  stderr tail: %s' % (err[-1][:200] if err else '(空)'))
    p = os.path.join(OUTD, 'a2_%s.xlsx' % tag)
    if os.path.exists(p):
        w = openpyxl.load_workbook(p)['Sheet1']
        filled = sum(1 for r in range(4, w.max_row + 1) if w.cell(r, 3).value)
        print('  产物存在；B..H 有值的块 = %d' % filled)


run('nonexist', ['--info', os.path.join(td, 'no_such_file.xlsx')])
run('isdir', ['--info', td])
run('emptywb', ['--info', empty])
run('hdronly', ['--info', hdr])
run('noinfo', [])
run('relpath_badcwd', ['--info', '基础信息.xlsx'], cwd=r'C:\Windows')
run('relpath_okcwd', ['--info', '基础信息.xlsx'], cwd=r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang')
run('okabs', ['--info', INFO_OK])
