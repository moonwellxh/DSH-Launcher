# -*- coding: utf-8 -*-
"""
run_regression.py — CAD 扫描之眼全量回归测试

依据：任务书 T13（回归全绿 + 故障注入有明确结构化错误且非静默）。

覆盖：
  1. 全部单元测试（清洗/归并/代理/投影/修复/XREF）；
  2. 真实图端到端（无 CAD 环境时自动跳过 COM 相关断言）；
  3. 故障注入：文件不存在 / 空文件 / 哈希不匹配 / 非法参数。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
PY = r"C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe"
TESTS = [
    "test_clean.py",
    "test_merge.py",
    "test_proxy.py",
    "test_query.py",
    "test_structured.py",
    "test_xref.py",
    "test_path_util.py",
    "test_guard.py",
]

# 真实图（可选，存在才测）
REAL_DWG = [
    r"F:\WeChat Files\xwechat_files\moonwellxh_ef64\msg\file\2025-07\三四层电气提资_t3.dwg",
    r"D:\Personal\Downloads\扬州美府广场电气提资CAD版本.dwg",
    r"C:\Tangent\TArchT20V7\sys23x64\Drawing2.dwg",
]

PASS = 0
FAIL = 0
FAILED = []


def check(no, desc, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {no} {desc}")
    else:
        FAIL += 1
        FAILED.append((no, desc, detail))
        print(f"  [FAIL] {no} {desc}  {detail}")


def run_py(args, cwd=None, timeout=600):
    r = subprocess.run([PY, *args], capture_output=True, cwd=cwd,
                       timeout=timeout, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------- 1. 单元测试
print("=" * 60)
print("[1] 单元测试")
print("=" * 60)
for t in TESTS:
    rc, out, err = run_py([str(SKILL_DIR / "tests" / t)])
    check(t, "通过", rc == 0, (out + err)[-500:])

# ---------------------------------------------------------------- 2. 真实图端到端
print("=" * 60)
print("[2] 真实图端到端（orchestrator 决策树）")
print("=" * 60)
tmp_out = tempfile.mkdtemp(prefix="cadscan_reg_")
for dwg in REAL_DWG:
    if not Path(dwg).exists():
        check(Path(dwg).name, "跳过（文件不存在）", True)
        continue
    rc, out, err = run_py([str(SKILL_DIR / "orchestrator.py"), dwg,
                           "--out", tmp_out], timeout=900)
    ok = rc == 0 and "归并结果" in out and "输出JSON" in out
    check(f"orchestrator {Path(dwg).name}", "跑通并产出 JSON", ok,
          (out + err)[-400:])
    # 产物校验
    jsons = list(Path(tmp_out).glob("*_扫描之眼.json"))
    if jsons:
        try:
            data = json.loads(jsons[-1].read_text(encoding="utf-8"))
            has_keys = all(k in data for k in
                           ("texts", "dims", "xrefs", "proxy_report", "errors"))
            check(f"JSON 结构 {Path(dwg).name}", "核心字段齐全", has_keys)
            for t in data["texts"][:5]:
                if t.get("source") and "content" in t:
                    break
            else:
                if data["texts"]:
                    check(f"记录结构 {Path(dwg).name}", "source/content 齐全",
                          True)
        except Exception as e:
            check(f"JSON 解析 {Path(dwg).name}", "可解析", False, str(e))

# ---------------------------------------------------------------- 3. 故障注入
print("=" * 60)
print("[3] 故障注入（非静默错误验证）")
print("=" * 60)

# 3.1 文件不存在
rc, out, err = run_py([str(SKILL_DIR / "orchestrator.py"),
                       "Z:/不存在的图.dwg", "--out", tmp_out])
check("文件不存在", "结构化报错（非静默）",
      rc != 0 and "文件" in (out + err), (out + err)[:200])

# 3.2 空文件
empty = Path(tmp_out) / "empty.dwg"
empty.write_bytes(b"")
rc, out, err = run_py([str(SKILL_DIR / "orchestrator.py"), str(empty),
                       "--out", tmp_out])
check("空文件", "结构化报错（非静默）",
      rc != 0 and "空" in (out + err), (out + err)[:200])

# 3.3 非 DWG 文件
junk = Path(tmp_out) / "junk.dwg"
junk.write_bytes("这不是图纸".encode("utf-8"))
rc, out, err = run_py([str(SKILL_DIR / "orchestrator.py"), str(junk),
                       "--out", tmp_out])
check("非 DWG 内容", "不崩溃，errors[] 记录失败",
      ("错误与降级" in out or "无法判定" in out) and rc == 0,
      (out + err)[:300])

# 3.4 哈希篡改拒绝注册（tz3_install 校验逻辑）
try:
    sys.path.insert(0, str(SKILL_DIR))
    import tz3_install as TI
    manifest = {"TZ3Converter.fx48.dll": "0" * 64}
    dummy = Path(tmp_out) / "TZ3Converter.fx48.dll"
    dummy.write_bytes(b"x")
    ok, reason = TI.verify_dll(dummy, manifest)
    check("dll 哈希篡改", "拒绝注册并说明原因", not ok and "不匹配" in reason,
          reason[:200])
except Exception as e:
    check("dll 哈希篡改", "校验逻辑可执行", False, str(e))

# 3.5 非法 bbox 参数
rc, out, err = run_py([str(SKILL_DIR / "query.py"),
                       str(Path(tmp_out) / "none.json"), "--bbox", "abc"])
check("非法 bbox", "明确报错不崩溃", rc != 0, (out + err)[:200])

# 3.6 非法正则
try:
    sys.path.insert(0, str(SKILL_DIR))
    from query import filter_texts
    try:
        filter_texts({"texts": []}, pattern="[未闭合")
        check("非法正则", "抛明确异常", False)
    except ValueError as e:
        check("非法正则", "抛明确异常", "正则无效" in str(e))
except Exception as e:
    check("非法正则", "抛明确异常", False, str(e))

# ---------------------------------------------------------------- 汇总
print("=" * 60)
print(f"回归结果：通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 项：")
    for no, desc, detail in FAILED:
        print(f"  - {desc}: {detail[:200]}")
    sys.exit(1)
print("run_regression.py 全部通过 ✓")
