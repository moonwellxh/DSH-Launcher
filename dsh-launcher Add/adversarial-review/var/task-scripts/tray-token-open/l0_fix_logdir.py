#!/usr/bin/env python3
"""l0_fix_logdir.py

作用: 把 apply-no-store-patch.ps1 的执行日志目录从 <安装目录>\\升级 改为 <脚本所在目录>\\日志，
      避免日志散落在"升级"根目录。幂等（CRLF 感知）。
输入: --ps1 <脚本路径>
输出: 命中数 + JSON
复跑: python l0_fix_logdir.py   （再跑命中 0）
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT = "D:\\DSHS\\升级\\脚本\\apply-no-store-patch.ps1"
OLD = "$LogDir = Join-Path $script:InstallDir '升级'"
NEW = "$LogDir = Join-Path (Split-Path -Parent $PSCommandPath) '日志'   # 日志就放在脚本旁边，别散落到升级根目录"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps1", default=DEFAULT)
    args = ap.parse_args()
    with open(args.ps1, "rb") as fh:
        raw = fh.read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    crlf = "\r\n" in text
    text_lf = text.replace("\r\n", "\n")
    n = text_lf.count(OLD)
    if n:
        text_lf = text_lf.replace(OLD, NEW, 1)
        out = text_lf.replace("\n", "\r\n") if crlf else text_lf
        with open(args.ps1, "wb") as fh:
            if bom:
                fh.write(b"\xef\xbb\xbf")
            fh.write(out.encode("utf-8"))
    print("replaced=%d" % n)
    print(json.dumps({"applied": n}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
