# -*- coding: utf-8 -*-
"""对抗性用例：cell_auto / is_num_text / num_text / parse_info / find_info / cat_of"""
import os, sys, re
SK = r'C:\Users\雍远\.agents\skills\fire-check-consolidation'
sys.path.insert(0, os.path.join(SK, 'scripts'))
import f3_register as f3

def safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        return 'EXC:%s: %s' % (type(e).__name__, e)

print('=== 1. cell_auto / is_num_text / num_text ===')
vals = ['2022', ' 2022 ', '2022.0', '1e3', '1E3', 'nan', 'NaN', 'inf', '-inf', 'Infinity',
        '007', '0.5', '+3', '3.', '.5', '1,000', '１２３', '2022年', '2007年建成，2023年改造',
        '12345678901234567890', '1e400', '-', '--', 'true', 'None', '', '  ', None,
        '0x10', '1_000', '٣', '2022\n']
for v in vals:
    try:
        nt = f3.num_text(v)
    except Exception as e:
        nt = 'EXC:%s' % e
    try:
        im = f3.is_num_text(v)
    except Exception as e:
        im = 'EXC:%s' % e
    try:
        ce = f3.cell_auto('G4', 6, nt)
    except Exception as e:
        ce = 'EXC:%s' % e
    kind = 'NUM' if 't="inlineStr"' not in ce else 'TXT'
    flag = ''
    if im is True and kind == 'NUM' and not re.fullmatch(r'-?\d+(\.\d+)?', str(nt)):
        flag = '  <== 数值单元格但值不是普通十进制'
    if im is False and kind == 'TXT':
        pass
    print('  %-24r num_text=%-24r is_num=%s -> %s%s' % (v, nt, im, kind, flag))

print()
print('=== 2. 检查写出的 <v> 是否是合法 xsd:double ===')
bad = []
for v in vals:
    nt = f3.num_text(v)
    if f3.is_num_text(nt):
        s = str(nt)
        if not re.fullmatch(r'[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?|[+-]?(INF|NaN)', s):
            bad.append((v, s))
print('  合法 xsd:double 之外的数值单元格取值:', bad if bad else '无')

print()
print('=== 3. 端到端：把异常值写进 E/F/G 再让 openpyxl 读 ===')
import zipfile, shutil, tempfile
TMP = r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\_rev_adv'
os.makedirs(TMP, exist_ok=True)
# 手工拼一个最小 sheet1：复用模板
tpl = os.path.join(SK, 'resources', 'templates', '消防隐患联合排查整治行动情况登记表-模板.xlsx')
ent = __import__('fire_common').load_zip(tpl)
sh = ent['xl/worksheets/sheet1.xml'].decode('utf-8')
tests = ['nan', 'inf', '1e3', '  2022  ', '007', '2007年建成，2023年改造']
rows = []
for i, t in enumerate(tests):
    rn = 4 + i
    rows.append('<row r="%d" spans="1:16">%s%s%s</row>' % (
        rn, f3.cell_auto('E%d' % rn, 6, t), f3.cell_auto('F%d' % rn, 6, t), f3.cell_auto('G%d' % rn, 6, t)))
s = re.sub(r'<sheetData>[\s\S]*?</sheetData>', '<sheetData>' + ''.join(rows) + '</sheetData>', sh, count=1)
ent['xl/worksheets/sheet1.xml'] = s.encode('utf-8')
outp = os.path.join(TMP, 'adv.xlsx')
__import__('fire_common').save_zip(outp, ent)
import openpyxl
try:
    wb = openpyxl.load_workbook(outp)
    ws = wb.active
    for i, t in enumerate(tests):
        rn = 4 + i
        print('  输入 %-24r -> openpyxl E=%r G=%r (types %s/%s)' % (
            t, ws.cell(rn, 5).value, ws.cell(rn, 7).value,
            type(ws.cell(rn, 5).value).__name__, type(ws.cell(rn, 7).value).__name__))
except Exception as e:
    print('  openpyxl 读取失败:', type(e).__name__, e)

