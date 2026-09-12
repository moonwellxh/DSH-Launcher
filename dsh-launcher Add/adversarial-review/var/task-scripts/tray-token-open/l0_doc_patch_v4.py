#!/usr/bin/env python3
"""l0_doc_patch_v4.py

作用: 把 L0 对 v4 的实测输出写进 v4 §九.10（幂等，仅一处替换）。
输入: --doc <设计文档路径>
输出: 命中数 + JSON
复跑: python l0_doc_patch_v4.py   （再跑命中 0）
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v4.md"
OLD = "本轮各版本实测：v1 `38/38/0/0`、v2 `70/68/2/0`、v3 `68/66/2/0`（skip 均为 `$DSH_HOME/...` 与 `~\\.dsh\\gh-sync\\config.json` 环境变量路径）。"
NEW = "本轮各版本实测：v1 `38/38/0/0`、v2 `70/68/2/0`、v3 `68/66/2/0`、**v4 `76/74/2/0`**（skip 均为 `$DSH_HOME/...` 与 `~\\.dsh\\gh-sync\\config.json` 环境变量路径）。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    args = ap.parse_args()
    with open(args.doc, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"
    n = text.count(OLD)
    if n:
        text = text.replace(OLD, NEW)
        with open(args.doc, "wb") as fh:
            if bom:
                fh.write(b"\xef\xbb\xbf")
            fh.write(text.encode("utf-8"))
    print("replaced=%d" % n)
    print(json.dumps({"applied": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
