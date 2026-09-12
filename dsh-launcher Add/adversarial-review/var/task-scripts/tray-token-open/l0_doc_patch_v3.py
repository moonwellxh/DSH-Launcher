#!/usr/bin/env python3
"""l0_doc_patch_v3.py

作用: 把 L0 对 v3 的实测输出写进 §九.10（幂等）。仅一处替换。
输入: --doc <设计文档路径>
输出: 命中数 + JSON
复跑: python l0_doc_patch_v3.py   （再跑命中 0）
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v3.md"
OLD = "  10. L0 锚点校验（本轮实测输出，命令见 registry.json）：以 `l0_anchor_check.py --doc` 对本文档运行的结果为准（v2 为 `{\"total\": 70, \"ok\": 68, \"skip\": 2, \"fail\": 0}`，2 项 skip 为 `$DSH_HOME/...` 与 `~\\.dsh\\...` 环境变量路径）。"
NEW = "  10. L0 锚点校验（本轮实测输出，命令见 registry.json）：`python l0_anchor_check.py --doc \"…v3.md\"` → `{\"total\": 68, \"ok\": 66, \"skip\": 2, \"fail\": 0}`；2 项 skip 为 `$DSH_HOME/...` 与 `~\\.dsh\\gh-sync\\config.json` 两类环境变量路径（解析器有意跳过，非缺失）。v2 的同一检查为 `{\"total\": 70, \"ok\": 68, \"skip\": 2, \"fail\": 0}`。"


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
