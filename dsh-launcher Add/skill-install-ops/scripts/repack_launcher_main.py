#!/usr/bin/env python3
"""Rebuild the launcher main package with official excludes; verify against git HEAD baseline."""
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
SLUG = "skill-install-ops"
MASTER = "C:\\Users\\雍远\\.agents\\skills\\dsh-launcher"
MIRROR = "C:\\Users\\雍远\\.dsh\\gh-sync\\DSH-Launcher"
REL = os.path.join(MIRROR, "releases", "v1.1.92")
MAIN = os.path.join(REL, "dsh-launcher__skillhub.zip")
EMB = "dsh-launcher/assets/配套技能/%s__skillhub.zip" % SLUG
RULES = [r"(^|[\\/])var[\\/]", r"^assets/install-dir\.txt$",
         r"(^|/)(config\.json|credentials[^/]*|\.dsh[^/]*|[^/]*\.token[^/]*)$",
         r"(^|[\\/])tests[\\/]vision_shootout[\\/]", r"(^|[\\/])_backup([\\/]|$)"]
fails = []

# baseline = committed HEAD (not the file itself!)
head = os.path.join(os.environ.get("TEMP", "."), "head_main2.zip")
r = subprocess.run(["git", "-C", MIRROR, "show", "HEAD:releases/v1.1.92/dsh-launcher__skillhub.zip"],
                   capture_output=True)
open(head, "wb").write(r.stdout)
zh = zipfile.ZipFile(head)
b = set(n for n in zh.namelist() if not n.endswith("/"))
print("基线（HEAD 发布版）条目=%d" % len(b))

kept = []
for root, dirs, files in os.walk(MASTER):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if f.endswith(".pyc"):
            continue
        rel = os.path.relpath(os.path.join(root, f), MASTER).replace("\\", "/")
        if not any(re.search(p, rel) for p in RULES):
            kept.append(rel)
with zipfile.ZipFile(MAIN, "w", zipfile.ZIP_DEFLATED) as zm:
    for rel in sorted(kept):
        zm.write(os.path.join(MASTER, rel), "dsh-launcher/" + rel)
zm = zipfile.ZipFile(MAIN)
a = set(n for n in zm.namelist() if not n.endswith("/"))
print("重打后条目=%d" % len(a))
if b - a:
    fails.append("丢失条目: %s" % sorted(b - a)[:5])
else:
    print("✓ 判据1 无丢失：HEAD 全部条目保留")
# 判据2（审查更正后读法）：差集只说明"基线没有、现态有"；配套被替换时不进差集（同名），故不做等值断言
only_new = sorted(a - b)
print("判据2 状态差集（基线无、现态有）=%s" % only_new)
extra_non_companion = [n for n in only_new if "/assets/配套技能/" not in n]
if extra_non_companion:
    fails.append("差集含非配套条目: %s" % extra_non_companion)
else:
    print("✓ 判据2 差集内无「非配套」条目（新增只发生在配套目录）")
# 判据3：共有条目内容变化 —— 应只含本轮真正改动的配套；0 条说明改动没打进去；含非配套＝重打越界
COMPDIR = "dsh-launcher/assets/配套技能/"
changed = [n for n in sorted(b) if zm.read(n) != zh.read(n)]
comp_changed = [n for n in changed if n.startswith(COMPDIR)]
non_comp_changed = [n for n in changed if not n.startswith(COMPDIR)]
print("判据3 共有条目内容变化=%d 条：配套 %s ｜ 非配套 %d %s"
      % (len(changed), [x.split("/")[-1] for x in comp_changed], len(non_comp_changed),
         non_comp_changed[:3]))
if non_comp_changed:
    fails.append("非配套条目被改动: %s" % non_comp_changed[:3])
if not comp_changed:
    fails.append("没有任何配套内容变化——改动可能没打进包（漏更新）")
else:
    print("✓ 判据3 变化仅发生在配套目录且非空")

# embedded companion must equal the distributed one, and carry the new version
comp = os.path.join(MASTER, "assets", "配套技能", "%s__skillhub.zip" % SLUG)
emb_bytes = zm.read(EMB)
ck1 = hashlib.sha256(emb_bytes).hexdigest() == hashlib.sha256(open(comp, "rb").read()).hexdigest()
zz = zipfile.ZipFile(__import__("io").BytesIO(emb_bytes))
mm = json.loads(zz.read("%s/_meta.json" % SLUG).decode("utf-8-sig"))
ents = [n.split("/", 1)[1] for n in zz.namelist()]
print("内嵌配套 version=%s 条目=%s 与技能侧逐字节一致=%s" % (mm["version"], ents, ck1))
if not ck1 or mm["version"] != "1.1.13" or any(".bak" in e for e in ents):
    fails.append("内嵌配套不正确")
print("主包 %d B %s" % (os.path.getsize(MAIN), hashlib.sha256(open(MAIN, "rb").read()).hexdigest()[:16].upper()))
print("\nRESULT: %s" % ("ALL PASS" if not fails else "FAIL %s" % fails))
sys.exit(0 if not fails else 1)