print()
print('=== 4. parse_info / find_info（真实基础信息表）===')
info = f3.parse_info(r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\基础信息.xlsx')
print('  键:', sorted(info.keys()))
print('  _norm 内容:', {k: v for k, v in info['_norm'].items()})
for nm in ['监区大门', '监区大门10-1', '劳动改造用房', '3-劳动改造用房', '备勤楼（原小学）',
           '备勤楼（原幼儿园）', '习艺楼', '机关大楼', '招待所厨房', '不存在', '', None,
           '_norm', '备勤楼', '监舍楼（1号）', '监舍楼（2号）']:
    try:
        r = f3.find_info(info, nm)
    except Exception as e:
        r = 'EXC:%s: %s' % (type(e).__name__, e)
    rn = r.get('cname') if isinstance(r, dict) else r
    print('  find_info(%-16r) -> %r' % (nm, rn))

print()
print('=== 5. find_info 空/畸形 info ===')
print('  {} ->', safe(f3.find_info, {}, 'x'))
print('  None ->', safe(f3.find_info, None, 'x'))
print('  {"_norm":{}} ->', safe(f3.find_info, {'_norm': {}}, 'x'))
print('  find_info(info,"_norm") ->', safe(f3.find_info, info, '_norm'))
sk = {'a': {'idx': 1, 'cname': 'a'}}
print('  手造 {"a":...} 查 "ab" ->', safe(f3.find_info, sk, 'ab'))
print('  手造 {"abc":...} 查 "ab" ->', safe(f3.find_info, {'abc': {'idx': 1, 'cname': 'abc'}}, 'ab'))
print('  手造 {"" :...} 查 "" ->', safe(f3.find_info, {'': {'idx': 9, 'cname': 'EMPTYKEY'}}, ''))
print('  手造 {"_norm":{}, "":...} 查 "" ->', safe(f3.find_info, {'_norm': {}, '': {'idx': 9, 'cname': 'E2'}}, ''))

print()
print('=== 6. parse_info：A 列非数字 / 空 C ===')
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active
ws.append(['序号', '单位名称', '建筑名称', '原设计用途', '现使用性质', '建筑面积', '占地', '建设时间', '验收'])
ws.append([1, 'X', '楼A', '', '', '', '', '', ''])
ws.append(['2 ', 'X', '楼B', '', '', '', '', '', ''])       # A 带空格
ws.append(['²', 'X', '楼C', '', '', '', '', '', ''])        # A 上标数字（isdigit()=True!）
ws.append(['٣', 'X', '楼D', '', '', '', '', '', ''])        # 阿拉伯-印度数字（isdigit()=True）
ws.append(['3', 'X', '', '', '', '', '', '', ''])           # 空 C
ws.append(['4', 'X', '楼E（原甲）', '', '', '', '', '', ''])
ws.append(['5', 'X', '楼E（原乙）', '', '', '', '', '', ''])
ws.append(['A', 'X', '楼F', '', '', '', '', '', ''])        # A 非数字
p2 = os.path.join(TMP, 'adv_info.xlsx'); wb.save(p2)
try:
    i2 = f3.parse_info(p2)
except Exception as e:
    print('  !! parse_info 崩溃:', type(e).__name__, e)
    # 逐行定位是哪个 A 值挂的
    for probe in ['1', '2 ', '²', '٣', '3', '4', '5', 'A', '２', '三']:
        print('     .isdigit()=%-5s int()=%s' % (probe.isdigit(), safe(int, probe)))
    i2 = None
if i2 is not None:
    print('  键:', sorted(i2.keys()))
    print('  _norm:', {k: v for k, v in i2['_norm'].items()})
    for nm in ['楼E（原甲）', '楼E（原乙）', '楼E', '楼A', '楼B', '楼F']:
        r = safe(f3.find_info, i2, nm)
        print('  find_info(%-10r)-> %r' % (nm, r.get('cname') if isinstance(r, dict) else r))

print()
print('=== 7. name_from_filename 与 find_info 联动：alt 分支 ===')
for fn_name in ['3-劳动改造用房', '13-习艺楼', '5-监区大门', '15-备勤楼（原小学）', '习艺楼']:
    it = f3.find_info(info, fn_name)
    alt = re.sub(r'^\d{1,3}[-—–]', '', fn_name).strip()
    it2 = f3.find_info(info, alt) if (alt and alt != fn_name) else None
    print('  %-16r 直接命中=%r  去序号后 %-12r 命中=%r' % (
        fn_name, it.get('cname') if it else None, alt, it2.get('cname') if it2 else None))

print()
print('=== 8. cat_of 关键词先命中（文档自称遗留）===')
cases = [
    ('消防控制室窗户面对走廊不是防火窗', ''),
    ('设备间数据中心机房档案室等均未设置防火门', ''),
    ('一层处厨房和浴室走道之间有窗，不满足2h防火分隔要求', ''),
    ('北侧有自建工艺房，其上有开窗，和本栋楼距离过近，无法满足防火间距要求', ''),
    ('楼梯高窗上方不需要加救援窗标识', ''),
    ('停车位距建筑窗不足6m', ''),
    ('电缆井未封堵', ''),
    ('防火卷帘损坏', ''),
]
for d, c in cases:
    print('  %-5s %s' % (f3.cat_of(d, c if c else d), d))
