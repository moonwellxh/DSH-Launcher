#!/usr/bin/env python3
"""l0_fix_patch_script_r2.py

作用: 按第二轮代码审查（阻断1/严重4/轻微5/建议3）修订 apply-no-store-patch.ps1。
      仅做字面锚点替换，幂等（每条命中 0 表示已修订或锚点不存在）。
输入: --ps1 <脚本路径>
输出: 每条规则命中数 + JSON
复跑: python l0_fix_patch_script_r2.py
依赖: 标准库
"""
import argparse
import json
import sys

DEFAULT = "D:\\DSHS\\升级\\no-store补丁脚本\\apply-no-store-patch.ps1"

RULES = []

# R1: 304 判定改走 .NET（curl 在 PS 5.1 下会吞掉 ETag 内层双引号）
RULES.append(("R1-add-dotnet-probe",
"""function Get-AssetDir {""",
"""function Get-HttpStatusDotNet {
    # 304 判定必须走 .NET：PS 5.1 调 curl 时 -H "If-None-Match: W/\\"…\\"" 的内层双引号会在 argv 层被吞，
    # 服务端拿到不带引号的 ETag → 精确比较失败 → 永不 304（第二轮审查 阻断 B1 实测）
    param([string]$Url, [string]$ETag)
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Method = 'GET'; $req.AllowAutoRedirect = $false; $req.Proxy = $null; $req.Timeout = 8000
        if ($ETag) { $req.Headers['If-None-Match'] = $ETag }
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode; $resp.Close(); return $code
    } catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) { $code = [int]$r.StatusCode; $r.Close(); return $code }
        return 0
    } catch { return 0 }
}

function Get-AssetDir {"""))

# R2: 用 .NET 探针做 304 检查
RULES.append(("R2-use-dotnet-for-304",
"""        $h2 = Get-HttpHeaders -Url ("http://127.0.0.1:{0}/assets/{1}" -f $script:Port, $asset.Name) -CookieJar $jar -IfNoneMatch $et
        if (("$($h2 | Select-Object -First 1)") -match '304') { Write-Log ('②b 带 If-None-Match 复请求 → 304  [OK]（etag={0}）' -f $et) 'OK' }
        else { Write-Log '②b 带 If-None-Match 复请求 → 非 304  [FAIL]' 'ERR'; $fail += 'etag304' }""",
"""        $code304 = Get-HttpStatusDotNet -Url ("http://127.0.0.1:{0}/assets/{1}" -f $script:Port, $asset.Name) -ETag $et
        if ($code304 -eq 304) { Write-Log ('②b 带 If-None-Match 复请求 → 304  [OK]（etag={0}）' -f $et) 'OK' }
        else { Write-Log ('②b 带 If-None-Match 复请求 → {0}（期望 304）  [FAIL]' -f $code304) 'ERR'; $fail += 'etag304' }"""))

# R3: ① 必须要求 200（401 的 no-store 来自认证层，不代表补丁生效）
RULES.append(("R3-index-requires-200",
"""$h  = Get-HttpHeaders -Url ("http://127.0.0.1:{0}/" -f $script:Port) -CookieJar $jar
$cc = Get-HeaderValue -Headers $h -Name 'cache-control'
if ($cc -eq 'no-store') { Write-Log ('① index → {0}  [OK]' -f $cc) 'OK' }
else { Write-Log ('① index → {0}（期望 no-store）  [FAIL]' -f ($(if ($cc) { $cc } else { '<无该头>' }))) 'ERR'; $fail += 'index' }""",
"""$h  = Get-HttpHeaders -Url ("http://127.0.0.1:{0}/" -f $script:Port) -CookieJar $jar
$line1 = "$($h | Select-Object -First 1)"
$cc = Get-HeaderValue -Headers $h -Name 'cache-control'
if ($line1 -notmatch '\\s200\\s') {
    Write-Log ('① index → 响应 {0}：不是 200，无法判定补丁（401 附带的 no-store 来自认证层，不代表补丁生效）  [FAIL]' -f $line1.Trim()) 'ERR'
    $fail += 'index-status'
    Write-Log '提示：先在浏览器用带令牌地址完成一次握手，或让 Web 由托盘启动（日志里才有令牌行）后重跑核验。' 'WARN'
} elseif ($cc -eq 'no-store') { Write-Log ('① index(200) → {0}  [OK]' -f $cc) 'OK' }
else { Write-Log ('① index(200) → {0}（期望 no-store）  [FAIL]' -f ($(if ($cc) { $cc } else { '<无该头>' }))) 'ERR'; $fail += 'index' }"""))

