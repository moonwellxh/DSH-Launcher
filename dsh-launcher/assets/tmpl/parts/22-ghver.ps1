function Get-GhLauncherVersion {
    # 拉取 GitHub 仓库内启动器 _meta.json 的版本号（__MODE_GHVER_COMMENT__）
    param([int]$TimeoutSec = 8)
    try {
        try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 } catch {}
        $u = "https://raw.githubusercontent.com/$ghRepo/$ghBranch/dsh-launcher/_meta.json"
        $r = $null
        try {
            $wc = New-Object System.Net.WebClient
            $wc.Proxy = $null
            $wc.Encoding = [System.Text.Encoding]::UTF8
            $wc.Headers.Add('User-Agent', 'DSH-tray')
            $r = [string]($wc.DownloadString($u) | ConvertFrom-Json).version
        } catch {
            $r = [string](Invoke-RestMethod -Uri $u -TimeoutSec $TimeoutSec).version
        }
        if ($r) { return $r }
    } catch {}
    return $null
}
