#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L0 确定性检查：审查脚本 registry 自洽（R1/R3 保障）。
作用：校验 审查脚本/registry.json 每条登记可达（code_path 存在、run 入口可定位、条目字段齐全）。
输入：registry.json 所在目录（缺省 = 本脚本同目录）。
输出：每条目一行 OK/MISS + 汇总一行可 grep。纯计算，无结论断言。
复跑：python l0_registry_check.py [审查脚本目录]；依赖：仅标准库。"""
import json
import re
import sys
from pathlib import Path

REQUIRED = ("name", "ns", "code_path", "entrypoint", "run", "purpose", "hash")   # R3 定稿含 hash（步骤7 落码）
DOCSTRING_LINES = ("作用", "输入", "输出", "复跑")   # R1 说明模板四行（docstring 首四行内出现）


def main():
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    reg = base / "registry.json"
    if not reg.exists():
        print("REGISTRY_MISSING=" + str(reg))
        return 1
    data = json.loads(reg.read_text(encoding="utf-8"))
    scripts = data.get("scripts", [])
    # code_path 解析：R3 定稿推荐绝对路径（直接命中）；相对路径仅作历史/兼容回退，
    # 回退候选 = base 逐级上溯（base.parent/base.parents[1]/base），首个命中即用。
    root_cands = [base.parent, base.parents[1], base]
    bad = 0
    for e in scripts:
        miss = [k for k in REQUIRED if k not in e]
        if miss:
            print(f"MISS {e.get('name', '?')}: missing_fields={miss}")
            bad += 1
            continue
        p = None
        cp = Path(e["code_path"])
        if cp.is_absolute():
            p = cp
        else:
            for r in root_cands:
                cand = r / e["code_path"]
                if cand.exists():
                    p = cand
                    break
        if p is None:
            print(f"MISS {e['name']}: file_not_found(相对各候选根) code_path={e['code_path']}")
            bad += 1
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        entry_ok = f"def {e['entrypoint']}(" in src
        doc_ok = True
        if e["name"].startswith("l0_"):   # R1 说明模板只强约束 l0_* 脚本
            doc = src.split('"""')
            doc_txt = doc[1] if len(doc) > 1 else ""
            doc_ok = all(k in doc_txt for k in DOCSTRING_LINES)
        hash_ok = True
        hv = e.get("hash")
        if hv:
            import hashlib
            actual = hashlib.sha1(p.read_bytes()).hexdigest()
            hash_ok = actual == hv
        doc_show = ('yes' if doc_ok else 'no') if e["name"].startswith("l0_") else '-'
        print(f"{'OK' if entry_ok and doc_ok and hash_ok else 'MISS'} {e['name']}: "
              f"entry={e['entrypoint']} doc4lines={doc_show} "
              f"hash={'ok' if hash_ok else 'MISMATCH'} path={p}")
        if not (entry_ok and doc_ok and hash_ok):
            bad += 1
    print(f"REGISTRY_CHECK entries={len(scripts)} bad={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
