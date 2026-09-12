#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-1.2/1.3 _collect_candidates.py —— 候选生成器 + R2 候选校验器（spec §5 W2/W3 输入、§4.2）
作用：扫描任务级 var/task-scripts/<task-id>/ 下未入候选/归档的 l0_*.py，生成 R2 候选 JSON
     （确定性字段全产，含 task_id；found_issues/test_problem=null+pending_review 待评审回填），
     regression 以实跑退出码+输出为证据；候选写 var/queue/candidates/<name>.json。
输入：task_id（可选 --validate 对已有候选做校验）。
输出：候选文件 + 确定性一行可 grep。
复跑：python scripts/_collect_candidates.py <task_id> [--validate <候选json>]；依赖：仅标准库 + _registry_io。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from _registry_io import task_registry_path, read_registry, SKILL

QUEUE = SKILL / "var" / "queue"
CAND_DIR = QUEUE / "candidates"
DONE_DIR = QUEUE / "done"
DETERMINISTIC = ("name", "ns", "task_id", "version", "environment", "regression")


def validate_candidate(cand: dict) -> list:
    """R2 schema 校验（闭合 spec §8 第 3 条；found_issues null+pending 不算缺；code|code_path 二选一）。"""
    problems = []
    if not isinstance(cand, dict):
        return ["候选非 dict"]
    for k in DETERMINISTIC:
        if k not in cand or cand[k] in (None, ""):
            problems.append(f"确定性字段缺 {k}")
    if "code_path" not in cand and "code" not in cand:
        problems.append("code_path|code 至少其一（二选一）")
    elif "code_path" in cand and "code" not in cand and cand["code_path"] \
            and not Path(str(cand["code_path"])).exists():
        problems.append(f"code_path 文件不存在 {cand['code_path']}")
    r = cand.get("regression")
    if not isinstance(r, dict) or "passed" not in r:
        problems.append("regression{passed} 缺失")
    fi = cand.get("found_issues")
    if fi is not None and not isinstance(fi, list):
        problems.append("found_issues 非 list/null")
    if fi is None and cand.get("pending_review") is not True:
        problems.append("found_issues=null 但缺 pending_review=true 标注")
    return problems


def _docstring_of(src: str) -> str:
    parts = src.split('"""')
    return parts[1] if len(parts) > 1 else ""


def _derive_description(src: str, name: str) -> str:
    doc = _docstring_of(src)
    for line in doc.splitlines():
        if line.strip().startswith("作用"):
            return line.split("作用", 1)[1].strip(" ：:-").strip()
    return name


def _run_evidence(script_path) -> dict:
    """实跑候选脚本取证 regression（S-2 闭合；证据字段名=evidence，m4 闭合）。"""
    try:
        r = subprocess.run([sys.executable, str(script_path)], capture_output=True,
                           text=True, encoding="utf-8", timeout=300)
        out = (r.stdout or "") + (r.stderr or "")
        ev = "\n".join(out.splitlines()[-6:])
        if r.returncode == 0:
            return {"passed": True, "exit": 0, "evidence": ev}
        return {"passed": None, "exit": r.returncode,
                "invocation": "bare",
                "reason": "无参裸跑非 0：需带参调用（needs invocation，不判失败/不晋升）",
                "evidence": ev}
    except Exception as e:
        return {"passed": None, "exit": None, "reason": f"run_error: {e}",
                "evidence": f"run_error: {e}"}


def _cand_name(task_id: str, name: str) -> str:
    """跨任务共享队列中的候选文件名带 task_id（S-1 闭合：任务 B 同名不误判已收集）。"""
    return f"{task_id}__{name}.json"


def _next_version(task_id: str, name: str) -> str:
    existing = []
    pref = f"{task_id}__{name}.json"
    for d in (CAND_DIR, DONE_DIR):
        for f in d.glob("*.json"):
            if f.name == pref:
                try:
                    cand = json.loads(f.read_text(encoding="utf-8"))
                    m = re.match(r"r(\d+)", str(cand.get("version", "")))
                    existing.append(int(m.group(1)) if m else 0)
                except Exception:
                    continue
    return f"r{max(existing, default=0) + 1}"


