#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_ms5_acceptance.py —— MS-5 端到端验收（黄金夹具离线重放，硬指标五条）
====================================================================
用黄金夹具 180 页 md_results 跑 pipeline.py（适配层→校验门→阶梯→structurer→quality），
按需求书 §7.1 五条硬指标验收：守恒写回 100% / 标记完备 100% / 台账捕捉 100% / 溯源 100% / 成本可观测 100%。
用法：python tests/v4/test_ms5_acceptance.py
"""
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "assets" / "v4"))

from pipeline import acceptance_offline  # noqa: E402

BATCH = SKILL / "tests" / "vision_shootout" / "results" / "batch"
CFG = json.loads((SKILL / "assets" / "v4" / "config.default.json").read_text(encoding="utf-8"))


class Tally:
    def __init__(self):
        self.p = 0
        self.f = 0
        self.failures = []

    def check(self, name, ok, detail=""):
        if ok:
            self.p += 1
            print(f"[PASS] {name} {detail}")
        else:
            self.f += 1
            self.failures.append(name)
            print(f"[FAIL] {name} {detail}")


def main():
    t = Tally()
    v4, report = acceptance_offline(CFG, BATCH)
    hm = report["hard_metrics"]
    t.check("MS5 产 schema_version=4.0", v4.get("schema_version") == "4.0")
    t.check("MS5 表状态计数一致", report["tables_total"] > 0,
            f"tables={report['tables_total']} marked={report['marked_total']}")
    # 五条硬指标
    t.check("MS5 硬指标-守恒写回 100%", hm["conservation_writeback"]["passed"],
            hm["conservation_writeback"]["detail"])
    t.check("MS5 硬指标-标记完备 100%", hm["honest_marking"]["passed"],
            hm["honest_marking"]["detail"])
    t.check("MS5 硬指标-台账捕捉 100%", hm["defect_capture"]["passed"],
            hm["defect_capture"]["detail"])
    t.check("MS5 硬指标-溯源 100%", hm["source_locatable"]["passed"],
            hm["source_locatable"]["detail"])
    t.check("MS5 硬指标-成本可观测 100%", hm["cost_observable"]["passed"],
            hm["cost_observable"]["detail"])
    t.check("MS5 整体 accepted（硬指标全过）", report["accepted"], report["summary"])

    print(f"\nRESULT pass={t.p} fail={t.f}")
    if t.f:
        print("FAILED:", ", ".join(t.failures))
    return 0 if t.f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
