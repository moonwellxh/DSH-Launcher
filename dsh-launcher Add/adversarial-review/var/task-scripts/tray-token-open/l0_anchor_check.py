#!/usr/bin/env python3
"""l0_anchor_check.py

作用: 确定性校验（零模型判断）——把设计文档里每处 `文件:行` 反引号锚点抽出来，
      逐条核对"该文件存在、该行号在范围内、该行内容是什么"，并独立重算文档引用的
      本机事实（版本号/日志行数/parts 编码）。只输出观测值，不判断文档结论对错。
输入: --doc <设计文档路径>（默认 D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md）
输出: stdout 逐条明细（ASCII 安全，中文以 utf-8 写出）+ 末行单行 JSON 摘要
      {'total':n,'ok':n,'fail':n,'failures':[...]}
复跑: python l0_anchor_check.py --doc "<doc>"
依赖: 标准库 + git（用于核对上游 tag 文件；缺失时对应条目记为 skip）
"""
import argparse
import json
import os
import re
import subprocess
import sys

TAG = "dsh-v0.1.5-rc.1"
REPO = r"C:\Users\雍远\deepseek-harness"
SKILL = os.path.join(os.environ.get("USERPROFILE", ""), ".agents", "skills", "dsh-launcher")
PARTS = os.path.join(SKILL, "assets", "tmpl", "parts")
DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md"

CITE = re.compile(r"`([^`\s]+?\.(?:ps1|json|md|ts|log|yaml|yml|jsonl))((?::[0-9]+(?:[,\-][0-9]+)*)*)`")


def line_numbers(spec):
    out = []
    for token in spec.strip(":").split(":"):
        if not token:
            continue
        for part in token.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                if a.strip().isdigit() and b.strip().isdigit():
                    out.extend(range(int(a), int(b) + 1))
            elif part.isdigit():
                out.append(int(part))
    return out


def resolve(path):
    """Return ('local', abspath) | ('upstream', gitpath) | ('bare-log', abspath) | ('skip', reason)."""
    if re.match(r"^[A-Za-z]:[\\/]", path):
        return ("local", path)
    if path.startswith(("$", "~", "%")):
        return ("skip", "env-var or home-relative path")
    if path.endswith("dsh-web.log"):
        return ("bare-log", r"D:\DSHS\dsh-web.log")
    if path.startswith(("packages/", "apps/", ".agents/")):
        return ("upstream", path)
    if path.startswith(".../"):
        return ("local", os.path.join(SKILL, "assets", "tmpl", path[4:]))
    if "/" in path:
        return ("local", os.path.join(SKILL, path))
    # bare filename
    for cand in (os.path.join(PARTS, path), os.path.join(SKILL, path), os.path.join(SKILL, "assets", path),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), path)):
        if os.path.exists(cand):
            return ("local", cand)
    return ("skip", "unresolved bare name")


