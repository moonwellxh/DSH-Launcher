# ============================================================
#  switch-dsh-home3.ps1 —— 家目录切换 v3
#  必须由计划任务 DSH-Home-Switch 启动（脚本会自检：若自身在 dsh web 进程树里就拒绝运行）。
#  与 v2 的区别（两份对抗审查的结论）：
#   - 不再 setx、不再改 VBS：家目录只由 D:\DSHS\dsh-home.txt 表达，托盘 Start-DshServer 读它并只传给 node
#   - 校验基准挪到 robocopy 完成之后（否则被复制的旧写入会伪造成功）
#   - 恢复 taskkill /T（在任务进程树里安全），并在杀完轮询端口直到真正释放
#   - 成功判据：新 PID ≠ 旧 PID 且新家 cordis.yml 的 mtime 晚于托盘启动
#   - 失败/异常一律回滚并写状态；结束注销自身任务
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$NewHome,
    [string]$OldHome = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$InstallDir = 'D:\DSHS'
$HomeFile   = Join-Path $InstallDir 'dsh-home.txt'
$logPath    = Join-Path $InstallDir 'dsh-home-switch.log'
$statusPath = Join-Path $InstallDir 'dsh-home-switch.txt'
$taskName   = 'DSH-Home-Switch'
$port       = 3080

function L([string]$m) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
    Write-Host $m
    try { [IO.File]::AppendAllText($logPath, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false))) } catch {}
}
function Test-PortOwner {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess } return 0
}
function Write-Status([string]$text) {
    if ($DryRun) { L '  【DryRun】不写状态文件'; return }
    try { [IO.File]::WriteAllText($statusPath, ($text + "`r`nat=" + (Get-Date).ToString('o')), (New-Object System.Text.UTF8Encoding($false))) } catch {}
}
# 祖先链里是否包含指定 PID（防止在被杀的那棵树里运行）
function Test-AncestorPid([int]$targetPid) {
    $cur = $PID
    for ($i = 0; $i -lt 12; $i++) {
        $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $cur) -ErrorAction SilentlyContinue
        if (-not $p) { return $false }
        if ([int]$p.ParentProcessId -eq $targetPid) { return $true }
        $cur = [int]$p.ParentProcessId
        if ($cur -le 0) { return $false }
    }
    return $false
}
function Stop-Dsh([int]$owner) {
    if ($DryRun) { L '  【DryRun】跳过停服务'; return }
    # 守卫前置：确认自己不在将被杀的树里，再动任何进程
    if ($owner -gt 0 -and (Test-AncestorPid $owner)) {
        L '  致命：本脚本运行在 dsh web 的进程树内，杀树会把自己杀掉。必须以计划任务方式运行。'
        throw 'running-inside-web-tree'
    }
    $trays = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match '-File\s+.*DSH-tray\.ps1' })
    foreach ($t in $trays) { L ("  结束托盘 PID " + $t.ProcessId); Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($owner -gt 0) {

        L ("  结束 dsh web 进程树 PID $owner（/T）")
        & taskkill /PID $owner /T /F 2>$null | Out-Null
    }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if ((Test-PortOwner) -eq 0) { L ("  端口已释放（第 $($i + 1) 秒）"); return }
    }
    L '  端口 30 秒内未释放，继续尝试'
}
function Start-TrayAndWait([int]$timeout = 150) {
    if ($DryRun) { L '  【DryRun】将运行 DSH-Tray-Elevated 并等待端口'; return $true }
    Start-ScheduledTask -TaskName 'DSH-Tray-Elevated'
    for ($i = 0; $i -lt $timeout; $i++) {
        Start-Sleep -Seconds 1
        if ((Test-PortOwner) -ne 0) { L ("  端口已就绪（第 $($i + 1) 秒）"); return $true }
    }
    L '  等待超时，端口未监听'
    return $false
}
function Restore-HomeFile([string]$prev, [bool]$existedBefore) {
    if ($DryRun) { return }
    try {
        if ($existedBefore) { [IO.File]::WriteAllText($HomeFile, $prev, (New-Object System.Text.UTF8Encoding($false))) }
        else { Remove-Item -LiteralPath $HomeFile -Force -ErrorAction SilentlyContinue }
    } catch {}
}

