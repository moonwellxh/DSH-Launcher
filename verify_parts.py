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


def check_no_placeholders(text, mode):
    found = set(re.findall(r'__[A-Z_][A-Z0-9_]*__', text))
    if found:
        print(f'[FAIL] {mode}: 残留占位符 {found}')
        return False
    print(f'[OK] {mode}: 无残留占位符，渲染成功')
    return True


def check_references(mode, var_map):
    generated = render_tray(mode, var_map)
    return check_no_placeholders(generated, mode)


all_ok = True
all_ok &= check_references('source', {'__NODE_EXE__': 'C:\\fake\\node.exe', '__DSH_ROOT__': 'C:\\fake\\deepseek-harness'})
all_ok &= check_references('path', {'__DSH_CMD__': 'C:\\fake\\dsh.cmd'})

if all_ok:
    print('\nAll checks passed.')
else:
    print('\nSome checks failed.')
    exit(1)
