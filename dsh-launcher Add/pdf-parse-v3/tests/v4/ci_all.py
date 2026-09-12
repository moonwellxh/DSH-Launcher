#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/ci_all.py —— v4 CI 一键运行器（R-07/升级步 8）
==================================================================
作用：离线一键回归 v4 全部测试（既有四件 + 新增三件）+ 语法编译 + 文档-实物一致校验。
输入：无；输出：逐套 RESULT + 汇总 + 退出码。
复跑：python tests/v4/ci_all.py   （零网络、零出域；hash 数值等真实断言）
"""
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
V4 = SKILL / "assets" / "v4"
TESTS = Path(__file__).resolve().parent

SUITES = ["test_ms1_smoke.py", "test_ms2_replay.py", "test_ms3_ladder.py",
          "test_ms5_acceptance.py", "test_triage.py", "test_render.py",
          "test_orchestrator_pdf.py"]

PY = sys.executable


def compile_all():
    """语法编译 v4 全部 py + 新增。"""
    bad = []
    files = sorted(V4.glob("*.py"))
    for f in files:
        r = subprocess.run([PY, "-m", "py_compile", str(f)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            bad.append(f.name)
    return bad, len(files)


def check_doc_consistency():
    """文档-实物一致（R-04 处理遗留 C-6/C-A2）：①找不到 CLI 示例行→False（非空转）；
    ②正向 skill 旗标 ⊆ argparse 旗标；③反向 argparse 公开旗标（−4 兼容内部）⊆ skill（R-04 新增，旗标集口径注：
    位置参数 <pdf> 恒同现不参与旗标集合差）；模块清单对文件。返回 (ok, details)。"""
    sk = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    orc_src = (V4 / "orchestrator.py").read_text(encoding="utf-8")
    details = []
    import re
    cli_line = None
    for line in sk.splitlines():
        if "orchestrator.py <pdf>" in line:
            cli_line = line
            break
    if cli_line is None:
        return False, ["SKILL.md 缺 orchestrator.py <pdf> CLI 示例行（无法对账）"]
    args_in_skill = set(re.findall(r"--[\w-]+", cli_line))
    args_in_parse = set(re.findall(r'add_argument\("(--[\w-]+)"', orc_src))   # 只取旗标；<pdf> 位置参数不在旗标集（严重-1 修复）
    missing_fwd = args_in_skill - args_in_parse            # 正向：skill ⊆ argparse
    COMPAT_INTERNAL = {"--page-image", "--page", "--render-reg-json", "--doc-sha1"}
    public = args_in_parse - COMPAT_INTERNAL
    missing_rev = public - args_in_skill                   # 反向（R-04）：公开旗标 ⊆ skill
    ok1 = (not missing_fwd) and (not missing_rev)
    details.append("CLI: skill%s ⊆ argparse%s fwd_missing=%s rev_missing=%s" % (
        sorted(args_in_skill), sorted(args_in_parse), sorted(missing_fwd), sorted(missing_rev)))
    # 2) SKILL.md 模块清单（含 M1..M14 名）关键模块对实物
    need_mods = ["triage", "render", "vision_client", "textlayer", "ocr_channel",
                 "table_adapter", "gate", "defect_ladder", "structurer", "figures",
                 "quality", "orchestrator", "serialize_md", "serialize_html",
                 "geo_rebuild", "pipeline", "config.default"]
    files_exist = {f.stem for f in V4.glob("*") if f.suffix in (".py", ".json")}
    missing_mods = [m for m in need_mods if m not in files_exist
                    and m != "config.default" or (m == "config.default"
                                                  and not (V4 / "config.default.json").exists())]
    ok2 = not missing_mods
    details.append("mods missing=%s" % missing_mods)
    return ok1 and ok2, details


def main():
    # 输出编码钉死（Step 8 CI 修复 S1）：details 含 ⊆ 等非 GBK 字符，裸命令/重定向下须 UTF-8 防 UnicodeEncodeError 假红
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    results = {}
    total_pass = total_fail = 0
    for tn in SUITES:
        r = subprocess.run([PY, str(TESTS / tn)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=900)
        tail = [ln for ln in (r.stdout or "").splitlines()
                if "RESULT" in ln and ("pass=" in ln or "fail=" in ln)]
        results[tn] = {"rc": r.returncode, "tail": tail}
        import re as _re
        for ln in tail:
            mm = _re.search(r"pass=(\d+)\s+fail=(\d+)", ln)
            if mm:
                total_pass += int(mm.group(1))
                total_fail += int(mm.group(2))
    bad_compile, n_files = compile_all()
    doc_ok, doc_details = check_doc_consistency()

    print("== v4 CI 汇总 ==")
    for tn, res in results.items():
        print("  %-28s rc=%d %s" % (tn, res["rc"], " ".join(res["tail"])))
    print("  compile           py=%d bad=%s" % (n_files, bad_compile or "0"))
    print("  doc-consistency   ok=%s %s" % (doc_ok, doc_details))
    print("== TOTAL pass=%d fail=%d ==" % (total_pass, total_fail))
    all_green = all(res["rc"] == 0 for res in results.values()) and not bad_compile and doc_ok \
        and total_pass > 0
    print("RESULT CI %s" % ("ALL_GREEN" if all_green else "FAIL"))
    sys.exit(0 if all_green else 1)


if __name__ == "__main__":
    main()
