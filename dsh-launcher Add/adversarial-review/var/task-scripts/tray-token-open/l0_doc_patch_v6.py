#!/usr/bin/env python3
"""l0_doc_patch_v6.py

作用: 把 L0 对 v6 的实测输出写进 v6 §九.10（幂等，仅一处替换）。
输入: --doc <设计文档路径>
输出: 命中数 + JSON
复跑: python l0_doc_patch_v6.py   （再跑命中 0）
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v6.md"
OLD = "v5 `75/73/2/0`（skip 均为"
NEW = "v5 `75/73/2/0`、**v6 `__V6__`**（skip 均为"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    ap.add_argument("--counts", default="")
    args = ap.parse_args()
    with open(args.doc, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"
    new = NEW.replace("__V6__", args.counts) if args.counts else NEW
    n = text.count(OLD)
    if n:
        text = text.replace(OLD, new)
        with open(args.doc, "wb") as fh:
            if bom:
                fh.write(b"\xef\xbb\xbf")
            fh.write(text.encode("utf-8"))
    print("replaced=%d" % n)
    print(json.dumps({"applied": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
