# -*- coding: utf-8 -*-
import os, sys, json
sys.path.insert(0, r'C:\Users\雍远\.agents\skills\fire-check-consolidation\scripts')
import f3_register as f3

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

roots = [r'D:\W\2026.0909 监狱消防查验']
infos = []
dirs = []
for dp, dns, fs in os.walk(r'D:\W\2026.0909 监狱消防查验'):
    for f in fs:
        if f.lower().endswith('.xlsx') and ('基础信息' in f or '建筑基础' in f):
            infos.append(os.path.join(dp, f))
    for dn in dns:
        if '记录表' in dn:
            dirs.append(os.path.join(dp, dn))
print('INFO FILES:'); [print(' ', p) for p in infos]
print('RECORD DIRS:'); [print(' ', p) for p in dirs]
