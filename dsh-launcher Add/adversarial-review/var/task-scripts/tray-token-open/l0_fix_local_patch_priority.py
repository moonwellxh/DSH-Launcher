#!/usr/bin/env python3
"""l0_fix_local_patch_priority.py

作用: 让脚本按"本地优先"取补丁：脚本目录内的 *.patch → 脚本目录内的 *no-store-patch*.zip → 参数/默认(Z:)。
      幂等（存在性守卫）。
输入: --ps1 <脚本路径>
输出: 命中数 + JSON
复跑: python l0_fix_local_patch_priority.py   （再跑命中 0）
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT = "D:\\DSHS\\升级\\no-store补丁脚本\\apply-no-store-patch.ps1"

OLD = """Step '定位补丁文件'
$patchFile = $PatchPath
if (-not $patchFile) {
    if (-not (Test-Path -LiteralPath $ZipPath)) { Stop-With 2 ("补丁包不存在：{0}（可用 -PatchPath 直接指定 .patch）" -f $ZipPath) }"""

NEW = """Step '定位补丁文件'
$patchFile = $PatchPath
if (-not $patchFile) {
    # 本地优先：脚本目录里的 .patch → 脚本目录里的 *no-store-patch*.zip → 参数/默认（Z: 网络盘）
    $hereDir = Split-Path -Parent $PSCommandPath
    $localPatch = Get-ChildItem -LiteralPath $hereDir -Filter '*.patch' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($localPatch) {
        $patchFile = $localPatch.FullName
        Write-Log ("使用脚本目录内的补丁：{0}" -f $localPatch.Name)
    } else {
        $localZip = Get-ChildItem -LiteralPath $hereDir -Filter '*no-store-patch*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($localZip) {
            $ZipPath = $localZip.FullName
            Write-Log ("使用脚本目录内的补丁包：{0}" -f $localZip.Name)
        }
    }
}
if (-not $patchFile) {
    if (-not (Test-Path -LiteralPath $ZipPath)) { Stop-With 2 ("补丁包不存在：{0}（可用 -PatchPath 直接指定 .patch）" -f $ZipPath) }"""

GUARD = "使用脚本目录内的补丁"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps1", default=DEFAULT)
    args = ap.parse_args()
    with open(args.ps1, "rb") as fh:
        raw = fh.read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")            # 统一为 LF 再匹配锚点（文件行尾可能是 CRLF）
    if GUARD in text:
        n = 0
    else:
        n = text.count(OLD)
        if n:
            text = text.replace(OLD, NEW, 1)
            out = text.replace("\n", "\r\n") if crlf else text
            with open(args.ps1, "wb") as fh:
                if bom:
                    fh.write(b"\xef\xbb\xbf")
                fh.write(out.encode("utf-8"))
    print("replaced=%d" % n)
    print(json.dumps({"applied": n}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
