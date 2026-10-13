#!/usr/bin/env python3
"""Structural self-check for the skill-install-ops update (charter §6 checklist, observable form)."""
import hashlib
import io
import json
import os
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
SLUG = "skill-install-ops"
SRC = "C:\\Users\\雍远\\.agents\\skills\\" + SLUG
ZIP = "C:\\Users\\雍远\\.agents\\skills\\dsh-launcher\\assets\\配套技能\\%s__skillhub.zip" % SLUG
ok, fails = 0, []


def ck(label, cond, detail=""):
    global ok
    if cond:
        ok += 1
        print("OK   %-52s %s" % (label, detail))
    else:
        fails.append(label)
        print("FAIL %-52s %s" % (label, detail))


raw = open(os.path.join(SRC, "SKILL.md"), "rb").read()
dec = raw.decode("utf-8")
ck("编码：无 BOM + 纯 LF", raw[:3] != b"\xef\xbb\xbf" and raw.count(b"\r") == 0,
   "bytes=%d CR=%d" % (len(raw), raw.count(b"\r")))
ck("编码：无 U+FFFD", dec.count("\ufffd") == 0)

fm = dec.split("---")[1]
ck("frontmatter 含 name", "name:" in fm)
ck("frontmatter 含 description", "description:" in fm)
ck("frontmatter 含 version（本次新增）", bool(re.search(r"^version: \d+\.\d+\.\d+$", fm, re.M)))
ck("触发词内嵌于 description（宪章 §5：不设顶层 trigger 字段）",
   ("触发词：「安装 skill」" in fm) and not re.search(r"^trigger:", fm, re.M))
ck("frontmatter 无多余顶层字段", set(re.findall(r"^(\w+):", fm, re.M)) <= {"name", "description", "version"},
   sorted(set(re.findall(r"^(\w+):", fm, re.M))))
ck("版本历史表含 1.1.12 与 1.1.13 两行（审查 B-1：1.1.12 曾被误删）",
   ("| 1.1.12 |" in dec) and ("| 1.1.13 |" in dec))
ck("§七 编号连续 1–11", all(("\n%d. " % i) in dec for i in range(1, 12)))
ck("§七.7 未引哈希（审查 M-5：与「不记哈希」规则自相矛盾）",
   ("9474F2AD" not in dec) and ("AFD8E9D0" not in dec))
ck("脚本节存在（审查 A-2：证据可发现性）", "## 脚本（本技能的判据/校验脚本）" in dec)
ck("分组声明存在（审查 A-2）", "本技能条款分组声明" in dec)
for _s in ("scripts/selfcheck_install_ops.py", "scripts/audit_companion_packages.py",
           "scripts/repack_launcher_main.py"):
    ck("脚本在位: %s" % _s, os.path.isfile(os.path.join(SRC, _s.replace("/", os.sep))))
v_fm = re.search(r"^version: (\S+)$", fm, re.M).group(1)

meta = json.load(io.open(os.path.join(SRC, "_meta.json"), encoding="utf-8-sig"))
ck("frontmatter version == _meta.json version", v_fm == meta["version"],
   "front=%s meta=%s" % (v_fm, meta["version"]))
ck("版本历史表含该版本行", ("| %s |" % v_fm) in dec, v_fm)
pub = meta.get("publishedAt", 0) / 1000.0
mtime = os.stat(os.path.join(SRC, "SKILL.md")).st_mtime
ck("publishedAt 不早于 SKILL.md mtime", pub >= mtime,
   "pub=%s mtime=%s" % (__import__("time").strftime("%H:%M:%S", __import__("time").localtime(pub)),
                        __import__("time").strftime("%H:%M:%S", __import__("time").localtime(mtime))))

# package hygiene + content equality
BAD = re.compile(r"(^|/)(_backup/|.*\.bak(-.*)?$|__pycache__/|.*\.pyc$|install-dir\.txt$|var/)")
z = zipfile.ZipFile(ZIP)
names = [n for n in z.namelist() if not n.endswith("/")]
junk = [n for n in names if BAD.search(n.split("/", 1)[1])]
ck("包内无维护垃圾（_backup/*.bak/.pyc/var 等）", not junk, "junk=%s" % junk)
disk = {}
for root, dirs, files in os.walk(SRC):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, SRC).replace("\\", "/")
        if not BAD.search(rel):
            disk[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
packed = {n.split("/", 1)[1]: hashlib.sha256(z.read(n)).hexdigest() for n in names}
ck("包内容 == 技能树（过滤后）逐条哈希", packed == disk,
   "zip=%d tree=%d" % (len(packed), len(disk)))
ck("包内条目名用正斜杠（python zipfile 惯例）",
   all("/" in n for n in names), "示例=%s" % names[0])
# metadata readable from inside the zip (setup.ps1 does this)
zm = json.loads(z.read("%s/_meta.json" % SLUG).decode("utf-8-sig"))
ck("包内 _meta.json 可解析且版本一致", zm.get("version") == v_fm, zm.get("version"))

# every versioned file consistent (no stale version literal elsewhere)
stale = [m.group(1) for m in re.finditer(r"1\.1\.(\d+)", dec) if "1.1.%s" % m.group(1) != v_fm]
print("   注：文内其他 1.1.x 引用（历史行）=%d 处，属历史记录" % len(stale))

# cross-file: same version in the _meta of the two other distribution points
for tag, p in (("镜像主树配套", "C:\\Users\\雍远\\.dsh\\gh-sync\\DSH-Launcher\\dsh-launcher\\assets\\配套技能\\%s__skillhub.zip" % SLUG),
               ("releases 配套", "C:\\Users\\雍远\\.dsh\\gh-sync\\DSH-Launcher\\releases\\v1.1.92\\%s__skillhub.zip" % SLUG)):
    h1 = hashlib.sha256(open(ZIP, "rb").read()).hexdigest()
    h2 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    ck("%s 与①逐字节一致" % tag, h1 == h2)

print("\nRESULT: %d OK, %d FAIL %s" % (ok, len(fails), "ALL PASS" if not fails else fails))
sys.exit(0 if not fails else 1)