def collect_candidates(task_id: str, *, env_note=None) -> list:
    """扫描任务级目录生成候选（写入 CAND_DIR，文件名 {task_id}__{name}.json）。返回候选列表。"""
    tdir = task_registry_path(task_id).parent
    if not tdir.exists():
        return []
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for sp in sorted(tdir.glob("l0_*.py")):
        name = sp.stem if sp.stem.startswith("l0_") else "l0_" + sp.stem
        fname = _cand_name(task_id, name)
        if (CAND_DIR / fname).exists() or (DONE_DIR / fname).exists():
            continue
        src = sp.read_text(encoding="utf-8", errors="ignore")
        reg = _run_evidence(sp)
        cand = {
            "name": name, "ns": "code", "task_id": task_id,
            "version": _next_version(task_id, name),
            "code_path": str(sp.resolve()).replace("\\", "/"),
            "description": _derive_description(src, name),
            "test_problem": None,
            "environment": env_note or f"python={sys.executable}",
            "found_issues": None,
            "pending_review": True,
            "regression": reg,
        }
        (CAND_DIR / fname).write_text(
            json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
        made.append(cand)
    return made


def _self_test():
    import tempfile
    from unittest import mock
    ok = []
    def chk(n, c, d=""):
        ok.append((n, bool(c), d))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with mock.patch.object(sys.modules[__name__], "QUEUE", tmp / "queue"), \
             mock.patch.object(sys.modules[__name__], "CAND_DIR", tmp / "queue" / "candidates"), \
             mock.patch.object(sys.modules[__name__], "DONE_DIR", tmp / "queue" / "done"), \
             mock.patch.object(sys.modules["_registry_io"], "VAR", tmp):
            # 造一个合法 l0 脚本
            tdir = task_registry_path("t2").parent
            tdir.mkdir(parents=True, exist_ok=True)
            demo = tdir / "l0_demo.py"
            demo.write_text('#!/usr/bin/env python3\n"""作用：demo 检查。\n输入：无。\n输出：OK。\n复跑：python l0_demo.py；依赖：无。"""\nprint("OK")\n', encoding="utf-8")
            made = collect_candidates("t2")
            chk("收集 ≥1 候选", len(made) == 1, f"n={len(made)}")
            cand = made[0]
            probs = validate_candidate(cand)
            chk("候选校验通过(确定性字段)", probs == [], f"probs={probs}")
            chk("found_issues null+pending", cand["found_issues"] is None and cand.get("pending_review") is True)
            chk("regression 有据", cand["regression"]["passed"] is True, cand["regression"].get("evidence", "")[:40])
            chk("task_id 写入候选", cand["task_id"] == "t2")
            # 幂等：二次收集不重复
            made2 = collect_candidates("t2")
            chk("二次收集不重复", len(made2) == 0)
            # 反例：确定性字段缺失 → validate 报问题
            bad = {"name": "x"}
            chk("校验器抓确定性字段缺", len(validate_candidate(bad)) >= 1)
            # 反例：found_issues null 无 pending → 报
            bad2 = {"name": "y", "ns": "code", "task_id": "t", "version": "r1",
                    "code_path": str(demo), "environment": "py", "found_issues": None,
                    "regression": {"passed": True}}
            chk("校验器抓 null 无 pending", any("pending_review" in p for p in validate_candidate(bad2)))
            # 候选文件已落盘
            chk("候选落盘", (tmp / "queue" / "candidates" / "t2__l0_demo.json").exists())
    fails = [n for n, c, _ in ok if not c]
    for n, c, d in ok:
        print(f"{'PASS' if c else 'FAIL'} {n} {d}")
    print(f"COLLECT_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--validate":
        c = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        p = validate_candidate(c)
        print("VALIDATE probs=" + (";".join(p) if p else "none"))
        sys.exit(1 if p else 0)
    if len(sys.argv) >= 2:
        made = collect_candidates(sys.argv[1])
        print(f"COLLECT task={sys.argv[1]} new={len(made)}")
        sys.exit(0)
    sys.exit(_self_test())