def read_lines(kind, target):
    if kind == "upstream":
        try:
            out = subprocess.run(["git", "-C", REPO, "show", TAG + ":" + target],
                                 capture_output=True, timeout=60)
            if out.returncode != 0:
                return None, "git show failed: " + out.stderr.decode("utf-8", "replace").strip()[:120]
            return out.stdout.decode("utf-8", "replace").splitlines(), None
        except Exception as exc:  # noqa: BLE001
            return None, "git unavailable: %s" % exc
    if not os.path.exists(target):
        return None, "missing file"
    with open(target, "rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8", "replace").splitlines(), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    args = ap.parse_args()

    with open(args.doc, "rb") as fh:
        doc = fh.read().decode("utf-8", "replace")
    doc_lines = doc.splitlines()

    # de-dup citations, keep first-seen order, ignore pure-prose backticks
    seen, cites = set(), []
    for lineno, text in enumerate(doc_lines, 1):
        for m in CITE.finditer(text):
            key = (m.group(1), m.group(2))
            if key in seen:
                continue
            seen.add(key)
            cites.append((lineno, m.group(1), m.group(2)))

    results, failures = [], []
    for docline, path, spec in cites:
        kind, target = resolve(path)
        want = line_numbers(spec)
        if kind == "skip":
            results.append({"path": path, "status": "skip", "note": target})
            continue
        lines, err = read_lines(kind, target)
        if lines is None:
            status = "fail" if (err == "missing file" or err.startswith("git show failed")) else "skip"
            rec = {"path": path, "kind": kind, "target": target, "status": status,
                   "note": err, "doc_line": docline}
            results.append(rec)
            if status == "fail":
                failures.append(rec)
            continue
        if want and max(want) > len(lines):
            rec = {"path": path, "kind": kind, "target": target, "status": "fail",
                   "note": "cited line %d > file lines %d" % (max(want), len(lines)), "doc_line": docline}
            results.append(rec)
            failures.append(rec)
            continue
        samples = []
        for n in want[:3]:
            content = lines[n - 1].strip()
            samples.append("%d: %s" % (n, content[:110]))
        results.append({"path": path, "kind": kind, "target": target, "status": "ok",
                        "lines": want, "samples": samples, "doc_line": docline})

    # independent recomputation of local facts asserted by the doc
    facts = {}
    pkg = os.path.join(REPO, "package.json")
    try:
        with open(pkg, "rb") as fh:
            facts["harness_version"] = json.loads(fh.read().decode("utf-8"))["version"]
    except Exception as exc:  # noqa: BLE001
        facts["harness_version"] = "ERROR: %s" % exc
    logp = r"D:\DSHS\dsh-web.log"
    if os.path.exists(logp):
        with open(logp, "rb") as fh:
            raw = fh.read()
        txt = raw.decode("utf-8", "replace")
        facts["dsh_web_log_lines"] = len([x for x in txt.splitlines() if x.strip()])
        facts["dsh_web_log_last"] = txt.strip().splitlines()[-1][:80] if txt.strip() else ""
    else:
        facts["dsh_web_log_lines"] = "missing"
    facts["tray_bom_utf8"] = None
    tray = r"D:\DSHS\DSH-tray.ps1"
    if os.path.exists(tray):
        with open(tray, "rb") as fh:
            head = fh.read(3)
        facts["tray_bom_utf8"] = head == b"\xef\xbb\xbf"
        facts["tray_size"] = os.path.getsize(tray)
    enc = {}
    for name in ("10-utils.ps1", "90-main.ps1", "50-url.ps1", "60-dialogs.ps1"):
        p = os.path.join(PARTS, name)
        if not os.path.exists(p):
            enc[name] = "missing"
            continue
        with open(p, "rb") as fh:
            raw = fh.read()
        enc[name] = {"bom": raw[:3] == b"\xef\xbb\xbf",
                     "nonascii": sum(1 for b in raw if b > 0x7F),
                     "bytes": len(raw)}
    facts["parts_encoding"] = enc
    try:
        tag = subprocess.run(["git", "-C", REPO, "rev-parse", TAG],
                             capture_output=True, timeout=30)
        facts["tag_resolves"] = tag.returncode == 0
    except Exception:  # noqa: BLE001
        facts["tag_resolves"] = "git unavailable"

    for rec in results:
        print("[%s] %s (%s) %s" % (rec["status"].upper(), rec.get("path"), rec.get("kind", "-"),
                                   rec.get("note", "")))
        for s in rec.get("samples", []):
            print("      " + s)
    print("--- independent facts ---")
    print(json.dumps(facts, ensure_ascii=True, sort_keys=True))
    summary = {"total": len(results), "ok": sum(1 for r in results if r["status"] == "ok"),
               "skip": sum(1 for r in results if r["status"] == "skip"),
               "fail": len(failures), "failures": [f.get("path") for f in failures]}
    print(json.dumps(summary, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
