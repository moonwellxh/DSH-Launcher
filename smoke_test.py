#!/usr/bin/env python3
"""DSH-Launcher 冒烟测试：验证关键文件、JSON、模板渲染与同步 CLI 结构。"""
import json
import re
from pathlib import Path

ROOT = Path('/workspace')
ASSETS = ROOT / 'dsh-launcher' / 'assets'
TMPL = ASSETS / 'tmpl'
PARTS = TMPL / 'parts'


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def render_tray(mode, var_map):
    mode_repl = load_json(PARTS / f'mode-{mode}.json')
    for k, v in list(mode_repl.items()):
        if isinstance(v, str) and v.startswith('parts/'):
            mode_repl[k] = (PARTS / re.sub(r'^parts/', '', v)).read_text(encoding='utf-8')
    parts = sorted([p for p in PARTS.glob('*.ps1') if not p.name.startswith('70-sync-')])
    sb = []
    for part in parts:
        content = part.read_text(encoding='utf-8')
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


def check_files():
    required = [
        ASSETS / 'setup.ps1',
        ASSETS / 'dsh-sync.ps1',
        PARTS / 'mode-source.json',
        PARTS / 'mode-path.json',
        PARTS / '00-header.ps1',
        PARTS / '10-utils.ps1',
        PARTS / '90-main.ps1',
    ]
    for f in required:
        assert f.exists(), f'缺少文件：{f}'
        print(f'[OK] 文件存在：{f.name}')


def check_json():
    for mode in ['source', 'path']:
        data = load_json(PARTS / f'mode-{mode}.json')
        assert '__MODE_SYNC_CALL__' in data, f'mode-{mode}.json 缺少 __MODE_SYNC_CALL__'
        assert 'dsh-sync.ps1' in data['__MODE_SYNC_CALL__'], f'mode-{mode}.json 未调用 dsh-sync.ps1'
        print(f'[OK] mode-{mode}.json 格式正确且使用 dsh-sync.ps1')


def check_render():
    cases = [
        ('source', {'__NODE_EXE__': 'C:\\fake\\node.exe', '__DSH_ROOT__': 'C:\\fake\\deepseek-harness'}),
        ('path', {'__DSH_CMD__': 'C:\\fake\\dsh.cmd'}),
    ]
    for mode, var_map in cases:
        text = render_tray(mode, var_map)
        found = set(re.findall(r'__[A-Z_][A-Z0-9_]*__', text))
        assert not found, f'{mode} 渲染后残留占位符：{found}'
        assert 'dsh-sync.ps1' in text, f'{mode} 渲染后未包含 dsh-sync.ps1 调用'
        assert 'function Get-SystemProxy' in text, f'{mode} 渲染后缺少 Get-SystemProxy'
        assert 'function Invoke-DshHttp' in text, f'{mode} 渲染后缺少 Invoke-DshHttp'
        print(f'[OK] {mode} 渲染产物完整且无残留占位符')


def check_dsh_sync():
    text = (ASSETS / 'dsh-sync.ps1').read_text(encoding='utf-8')
    required = [
        'function Sync-LauncherScript',
        'function Repair-SyncCache',
        'function Invoke-SyncGit',
        'function Write-SyncStatus',
        'function Get-SystemProxy',
        '[switch]$NoUI',
    ]
    for name in required:
        assert name in text, f'dsh-sync.ps1 缺少：{name}'
    print('[OK] dsh-sync.ps1 包含关键函数与参数')


def check_setup():
    text = (ASSETS / 'setup.ps1').read_text(encoding='utf-8')
    assert "'dsh-sync.ps1'" in text, 'setup.ps1 未复制 dsh-sync.ps1'
    assert 'Render-Tray' in text, 'setup.ps1 缺少 Render-Tray'
    print('[OK] setup.ps1 包含复制 dsh-sync.ps1 和 Render-Tray 逻辑')


def main():
    check_files()
    check_json()
    check_render()
    check_dsh_sync()
    check_setup()
    print('\nAll smoke tests passed.')


if __name__ == '__main__':
    main()
