__MODE_WINACTIVATE_BODY__function Open-DshApp {
    # 打开 DSH 主窗口：已有窗口则恢复+置顶（不开多个）；没有才启动，且只启动一次。
    # 检测：读 Edge Preferences.web_apps.daily_metrics["http://127.0.0.1:3080/"].installed
    # 已装且窗口已存在 → PostMessage(SC_RESTORE) + SetForegroundWindow（实测对 Edge PWA 有效）；
    #   没有窗口 → msedge --app-id=<已装 PWA> 启动一次（2026-10-25 起只发一次，不再两段重试）；
    #   未装 PWA → 打开 Edge 页面 + 气泡引导「安装为应用」（返回 $true）
    param([string]$Url = $webUrl)
    # 已装 PWA 的应用 id（与 setup.ps1 建的 DSH应用.lnk 同一个）
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
            try { Show-DshNotice(8000, 'DSH 安装为应用', '已打开 DSH 页面。点 Edge 地址栏右侧的「安装」图标，选「安装」，即可变成独立窗口应用（桌面会多一个「DSH应用」快捷方式，双击它打开的就是这个应用窗口）。', 'Info') } catch {}
        }
        return $true   # 已处理（打开页面+引导），不让 Open-Url 再开普通网页
    }
    # 编译 Win32 辅助类（聚焦已有窗口，不开新的）
__MODE_WINACTIVATE_CALL__
    # 只认应用窗口：普通浏览器窗口（标题以 "- Microsoft Edge" 结尾）里的 DSH 标签页不算，
    # 防止 --app=URL 被 Edge 转发成标签页后，浏览器窗口抢焦点（2026-08-30 实测案例）
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
    # 冷启动（2026-10-25 三轮定稿，按用户指定分两级）：
    #   默认模式 = --app-id=<已装 PWA>：无标题栏的独立应用窗口（WCO，没有标签栏/地址栏）；
    #   降级模式 = --app=<带令牌 URL>：带标题栏的应用窗口（页面能用、观感差一档，只作兜底）。
    # 旧实现（1.1.89~1.1.93）的毛病不只是"两种外观"：它先 --app=URL 睡 4 秒、再按需补发 --app-id，
    # 所以表现为"先冒带标题栏的那个、4 秒后再冒无标题栏的"，关掉第一个正好触发第二个。
    # 现在：默认入口只发一次 → 250ms 轮询最多 12 秒（Edge 冷启动要几秒，留足余量以免误判降级；
    # 窗口一出现就置顶返回，用户随后关掉也不会补开）。只有"整整 12 秒一个窗口都没枚举到"
    # （PWA 起不来，或标题一直不就位——例如 cookie 过期后的 401 页）才降级发 --app=<带令牌 URL>，
    # 再轮询 6 秒。两条都没窗口时才返回 $false，交给 Open-Url 用默认浏览器做最后兜底。
    # 令牌两处都带着：--app-id 用 Chromium 的 app-launch-url 开关捎进去（认就顺带刷新 30 天 cookie，
    # 不认就退回 app 自己的 start_url，等于旧版 --app-id 行为），--app=URL 本身就在令牌入口上。
    $launchArgs = @("--app-id=$appId", "--app-launch-url-for-shortcuts-menu-item=$Url")
    try { Start-Process -FilePath $edge -ArgumentList $launchArgs -ErrorAction Stop } catch { return $false }
    for ($i = 0; $i -lt 48; $i++) {
        Start-Sleep -Milliseconds 250
        $wins = @(Get-DshAppWindows)
        if ($wins.Count -gt 0) {
            [DshWinActivate]::RestoreAndFocus($wins[0])
            return $true
        }
    }
    # 降级：默认入口 12 秒内没出窗口 → 用带令牌 URL 的应用窗口兜底（令牌当场换 cookie，不会 401）
    try { Start-Process -FilePath $edge -ArgumentList @("--app=$Url") -ErrorAction Stop } catch { return $true }
    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep -Milliseconds 250
        $wins = @(Get-DshAppWindows)
        if ($wins.Count -gt 0) {
            [DshWinActivate]::RestoreAndFocus($wins[0])
            return $true
        }
    }
    # 两级入口都没枚举到窗口：才返回 $false，由 Open-Url 用默认浏览器做最后一次兜底（保证一定有页面）。
    # 这种情况只可能是 Edge 完全不响应启动请求；正常与降级两种结果都已在上面的轮询里返回。
    return $false
}
