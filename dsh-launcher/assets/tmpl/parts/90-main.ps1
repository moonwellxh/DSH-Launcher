# ---------- 启动/附着服务 ----------
$listener = Get-DshListenerPid
if ($CheckOnly) {
    # CheckOnly：只探测，不启动服务、不产生孤儿进程
    if ($listener -ne 0) { Write-Output "DSH Web 已在运行（PID $listener）" }
    else { Write-Output 'DSH Web 未运行（CheckOnly 不启动服务）' }
    Write-Output 'CheckOnly 模式结束'
    exit 0
}
$proc = $null
$script:startFailed = $false
if ($listener -eq 0) {
    $proc = Start-DshServer
    if ($proc) { Write-Output "已启动 DSH Web（PID $($proc.Id)）" }
    else { Write-Output '__MODE_START_FAILED_MSG__'; $script:startFailed = $true }
} else {
    Write-Output "DSH Web 已在运行（PID $listener）"
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$mutex = New-Object System.Threading.Mutex($false, 'Local\DSH-Tray-3080')
if (-not $mutex.WaitOne(0, $false)) {
    # 残留托盘（旧代码/图标丢失的僵尸）占着互斥锁：结束它们后接管，保证双击必定出新托盘
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '-File\s+.*DSH-tray\.ps1' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 800
    $mutex = New-Object System.Threading.Mutex($false, 'Local\DSH-Tray-3080')
    $owned = $false
    try { $owned = $mutex.WaitOne(0, $false) } catch { $owned = $true }
    if (-not $owned) { if ($OpenBrowser) { try { Open-Url $webUrl } catch {} }; exit 0 }
}

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Text = "DSH Web UI  -  $webUrl"
$icoPath = Join-Path $PSScriptRoot 'whale-white.ico'
if (-not (Test-Path -LiteralPath $icoPath)) { $icoPath = Join-Path $PSScriptRoot 'whale.ico' }
if (-not (Test-Path -LiteralPath $icoPath)) { $icoPath = Join-Path $PSScriptRoot 'tray.ico' }
if (Test-Path -LiteralPath $icoPath) { $notify.Icon = New-Object System.Drawing.Icon($icoPath) } else { $notify.Icon = [System.Drawing.SystemIcons]::Application }
$notify.Visible = $true
__MODE_START_FAILED_BLOCK__
# 外壳（Explorer）看护：Explorer 崩溃重启会丢失托盘图标注册，检测到后自动重新注册
$script:shellPid = 0
$script:shellStart = [datetime]::MinValue
try {
    $sh0 = Get-Process explorer -ErrorAction Stop | Select-Object -First 1
    if ($sh0) { $script:shellPid = $sh0.Id; $script:shellStart = $sh0.StartTime }
} catch {}
$shellTimer = New-Object System.Windows.Forms.Timer
$shellTimer.Interval = 5000
$shellTimer.Add_Tick({
    try {
        $sh = Get-Process explorer -ErrorAction Stop | Select-Object -First 1
        if ($sh -and ($sh.Id -ne $script:shellPid -or $sh.StartTime -ne $script:shellStart)) {
            $script:shellPid = $sh.Id
            $script:shellStart = $sh.StartTime
            try { $notify.Visible = $false; $notify.Visible = $true } catch {}
        }
    } catch {}
})
$shellTimer.Start()

# Web（dsh 服务）看护：服务意外停止后自动重启，无需手动（升级/崩溃后自动恢复）
# 带重启上限：连续 3 次自动重启仍未恢复 → 停止自动重启并提示（防老 DSH/坏安装反复拉起开浏览器）
$script:webDownCount = 0
$script:webRestartCount = 0
$script:webWatchdogDisabled = $false
$script:lastWebStart = [datetime]::MinValue
$webTimer = New-Object System.Windows.Forms.Timer
$webTimer.Interval = 5000
$webTimer.Add_Tick({
    try {
        if ($script:webWatchdogDisabled) { return }
        $listener = Get-DshListenerPid
        if ($listener -eq 0) {
            $script:webDownCount++
            if ($script:webDownCount -ge 3 -and ((Get-Date) - $script:lastWebStart).TotalSeconds -gt 30) {
                $script:webDownCount = 0
                $script:lastWebStart = Get-Date
                $script:webRestartCount++
                if ($script:webRestartCount -ge 3) {
                    $script:webWatchdogDisabled = $true
                    $notify.ShowBalloonTip(6000, 'DSH', 'DSH Web 反复启动失败（可能 DSH 版本过旧或安装异常），已停止自动重启。请升级 DSH，或用托盘「重启 DSH」/手动启动。', 'Warning')
                    return
                }
                $notify.ShowBalloonTip(3000, 'DSH', 'DSH Web 已停止，正在自动重启…', 'Info')
                $script:proc = Start-DshServer
                if ($null -eq $script:proc) {
                    $notify.ShowBalloonTip(4000, 'DSH', '__MODE_WEB_WATCHDOG_FAIL__', 'Error')
                }
            }
        } else {
            if ($script:webDownCount -ge 3) {
                $notify.ShowBalloonTip(2000, 'DSH', "DSH Web 已恢复（PID $listener）。", 'Info')
            }
            $script:webDownCount = 0
            $script:webRestartCount = 0
            # 服务恢复 → 重新武装看护（之前连续失败被禁用时，用户手动/升级救活后应能继续自动守护）
            if ($script:webWatchdogDisabled) {
                $script:webWatchdogDisabled = $false
                $notify.ShowBalloonTip(2000, 'DSH', 'DSH Web 已恢复，看护已重新武装。', 'Info')
            }
        }
    } catch {}
})
$webTimer.Start()



$menu = New-Object System.Windows.Forms.ContextMenuStrip
# 顶部分隔线上方三行：DSH 现有版本（加粗）/ 最新版本（可更新可点）/ 启动托盘版本（可更新/已是最新）
$miCur = New-Object System.Windows.Forms.ToolStripMenuItem
$miCur.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)
$miCur.Text = "DSH 版本 $(Get-CurrentDshVersion)"
$menu.Items.Add($miCur) | Out-Null
$miLatest = New-Object System.Windows.Forms.ToolStripMenuItem
$miLatest.Enabled = $false
$miLatest.Text = '最新版本：查询中…'
$menu.Items.Add($miLatest) | Out-Null
$miLauncher = New-Object System.Windows.Forms.ToolStripMenuItem
$miLauncher.Text = "启动托盘 $(Get-LauncherVersion) 版（检查中…）"
$menu.Items.Add($miLauncher) | Out-Null
$menu.Items.Add('-') | Out-Null
$miOpen  = $menu.Items.Add('打开 Web UI')
$miTui   = $menu.Items.Add('终端界面 (TUI)')
$miHead  = $menu.Items.Add('无界面模式 (Headless)')
$miDocs  = $menu.Items.Add('DS 开放平台')
$menu.Items.Add('-') | Out-Null
$miRestart = $menu.Items.Add('重启 DSH')
$miExit  = $menu.Items.Add('退出并停止 DSH')
$miCur.Add_Click({ try { Open-Url 'https://deepseekdocs.com/' } catch { $notify.ShowBalloonTip(3000, 'DSH', "打开文档失败：$($_.Exception.Message)", 'Error') } })
$miOpen.Add_Click({ try { Open-Url $webUrl } catch { $notify.ShowBalloonTip(3000, 'DSH', "打开 Web UI 失败：$($_.Exception.Message)", 'Error') } })
$miDocs.Add_Click({ try { Open-Url 'https://platform.deepseek.com/' } catch { $notify.ShowBalloonTip(3000, 'DSH', "打开开放平台失败：$($_.Exception.Message)", 'Error') } })

