#!/usr/bin/env python3
"""Audit ALL companion packages for maintenance artifacts (in-package hygiene)."""
import io
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
D = "C:\\Users\\雍远\\.agents\\skills\\dsh-launcher\\assets\\配套技能"
import re
BAD = re.compile(r"(^|/)(_backup/|.*\.bak(-.*)?$|__pycache__/|.*\.pyc$|install-dir\.txt$|var/)")
print("== 各配套包内维护垃圾审计 ==")
total_bad = 0
for f in sorted(os.listdir(D)):
    if not f.endswith("__skillhub.zip"):
        continue
    z = zipfile.ZipFile(os.path.join(D, f))
    names = [n for n in z.namelist() if not n.endswith("/")]
    hits = [n for n in names if BAD.search(n.split("/", 1)[1] if "/" in n else n)]
    total_bad += len(hits)
    print("  %-42s 条目=%-4d 垃圾=%d %s" % (f, len(names), len(hits), hits if hits else ""))
print("\n合计垃圾条目=%d" % total_bad)
