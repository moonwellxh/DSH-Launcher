# -*- coding: utf-8 -*-
"""验证 find_info 前缀兜底的"取首个"歧义（合成数据），并检查是否有确定性错配。"""
import os, sys
SK = r'C:\Users\雍远\.agents\skills\fire-check-consolidation'
sys.path.insert(0, os.path.join(SK, 'scripts'))
import f3_register as f3


def mk(pairs):
    keys = [f3.full_key(k) for k, _ in pairs]
    out = {}
    nm = {}
    for (k, idx) in pairs:
        fk = f3.full_key(k)
        out[fk] = {'idx': idx, 'cname': k, 'purpose': '', 'nowUse': '', 'area': '', 'foot': '',
                   'year': '', 'approval': ''}
        nm.setdefault(f3.norm_name(k), []).append(fk)
    out['_norm'] = nm
    return out


print('=== A. 前缀兜底按"首个命中"取胜（顺序敏感）===')
info = mk([('习艺楼', 1), ('习艺楼2号', 2)])
print('  keys=', [k for k in info if k != '_norm'])
print('  find_info("习艺楼") ->', f3.find_info(info, '习艺楼')['cname'])
print('  find_info("习艺楼二期") ->', f3.find_info(info, '习艺楼二期')['cname'], ' (info 里没有此楼，却命中了上面那栋)')
info2 = mk([('习艺楼2号', 2), ('习艺楼', 1)])
print('  键序反转后 find_info("习艺楼") ->', f3.find_info(info2, '习艺楼')['cname'], ' (同一份数据、仅行序不同，结果就变)')

print()
print('=== B. n.startswith(k)：文件名比键长一个"序号-"，但归一化键已存在 ===')
info3 = mk([('劳动改造用房', 3)])
print('  keys=', [k for k in info3 if k != '_norm'])
print('  find_info("3-劳动改造用房") ->', f3.find_info(info3, '3-劳动改造用房'))
# 若 info 里额外有一条归一化后与目标同名（例如"劳动改造用房（东区）"）
info4 = mk([('劳动改造用房（东区）', 21), ('劳动改造用房', 3)])
print('  加入"劳动改造用房（东区）"后 keys=', [k for k in info4 if k != '_norm'])
r4 = f3.find_info(info4, '3-劳动改造用房')
print('  find_info("3-劳动改造用房") ->', (r4 or {}).get('cname'), ' <== 主循环本意是"劳动改造用房"，实际取到东区（错）')
info5 = mk([('劳动改造用房', 3), ('劳动改造用房（东区）', 21)])
r5 = f3.find_info(info5, '3-劳动改造用房')
print('  仅把两行顺序对调 ->', (r5 or {}).get('cname'), ' <== 同一份数据、仅行序不同结果就不同')
print('  该场景下主循环的 alt 兜底能否纠正：alt="劳动改造用房" ->',
      (f3.find_info(info5, '劳动改造用房') or {}).get('cname'), '（不会执行，因为 it 非 None）')

print()
print('=== C. 文件名解析出的残余 index 前缀会不会在真实基础信息里命中别的楼 ===')
base = f3.parse_info(r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\基础信息.xlsx')
for nm in ['3-劳动改造用房', '13-习艺楼', '18-招待所厨房', '15-备勤楼（原小学）', '16-备勤楼（原幼儿园）', '14-机关大楼', '5-监区大门', '4-中转仓库']:
    a = f3.find_info(base, nm)
    b = f3.find_info(base, nm.split('-', 1)[1])
    print('  %-18s 原名命中=%-18r 去序号命中=%-18r 一致=%s' % (
        nm, a['cname'] if a else None, b['cname'] if b else None,
        (a['cname'] if a else None) == (b['cname'] if b else None)))

print()
print('=== D. full_key / norm_name 交互：名字含换行、全角空格、# ===')
for s in ['监区大门\r\n10-1', '监区大门 10-1', '监区大门\n10-1', '1号监舍楼#2', '1号监舍楼＃2',
          '楼A（原甲）', '楼A(原甲)', '楼A（原甲）(', '（只括号）', '#']:
    print('  %-18r full_key=%-18r norm_name=%r' % (s, f3.full_key(s), f3.norm_name(s)))