$miTui.Add_Click({ try { if (Test-Path -LiteralPath $launchBat) { Start-Process -FilePath $launchBat -ArgumentList '2' } else { Open-Url $webUrl } } catch { $notify.ShowBalloonTip(3000, 'DSH', "打开 TUI 失败：$($_.Exception.Message)", 'Error') } })
$miHead.Add_Click({ try { if (Test-Path -LiteralPath $launchBat) { Start-Process -FilePath $launchBat -ArgumentList '3' } else { Open-Url $webUrl } } catch { $notify.ShowBalloonTip(3000, 'DSH', "打开无界面模式失败：$($_.Exception.Message)", 'Error') } })
__MODE_RESTART_BODY__
$miExit.Add_Click({
    $toKill = Get-DshListenerPid
    if ($toKill -gt 0) { & taskkill /PID $toKill /T /F 2>$null | Out-Null }
    $notify.Visible = $false; $notify.Dispose()
    [System.Windows.Forms.Application]::Exit()
})
$notify.ContextMenuStrip = $menu

# 启动后延迟检查更新：刷新顶部三行版本信息
$script:newerAvail = $false
$script:latestVersion = $null
$verCheckTimer = New-Object System.Windows.Forms.Timer
$verCheckTimer.Interval = 2500
$verCheckTimer.Add_Tick({
    $verCheckTimer.Stop()
    try {
        $cur = Get-CurrentDshVersion
        $latest = Get-LatestDshInfo -TimeoutSec 8
        $miCur.Text = "DSH 版本 $cur"
        if ($latest) {
            $script:latestVersion = $latest.version
            if (Test-NewerVersion $cur $latest.version) {
                $script:newerAvail = $true
                $miLatest.Enabled = $true
                $miLatest.Text = "最新版本 $($latest.version)（点击升级）"
            } else {
                $miLatest.Enabled = $false
                $miLatest.Text = "最新版本 $($latest.version)（已是最新）"
            }
        } else {
            $miLatest.Enabled = $false
            $miLatest.Text = '最新版本：查询失败'
        }
        # 启动托盘行：显示本机启动器版本 + 与 GitHub 主分支对比后的可更新状态
        $ghVer = Get-GhLauncherVersion -TimeoutSec 8
        $lv = Get-LauncherVersion
        if ($ghVer -and (Test-NewerVersion $lv $ghVer)) {
            $miLauncher.Text = "启动托盘 $lv 版（点击可更新）"
        } elseif ($ghVer) {
            $miLauncher.Text = "启动托盘 $lv 版（已是最新）"
        } else {
            $miLauncher.Text = "启动托盘 $lv 版（检查失败）"
        }
    } catch {}
})
$verCheckTimer.Start()