try {
    $oldOwner = Test-PortOwner
    L '=== 切换到新家目录（v3）==='
    L ("目标: " + $NewHome)
    if (-not $OldHome) {
        if (Test-Path -LiteralPath $HomeFile) { $OldHome = ([IO.File]::ReadAllText($HomeFile, [Text.Encoding]::UTF8)).Trim() }
        if (-not $OldHome) { $OldHome = $env:DSH_HOME }
        if (-not $OldHome) { $OldHome = Join-Path $env:USERPROFILE '.dsh' }
    }
    L ("来源: " + $OldHome)
    L ("旧监听 PID: " + $oldOwner)

    if (-not (Test-Path -LiteralPath (Join-Path $NewHome 'profiles\web\package.json'))) {
        L '错误：新目录缺少 profiles\web\package.json，拒绝切换'
        Write-Status 'result=aborted-missing-profile'
        exit 1
    }

    $hadFile = $false; $prevContent = ''
    $hadFile = Test-Path -LiteralPath $HomeFile
    $prevContent = if ($hadFile) { [IO.File]::ReadAllText($HomeFile, [Text.Encoding]::UTF8) } else { '' }

    Stop-Dsh $oldOwner

    L '=== 增量同步（旧 → 新）==='
    $syncDone = Get-Date
    if ($DryRun) { L '  【DryRun】robocopy /E /XO /XJ /R:2 /W:2' }
    else {
        $rc = robocopy $OldHome $NewHome /E /XO /XJ /R:2 /W:2 /NFL /NDL /NJH /NJS /NP
        L ("  robocopy exit=" + $LASTEXITCODE)
        $syncDone = Get-Date
        if ($LASTEXITCODE -ge 8) {
            L '  robocopy 失败 → 不做切换，直接把服务拉回来'
            $null = Start-TrayAndWait
            Write-Status 'result=aborted-robocopy'
            exit 1
        }
    }

    L '=== 写家目录文件 ==='
    if ($DryRun) { L ("  【DryRun】写 " + $HomeFile + " = " + $NewHome) }
    else {
        [IO.File]::WriteAllText($HomeFile, $NewHome, (New-Object System.Text.UTF8Encoding($false)))
        L ("  dsh-home.txt = " + $NewHome)
    }

    L '=== 重启托盘 ==='
    $trayStart = Get-Date
    $ok = Start-TrayAndWait
    if ($ok) {
        $newOwner = Test-PortOwner
        L ("  新监听 PID: " + $newOwner + "（旧: " + $oldOwner + "）")
        if ($newOwner -eq $oldOwner -and -not $DryRun) { L '  PID 未变化，判定未重启'; $ok = $false }
        else {
            # 只认新家里真实更新的配置文件，且时间晚于托盘启动
            $cfg = Join-Path $NewHome 'profiles\web\cordis.yml'
            $cfgOk = $false
            for ($i = 0; $i -lt 30; $i++) {
                if (Test-Path -LiteralPath $cfg) {
                    $mt = (Get-Item -LiteralPath $cfg).LastWriteTime
                    if ($mt -ge $trayStart.AddSeconds(-2)) { $cfgOk = $true; L ("  cordis.yml 已在新家更新: " + $mt); break }
                }
                Start-Sleep -Seconds 1
            }
            if (-not $cfgOk) { L '  新家 cordis.yml 未更新，判定未生效'; $ok = $false }
        }
    }
    if ($ok) {
        # robocopy 之后的写入才算数（防止旧写入被复制造成假阳性）
        $recent = Get-ChildItem (Join-Path $NewHome 'sessions') -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $syncDone } | Select-Object -First 1
        if ($recent) { L ("  新家已有同步后的新写入: " + $recent.LastWriteTime) }
        L '=== 切换完成 ==='
        Write-Status ("result=ok`r`nhome=" + $NewHome)
    } else {
        L '切换失败 → 回滚（先停掉新家实例，再还原 dsh-home.txt，最后拉起托盘）'
        Stop-Dsh (Test-PortOwner)
        Restore-HomeFile $prevContent $hadFile
        $null = Start-TrayAndWait
        Write-Status 'result=rolled-back'
    }
}
catch {
    L ('异常: ' + $_.Exception.Message)
    if ($_.Exception.Message -eq 'running-inside-web-tree') {
        $null = Start-TrayAndWait
        Write-Status 'result=aborted-inside-web-tree'
    } else {
        Stop-Dsh (Test-PortOwner)
        Restore-HomeFile $prevContent $hadFile
        $null = Start-TrayAndWait
        Write-Status 'result=rolled-back-on-exception'
    }
}
finally {
    L '=== 结束（注销一次性任务）==='
    if (-not $DryRun) { try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch {} }
}
