#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-4.2 节点测试：collect_snapshot.py 的 reuse_ledger（校验+默认回填+落盘）。
作用：验证快照顶层可选 reuse_ledger 与既有 schema 兼容、畸形被拒、列表字段默认补齐。
输入：无（自构造快照经 stdin 送 collect_snapshot）。
输出：确定性一行 + 逐项 PASS/FAIL。
复跑：python scripts/tests_node/test_4_2_snapshot.py；依赖：collect_snapshot（同目录）。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CS = HERE / "collect_snapshot.py"
PY = sys.executable


def run(obj):
    return subprocess.run([PY, str(CS), "--ns", "code", "--state-dir", str(tmp)],
                          input=json.dumps(obj, ensure_ascii=False), capture_output=True,
                          text=True, encoding="utf-8")


base = {"id": "snap-node42-0001", "ns": "code", "ts": "2026-09-07T00:00:00+08:00",
        "env": {"platform": "win", "pricing_version": "x"},
        "task": {"summary": "t", "object_type": "spec"}, "mode": "closed_loop",
        "rounds": 1, "outcome": "passed",
        "issues": [{"id": "i1", "severity": "minor", "type": "x", "anchor": "a", "basis": "b", "status": "open"}],
        "tokens": []}

ok = []
def chk(n, c, d=""):
    ok.append((n, bool(c), d))
with tempfile.TemporaryDirectory() as td:
    global tmp
    tmp = Path(td) / "state"
    # 合法：含 reuse_ledger（缺列表字段→应回填）
    good = dict(base, reuse_ledger={"round": "r3", "reused_count": 2, "new_count": 0, "est_saved_tokens": 120})
    r = run(good)
    chk("合法 reuse_ledger 落盘", r.returncode == 0, f"exit={r.returncode} {r.stdout[:120]}")
    written = json.loads(r.stdout)["written"] if r.returncode == 0 else None
    if written:
        snap = json.loads(Path(written).read_text(encoding="utf-8"))
        chk("reused_scripts 默认回填", snap["reuse_ledger"].get("reused_scripts") == [] and
            snap["reuse_ledger"].get("new_scripts") == [])
        chk("顶层 rounds 未被覆盖", snap["rounds"] == 1)
    # 畸形：reuse_ledger 非 dict / 缺字段 → 拒
    bad1 = dict(base, reuse_ledger="oops")
    chk("reuse_ledger 非 dict 被拒", run(bad1).returncode != 0)
    bad2 = dict(base, reuse_ledger={"round": "r1"})
    chk("reuse_ledger 缺字段被拒", run(bad2).returncode != 0)
    # 无 reuse_ledger 原样兼容
    chk("无 reuse_ledger 仍兼容", run(base).returncode == 0)
fails = [n for n, c, _ in ok if not c]
for n, c, d in ok:
    print(f"{'PASS' if c else 'FAIL'} {n} {d}")
print(f"SNAPSHOT42_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
sys.exit(1 if fails else 0)
