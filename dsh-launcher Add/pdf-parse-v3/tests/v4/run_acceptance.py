#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/run_acceptance.py —— 最终验收（六）单命令入口
================================================
a) 四层测试（L1/语法 + L3 离线单元·黄金夹具重放，不打 API）——跑 4 个 v4 测试脚本；
b) 黄金夹具完整性（180 页 + page_0087 实证页）；
c) 需求书 §7.1 五条硬指标（守恒写回/标记完备/台账捕捉/溯源/成本可观测）——任一不过即红灯。

用法：python tests/v4/run_acceptance.py
输出：RESULT accepted=True/False + 五硬指标明细。
"""
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "assets" / "v4"))

TESTS = ["test_ms1_smoke.py", "test_ms2_replay.py", "test_ms3_ladder.py", "test_ms5_acceptance.py"]
BATCH = SKILL / "tests" / "vision_shootout" / "results" / "batch"
CFG = json.loads((SKILL / "assets" / "v4" / "config.default.json").read_text(encoding="utf-8"))


def run_test(path):
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def main():
    ok_all = True
    print("== a) 四层测试（v4 离线）==")
    for t in TESTS:
        ok, out = run_test(SKILL / "tests" / "v4" / t)
        ok_all &= ok
        res = [l for l in out.splitlines() if "RESULT pass=" in l]
        print(f"  {'PASS' if ok else 'FAIL'}  {t}  {res[-1] if res else ''}")

    print("== b) 黄金夹具完整性（180 页 + page_0087）==")
    n = len(list(BATCH.glob("page_*.json")))
    has87 = (BATCH / "page_0087.json").exists()
    ok_fix = (n == 180) and has87
    ok_all &= ok_fix
    print(f"  {'PASS' if ok_fix else 'FAIL'}  pages={n} page_0087={has87}")

    print("== c) 硬指标（§7.1，任一不过即红灯）==")
    from pipeline import acceptance_offline
    v4, report = acceptance_offline(CFG, BATCH)
    hm = report["hard_metrics"]
    for k, v in hm.items():
        ok_all &= v["passed"]
        print(f"  {'PASS' if v['passed'] else 'FAIL'}  {k}  rate={v['rate']} detail={v['detail']}")
    ok_all &= report["accepted"]
    print(f"\nRESULT accepted={'TRUE' if ok_all and report['accepted'] else 'FALSE'}")
    return 0 if (ok_all and report['accepted']) else 1


if __name__ == "__main__":
    sys.exit(main())