# 顶部三行点击：最新版本→DSH 升级（弹窗确认后提交）；托盘版本→与 GitHub 双向同步
$miLatest.Add_Click({
    if (-not $script:newerAvail) { return }
    try {
        $instruction = Build-UpgradeInstruction (Get-CurrentDshVersion) $script:latestVersion
        Show-UpgradeDialog 'DSH 升级' $instruction
    } catch { $notify.ShowBalloonTip(3000, 'DSH 升级', "准备失败：$($_.Exception.Message)", 'Error') }
})
$miLauncher.Add_Click({
    __MODE_SYNC_CALL__
})


# 单击无动作（不弹气泡，信息在右键菜单顶部三行显示）；双击→开 DSH 主应用（PWA 优先，回退普通浏览器）
$notify.Add_DoubleClick({ param($s, $e) try { Open-Url $webUrl } catch { Start-Process $webUrl } })

# 启动状态气泡（透明度）
$notify.ShowBalloonTip(3000, 'DSH', $(if ($listener -eq 0) { "正在启动 DSH Web（PID $($proc.Id)）..." } else { "DSH Web 已在运行（PID $listener）" }), 'Info')

# 非阻塞就绪检查（Timer，不卡消息循环）
if ($OpenBrowser) {
    $script:browserOpened = $false
$readyTimer = New-Object System.Windows.Forms.Timer
    $readyTimer.Interval = 1000
    $readyTimer.Add_Tick({
        try {
            $ok = $false
            if ($null -ne $script:proc) {
                $script:proc.Refresh()
                if ($script:proc.HasExited) { $readyTimer.Stop(); return }
                if (Test-DshReady) { $ok = $true }
            } else {
                try { $r = Invoke-WebRequest -Uri $webUrl -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 600) { $ok = $true } } catch {}
            }
            if ($ok) { $readyTimer.Stop(); if (-not $script:browserOpened) { $script:browserOpened = $true; $notify.ShowBalloonTip(2000, 'DSH', 'DSH Web 已就绪，打开浏览器。', 'Info'); try { Open-Url $webUrl } catch {} } }
        } catch {}
    })
    $readyTimer.Start()
}

try { [System.Windows.Forms.Application]::Run() } finally { $notify.Visible = $false; $notify.Dispose() }
