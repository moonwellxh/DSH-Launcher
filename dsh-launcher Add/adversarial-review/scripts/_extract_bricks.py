#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-3.1 _extract_bricks.py —— 积木提取器（spec §5 W4 / §4.4；需求 R4）
作用：把候选/任务脚本中的通用片段提取为积木：准入（回归+命中计数）→ 剥任务逻辑（机械只剥
     模块内引用，拆参等语义由 LLM 裁决后走 defaults/重建）→ 参数化纯函数（形参带默认值，
     硬约束 b）→ 内容哈希去重 → 登记 _shared/bricks/registry.json。
输入：源码文本 + 函数名 + admission 计数 + （可选）缺省形参 defaults。
输出：积木条目 dict 或 None（准入未达/缺默认形参/引任务常量 → None+reason 诚实返回）。
复跑：python scripts/_extract_bricks.py <src.py> <func> --task <tid> --admission '{"cross_task":2}'；
     依赖：仅标准库；bricks 根默认 ~/.agents/skills/_shared/bricks，可用环境变量 BRICKS_ROOT 覆盖。
"""
import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path

BRICKS_ROOT = Path(os.environ.get("BRICKS_ROOT", Path.home() / ".agents" / "skills" / "_shared" / "bricks"))


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _defval(node):
    """AST 默认值节点 → JSON 可序列化字面量。"""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        try:
            return ast.unparse(node)
        except Exception:
            return str(node)


def _param_defaults(fn):
    """函数各形参的默认值字面量（无默认 → None）。"""
    out = {}
    pos = list(fn.args.posonlyargs) + list(fn.args.args)
    ndefs = len(fn.args.defaults)
    pos_names = [a.arg for a in pos]
    for i, name in enumerate(pos_names):
        di = i - (len(pos_names) - ndefs)
        out[name] = _defval(fn.args.defaults[di]) if 0 <= di < ndefs else None
    for name, d in zip([a.arg for a in fn.args.kwonlyargs], fn.args.kw_defaults):
        out[name] = _defval(d)
    return out


def admission_ok(admission: dict) -> bool:
    a = admission or {}
    return (int(a.get("cross_task", 0)) >= 2) or (int(a.get("same_task_rounds", 0)) >= 3)


def _global_names_used(body) -> set:
    names = set()
    for n in ast.walk(body):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            names.add(n.id)
    return names


def _top_level_imports(tree) -> set:
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
    return out


def _top_level_assigned(tree) -> set:
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)     # S-3：模块级函数/类名亦属任务胶水——被引则拒绝（需拆参/一并提取）
    return out


def extract_brick(source_text: str, func_name: str, *, task_id: str, source_script: str,
                  admission: dict, defaults: dict = None) -> dict:
    """提取积木。返回 {"action": "registered"|"dedup"|"versioned"|"refused", "brick":…, "reason":…}。"""
    adm = admission or {}
    if not admission_ok(adm):
        return {"action": "refused", "reason": f"准入未达 cross_task={adm.get('cross_task',0)}"
                f" same_task_rounds={adm.get('same_task_rounds',0)}（需 ≥2 任务 或 ≥3 轮）"}
    try:
        tree = ast.parse(source_text)
    except SyntaxError as e:
        return {"action": "refused", "reason": f"源码解析失败: {e}"}
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name), None)
    if fn is None:
        return {"action": "refused", "reason": f"无函数 {func_name}"}
    src = ast.get_source_segment(source_text, fn)
    if src is None:
        return {"action": "refused", "reason": "无法取得函数源码段"}

    # 硬约束 a（拆解边界，机械部分）：函数体不得引用模块级任务常量（胶水）
    assigned = _top_level_assigned(tree) - _top_level_imports(tree)
    used = _global_names_used(fn)
    glue_refs = used & assigned
    if glue_refs:
        return {"action": "refused",
                "reason": f"函数引用模块级常量 {sorted(glue_refs)}（任务胶水）——需 LLM 裁决拆参后重建"}

    # 硬约束 b：所有形参须有默认值；缺者用 defaults 补（LLM 提供），否则拒绝
    param_defaults = _param_defaults(fn)
    missing_defaults = [p for p, v in param_defaults.items() if v is None]
    if missing_defaults:
        if not defaults:
            return {"action": "refused",
                    "reason": f"形参 {missing_defaults} 无默认值——需 LLM 提供 defaults 后重试（硬约束 b）"}
        for p, v in defaults.items():
            if p in missing_defaults:
                src = _inject_default(src, p, v)
                param_defaults[p] = v
                missing_defaults.remove(p)
        if missing_defaults:
            return {"action": "refused",
                    "reason": f"defaults 未覆盖 {missing_defaults}（硬约束 b）"}

    content_hash = _hash(src)
    reg_path = BRICKS_ROOT / "registry.json"
    container = _read_bricks(reg_path)
    existing = next((b for b in container.get("bricks", []) if b.get("name") == func_name), None)
    if existing is not None and existing.get("hash") == content_hash:
        return {"action": "dedup", "brick": existing, "reason": "同内容已登记（幂等），未重复落盘"}
    brick = {"name": func_name, "version": "1.0.0",
             "code_path": str((BRICKS_ROOT / f"{func_name}.py").resolve()).replace("\\", "/"),
             "hash": content_hash,
             "params": param_defaults,
             "changelog": f"首次提取自 {task_id}/{source_script}", "source": {"task_id": task_id,
                                                                               "script": source_script},
             "catalog_ref": True}
    if existing is not None:
        # S-4：同名异内容 = 版本升级（不 append 重复；覆写文件+条目，版本号 +0.1，变更说明追加）
        major, *minor = (existing.get("version") or "1.0.0").split(".")
        try:
            nxt = int(minor[0]) + 1 if minor else 1
        except ValueError:
            nxt = 1
        brick["version"] = f"{major}.{nxt}.0"
        old = existing.get("changelog", "")
        brick["changelog"] = old + f" | 升级自 {task_id}/{source_script}"
        idx = next((i for i, b in enumerate(container["bricks"]) if b.get("name") == func_name), None)
        container["bricks"][idx] = brick
        _write_bricks(reg_path, container)
        (BRICKS_ROOT / f"{func_name}.py").write_text(_module_text(func_name, src), encoding="utf-8")
        return {"action": "versioned", "brick": brick, "reason": "同名异内容 → 版本升级"}
    BRICKS_ROOT.mkdir(parents=True, exist_ok=True)
    container["bricks"].append(brick)
    _write_bricks(reg_path, container)
    (BRICKS_ROOT / f"{func_name}.py").write_text(_module_text(func_name, src), encoding="utf-8")
    return {"action": "registered", "brick": brick}


def _inject_default(src: str, param: str, value) -> str:
    """在 def 行给 param 补默认值（机械文本注入；字符串值加引号，su-1）。"""
    m = re.search(r"(def\s+\w+\s*\([^)]*?)\b" + re.escape(param) + r"(\s*(?:[,)]))", src)
    if not m:
        return src
    vtxt = repr(value) if isinstance(value, str) else str(value)
    return src[:m.start()] + m.group(1) + param + "=" + vtxt + m.group(2) + src[m.end():]


def _module_text(name: str, func_src: str) -> str:
    return (f'"""积木 {name}\n作用：从任务脚本提取的通用函数。\n输入：见函数形参。\n'
            f'输出：函数返回值。\n复跑：import 后调用 {name}（带参/默认值）；依赖：仅标准库。"""\n\n'
            + func_src + "\n")


