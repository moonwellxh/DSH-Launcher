#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 8 CI：一次性运行全部节点自测/单测（离线），聚合 PASS/FAIL。
作用：确定性回归门（零 API）。输出 RESULT 一行可 grep。
复跑：python scripts/tests_node/ci_all.py；依赖：各节点脚本 + 本机 DSH python。
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]      # .../adversarial-review/scripts
PY = sys.executable

JOBS = [
    (HERE / "_registry_io.py", "registry_io"),
    (HERE / "_collect_candidates.py", "collect_candidates"),
    (HERE / "tests_node" / "test_2_1_phaseS3.py", "phase_S3"),
    (HERE / "tests_node" / "test_4_2_snapshot.py", "snapshot_reuse"),
    (HERE / "_extract_bricks.py", "extract_bricks"),
    (HERE / "_gen_catalog.py", "gen_catalog"),
    (HERE / ".." / "var" / "task-scripts" / "pdf-parse-v3" / "e2e_replay.py", "e2e_pilot"),
    (HERE / ".." / "var" / "task-scripts" / "pdf-parse-v3" / "l0_registry_check.py", "real_registry_check"),
]


def main():
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    fails = []
    for path, name in JOBS:
        r = subprocess.run([PY, str(path)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
        tail = (r.stdout or "").strip().splitlines()
        ok_line = next((ln for ln in tail if "pass=" in ln and "fail=" in ln), "")
        if r.returncode == 0:
            print(f"PASS {name}  {ok_line}")
        else:
            fails.append(name)
            print(f"FAIL {name}  exit={r.returncode}")
            for ln in tail[-4:]:
                print("    " + ln)
    # L1 语法：全部 scripts/*.py 与节点测试 py_compile
    for f in sorted(HERE.glob("*.py")) + sorted((HERE / "tests_node").glob("*.py")):
        rc = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True)
        if rc.returncode != 0:
            fails.append("py_compile:" + f.name)
            print(f"FAIL py_compile {f.name}")
    print(f"RESULT ci_pass={len(JOBS)-len([f for f in fails if not f.startswith('py_compile')])} "
          f"ci_fail={len([f for f in fails if not f.startswith('py_compile')])} compile_fail={sum(1 for f in fails if f.startswith('py_compile'))}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
