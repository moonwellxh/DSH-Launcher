# -*- coding: utf-8 -*-
"""A1 前缀兜底改「唯一命中」的回归扫描：old(取首个) vs new(唯一) 对比。

输入：D:\W 下全部记录表目录的文件名 + 所有可用的基础信息/登记表 xlsx
输出：差异清单 + 多命中 n 的潜在风险面
"""
import os
import re
import sys

sys.path.insert(0, r'C:\Users\雍远\.agents\skills\fire-check-consolidation\scripts')
import f3_register as f3

FIRE = r'D:\W\2026.0909 监狱消防查验'


def old_find_info(info, name):
    normmap = info.get('_norm', {}) if isinstance(info, dict) else {}
    n = f3.full_key(name)
    if n in info:
        return info[n]
    cands = normmap.get(f3.norm_name(name), [])
    if len(cands) == 1:
        return info[cands[0]]
    if len(cands) > 1:
        return None
    for k, v in info.items():
        if k.startswith('_'):
            continue
        if n and (k.startswith(n) or n.startswith(k)):
            return v
    return None


def collect_names():
    names = set()
    dirs = []
    for dp, dns, fs in os.walk(FIRE):
        if os.path.basename(dp).startswith('~$'):
            continue
        if '记录表' in os.path.basename(dp) or os.path.basename(dp).endswith('现场记录表'):
            dirs.append(dp)
        for f in fs:
            if f.lower().endswith(('.docx', '.doc')) and not f.startswith('~$'):
                names.add(f)
    # 目录内文件（单独判是否记录表目录）
    for d in dirs:
        for f in os.listdir(d):
            if f.lower().endswith(('.docx', '.doc')) and not f.startswith('~$'):
                names.add(f)
    return sorted(names), sorted(set(dirs))


INFO_CANDS = [
    r'D:\DeepSeekS\My Projcet\.tmp_fire_lianyungang\基础信息.xlsx',
    os.path.join(FIRE, '02_内部标准', '基础信息-格式样例-竹箦.xlsx'),
    os.path.join(FIRE, '2026.0827_竹箦分监狱查验', '05_汇总（记录表与登记表）', '消防隐患联合排查整治行动情况登记表 - 竹箦.xlsx'),
    os.path.join(FIRE, '2026.0828_薛埠分监狱查验', '05_汇总（记录表与登记表）', '消防隐患联合排查整治行动情况登记表 - 薛埠.xlsx'),
    os.path.join(FIRE, '2026.0903_洪泽湖监狱查验', '01_甲方输入', '提供的资料', '调查表.xlsx'),
]

names, dirs = collect_names()
print('记录表目录 %d 个；文件名样本 %d 条' % (len(dirs), len(names)))
for d in dirs:
    print('  DIR', d)

infos = {}
for p in INFO_CANDS:
    if not os.path.exists(p):
        print('INFO 缺失:', p)
        continue
    try:
        infos[p] = f3.parse_info(p)
    except Exception as e:
        print('INFO 解析失败:', p, type(e).__name__, e)
        continue
    ks = [k for k in infos[p] if not k.startswith('_')]
    print('INFO %s -> %d 键' % (os.path.basename(p), len(ks)))
    print('     ', ks)

diffs = 0
for p, info in infos.items():
    print('\n== 对比信息源 %s ==' % os.path.basename(p))
    for fn in names:
        raw = f3.name_from_filename(fn)
        for cand in {raw, re.sub(r'^\d{1,3}[-—–]', '', raw).strip()}:
            if not cand:
                continue
            a = old_find_info(info, cand)
            b = f3.find_info(info, cand)
            if (a is None) != (b is None) or (a and b and (a['cname'] != b['cname'] or a['idx'] != b['idx'])):
                diffs += 1
                print('  DIFF name=%r  old=%s  new=%s' % (cand, a and (a['idx'], a['cname']), b and (b['idx'], b['cname'])))
print('\n差异合计 =', diffs)

# 潜在风险面：对每个 info，列出所有「前缀多命中」的 n（用键的子串枚举）
print('\n== 前缀多命中潜在面（键的子串枚举，len(hits)>1）==')
for p, info in infos.items():
    ks = [k for k in info if not k.startswith('_')]
    risky = []
    for k in ks:
        for i in range(1, len(k) + 1):
            n = k[:i]
            hits = [x for x in ks if x.startswith(n) or n.startswith(x)]
            if len(hits) > 1:
                risky.append((n, tuple(hits)))
    seen = set()
    for n, hits in risky:
        if (n, hits) in seen:
            continue
        seen.add((n, hits))
        # 该 n 是否出现在任何真实文件解析名里
        used = [fn for fn in names if n in f3.name_from_filename(fn)]
        print('  [%s] n=%r hits=%s 真实文件名命中=%d' % (os.path.basename(p), n, hits, len(used)))