# R4: ② 找不到资源时必须计入失败，不能静默跳过却宣称通过
RULES.append(("R4-asset-missing-fails",
"""} else {
    Write-Log '② 未找到内容寻址资源（dist/assets 下无 -<hash>.js），跳过该项' 'WARN'
}""",
"""} else {
    Write-Log '② 未找到内容寻址资源（dist/assets 下无 -<hash>.js）：前端 dist 可能未构建，或 dist 路径已变  [FAIL]' 'ERR'
    Write-Log '提示：先在源码树跑 pnpm run build:web（或 pnpm run build）再重跑核验。' 'WARN'
    $fail += 'asset-missing'
}"""))

# R5: 修 -Force 与"已打补丁"的分支错位
RULES.append(("R5-apply-branch",
"""if ($alreadyPatched -and -not $Force) {
    Write-Log '目标文件已含补丁内容（INDEX_CACHE）：跳过打补丁，仅继续构建/重启/核验' 'WARN'
} elseif (-not $checkOk) {""",
"""$willApply = -not $alreadyPatched
if (-not $willApply) {
    Write-Log '目标文件已含补丁内容（INDEX_CACHE）：跳过打补丁，仅继续构建/重启/核验（要重打请先还原：菜单 4）' 'WARN'
} elseif (-not $checkOk) {"""))

RULES.append(("R5b-step4-guard",
"""if (-not ($alreadyPatched -and -not $Force)) {
    Step '备份并应用补丁'""",
"""if ($willApply) {
    Step '备份并应用补丁'"""))

# R6: 构建失败只在"本次确实应用过补丁"时回滚
RULES.append(("R6-build-fail-rollback",
"""} elseif (-not (Invoke-Build)) {
    Write-Log '构建失败：自动回滚源码文件，且不重启（保持现状）' 'ERR'
    $bak = Get-LatestBackup
    if ($bak) {
        Copy-Item -LiteralPath $bak.FullName -Destination $TargetFile -Force
        Write-Log ("已还原为：{0}" -f $bak.Name) 'WARN'
    }
    Stop-With 3 '构建失败，已回滚源码（可加 -WithInstall 先跑一次 pnpm install 再试）'
}""",
"""} elseif (-not (Invoke-Build)) {
    if ($willApply) {
        Write-Log '构建失败：本次已应用补丁 → 自动回滚源码文件，且不重启（保持现状）' 'ERR'
        $bak = Get-LatestBackup
        if ($bak) {
            Copy-Item -LiteralPath $bak.FullName -Destination $TargetFile -Force
            Write-Log ("已还原为：{0}" -f $bak.Name) 'WARN'
        }
        Stop-With 3 '构建失败，已回滚源码（可加 -WithInstall 先跑一次 pnpm install 再试）'
    }
    Write-Log '构建失败：本次未应用补丁（文件原本就是补丁状态）→ 不做任何回滚，保持现状' 'ERR'
    Stop-With 3 '构建失败（源码未改动；可加 -WithInstall 先跑一次 pnpm install 再试）'
}"""))

# R7: 还原改用 git checkout（避免把上一版本的本地备份覆盖回来）
RULES.append(("R7-rollback-via-git",
"""if ($Rollback) {
    Step '还原补丁'
    $bak = Get-LatestBackup
    if (-not $bak) { Stop-With 2 '找不到 index.ts.bak-nostore-* 备份；可改用 git checkout -- 该文件手工还原' }
    Write-Log ("使用备份：{0}" -f $bak.Name)
    if (-not $DryRun) {
        Copy-Item -LiteralPath $bak.FullName -Destination $TargetFile -Force
        if (-not $SkipBuild -and -not (Invoke-Build)) { Stop-With 3 '还原后构建失败，请检查源码树' }
        if (-not $SkipRestart) { Restart-TrayAndWeb; [void](Wait-WebReady) }
    } else { Write-Log 'DryRun：未做修改' 'WARN' }
    Write-Log '还原流程结束' 'OK'
    exit 0
}""",
"""if ($Rollback) {
    Step '还原补丁（默认用 git checkout 取回当前提交的上游版本，避免把过期的本地备份盖回来）'
    if (-not $DryRun) {
        $co = Invoke-Native -FilePath 'git' -Arguments @('-C', $script:Repo, 'checkout', '--', $TargetRel)
        foreach ($l in $co.Output) { if ("$l".Trim()) { Write-Log ("  git: {0}" -f "$l".Trim()) } }
        if ($co.ExitCode -ne 0) {
            Write-Log 'git checkout 失败（该文件可能有未提交的其它改动）→ 退回使用最近的 .bak-nostore-* 备份' 'WARN'
            $bak = Get-LatestBackup
            if (-not $bak) { Stop-With 2 'git checkout 失败且找不到备份；请手工处理该文件' }
            Write-Log ("使用备份：{0}（注意：备份诞生于更早的版本，可能存在版本漂移，请自行确认）" -f $bak.Name) 'WARN'
            Copy-Item -LiteralPath $bak.FullName -Destination $TargetFile -Force
        }
        $nowText = Get-Content -LiteralPath $TargetFile -Raw -Encoding UTF8
        if ($nowText.Contains('INDEX_CACHE')) { Stop-With 3 '还原后文件里仍有 INDEX_CACHE，请人工核对' }
        Write-Log '已还原为上游版本（不再含 no-store 补丁）。' 'OK'
        if (-not $SkipBuild -and -not (Invoke-Build)) { Stop-With 3 '还原后构建失败，请检查源码树' }
        if (-not $SkipRestart) { Restart-TrayAndWeb; [void](Wait-WebReady) }
    } else { Write-Log 'DryRun：未做修改' 'WARN' }
    Write-Log '还原流程结束' 'OK'
    exit 0
}"""))

