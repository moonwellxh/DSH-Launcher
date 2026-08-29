#Requires -Version 5.1
# ============================================================
# configure-git-credentials.ps1
# 配置 DSH-Launcher 的 GitHub 凭据（git push + 托盘同步共用 fine-grained token）
# ============================================================
<#
.SYNOPSIS
    一键配置 Git 凭据与 dsh-sync 同步配置。

.DESCRIPTION
    1. 安全提示输入 GitHub fine-grained PAT（输入过程不显示）。
    2. 通过 git credential approve 把 token 交给 Git Credential Manager。
    3. 写入 ~/.dsh/gh-sync/config.json，供 dsh-sync.ps1 读取。
    4. 可选执行 git fetch 测试连通性。

.REQUIREMENTS
    - Windows PowerShell 5.1 或 PowerShell 7+
    - 已安装 Git for Windows（带 Credential Manager）
#>
$ErrorActionPreference = 'Stop'

function Read-SecureToken([string]$Prompt = '请输入 GitHub fine-grained PAT') {
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    return $plain
}

function Invoke-GitCredentialApprove([string]$Token) {
    $credInput = @"
protocol=https
host=github.com
username=x-access-token
password=$Token

"@
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'git'
    $psi.Arguments = 'credential approve'
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.StandardInput.Write($credInput)
    $p.StandardInput.Close()
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) {
        throw "git credential approve 失败（exit $($p.ExitCode)）：$($p.StandardError.ReadToEnd())"
    }
}

# ---------- 1. 读 token ----------
$token = Read-SecureToken
if (-not $token) {
    Write-Warning '未输入 token，已退出。'
    exit 1
}
if (-not $token.StartsWith('github_pat_')) {
    Write-Warning '输入的不是 github_pat_ 开头的 fine-grained token，已退出。'
    exit 1
}

# ---------- 2. 配置 git credential ----------
Invoke-GitCredentialApprove $token
Write-Host 'git 凭据已配置。' -ForegroundColor Green

# ---------- 3. 写入 dsh-sync 配置 ----------
$configDir = Join-Path $env:USERPROFILE '.dsh\gh-sync'
$configPath = Join-Path $configDir 'config.json'
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
$cfg = [ordered]@{
    repo   = 'moonwellxh/DSH-Launcher'
    branch = 'feature/github-sync-v1.1.66'
    token  = $token
}
$cfg | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Host "dsh-sync 配置已写入：$configPath" -ForegroundColor Green

# ---------- 4. 可选测试 ----------
$test = Read-Host '是否测试 git fetch origin？（Y/N，默认 N）'
if ($test -eq 'Y' -or $test -eq 'y') {
    git fetch origin
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'git fetch 测试通过。' -ForegroundColor Green
    } else {
        Write-Warning 'git fetch 测试失败，请检查 token 权限与仓库访问。'
    }
}

Write-Host '完成。' -ForegroundColor Green