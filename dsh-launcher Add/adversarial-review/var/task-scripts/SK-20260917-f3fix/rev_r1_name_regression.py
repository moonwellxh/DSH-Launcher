# -*- coding: utf-8 -*-
"""独立回归复算：旧解析器从 .rollback/.../f3_register.py.pre 的 AST 提取，不复用 tests/ 里的函数。"""
import ast, os, re, sys, io

SK = r'C:\Users\雍远\.agents\skills\fire-check-consolidation'
sys.path.insert(0, os.path.join(SK, 'scripts'))
import f3_register as f3

# --- 从改前原文提取内联在 main() 里的旧 4 行解析逻辑，按 AST 原样重建 ---
pre = open(os.path.join(SK, '.rollback', 'SK-20260917-f3fix', 'f3_register.py.pre'), encoding='utf-8').read()
tree = ast.parse(pre)
cand = [n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == 'name' and '现场记录表' in ast.unparse(n.value)]
assert len(cand) == 1, '提取到 %d 条候选' % len(cand)
start = cand[0].lineno
pre_lines = pre.splitlines()
src_lines = pre_lines[start - 1:start + 3]
print('=== 从基线文件第 %d~%d 行原样提取的旧解析器 ===' % (start, start + 3))
print('\n'.join(src_lines))
old_src = 'def old_name(fn):\n' + '\n'.join('    ' + l.strip() for l in src_lines) + '\n    return name\n'
ns = {'re': re}
exec(old_src, ns)
old_name = ns['old_name']

EX_DIRS = [
    os.path.join(SK, 'resources', 'examples', '常州监狱巡查汇总'),
    r'D:\W\2026.0909 监狱消防查验\02_内部标准\范例-常州监狱巡查汇总（用于学习问题对应的条文和整改意见）',
    r'D:\W\2026.0909 监狱消防查验\2026.0903_洪泽湖监狱查验\03_原始记录\初始表格~勿删',
    r'D:\W\2026.0909 监狱消防查验\2026.0903_洪泽湖监狱查验\04_记录表（分专业）\01 建筑专业',
]
files = []
for d in EX_DIRS:
    for dp, _, fs in os.walk(d):
        for f in fs:
            if f.lower().endswith(('.docx', '.doc')) and not f.startswith('~$'):
                files.append(f)
uniq = sorted(set(files))
print('原始命中 %d，去重 %d' % (len(files), len(uniq)))

out = io.StringIO()
diff = 0
import collections
dups = collections.Counter(files)
for fn in uniq:
    a, b = old_name(fn), f3.name_from_filename(fn)
    flag = 'SAME' if a == b else 'DIFF'
    if a != b:
        diff += 1
    out.write('%s\tOLD=%r\tNEW=%r\t%s\n' % (flag, a, b, fn))
out.write('\n差异合计=%d / %d\n' % (diff, len(uniq)))
out.write('重名文件(跨目录同名)=%d\n' % sum(1 for k, v in dups.items() if v > 1))

# 统计命名形状，找出解析器"没吃到"的部分
print('\n--- 解析结果形状抽样统计 ---')
pat = collections.Counter()
for fn in uniq:
    n = f3.name_from_filename(fn)
    if not n:
        pat['EMPTY'] += 1
    elif re.match(r'^\d{1,3}[-—–]', n):
        pat['LEADING_DIGIT_DASH'] += 1
    elif '（' in n or '(' in n:
        pat['INNER_PAREN_KEPT'] += 1
    elif re.search(r'[-—–]\d', n):
        pat['MID_DIGIT_DASH'] += 1
    else:
        pat['PLAIN'] += 1
print(dict(pat))

# 关键：既有命名里有没有"新式"文件（带 专业意见 后缀 / 非"现场记录表（"前缀）？
print('\n--- 既有 199 条中命中新式特征的文件 ---')
for fn in uniq:
    if re.search(r'(建筑|给排水|电气|暖通)\s*意见\s*\.docx$', fn) or not re.search(r'现场记录表\s*[（(]', fn):
        print('  %r -> %r' % (fn, f3.name_from_filename(fn)))

# 全角/半角括号、.doc、空格、楼名含专业词 等对抗用例
print('\n--- 对抗用例 ---')
adv = [
    '',
    None,
    '消防安全隐患问题排查-现场记录表（连云港监狱-建筑工程）建筑意见.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-3-劳动改造用房） 建筑意见.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-3-劳动改造用房）-建筑意见.docx',
    '消防安全隐患问题排查-现场记录表(连云港监狱-3-劳动改造用房)建筑意见.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-建筑意见楼）.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-3-配电房(电气)）电气意见.doc',
    '消防安全隐患问题排查-现场记录表（连云港监狱-2007年建成）建筑意见.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-3-1）.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-3-劳动改造用房）建筑意见（终）.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-3-劳动改造用房）建筑意见书.docx',
    '某监狱-3-楼.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-习艺楼）建筑意见.docx',
    '消防安全隐患问题排查-现场记录表（连云港监狱-1号厂房-2-1）建筑意见.docx',
]
for fn in adv:
    try:
        r = repr(f3.name_from_filename(fn))
    except Exception as e:
        r = 'EXC %s: %s' % (type(e).__name__, e)
    print('  %-70r -> %s' % (fn, r))

open(r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\_rev_names.txt', 'w', encoding='utf-8').write(out.getvalue())
print('\n明细写入 _rev_names.txt')