# R8: 杀监听进程前核验身份
RULES.append(("R8-process-identity",
"""function Get-TrayProcesses {""",
"""function Test-IsDshWebProcess {
    # 只按端口杀进程风险大：先核验命令行确属 dsh web
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return $false }
    try { $p = Get-CimInstance Win32_Process -Filter ("ProcessId=$ProcessId") -ErrorAction Stop } catch { return $false }
    if (-not $p) { return $false }
    if ("$($p.Name)" -notmatch '^node(\\.exe)?$') { return $false }
    return ("$($p.CommandLine)" -match 'apps[\\\\/]cli[\\\\/]lib[\\\\/]bin\\.js')
}

function Get-TrayProcesses {"""))

RULES.append(("R8b-kill-guard",
"""    $webPid = Get-ListenerPid
    if ($webPid -ne 0) {
        Write-Log ("停止 Web 进程 PID {0}（端口 {1}）" -f $webPid, $script:Port)
        Stop-Process -Id $webPid -Force -ErrorAction SilentlyContinue
        for ($i = 0; $i -lt 20; $i++) { if ((Get-ListenerPid) -eq 0) { break }; Start-Sleep -Seconds 1 }
    }""",
"""    $webPid = Get-ListenerPid
    if ($webPid -ne 0) {
        if (Test-IsDshWebProcess -ProcessId $webPid) {
            Write-Log ("停止 Web 进程 PID {0}（端口 {1}；已核验命令行含 apps/cli/lib/bin.js）" -f $webPid, $script:Port)
            Stop-Process -Id $webPid -Force -ErrorAction SilentlyContinue
            for ($i = 0; $i -lt 20; $i++) { if ((Get-ListenerPid) -eq 0) { break }; Start-Sleep -Seconds 1 }
        } else {
            Write-Log ("端口 {0} 被 PID {1} 占用，但其命令行不像 dsh web → 不杀它；若随后 Web 起不来，请人工处理端口占用。" -f $script:Port, $webPid) 'WARN'
        }
    }"""))

# R9: 端口候选优先取"真的有监听"的那个
RULES.append(("R9-port-candidates",
"""function Find-Pnpm {""",
"""function Resolve-PortCandidates {
    param([string]$InstallDir, [int]$Explicit)
    $cands = New-Object System.Collections.Generic.List[int]
    $log = Join-Path $InstallDir 'dsh-web.log'
    if (Test-Path -LiteralPath $log) {
        foreach ($m in [regex]::Matches((Read-TextSmart $log), 'http://127\\.0\\.0\\.1:(\\d{2,5})/')) {
            $p = [int]$m.Groups[1].Value
            if (-not $cands.Contains($p)) { $cands.Add($p) }
        }
    }
    $tray = Join-Path $InstallDir 'DSH-tray.ps1'
    if (Test-Path -LiteralPath $tray) {
        $tt = Read-TextSmart $tray
        if ($tt -match '\\$webUrl\\s*=\\s*[''"]http://127\\.0\\.0\\.1:(\\d{2,5})') {
            $p = [int]$Matches[1]; if (-not $cands.Contains($p)) { $cands.Add($p) }
        }
        if ($tt -match '\\$port\\s*=\\s*(\\d{2,5})') {
            $p = [int]$Matches[1]; if (-not $cands.Contains($p)) { $cands.Add($p) }
        }
    }
    if ($Explicit -gt 0 -and -not $cands.Contains($Explicit)) { $cands.Add($Explicit) }
    if (-not $cands.Contains(3080)) { $cands.Add(3080) }
    return $cands
}

function Find-Pnpm {"""))

RULES.append(("R9b-port-pick",
"""$script:Port = Find-Port -InstallDir $script:InstallDir -Explicit $Port""",
"""$portCands = Resolve-PortCandidates -InstallDir $script:InstallDir -Explicit $Port
$script:Port = $portCands[0]
foreach ($pc in $portCands) {
    if (Get-NetTCPConnection -LocalPort $pc -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1) {
        $script:Port = $pc; break
    }
}
Write-Log ("端口候选：{0} → 采用 {1}（优先取真的有监听的那个）" -f ($portCands -join ','), $script:Port)"""))

