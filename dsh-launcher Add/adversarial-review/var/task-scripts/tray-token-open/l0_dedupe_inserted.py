#!/usr/bin/env python3
"""l0_dedupe_inserted.py

作用: 去掉 l0_fix_patch_script_r2.py 中三条"插入型"规则重复执行造成的重复函数定义
      （Get-HttpStatusDotNet / Test-IsDshWebProcess / Resolve-PortCandidates），每者只留第一份。幂等。
输入: --ps1 <脚本路径>
输出: 每项删除数 + JSON
复跑: python l0_dedupe_inserted.py   （再跑应全 0）
依赖: 标准库
"""
import argparse
import json
import re
import sys

DEFAULT = "D:\\DSHS\\升级\\no-store补丁脚本\\apply-no-store-patch.ps1"
FUNCS = ["Get-HttpStatusDotNet", "Test-IsDshWebProcess", "Resolve-PortCandidates"]


def block_of(text, name):
    """Return the exact text of `function <name> { ... }` including its leading comment lines."""
    start = text.find("function %s {" % name)
    if start < 0:
        return None, None
    # 向前吃掉紧邻的注释行（保持块内含注释）
    head = text.rfind("\n\n", 0, start)
    if head < 0:
        head = 0
    # 向后找匹配的结束大括号（按行首 '}' 判定，脚本风格一致）
    m = re.compile(r"^\}", re.M).search(text, start)
    if not m:
        return None, None
    return (head + 2, m.end()), text[head + 2:m.end()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps1", default=DEFAULT)
    args = ap.parse_args()

    with open(args.ps1, "rb") as fh:
        raw = fh.read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")

    removed = {}
    for name in FUNCS:
        n_removed = 0
        while True:
            (span, block) = block_of(text, name)
            if span is None:
                break
            second = text.find("function %s {" % name, span[1])
            if second < 0:
                break
            # 删除第二次出现（含其前置空行）
            (span2, _) = block_of(text[second:], name)
            if span2 is None:
                break
            abs_start = second + span2[0]
            abs_end = second + span2[1]
            # 连同前面的空行一起删，避免留 3 个空行
            cut_start = abs_start
            while cut_start > 0 and text[cut_start - 1] in "\r\n":
                cut_start -= 1
            text = text[:cut_start] + "\n\n" + text[abs_end:]
            n_removed += 1
        removed[name] = n_removed

    with open(args.ps1, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(text.encode("utf-8"))
    for k, v in removed.items():
        print("%-24s removed=%d" % (k, v))
    print(json.dumps({"removed": sum(removed.values())}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
