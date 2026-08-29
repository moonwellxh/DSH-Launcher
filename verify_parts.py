#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path('/workspace/dsh-launcher/assets/tmpl')
PARTS_DIR = ROOT / 'parts'

def load_mode(mode):
    path = PARTS_DIR / f'mode-{mode}.json'
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def render_tray(mode, var_map):
    mode_repl = load_mode(mode)
    # 模式值若以 parts/ 开头，则视为片段文件引用并读入内容
    for k, v in list(mode_repl.items()):
        if isinstance(v, str) and v.startswith('parts/'):
            mode_repl[k] = (PARTS_DIR / re.sub(r'^parts/', '', v)).read_text(encoding='utf-8')
    parts = sorted([p for p in PARTS_DIR.glob('*.ps1') if not p.name.startswith('70-sync-')])
    sb = []
    for part in parts:
        content = part.read_text(encoding='utf-8')
        # 多轮模式替换，处理嵌套占位符
        while True:
            prev = content
            for k, v in mode_repl.items():
                if v is not None:
                    content = content.replace(k, str(v))
            if content == prev:
                break
        for k, v in var_map.items():
            if v is not None:
                content = content.replace(k, str(v))
        sb.append(content)
    return ''.join(sb)

def normalize(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [r.rstrip() for r in text.split('\n')]
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines)

def compare(mode, var_map, old_tmpl):
    generated = render_tray(mode, var_map)
    old = old_tmpl.read_text(encoding='utf-8')
    # 旧模板也需要做同样的变量替换，才能与拼装产物公平比较
    for k, v in var_map.items():
        old = old.replace(k, str(v))
    g_norm = normalize(generated)
    o_norm = normalize(old)
    if g_norm == o_norm:
        print(f'[OK] {mode}: generated matches {old_tmpl.name}')
        return True
    else:
        print(f'[FAIL] {mode}: mismatch with {old_tmpl.name}')
        g_lines = g_norm.split('\n')
        o_lines = o_norm.split('\n')
        for i, (a, b) in enumerate(zip(g_lines, o_lines)):
            if a != b:
                print(f'  first diff at line {i+1}:')
                print(f'    gen: {repr(a)}')
                print(f'    old: {repr(b)}')
                start = max(0, i - 3)
                print('  generated context:')
                for j in range(start, min(len(g_lines), i + 5)):
                    print(f'    {j+1}: {repr(g_lines[j])}')
                print('  old context:')
                for j in range(start, min(len(o_lines), i + 5)):
                    print(f'    {j+1}: {repr(o_lines[j])}')
                break
        else:
            print(f'  line counts differ: gen={len(g_lines)} old={len(o_lines)}')
        return False

all_ok = True
all_ok &= compare('source', {'__NODE_EXE__': 'C:\\fake\\node.exe', '__DSH_ROOT__': 'C:\\fake\\deepseek-harness'}, ROOT / 'DSH-tray.ps1.tmpl')
all_ok &= compare('path', {'__DSH_CMD__': 'C:\\fake\\dsh.cmd'}, ROOT / 'DSH-tray.ps1.path.tmpl')

if all_ok:
    print('\nAll checks passed.')
else:
    print('\nSome checks failed.')
    exit(1)
