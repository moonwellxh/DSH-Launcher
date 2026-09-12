# -*- coding: utf-8 -*-
# =====================================================================
# l0_spec_code_sync.py —— 规格(SKILL.md §1 参数表) 与 实现(脚本常量) 一致性检查
# 作用: 静态解析 SKILL.md 参数表与 sediment_run.py 常量/argparse 默认值，比对是否同步。
#       本检查针对的缺陷类别：参数只在脚本里改、忘了登记进 SKILL.md §1（本次改造前
#       new_threshold/window 就处于"实现有、规格无"的不同步状态）。
# 输入: 无（以 <技能根> 为基准；也可 --skill-root 覆盖）
# 输出: 单行 JSON {"ok":bool,"checks":[{name,expect,found,ok}],"missing":[...]}
# 复跑: python3 var/task-scripts/adv-review-m4m7/l0_spec_code_sync.py
# 依赖: Python 3.9+ 标准库（import sediment_run 以取真实常量）
# =====================================================================
import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-root", default=None)
    args = ap.parse_args()
    root = Path(args.skill_root).resolve() if args.skill_root else Path(__file__).resolve().parents[3]

    sys.path.insert(0, str(root / "scripts"))
    import sediment_run as sr          # noqa: E402

    skill = (root / "SKILL.md").read_text(encoding="utf-8-sig")
    if "## 1. 参数表" not in skill:
        print(json.dumps({"ok": False, "error": "SKILL.md 缺 §1 参数表"}, ensure_ascii=False))
        return 2
    sec = skill.split("## 1. 参数表")[1].split("## 2.")[0]
    cells = [c.strip() for line in sec.splitlines() if line.strip().startswith("|")
             for c in line.strip().strip("|").split("|")]

    src = (root / "scripts" / "sediment_run.py").read_text(encoding="utf-8-sig")
    m = re.search(r'--new-threshold",\s*type=int,\s*default=(\d+)', src)
    nt = m.group(1) if m else None

    checks = [
        ("新增条款门槛登记", "新增条款门槛", any("新增条款门槛" in c for c in cells)),
        ("新增条款门槛值=5", "≥5", any("≥5" in c for c in cells)),
        ("new_threshold 默认=5", "5", nt == "5"),
        ("条款数上限登记", "条款数上限", any("条款数上限" in c for c in cells)),
        ("上限-通用=CLAUSE_CAP", "通用 ≤%d" % sr.CLAUSE_CAP["general"],
         any(("通用 ≤%d" % sr.CLAUSE_CAP["general"]) in c for c in cells)),
        ("上限-命名空间=CLAUSE_CAP", "每命名空间 ≤%d" % sr.CLAUSE_CAP["per_ns"],
         any(("每命名空间 ≤%d" % sr.CLAUSE_CAP["per_ns"]) in c for c in cells)),
        ("试用观察期登记", "试用观察期", any("试用观察期" in c for c in cells)),
        ("试用窗口=%d" % sr.TRIAL_WINDOWS_REQUIRED, "%d 个沉淀窗口" % sr.TRIAL_WINDOWS_REQUIRED,
         any(("%d 个沉淀窗口" % sr.TRIAL_WINDOWS_REQUIRED) in c for c in cells)),
        ("零证据降权窗口=%d" % sr.ZERO_EVIDENCE_DEMOTE, "连续 %d 窗口" % sr.ZERO_EVIDENCE_DEMOTE,
         any(("连续 %d 窗口" % sr.ZERO_EVIDENCE_DEMOTE) in c for c in cells)),
        ("零证据淘汰窗口=%d" % sr.ZERO_EVIDENCE_RETIRE, "连续 %d 窗口" % sr.ZERO_EVIDENCE_RETIRE,
         any(("连续 %d 窗口" % sr.ZERO_EVIDENCE_RETIRE) in c for c in cells)),
        ("聚合窗口登记", "聚合窗口", any("聚合窗口" in c for c in cells)),
    ]
    out = [{"name": n, "expect": e, "ok": bool(ok)} for n, e, ok in checks]
    missing = [x["name"] for x in out if not x["ok"]]
    print(json.dumps({"ok": not missing, "checks": out, "missing": missing}, ensure_ascii=False))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
