#!/usr/bin/env python3
"""l0_citation_normalize.py

作用: 幂等规范化设计文档里的引用写法，使每条 `文件[:行]` 锚点可被 l0_anchor_check.py
      无歧义解析（去 ~ 前缀、补全 parts/setup/mode 相对路径、补全上游包全路径）。
输入: --doc <设计文档路径>（默认 D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md）
输出: stdout 每条规则的替换次数（ASCII 安全）+ 末行 JSON 摘要 {'changed':n}
复跑: python l0_citation_normalize.py   （幂等，再跑一次 changed=0）
依赖: 标准库
"""
import argparse
import json
import re
import sys

DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md"

PARTS = ("00-header.ps1", "10-utils.ps1", "20-version.ps1", "21-latest.ps1", "22-ghver.ps1",
         "30-compare.ps1", "40-winapi.ps1", "50-url.ps1", "60-dialogs.ps1", "80-server.ps1", "90-main.ps1")

RULES = [
    ("strip-home", re.compile(r"~/\.agents/skills/dsh-launcher/"), ""),
    ("ellipsis-parts", re.compile(r"\.\.\./parts/"), "assets/tmpl/parts/"),
    ("frontend-short", re.compile(r"`frontend-static:(\d+)`"),
     r"`packages/host/frontend-static/src/index.ts:\1`"),
    ("webapp-short", re.compile(r"`web-app/src/index\.ts"), "`packages/bundle/web-app/src/index.ts"),
    ("browser-auth-short", re.compile(r"(?<![\w/.\-])browser-auth\.ts"),
     "packages/client/connection/src/browser-auth.ts"),
    ("rpc-host-short", re.compile(r"(?<![\w/.\-])rpc-host\.ts"),
     "packages/client/connection/src/rpc-host.ts"),
    ("mode-glob", re.compile(r"`mode-\*\.json`"), "`mode-source.json`"),
]

BARE_MAP = {
    "setup.ps1": "assets/setup.ps1",
    "mode-source.json": "assets/tmpl/parts/mode-source.json",
    "mode-path.json": "assets/tmpl/parts/mode-path.json",
}
for name in PARTS:
    BARE_MAP[name] = "assets/tmpl/parts/" + name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    args = ap.parse_args()

    with open(args.doc, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"

    counts = {}
    for label, pattern, repl in RULES:
        text, n = pattern.subn(repl, text)
        counts[label] = n

    # bare filenames: only when not already preceded by a path separator / word char
    for name, full in BARE_MAP.items():
        pattern = re.compile(r"(?<![\w/.\-])" + re.escape(name))
        text = pattern.sub(full, text)
        counts["bare:" + name] = counts.get("bare:" + name, 0) + 0  # kept for symmetry

    total = sum(v for k, v in counts.items())
    with open(args.doc, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(text.encode("utf-8"))
    for k, v in counts.items():
        if v:
            print("%-22s %d" % (k, v))
    print(json.dumps({"changed": total}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
