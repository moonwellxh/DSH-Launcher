#!/usr/bin/env python3
"""l0_patch_fit_check.py

作用: 判定外部分发的 frontend-static no-store 补丁与本机/上游文件是否匹配（零模型判断）。
      做法：把 patch 的前像（'-' 行）与后像（'+' 行）还原出来，分别与三方内容逐字节比较：
        ① 上游 tag 文件   git show dsh-v0.1.5-rc.1:packages/host/frontend-static/src/index.ts
        ② 本机工作树文件  <repo>/packages/host/frontend-static/src/index.ts
        ③ patch 附带的 index.ts.full
输入: --zip <补丁包路径> --repo <本机源码树>
输出: 每项 MATCH/DIFF + 行数/哈希；末行 JSON 摘要
复跑: python l0_patch_fit_check.py
依赖: 标准库 + git
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile

TAG = "dsh-v0.1.5-rc.1"
TARGET = "packages/host/frontend-static/src/index.ts"
DEFAULT_ZIP = ("Z:\\Date_Home\\\u3010MoonwelL\u3011\\\u3010AI\u3011\\LS\\"
               "DSH-frontend-static-no-store-patch-2026-09-10.zip")
DEFAULT_REPO = "C:\\Users\\\u96cd\u8fdc\\deepseek-harness"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_patch(patch_text):
    """Return (pre_image, post_image) as text, ignoring diff headers/hunks metadata."""
    pre, post = [], []
    for line in patch_text.replace("\r\n", "\n").split("\n"):
        if line.startswith(("diff --git", "index ", "--- ", "+++ ", "@@", "new file", "deleted file",
                            "similarity index", "rename ", "\\ No newline")):
            continue
        if line.startswith("-"):
            pre.append(line[1:])
        elif line.startswith("+"):
            post.append(line[1:])
        elif line.startswith(" "):
            pre.append(line[1:])
            post.append(line[1:])
    return "\n".join(pre), "\n".join(post)


def git_show(repo, path):
    out = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (TAG, path)],
                         capture_output=True, timeout=120)
    if out.returncode != 0:
        return None, out.stderr.decode("utf-8", "replace").strip()[:200]
    return out.stdout.decode("utf-8", "replace"), None


def read_file(path):
    if not os.path.exists(path):
        return None, "missing"
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace"), None


def report(label, a, b, a_name, b_name):
    same = a is not None and b is not None and a == b
    print("[%s] %s" % ("MATCH" if same else "DIFF ", label))
    print("        %-28s lines=%s sha=%s" % (a_name, "?" if a is None else len(a.split("\n")),
                                             "?" if a is None else sha(a)))
    print("        %-28s lines=%s sha=%s" % (b_name, "?" if b is None else len(b.split("\n")),
                                             "?" if b is None else sha(b)))
    return same


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=DEFAULT_ZIP)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    args = ap.parse_args()

    with zipfile.ZipFile(args.zip) as zf:
        names = zf.namelist()
        patch_text = zf.read("frontend-static-no-store.patch").decode("utf-8", "replace")
        full_text = zf.read("index.ts.full").decode("utf-8", "replace")

    pre, post = split_patch(patch_text)
    upstream, up_err = git_show(args.repo, TARGET)
    local, loc_err = read_file(os.path.join(args.repo, TARGET.replace("/", os.sep)))

    print("zip entries: %s" % ", ".join(names))
    print("patch: files touched = %s" % ", ".join(sorted({
        ln.split(" b/")[-1] for ln in patch_text.split("\n") if ln.startswith("diff --git")})))
    print("target path: %s ; upstream tag: %s" % (TARGET, TAG))
    if up_err:
        print("    upstream read error: %s" % up_err)
    if loc_err:
        print("    local read error: %s" % loc_err)

    r1 = report("patch pre-image  vs  上游 tag 文件", pre, upstream, "patch '-' 还原", "tag:%s" % TAG)
    r2 = report("patch post-image vs  index.ts.full", post, full_text, "patch '+' 还原", "index.ts.full")
    r3 = report("patch pre-image  vs  本机工作树文件", pre, local, "patch '-' 还原", "本机工作树")

    have_cache = {}
    for label, text in (("本机工作树", local), ("上游 tag", upstream), ("index.ts.full", full_text)):
        if text is None:
            have_cache[label] = None
            continue
        have_cache[label] = {
            "no-store": "no-store" in text,
            "immutable": "immutable" in text,
            "no-cache": "no-cache" in text,
        }

    print("--- 三类缓存策略常量是否存在 ---")
    for label, flags in have_cache.items():
        print("    %-14s %s" % (label, flags))

    summary = {
        "patch_preimage_matches_upstream_tag": r1,
        "patch_postimage_matches_full_file": r2,
        "patch_preimage_matches_local_tree": r3,
        "local_is_upstream_tag_content": (local == upstream) if (local and upstream) else False,
        "cache_flags": have_cache,
    }
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
