#!/usr/bin/env python3
"""Measure SKILL.md size metrics for all installed skills.

作用: 产出「正文体量」的确定性实测数字（行/非空行/字符/字节四口径），供 SKILL.md §5 引用
输入: 无参数；技能根路径内置（可传 --root 覆盖）
输出: stdout 一张表格 + 汇总（行/非空行/字符/字节的 min-max、>500 行计数）
复跑: python scripts/measure_skill_sizes.py   （依赖: Python 3.9+ 标准库）
"""
import argparse
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
DEFAULT_ROOT = "C:\\Users\\雍远\\.agents\\skills"


def measure(p):
    b = open(p, "rb").read()
    t = b.decode("utf-8", "replace")
    lines = t.splitlines()
    nonempty = [l for l in lines if l.strip()]
    return {
        "bytes": len(b),
        "chars": len(t),
        "lines": len(lines),
        "nonempty": len(nonempty),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = []
    for sk in sorted(glob.glob(os.path.join(args.root, "*", "SKILL.md"))):
        d = os.path.basename(os.path.dirname(sk))
        m = measure(sk)
        m["skill"] = d
        rows.append(m)
    if not rows:
        print("no SKILL.md found under %s" % args.root)
        sys.exit(2)
    rows.sort(key=lambda r: -r["chars"])
    f = {"lines": "lines", "nonempty": "nonempty", "chars": "chars", "bytes": "bytes"}
    summ = {}
    for k in f:
        vals = [r[k] for r in rows]
        summ[k] = {"min": min(vals), "max": max(vals)}
    summ["over500_lines"] = sum(1 for r in rows if r["lines"] >= 500)
    summ["over500_nonempty"] = sum(1 for r in rows if r["nonempty"] >= 500)
    summ["count"] = len(rows)
    if args.json:
        print(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1))
        return
    print("count=%d  lines min-max=%d-%d (>=500: %d)  nonempty=%d-%d (>=500: %d)  chars=%d-%d  bytes=%d-%d"
          % (summ["count"], summ["lines"]["min"], summ["lines"]["max"], summ["over500_lines"],
             summ["nonempty"]["min"], summ["nonempty"]["max"], summ["over500_nonempty"],
             summ["chars"]["min"], summ["chars"]["max"], summ["bytes"]["min"], summ["bytes"]["max"]))
    for r in rows[:8]:
        print("  %-24s chars=%5d bytes=%6d lines=%3d nonempty=%3d"
              % (r["skill"], r["chars"], r["bytes"], r["lines"], r["nonempty"]))


if __name__ == "__main__":
    main()
