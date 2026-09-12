#!/usr/bin/env python3
"""l0_repair_v2b.py

作用: 让 l0_anchor_check.py 的"裸文件名"解析也覆盖本任务目录（任务脚本自身被文档以裸名引用时
      不应记为 SKIP/无法解析）。幂等。
输入: 无参数
输出: stdout 命中数 + 末行 JSON
复跑: python l0_repair_v2b.py   （再跑应命中 0）
依赖: 标准库
"""
import json
import os
import sys

CRAWLER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "l0_anchor_check.py")
OLD = '    for cand in (os.path.join(PARTS, path), os.path.join(SKILL, path), os.path.join(SKILL, "assets", path)):'
NEW = ('    for cand in (os.path.join(PARTS, path), os.path.join(SKILL, path), os.path.join(SKILL, "assets", path),\n'
       '                 os.path.join(os.path.dirname(os.path.abspath(__file__)), path)):')


def main():
    with open(CRAWLER, "rb") as fh:
        text = fh.read().decode("utf-8")
    n_old = text.count(OLD)
    n_new = text.count(NEW)
    changed = 0
    if n_old:
        text = text.replace(OLD, NEW, 1)
        changed = 1
        with open(CRAWLER, "wb") as fh:
            fh.write(text.encode("utf-8"))
    print("old=%d new=%d changed=%d" % (n_old, n_new, changed))
    print(json.dumps({"changed": changed}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