def _read_bricks(reg_path) -> dict:
    if reg_path.exists():
        try:
            d = json.loads(reg_path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and "bricks" in d:
                return d
        except Exception:
            pass
    return {"namespace": "code", "updated": None, "bricks": []}


def _write_bricks(reg_path, container) -> None:
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = reg_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(container, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(reg_path))


def _self_test():
    import tempfile
    ok = []
    def chk(n, c, d=""):
        ok.append((n, bool(c), d))
    generic = ("import re\n"
               "BASE = 10\n"           # 模块级常量（任务胶水，函数不得引用）
               "def norm_num(s=''):\n"
               "    return re.sub(r'[\\s,，]', '', s or '')\n"
               "def glue():\n"
               "    return BASE + 1\n")
    with tempfile.TemporaryDirectory() as td:
        import os as _os
        _os.environ["BRICKS_ROOT"] = str(Path(td) / "bricks")
        import importlib
        import _extract_bricks as eb
        eb.BRICKS_ROOT = Path(_os.environ["BRICKS_ROOT"])
        # 准入未达 → refused
        r0 = eb.extract_brick(generic, "norm_num", task_id="t", source_script="a.py", admission={})
        chk("准入未达 refused", r0["action"] == "refused" and "准入" in r0["reason"])
        # 提取成功（回归+计数达标；纯函数，不引 BASE）
        r1 = eb.extract_brick(generic, "norm_num", task_id="tA", source_script="a.py",
                              admission={"cross_task": 2})
        chk("提取 registered", r1["action"] == "registered", r1.get("reason", ""))
        b1 = r1["brick"]
        chk("条目字段齐", all(k in b1 for k in ("name", "version", "code_path", "hash", "params", "changelog", "source")))
        chk("params 带默认", b1["params"].get("s") is not None or str(b1["params"].get("s")).find("=") >= 0
            or b1["params"].get("s") == "", f"params={b1['params']}")
        chk("模块落盘", (Path(td) / "bricks" / "norm_num.py").exists())
        # 幂等去重：同内容重提 → dedup 不重复
        r2 = eb.extract_brick(generic, "norm_num", task_id="tB", source_script="b.py",
                              admission={"same_task_rounds": 3})
        chk("同内容 dedup", r2["action"] == "dedup", r2.get("reason", ""))
        reg = json.loads((Path(td) / "bricks" / "registry.json").read_text(encoding="utf-8"))
        chk("registry 仅一条积木", len(reg["bricks"]) == 1)
        # 引用模块级常量（胶水）→ refused
        gluey = ("VAL = 7\n"
                 "def bad(v=''):\n"
                 "    return int(v or VAL)\n")
        r3 = eb.extract_brick(gluey, "bad", task_id="t", source_script="g.py",
                              admission={"cross_task": 2})
        chk("引任务常量 refused（需拆参）", r3["action"] == "refused" and "常量" in r3["reason"])
        # 缺默认形参且无 defaults → refused；有 defaults → 注入成功
        no_def = ("def add(a, b):\n    return a + b\n")
        r4 = eb.extract_brick(no_def, "add", task_id="t", source_script="n.py",
                              admission={"cross_task": 2})
        chk("无默认形参 refused", r4["action"] == "refused" and "默认值" in r4["reason"])
        r5 = eb.extract_brick(no_def, "add", task_id="t", source_script="n.py",
                              admission={"cross_task": 2}, defaults={"a": 0, "b": 0})
        chk("注入默认后 registered", r5["action"] == "registered", r5.get("reason", ""))
        # S-4：同名异内容 → 版本升级（不 append 重复）
        changed = ("def add(a=0, b=0):\n    return a + b + 1\n")
        r6 = eb.extract_brick(changed, "add", task_id="t", source_script="n2.py",
                              admission={"cross_task": 2})
        chk("同名异内容→版本升级", r6["action"] == "versioned" and r6["brick"]["version"].startswith("1.1"), r6["brick"]["version"])
        reg2 = json.loads((Path(td) / "bricks" / "registry.json").read_text(encoding="utf-8"))
        chk("版本升级不产生重复条目", len([b for b in reg2["bricks"] if b["name"] == "add"]) == 1)
        # S-3：引模块级函数（helper）→ refused（需拆/一并提取，防 import NameError）
        uses_helper = ("def _h(x=''):\n    return x\n"
                       "def use(v=''):\n    return _h(v)\n")
        r7 = eb.extract_brick(uses_helper, "use", task_id="t", source_script="u.py",
                              admission={"cross_task": 2})
        chk("引模块级函数 refused", r7["action"] == "refused" and ("常量" in r7["reason"] or "函数" in r7["reason"] or "胶水" in r7["reason"]), r7["reason"])
        _os.environ.pop("BRICKS_ROOT", None)
    fails = [n for n, c, _ in ok if not c]
    for n, c, d in ok:
        print(f"{'PASS' if c else 'FAIL'} {n} {d}")
    print(f"EXTRACT_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    # CLI（对齐 docstring，m1/a4 闭合）：python _extract_bricks.py <src.py> <func> --task <tid> --admission '<json>'
    args = sys.argv[1:]
    if len(args) >= 2 and Path(args[0]).exists():
        src = Path(args[0]).read_text(encoding="utf-8")
        adm = {}
        task = "cli"
        i = 2
        while i < len(args):
            if args[i] == "--task" and i + 1 < len(args):
                task = args[i + 1]; i += 2
            elif args[i] == "--admission" and i + 1 < len(args):
                try:
                    adm = json.loads(args[i + 1])
                except Exception:
                    print(json.dumps({"error": "admission JSON 解析失败", "hint": args[i + 1]}, ensure_ascii=False))
                    sys.exit(2)
                i += 2
            else:
                i += 1
        out = extract_brick(src, args[1], task_id=task, source_script=args[0], admission=adm)
        if out["action"] == "refused":
            print(json.dumps({"error": "refused", "reason": out.get("reason")}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps({"ok": out["action"], "brick": out["brick"]["name"],
                          "version": out["brick"]["version"]}, ensure_ascii=False))
        sys.exit(0)
    sys.exit(_self_test())
