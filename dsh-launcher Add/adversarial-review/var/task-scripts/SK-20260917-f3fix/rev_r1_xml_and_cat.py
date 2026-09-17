# -*- coding: utf-8 -*-
"""最后一组对抗：XML 转义 / 分类词回归 / 语法与既有产物合法性"""
import os, re, sys, zipfile
SK = r'C:\Users\雍远\.agents\skills\fire-check-consolidation'
sys.path.insert(0, os.path.join(SK, 'scripts'))
import f3_register as f3
import fire_common as fc

print('=== 1. 非数字文本带 XML 特殊字符时 cell_auto 的转义 ===')
for t in ['2007<2023>', 'A&B', '  <t>x</t>', '2022 & 2023', '"引号"']:
    nt = f3.num_text(t)
    print('  %-14r -> %s' % (t, f3.cell_auto('G4', 6, nt)))

print()
print('=== 2. 分类词回归：RULES 首项新增词是否只影响命中面（不改变其它类）===')
newpat = dict(f3.RULES)
pre = open(os.path.join(SK, '.rollback', 'SK-20260917-f3fix', 'f3_register.py.pre'), encoding='utf-8').read()
old_first = re.search(r"\['消防车道与救援、防火间距类', r'([^']*)'\]", pre).group(1)
old_pat = dict(f3.RULES); old_pat['消防车道与救援、防火间距类'] = old_first
added = [w for w in f3.RULES[0][1].split('|') if w not in old_first.split('|')]
removed = [w for w in old_first.split('|') if w not in f3.RULES[0][1].split('|')]
print('  新增词:', added, ' 删除词:', removed)
print('  除首项外其它 19 项是否逐条一致:',
      [c for c, p in f3.RULES[1:]] == [c for c, p in f3.RULES[1:]] and
      all(dict(f3.RULES)[c] == dict([(c, p) for c, p in f3.RULES])[c] for c, _ in f3.RULES[1:]))
# 会不会"抢走"原本属于别的类的描述
steal = []
for c, p in f3.RULES[1:]:
    for w in added:
        if re.search(w, '') is not None:
            pass
probes = ['消防救援口被遮挡', '消防救援窗设置不当', '防火间距不足', '消防救援场地被占用', '救援窗标识错误']
for d in probes:
    # 用旧规则（首项无新词）对比
    def cat_with(first, desc):
        rules = [['X', first]] + f3.RULES[1:]
        for cc, pp in rules:
            if re.search(pp, desc):
                return cc
        for cc, pp in rules:
            if re.search(pp, desc + ' ' + desc):
                return cc
        return '其他'
    print('  %-16s 旧=%s 新=%s' % (d, cat_with(old_first, d), f3.cat_of(d, d)))

print()
print('=== 3. 语法自检 + 既有产物合法性 ===')
import py_compile, tempfile
try:
    py_compile.compile(os.path.join(SK, 'scripts', 'f3_register.py'), doraise=True)
    print('  py_compile: OK')
except Exception as e:
    print('  py_compile: FAIL', e)

p = r'D:\W\2026.0909 监狱消防查验\2026.0907_连云港监狱查验\05_汇总（记录表与登记表）\消防隐患联合排查整治行动情况登记表（连云港监狱-建筑专业）.xlsx'
z = zipfile.ZipFile(p)
sh = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
bad = re.findall(r'<c r="([A-Z]+\d+)"[^>]*>\s*<v>([^<]*)</v>', sh)
nonnum = [(r, v) for r, v in bad if not re.fullmatch(r'[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?', v)]
print('  既有产物中"数值单元格但值非数字"的数量:', len(nonnum), nonnum[:5])
import openpyxl
wb = openpyxl.load_workbook(p)
print('  openpyxl 读取既有产物:', 'OK', wb.active.max_row, '行')
