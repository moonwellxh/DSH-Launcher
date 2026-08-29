function Get-GhLauncherVersion {
    # 拉取 GitHub 仓库内启动器 _meta.json 的版本号（__MODE_GHVER_COMMENT__）
    param([int]$TimeoutSec = 8)
    try {
        $u = "https://raw.githubusercontent.com/$ghRepo/$ghBranch/dsh-launcher/_meta.json"
        return [string]((Invoke-DshHttp -Uri $u -TimeoutSec $TimeoutSec) | ConvertFrom-Json).version
    } catch {}
    return $null
}