# R10: DryRun 判定不可应用时给退出码 2
RULES.append(("R10-dryrun-exit2",
"""    if ($DryRun) { Write-Log 'DryRun 结束：判定为「暂不可应用」。' 'WARN'; exit 0 }""",
"""    if ($DryRun) { Write-Log 'DryRun 结束：判定为「暂不可应用」（退出码 2 ＝ 条件不满足，不是失败）。' 'WARN'; exit 2 }"""))

# R11: 构建候选不含全量 build
RULES.append(("R11-build-candidates",
"""    foreach ($name in @($Preferred, 'build:lib:host', 'build:lib', 'build')) {""",
"""    # 只接受"只重建 lib"的脚本；不含全量 build（那会连带品牌/前端等步骤，改动面远超预期）
    foreach ($name in @($Preferred, 'build:lib:host', 'build:lib')) {"""))

# R12: 取不到令牌且服务端要认证时，不打开裸地址
RULES.append(("R12-no-bare-open",
"""    if ($tok) { Write-Log '打开浏览器：带令牌地址（自动完成握手）'; Start-Process $tok | Out-Null }
    else { Write-Log ("打开浏览器：http://127.0.0.1:{0}" -f $script:Port); Start-Process ("http://127.0.0.1:{0}" -f $script:Port) | Out-Null }""",
"""    if ($tok) {
        Write-Log '打开浏览器：带令牌地址（自动完成握手）'
        Start-Process $tok | Out-Null
    } elseif ((Get-RootStatus) -eq 200) {
        Write-Log ("打开浏览器：http://127.0.0.1:{0}（服务端未要求认证）" -f $script:Port)
        Start-Process ("http://127.0.0.1:{0}" -f $script:Port) | Out-Null
    } else {
        Write-Log '未取到令牌且服务端要求认证 → 不开裸地址（开了只会看到 401）；请让 Web 由托盘启动后重试，或按 SOP 的 R5 重启一次 Web。' 'WARN'
    }"""))

# R13: alreadyPatched 判定收紧
RULES.append(("R13-already-patched",
"""$alreadyPatched = ($fileText.Contains('INDEX_CACHE') -or $fileText.Contains('no-store'))""",
"""$alreadyPatched = ($fileText.Contains('INDEX_CACHE') -and $fileText.Contains('REVALIDATE_CACHE'))"""))

# R14: 日志读取循环读满
RULES.append(("R14-read-loop",
"""        $len = [int]$fs.Length
        $bytes = New-Object byte[] $len
        if ($len -gt 0) { [void]$fs.Read($bytes, 0, $len) }""",
"""        $len = [int]$fs.Length
        $bytes = New-Object byte[] $len
        $read = 0
        while ($read -lt $len) {                       # .NET 允许短读，必须循环读满
            $n = $fs.Read($bytes, $read, $len - $read)
            if ($n -le 0) { break }
            $read += $n
        }
        if ($read -lt $len -and $read -ge 0) { $bytes = $bytes[0..($read - 1)] }"""))

# R15: 去掉 Get-HttpHeaders 已不再使用的 -IfNoneMatch 形参
RULES.append(("R15-drop-ifnonematch",
"""    param([string]$Url, [string]$CookieJar = '', [string]$IfNoneMatch = '')
    $curlArgs = @('-s', '-D', '-', '-o', 'NUL', '--max-time', '8')
    if ($CookieJar -and (Test-Path -LiteralPath $CookieJar)) { $curlArgs += @('-b', $CookieJar) }
    if ($IfNoneMatch) { $curlArgs += @('-H', ("If-None-Match: {0}" -f $IfNoneMatch)) }
    $curlArgs += $Url""",
"""    param([string]$Url, [string]$CookieJar = '')
    $curlArgs = @('-s', '-D', '-', '-o', 'NUL', '--max-time', '8')
    if ($CookieJar -and (Test-Path -LiteralPath $CookieJar)) { $curlArgs += @('-b', $CookieJar) }
    $curlArgs += $Url"""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps1", default=DEFAULT)
    args = ap.parse_args()

    with open(args.ps1, "rb") as fh:
        raw = fh.read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")

    counts = {}
    for label, old, new in RULES:
        n = text.count(old)
        counts[label] = n
        if n:
            text = text.replace(old, new, 1)

    with open(args.ps1, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(text.encode("utf-8"))
    for k, v in counts.items():
        print("%-26s %d" % (k, v))
    print(json.dumps({"applied": sum(1 for v in counts.values() if v), "rules": len(RULES)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
