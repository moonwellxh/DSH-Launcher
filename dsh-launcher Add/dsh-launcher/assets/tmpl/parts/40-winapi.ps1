__MODE_WINACTIVATE_BODY__function Open-DshApp {
    # 优先打开用户已手动安装的「网址应用」（PWA）：已有窗口则恢复+置顶（不开多个），无则启动。
    # 检测：读 Edge Preferences.web_apps.daily_metrics["http://127.0.0.1:3080/"].installed
    # 已装且窗口已存在 → PostMessage(SC_RESTORE) + SetForegroundWindow（实测对 Edge PWA 有效）；
    #   窗口不存在 → msedge --app-id 启动；未装 PWA → 回退普通浏览器（返回 $false）
    param([string]$Url = $webUrl)
    $appId = 'hgiemfgfjhalibdoboikeiepnnjapnpc'
    $edge = $null
    # 用 [Environment]::GetFolderPath 而非 $env:ProgramFiles——托盘/安装流程若从 PATH 被精简的宿主进程
    #（如自动化 agent shell）启动，$env:ProgramFiles 可能为 null 导致 Join-Path 抛异常、静默退化成开标签页
    $edgeCands = @(
        (Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Microsoft\Edge\Application\msedge.exe')
    )
    foreach ($c in $edgeCands) { if (Test-Path -LiteralPath $c) { $edge = $c; break } }
    if (-not $edge) { return $false }
    # 检测 PWA 是否已安装
    $installed = $false
    $pref = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Microsoft\Edge\User Data\Default\Preferences'
    if (Test-Path -LiteralPath $pref) {
        try {
            $j = Get-Content -LiteralPath $pref -Raw -Encoding UTF8 | ConvertFrom-Json
            $dm = $j.web_apps.daily_metrics.'http://127.0.0.1:3080/'
            if ($dm -and $dm.installed) { $installed = $true }
        } catch {}
    }
    if (-not $installed) {
        # 未装 PWA → 引导式安装：打开 Edge 访问 3080（地址栏出现安装图标），气泡提示用户点一下
        # 用脚本级标记避免同一次托盘生命周期内重复引导（用户没装也不会每次双击都烦）
        try { Start-Process -FilePath $edge -ArgumentList $Url -ErrorAction Stop } catch {}
        if (-not $script:pwaGuideShown) {
            $script:pwaGuideShown = $true
            try { $notify.ShowBalloonTip(8000, 'DSH 安装为应用', '已打开 DSH 页面。点 Edge 地址栏右侧的「安装」图标，选「安装」，即可变成独立窗口应用（装好后双击托盘将直接打开它）。', 'Info') } catch {}
        }
        return $true   # 已处理（打开页面+引导），不让 Open-Url 再开普通网页
    }
    # 编译 Win32 辅助类（聚焦已有窗口，不开新的）
__MODE_WINACTIVATE_CALL__
    # 只认 PWA 应用窗口：普通浏览器窗口（标题以 "- Microsoft Edge" 结尾）里的 DSH 标签页不算，
    # 防止 Edge 把 --app-id 冷启动偶发开成标签后，浏览器窗口抢焦点（2026-08-30 实测案例）
    function Get-DshAppWindows {
        $appWins = @()
        $sb = New-Object System.Text.StringBuilder 300
        foreach ($h in [DshWinActivate]::FindDshWindows()) {
            $sb.Clear() | Out-Null
            [void][DshWinActivate]::GetWindowText($h, $sb, 300)
            if ($sb.ToString() -notmatch '-\s*Microsoft Edge\s*$') { $appWins += $h }
        }
        return $appWins
    }
    # 找已有 PWA 窗口 → 恢复+置顶；找不到 → 启动新的
    $wins = @(Get-DshAppWindows)
    if ($wins.Count -gt 0) {
        [DshWinActivate]::RestoreAndFocus($wins[0])
        return $true
    }
    # 冷启动重试：Edge 152 起 --app-id 在已有浏览器会话时可能被转发成普通标签页（实测）；
    # 第 1 次试 --app-id（真 PWA 身份），失败改 --app=URL（应用模式窗口，无需注册，Edge 152 实测可用）；
    # 仍无应用窗口则认输返回 $false，由 Open-Url 回退开普通标签页（保证双击一定有页面出来）
    $tryArgs = @("--app-id=$appId", "--app=$Url")
    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        try { Start-Process -FilePath $edge -ArgumentList @($tryArgs[$attempt]) -ErrorAction Stop } catch { continue }
        Start-Sleep -Seconds 4
        $wins = @(Get-DshAppWindows)
        if ($wins.Count -gt 0) {
            [DshWinActivate]::RestoreAndFocus($wins[0])
            return $true
        }
    }
    return $false
}
