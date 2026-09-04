function Get-GhLauncherVersion {
    # 拉取 GitHub 仓库内启动器 _meta.json 的版本号（__MODE_GHVER_COMMENT__）
    # 2026-08-30：带 $ghToken 访问——私有仓库也能检测；$ghToken 为空时匿名访问（公开仓库）。直连优先、失败回退系统代理。
    param([int]$TimeoutSec = 8)
    $u = "https://raw.githubusercontent.com/$ghRepo/$ghBranch/dsh-launcher/_meta.json"
    try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 } catch {}
    $proxies = @($null)
    $sysP = Get-SystemProxy
    if ($sysP) { $proxies += $sysP }
    foreach ($px in $proxies) {
        try {
            $wc = New-Object DshTimeoutWebClient
            $wc.TimeoutMs = $TimeoutSec * 1000
            if ($px) { $wc.Proxy = New-Object System.Net.WebProxy($px) } else { $wc.Proxy = $null }
            $wc.Encoding = [System.Text.Encoding]::UTF8
            $wc.Headers.Add('User-Agent', 'DSH-tray')
            if ($ghToken) { $wc.Headers.Add('Authorization', "token $ghToken") }
            return [string](([string]$wc.DownloadString($u)) | ConvertFrom-Json).version
        } catch {}
    }
    return $null
}
