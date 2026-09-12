#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-1.1 _registry_io.py —— registry 读写层（spec §5 W1 / §4.1）
作用：任务级/技能级 registry 的容器化读写（原子写保 meta）、register_l0、compute_hash、
     record_found_issues、run_registered（两分支）、record_false_positive。
输入：task_id / script 路径（registry 位于 <技能>/var/task-scripts/<task-id>/registry.json 与 var/registry/scripts.json）。
输出：函数返回值 + 确定性一行（自测）。
复跑：python scripts/_registry_io.py；依赖：仅标准库。
"""
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]           # .../adversarial-review
VAR = SKILL / "var"
CONTAINER_META = ("namespace", "target", "updated", "location_rule")  # 容器元数据（写回必保）


def task_registry_path(task_id: str) -> Path:
    return VAR / "task-scripts" / str(task_id) / "registry.json"


def skill_registry_path() -> Path:
    return VAR / "registry" / "scripts.json"


def compute_hash(path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def read_registry(path) -> dict:
    """读容器；文件不存在返回默认容器。返回 dict（含 meta 与 scripts）。"""
    p = Path(path)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {"namespace": "code", "target": None, "updated": None,
            "location_rule": None, "scripts": []}


def write_registry(path, container: dict) -> None:
    """原子写整个容器（临时文件+rename），保 meta 由调用方负责原样传入。
    强制 container 为 dict（容器模型）；传裸列表等抛 TypeError，防写坏文件。"""
    if not isinstance(container, dict):
        raise TypeError(f"write_registry 需容器 dict，得 {type(container).__name__}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(container, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(p))


def _merge_meta(base: dict, new: dict) -> dict:
    for k in CONTAINER_META:
        if k in new and new[k] is not None:
            base[k] = new[k]
    return base


def register_l0(task_id: str, script_path, purpose: str, found_issues=None) -> dict:
    """在任务级容器增/改 scripts[] 条目（含 hash；不写 task_id——目录即任务标识）。
    幂等：同 code_path 已存在 → 更新 hash/purpose/run/found_issues。"""
    sp = Path(script_path).resolve()
    stem = sp.stem if sp.stem.startswith("l0_") else "l0_" + sp.stem
    entry = {
        "name": stem,
        "ns": "code",
        "code_path": str(sp).replace("\\", "/"),
        "entrypoint": "main",
        "run": f"python {str(sp).replace(chr(92), '/')}",
        "purpose": purpose,
        "hash": compute_hash(sp),
    }
    if found_issues is not None:
        entry["found_issues"] = found_issues
    rp = task_registry_path(task_id)
    cont = read_registry(rp)
    cont = _merge_meta(cont, {"namespace": "code", "target": str(task_id),
                              "updated": None, "location_rule": None})
    idx = next((i for i, s in enumerate(cont["scripts"]) if s.get("code_path") == entry["code_path"]), None)
    if idx is None:
        cont["scripts"].append(entry)
    else:
        cont["scripts"][idx] = entry
    write_registry(rp, cont)
    return entry


def record_found_issues(task_id: str, name: str, issues) -> dict:
    """把 found_issues 写回任务级条目（评审回填点）。"""
    rp = task_registry_path(task_id)
    cont = read_registry(rp)
    for s in cont["scripts"]:
        if s.get("name") == name:
            s["found_issues"] = issues
            write_registry(rp, cont)
            return s
    raise KeyError(f"registry 无 {name}")


def skill_has(name: str, task_id: str) -> bool:
    """技能级晋升注册表是否已含该脚本（按 task_id+name 匹配）。"""
    cont = read_registry(skill_registry_path())
    return any(s.get("task_id") == task_id and s.get("name") == name for s in cont.get("scripts", []))


def run_registered(name: str, task_id: str) -> dict:
    """代跑两分支（spec §5 W6）：① 已晋升技能级 → hits+1；② 未晋升 → 记 reused_scripts[]。
    返回 {"branch": "hits"|"reused", "name": …, "task_id": …, "detail": "…"}。"""
    if skill_has(name, task_id):
        cont = read_registry(skill_registry_path())
        for s in cont["scripts"]:
            if s.get("task_id") == task_id and s.get("name") == name:
                s["hits"] = int(s.get("hits", 0)) + 1
                write_registry(skill_registry_path(), cont)
                return {"branch": "hits", "name": name, "task_id": task_id,
                        "detail": f"hits={s['hits']}"}
        raise KeyError(f"技能级含 {name} 但匹配失败")
    return {"branch": "reused", "name": name, "task_id": task_id,
            "detail": "未晋升 → 记入本轮 reused_scripts[]（R7 台账产端）"}


def record_false_positive(name: str, task_id: str) -> dict:
    """复审判定误报 → 技能级条目 false_positives+1。"""
    cont = read_registry(skill_registry_path())
    for s in cont["scripts"]:
        if s.get("task_id") == task_id and s.get("name") == name:
            s["false_positives"] = int(s.get("false_positives", 0)) + 1
            write_registry(skill_registry_path(), cont)
            return {"name": name, "false_positives": s["false_positives"]}
    raise KeyError(f"技能级无 {task_id}/{name}")


def build_reuse_ledger(round_id: str, reused_scripts, new_scripts, base_dir=None) -> dict:
    """R7 复用台账行（m2/a3 闭合）：est 取脚本文件实际字符数（无文件按名长代理），并注明估算口径。"""
    reused = list(reused_scripts or [])
    new = list(new_scripts or [])
    total_chars = 0
    for name in reused:
        got = None
        if base_dir:
            for cand_path in (Path(base_dir) / "task-scripts").glob("*"):
                reg = cand_path / "registry.json"
                if reg.exists():
                    try:
                        import json as _j
                        cont = _j.loads(reg.read_text(encoding="utf-8"))
                        hit = next((s for s in cont.get("scripts", [])
                                    if s.get("name") == name and "code_path" in s), None)
                        if hit:
                            fp = Path(hit["code_path"])
                            if fp.exists():
                                got = len(fp.read_text(encoding="utf-8", errors="ignore"))
                                break
                    except Exception:
                        continue
        total_chars += got if got else len(name)
    avg = (total_chars / max(1, len(reused)))
    est = len(reused) * math.ceil(avg / 2)
    return {"round": round_id, "reused_scripts": reused, "new_scripts": new,
            "reused_count": len(reused), "new_count": len(new), "est_saved_tokens": est,
            "est_note": "相对量估算 W≈ceil(字符/2)，文件不可得按名长代理"}


# ---------------- 自测（确定性对抗式：边界/反例/契约） ----------------
def _self_test():
    ok = []
    def chk(name, cond, detail=""):
        ok.append((name, bool(cond), detail))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 1) 容器读写往返保 meta（契约：不覆盖 meta）
        from unittest import mock
        with mock.patch.object(sys.modules[__name__], "VAR", tmp):
            task_registry_path("t1").parent.mkdir(parents=True, exist_ok=True)
            write_registry(task_registry_path("t1"),
                           {"namespace": "code", "target": "t1", "updated": "2026",
                            "location_rule": "var/task-scripts/<t-id>/", "scripts": []})
            # 反例：write_registry 若传裸列表会崩（dict 接口强制）→ 断言 TypeError 路径不写坏
            try:
                write_registry(task_registry_path("t1"), [])   # 裸列表应被拒绝
                chk("写裸列表被拒", False, "未拒绝")
            except (TypeError, AttributeError):
                chk("写裸列表被拒", True)
            cont = read_registry(task_registry_path("t1"))
            chk("容器保 meta", cont["updated"] == "2026" and cont["location_rule"].startswith("var"),
                f"meta={list(cont)}")
            # 2) register_l0 幂等 + hash
            sp = tmp / "l0_demo.py"
            sp.write_text("def main():\n    return 0\nif __name__=='__main__':\n    main()\n", encoding="utf-8")
            e1 = register_l0("t1", sp, "demo")
            e2 = register_l0("t1", sp, "demo2")            # 更新非新增
            cont = read_registry(task_registry_path("t1"))
            chk("register 幂等", len(cont["scripts"]) == 1, f"n={len(cont['scripts'])}")
            chk("hash 稳定", e1["hash"] == e2["hash"] == compute_hash(sp))
            chk("任务级条目不写 task_id", "task_id" not in e1)
            chk("条目字段齐", all(k in e1 for k in ("name", "ns", "code_path", "entrypoint", "run", "purpose", "hash")))
            # 3) run_registered 两分支：未晋升 → reused；晋升（写技能级）→ hits+1
            r1 = run_registered(e1["name"], "t1")
            chk("未晋升→reused", r1["branch"] == "reused", r1["detail"])
            # 构造技能级已晋升
            skill_registry_path().parent.mkdir(parents=True, exist_ok=True)
            write_registry(skill_registry_path(), {"namespace": "code", "target": "skill",
                                                   "scripts": [{"name": e1["name"], "task_id": "t1",
                                                                "code_path": e1["code_path"], "hash": e1["hash"],
                                                                "hits": 0, "false_positives": 0}]})
            r2 = run_registered(e1["name"], "t1")
            chk("已晋升→hits+1", r2["branch"] == "hits" and r2["detail"].endswith("hits=1"), r2["detail"])
            scont = read_registry(skill_registry_path())
            chk("hits 持久化", scont["scripts"][0]["hits"] == 1)
            fp = record_false_positive(e1["name"], "t1")
            chk("false_positives+1", fp["false_positives"] == 1)
            # 4) record_found_issues 回填
            rec = record_found_issues("t1", e1["name"], ["demo-issue"])
            chk("found_issues 回填", rec["found_issues"] == ["demo-issue"])
            # 5) 反例：未知 name → KeyError
            try:
                record_found_issues("t1", "l0_nope", [])
                chk("未知名抛 KeyError", False)
            except KeyError:
                chk("未知名抛 KeyError", True)
    fails = [n for n, c, _ in ok if not c]
    for n, c, d in ok:
        print(f"{'PASS' if c else 'FAIL'} {n} {d}")
    print(f"REGISTRY_IO_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    # CLI：python _registry_io.py set-found <task_id> <name> '<issues json>'
    if len(sys.argv) >= 5 and sys.argv[1] == "set-found":
        try:
            issues = json.loads(sys.argv[4])
        except Exception:
            issues = [sys.argv[4]]
        rec = record_found_issues(sys.argv[2], sys.argv[3], issues)
        print(f"FOUND_ISSUES_SET name={rec['name']}")
        sys.exit(0)
    sys.exit(_self_test())
