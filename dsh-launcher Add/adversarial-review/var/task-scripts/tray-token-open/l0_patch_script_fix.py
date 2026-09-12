#!/usr/bin/env python3
"""l0_patch_script_fix.py

作用: 修订 apply-nostore-patch.ps1 的原生命令调用（PS 5.1 下 stderr 会变终止异常的问题），
      引入 Invoke-Native 包装并替换 git/pnpm/curl 的调用点。幂等。
输入: --ps1 <脚本路径>
输出: 每条替换的命中数 + JSON
复跑: python l0_patch_script_fix.py   （再跑各条命中 0）
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT_PS1 = "D:\\DSHS\\升级\\no-store补丁脚本\\apply-nostore-patch.ps1"

INVOKE_NATIVE = '''function Step([string]$Text) { $script:StepNo++; Write-Log ("[{0}] {1}" -f $script:StepNo, $Text) 'STEP' }

function Invoke-Native {
    # 统一原生命令调用：把 stderr 也收成文本，避免 PS 5.1 在 Stop 偏好下把 stderr 变成终止异常
    param([string]$FilePath, [string[]]$Arguments)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $FilePath @Arguments 2>&1
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
    return @{ ExitCode = $code; Output = @($out) }
}'''

PAIRS = [
    # 1) 插入 Invoke-Native（锚点为 Step 函数那一行）
    ("insert-invoke-native",
     "function Step([string]$Text) { $script:StepNo++; Write-Log (\"[{0}] {1}\" -f $script:StepNo, $Text) 'STEP' }",
     INVOKE_NATIVE),

    # 2) git apply --check
    ("git-check",
     "$checkOut = & git -C $Repo apply --check $patchFile 2>&1\n$checkOk = ($LASTEXITCODE -eq 0)\nforeach ($l in $checkOut) { if (\"$l\".Trim()) { Write-Log (\"  git: {0}\" -f \"$l\".Trim()) } }",
     "$checkRes = Invoke-Native -FilePath 'git' -Arguments @('-C', $Repo, 'apply', '--check', $patchFile)\n$checkOk = ($checkRes.ExitCode -eq 0)\nforeach ($l in $checkRes.Output) { if (\"$l\".Trim()) { Write-Log (\"  git: {0}\" -f \"$l\".Trim()) } }"),

    # 3) git apply
    ("git-apply",
     "    & git -C $Repo apply $patchFile | Out-Host\n    if ($LASTEXITCODE -ne 0) { Stop-With 2 'git apply 失败（请检查 git status 后重试）' }",
     "    $applyRes = Invoke-Native -FilePath 'git' -Arguments @('-C', $Repo, 'apply', $patchFile)\n    foreach ($l in $applyRes.Output) { if (\"$l\".Trim()) { Write-Log (\"  git: {0}\" -f \"$l\".Trim()) } }\n    if ($applyRes.ExitCode -ne 0) { Stop-With 2 'git apply 失败（请检查 git status 后重试）' }"),

    # 4) pnpm build
    ("pnpm-build",
     "        & $script:Pnpm run $BuildCommand | Out-Host\n        $code = $LASTEXITCODE",
     "        $buildRes = Invoke-Native -FilePath $script:Pnpm -Arguments @('run', $BuildCommand)\n        foreach ($l in $buildRes.Output) { Write-Host \"$l\" }\n        $code = $buildRes.ExitCode"),

    # 5) 根路径状态码
    ("root-status",
     "    $code = & curl.exe -s -o NUL -w \"%{http_code}\" --max-time 5 \"http://127.0.0.1:$Port/\" 2>$null\n    if ([string]::IsNullOrWhiteSpace(\"$code\")) { return 0 }\n    return [int]\"$code\"",
     "    $res = Invoke-Native -FilePath 'curl.exe' -Arguments @('-s', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '5', \"http://127.0.0.1:$Port/\")\n    $code = (\"$($res.Output)\" -replace '\\s', '')\n    if ($code -notmatch '^\\d{3}$') { return 0 }\n    return [int]$code"),

    # 6) 令牌换 cookie
    ("cookie-exchange",
     "        & curl.exe -s -o NUL -c $jar --max-time 8 $tok | Out-Null",
     "        [void](Invoke-Native -FilePath 'curl.exe' -Arguments @('-s', '-o', 'NUL', '-c', $jar, '--max-time', '8', $tok))"),

    # 7) 抓响应头
    ("http-headers",
     "    $curlArgs += $Url\n    return @(& curl.exe @curlArgs)",
     "    $curlArgs += $Url\n    return @((Invoke-Native -FilePath 'curl.exe' -Arguments $curlArgs).Output)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps1", default=DEFAULT_PS1)
    args = ap.parse_args()

    with open(args.ps1, "rb") as fh:
        raw = fh.read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")

    counts = {}
    for label, old, new in PAIRS:
        n = text.count(old)
        counts[label] = n
        if n:
            text = text.replace(old, new, 1)

    with open(args.ps1, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(text.encode("utf-8"))
    for k, v in counts.items():
        print("%-22s %d" % (k, v))
    print(json.dumps({"applied": sum(1 for v in counts.values() if v), "bom_preserved": bom}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
