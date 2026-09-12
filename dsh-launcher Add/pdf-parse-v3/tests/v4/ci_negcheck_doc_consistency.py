#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/ci_negcheck_doc_consistency.py —— doc-consistency 反向校验负向自检（N3.2/R-04 收口）
作用：在合成临时树里删去 SKILL §0.1 一个公开旗标（--ignore-gpu-lib），确认 check_doc_consistency 检出（ok=False）。
输入：无（路径内置于脚本，基于技能根）。输出：NEG OK/FAIL 行。复跑：python tests/v4/ci_negcheck_doc_consistency.py
说明：不入 ci_all SUITES 主绿（防污染真实 SKILL 读取——本脚本用临时树 patch 模块级 SKILL/V4）；负向失效（未检出）→ 脚本 rc=1。
退出码：0=负向生效（检出缺失）；1=负向回归失效（未检出）。
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

REAL = Path(__file__).resolve().parents[2]          # 技能根


def _copy_v4_tree(t_root):
    """把 REAL assets/v4 全量文件（*.py + config.default.json）拷入临时树，保证 ok2（模块清单）为真，
    使负向判定只由反向缺失驱动（Step 8 CI 修复 S2）。"""
    v4 = t_root / "assets" / "v4"
    v4.mkdir(parents=True)
    for f in (REAL / "assets" / "v4").iterdir():
        if f.suffix == ".py" or f.name == "config.default.json":
            (v4 / f.name).write_bytes(f.read_bytes())
    return v4


def main():
    # 输出编码钉死（Step 8 复审 S-复审-1）：details 含 ⊆ 等非 GBK 字符，裸命令须 UTF-8 防假红
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    spec = importlib.util.spec_from_file_location("ci_all_mod", REAL / "tests" / "v4" / "ci_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sk_real = (REAL / "SKILL.md").read_text(encoding="utf-8")
    # ① 正控：真实 SKILL + 全量模块 → ok 应为 True（证明合成树模块完备）
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "SKILL.md").write_text(sk_real, encoding="utf-8")
        _copy_v4_tree(t)
        mod.SKILL, mod.V4 = t, t / "assets" / "v4"
        ok_pos, _ = mod.check_doc_consistency()
    if not ok_pos:
        print("NEG FAIL: 正控（真实 SKILL+全量模块）check_doc_consistency 非 True——合成基线不成立")
        return 2
    # ② 负控：SKILL 删公开旗标 --ignore-gpu-lib（全量模块保留）→ ok=False 且 details 显式含 rev_missing
    sk_neg = sk_real.replace("[--ignore-gpu-lib]", "")
    if sk_neg == sk_real:
        print("NEG FAIL: SKILL.md 现文不含 [--ignore-gpu-lib]，无法构造负向场景")
        return 2
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "SKILL.md").write_text(sk_neg, encoding="utf-8")
        v4 = _copy_v4_tree(t)
        mod.SKILL, mod.V4 = t, v4
        ok, details = mod.check_doc_consistency()
    rev_hit = details and "rev_missing=['--ignore-gpu-lib']" in details[0]
    if ok or not rev_hit:
        print("NEG FAIL: 反向删旗标后 check_doc_consistency ok=%s rev_hit=%s（反向回归保护失效）" % (ok, rev_hit))
        print(details)
        return 1
    print("NEG OK: 反向检出缺失 -> ok=False 且 rev_missing=['--ignore-gpu-lib']；details=%s" % details)
    return 0


if __name__ == "__main__":
    sys.exit(main())
