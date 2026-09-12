#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WBS-3.2 _gen_catalog.py —— 技能级可用积木清单生成器（spec §5 W5 / §4.4；需求 R5）
作用：从 _shared/bricks/ 目录 + registry.json 确定性生成 catalog.json（机器）与 catalog.md（人读）。
输入：bricks 根（默认 ~/.agents/skills/_shared/bricks，可 BRICKS_ROOT 覆盖）。
输出：catalog.json / catalog.md（同目录）。
复跑：python scripts/_gen_catalog.py [bricks_root]；依赖：仅标准库。
"""
import json
import sys
from pathlib import Path

BRICKS_DEFAULT = Path.home() / ".agents" / "skills" / "_shared" / "bricks"


def gen_catalog(bricks_root) -> dict:
    root = Path(bricks_root)
    reg = root / "registry.json"
    entries = []
    if reg.exists():
        try:
            d = json.loads(reg.read_text(encoding="utf-8"))
            entries = d.get("bricks", [])
        except Exception:
            entries = []
    enriched = []
    for e in entries:
        mod = root / f"{e['name']}.py"
        en = dict(e)
        en["module_exists"] = mod.exists()
        en["entrypoint"] = e["name"]
        en["run"] = f"import {e['name']}"
        enriched.append(en)
    entries = enriched
    catalog = {"namespace": "code", "kind": "bricks",
               "generated": None, "count": len(entries), "bricks": entries}
    (root / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 可用积木清单（跨任务）", "",
             "| 积木 | 作用 | 适用 ns | 路径 | 入口 | 复跑 |", "|---|---|---|---|---|---|"]
    for e in entries:
        lines.append(f"| {e['name']} | {e.get('changelog','')} | code | "
                     f"`{e['code_path']}` | `{e['name']}` | import {e['name']} |")
    (root / "catalog.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"count": len(entries), "catalog_json": str((root / "catalog.json").resolve()),
            "catalog_md": str((root / "catalog.md").resolve())}


def _self_test():
    import tempfile
    ok = []
    def chk(n, c, d=""):
        ok.append((n, bool(c), d))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "bricks"
        root.mkdir(parents=True)
        (root / "registry.json").write_text(json.dumps(
            {"namespace": "code", "bricks": [{"name": "norm_num", "version": "1.0.0",
                                               "code_path": str(root / "norm_num.py"),
                                               "hash": "abc", "params": {"s": ""},
                                               "changelog": "提取自 pdf-parse-v3/gate.py"}]},
            ensure_ascii=False), encoding="utf-8")
        (root / "norm_num.py").write_text("def norm_num(s=''):\n    return s\n", encoding="utf-8")
        res = gen_catalog(root)
        cj = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        chk("catalog.json 含积木", cj["count"] == 1 and cj["bricks"][0]["name"] == "norm_num"
            and cj["bricks"][0]["module_exists"] is True)
        md = (root / "catalog.md").read_text(encoding="utf-8")
        chk("catalog.md 含积木行", "norm_num" in md)
        chk("返回双路径", res["catalog_json"].endswith("catalog.json") and res["catalog_md"].endswith("catalog.md"))
        # 空目录 → count=0 不炸
        empty = Path(td) / "empty"
        empty.mkdir()
        res0 = gen_catalog(empty)
        chk("空目录 count=0", res0["count"] == 0)
    fails = [n for n, c, _ in ok if not c]
    for n, c, d in ok:
        print(f"{'PASS' if c else 'FAIL'} {n} {d}")
    print(f"CATALOG_SELFTEST pass={len(ok)-len(fails)} fail={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        r = gen_catalog(sys.argv[1])
        print(f"CATALOG count={r['count']} -> {r['catalog_json']}")
        sys.exit(0)
    sys.exit(_self_test())
