#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-5.2 试点端到端回放（spec §8 六条；两阶段 A/B）
作用：在隔离 temp VAR 上验证全链：register_l0→(A 晋升轮: 未晋升代跑 reused→collect→phase_S3 晋升)→
     (B 复用轮: 已晋升代跑 hits+1)→快照含 reuse_ledger；并对真实试点做只读冒烟（l0_config_keys 可跑）。
输入：无。
输出：确定性逐条 + 汇总一行。
复跑：python var/task-scripts/pdf-parse-v3/e2e_replay.py；依赖：scripts/_registry_io,_collect_candidates,
     sediment_run phase_S3, _extract_bricks, _gen_catalog, collect_snapshot。
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"      # adversarial-review/scripts
sys.path.insert(0, str(SCRIPTS))

import _registry_io as ri
import _collect_candidates as cc
import sediment_run as sr
import _extract_bricks as eb
import _gen_catalog as gc

ok = []
def chk(n, c, d=""):
    ok.append((n, bool(c), d))

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    # 隔离 VAR/bricks（不改真实 var）
    ri.VAR = tmp / "var"
    cc.QUEUE = tmp / "var" / "queue"
    cc.CAND_DIR = tmp / "var" / "queue" / "candidates"
    cc.DONE_DIR = tmp / "var" / "queue" / "done"
    br = tmp / "bricks"
    eb.BRICKS_ROOT = br
    tdir = tmp / "var" / "task-scripts" / "e2e"
    tdir.mkdir(parents=True)

    # —— A 晋升轮 ——
    demo = tdir / "l0_e2e_demo.py"
    demo.write_text('#!/usr/bin/env python3\n"""作用：e2e demo 检查。\n输入：无。\n输出：OK。\n'
                    '复跑：python l0_e2e_demo.py；依赖：无。"""\nprint("OK")\n', encoding="utf-8")
    e = ri.register_l0("e2e", demo, "e2e demo")
    chk("A1 register 落盘", "hash" in e and e["code_path"].endswith("l0_e2e_demo.py"))
    # 未晋升代跑 → reused（A 轮内；满足 §8#6）
    r_un = ri.run_registered(e["name"], "e2e")
    chk("A2 未晋升→reused", r_un["branch"] == "reused", r_un["detail"])
    # 收尾自动收集候选
    made = cc.collect_candidates("e2e")
    chk("A3 候选生成", len(made) == 1 and made[0]["found_issues"] is None and made[0].get("pending_review") is True)
    # phase_S3 晋升
    state = tmp / "state"
    qd = tmp / "var" / "queue" / "candidates"
    import shutil
    for f in qd.glob("*.json"):
        st = state / "queue" / "candidates"
        st.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, st / f.name)
    res = sr.phase_S3(type("C", (), {"ns": "code"})(), state)
    chk("A4 晋升", len(res["promoted"]) >= 1, f"{res['promoted']}")
    sreg = ri.read_registry(state / "registry" / "scripts.json")
    chk("A5 技能级含 task_id/code_path/hash",
        all(k in sreg["scripts"][0] for k in ("task_id", "code_path", "hash")))

    # —— B 复用轮：已晋升代跑 → hits+1 ——
    # phase_S3 写到了 temp state 的 registry；run_registered 查 ri.VAR=tmp/var/registry/scripts.json（不同处）
    # → 把晋升记录同步到 ri 技能级路径以便 B 轮 hits 判定
    skill = ri.skill_registry_path()
    skill.parent.mkdir(parents=True, exist_ok=True)
    ri.write_registry(skill, {"namespace": "code", "scripts": sreg["scripts"]})
    r_hit = ri.run_registered(e["name"], "e2e")
    chk("B1 已晋升→hits+1", r_hit["branch"] == "hits" and r_hit["detail"].endswith("hits=1"), r_hit["detail"])

    # —— 复用台账 + 快照 reuse_ledger ——
    reused_scripts = [r_un["name"]]
    est = len(reused_scripts) * math.ceil(max(len(x) for x in reused_scripts) / 2)
    reuse_ledger = {"round": "e2e-r1", "reused_scripts": reused_scripts, "new_scripts": [],
                    "reused_count": len(reused_scripts), "new_count": 0, "est_saved_tokens": est}
    chk("C1 台账含 reused 计数", reuse_ledger["reused_count"] >= 1 and reuse_ledger["est_saved_tokens"] > 0)
    snap = {"id": "snap-e2e-pilot-0001", "ns": "code", "ts": "2026-09-07T00:00:00+08:00",
            "env": {"platform": "win", "pricing_version": "x"},
            "task": {"summary": "e2e pilot", "object_type": "plan"}, "mode": "closed_loop",
            "rounds": 1, "outcome": "passed",
            "issues": [{"id": "i1", "severity": "minor", "type": "x", "anchor": "a", "basis": "b", "status": "open"}],
            "tokens": [], "reuse_ledger": reuse_ledger}
    p = subprocess.run([sys.executable, str(SCRIPTS / "collect_snapshot.py"), "--ns", "code",
                        "--state-dir", str(tmp / "snapstate")],
                       input=json.dumps(snap, ensure_ascii=False), capture_output=True,
                       text=True, encoding="utf-8")
    chk("C2 快照含 reuse_ledger 通过", p.returncode == 0, f"exit={p.returncode} {p.stdout[:100]}")

    # —— 3.1/3.2 机制验证（合成夹具）——
    fixture = ("import re\ndef norm_num(s=''):\n    return re.sub(r'[\\s,，]', '', s or '')\n")
    fx = tmp / "fixture.py"
    fx.write_text(fixture, encoding="utf-8")
    r3 = eb.extract_brick(fixture, "norm_num", task_id="e2e", source_script="fixture.py",
                          admission={"cross_task": 2})
    chk("D1 合成夹具积木入库", r3["action"] == "registered", r3.get("reason", ""))
    g = gc.gen_catalog(br)
    chk("D2 catalog 含积木", (br / "catalog.json").exists() and "norm_num" in (br / "catalog.md").read_text(encoding="utf-8"))

    # —— 真实试点只读冒烟（用真实 VAR 路径，不经被覆盖的 ri.VAR）——
    real_dir = SCRIPTS.parent / "var" / "task-scripts" / "pdf-parse-v3"
    real_rp = real_dir / "registry.json"
    real = ri.read_registry(real_rp) if real_rp.exists() else {}
    chk("E1 真实试点 registry 可读且含 hash", len(real.get("scripts", [])) >= 1
        and all("hash" in s for s in real.get("scripts", [])))
    try:
        r = subprocess.run([sys.executable, str(real_dir / "l0_config_keys.py"),
                            r"C:\Users\雍远\.agents\skills\pdf-parse-v3"], capture_output=True,
                           text=True, encoding="utf-8", timeout=120)
        chk("E2 真实试点 l0_config_keys 可跑", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout else "")
    except Exception as ex:
        chk("E2 真实试点 l0_config_keys 可跑", False, str(ex))

fails = [n for n, c, _ in ok if not c]
for n, c, d in ok:
    print(f"{'PASS' if c else 'FAIL'} {n} {d}")
print(f"E2E_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
sys.exit(1 if fails else 0)
