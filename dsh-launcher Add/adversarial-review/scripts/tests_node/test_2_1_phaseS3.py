#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-2.1 节点测试：phase_S3 扩展（读 R2 全字段/写 task_id+code_path+hash/幂等去重/失败归档）。
作用：验证 sediment_run.phase_S3 在隔离临时 state 上的确定性行为。
输入：无（自构造临时候选）。
输出：确定性一行 + 逐项 PASS/FAIL。
复跑：python scripts/tests_node/test_2_1_phaseS3.py；依赖：sediment_run（同目录）。
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sediment_run as sr

C = SimpleNamespace(ns="code")


def main():
    ok = []
    def chk(n, c, d=""):
        ok.append((n, bool(c), d))
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        (state / "queue" / "candidates").mkdir(parents=True)
        # 候选1：code_path（含 task_id）
        sp = state / "queue" / "l0_a.py"
        sp.write_text("print('OKA')\n", encoding="utf-8")
        cand1 = {"name": "l0_a", "ns": "code", "task_id": "taskA", "version": "r1",
                 "code_path": str(sp), "environment": "py",
                 "found_issues": None, "pending_review": True,
                 "regression": {"passed": True}}
        # 候选2：内联 code（含 task_id）
        cand2 = {"name": "l0_b", "ns": "code", "task_id": "taskA", "version": "r1",
                 "code": "print('OKB')", "environment": "py",
                 "regression": {"passed": True}}
        # 候选3：回归失败
        cand3 = {"name": "l0_c", "ns": "code", "task_id": "taskA", "version": "r1",
                 "code_path": str(sp), "environment": "py",
                 "regression": {"passed": False}}
        qd = state / "queue" / "candidates"
        for n, c in (("l0_a.json", cand1), ("l0_b.json", cand2), ("l0_c.json", cand3)):
            (qd / n).write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        res = sr.phase_S3(C, state)
        reg = sr.load_json(state / "registry" / "scripts.json", {"scripts": []})
        chk("通过2晋升", len(res["promoted"]) == 2, f"promoted={res['promoted']}")
        chk("失败1拒绝", len(res["rejected"]) == 1 and res["rejected"] == ["l0_c"])
        chk("技能级含 task_id", {r["task_id"] for r in reg["scripts"]} == {"taskA"})
        chk("技能级含 code_path+hash(code_path)", any(r["name"] == "l0_a" and r["code_path"].endswith("l0_a.py")
            and isinstance(r["hash"], str) and len(r["hash"]) == 40 for r in reg["scripts"]))
        chk("内联 code 有 hash 无 code_path", any(r["name"] == "l0_b" and r["code_path"] is None
            and isinstance(r["hash"], str) and len(r["hash"]) == 40 for r in reg["scripts"]))
        chk("失败候选入 failed 目录", (state / "queue" / "failed" / "l0_c.json").exists())
        chk("done 两文件", len(list((state / "queue" / "done").glob("*.json"))) == 2)
        # 幂等去重：同一 hash 内容再入候选 → 只更新不重复
        cand1b = dict(cand1, version="r2")
        (qd / "l0_a.json").write_text(json.dumps(cand1b, ensure_ascii=False), encoding="utf-8")
        res2 = sr.phase_S3(C, state)
        reg2 = sr.load_json(state / "registry" / "scripts.json", {"scripts": []})
        chk("同 hash 去重（不增条目）", len(reg2["scripts"]) == 2, f"total={len(reg2['scripts'])}")
        chk("同 hash 更新版本", any(r["name"] == "l0_a" and r["version"] == "r2" for r in reg2["scripts"]))
    fails = [n for n, c, _ in ok if not c]
    for n, c, d in ok:
        print(f"{'PASS' if c else 'FAIL'} {n} {d}")
    print(f"PHASES3_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
