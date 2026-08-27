# ============================================================
#  apply-patches.ps1 - DSH 补丁自动载入引擎
#  读取 manifest.json（自动载入清单），按顺序应用或还原补丁。
#
#  用法：
#    powershell -NoProfile -ExecutionPolicy Bypass -File apply-patches.ps1                 # 应用清单中启用的补丁
#    powershell -NoProfile -ExecutionPolicy Bypass -File apply-patches.ps1 -Restore        # 还原所有已应用补丁
#    powershell -NoProfile -ExecutionPolicy Bypass -File apply-patches.ps1 -CheckOnly      # 只列出将做什么
#  可选参数：
#    -Manifest   <json 路径>   默认：本脚本同目录 manifest.json
#    -ProfileDir <目录>        默认：~\.dsh\profiles\node_modules
#    -BackupRoot <目录>        默认：~\.dsh\patches-backup
# ============================================================
param(
    [string]$Manifest = '',
    [string]$ProfileDir = '',
    [string]$BackupRoot = '',
    [switch]$Restore,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }

# ---------- 定位 DSH web profile node_modules ----------
if (-not $ProfileDir) {
    $cand = Join-Path $env:USERPROFILE '.dsh\profiles\node_modules'
    if (Test-Path -LiteralPath $cand) { $ProfileDir = $cand }
}
if (-not $ProfileDir -or -not (Test-Path -LiteralPath $ProfileDir)) {
    # 非源码/profile 结构安装时补丁无目标可打：警告并跳过（不报错、不撞墙）
    Write-Host '警告：未找到 DSH web profile 的 node_modules（默认 ~\.dsh\profiles\node_modules），' -ForegroundColor Yellow
    Write-Host '      本机可能非源码结构安装，补丁跳过未应用。' -ForegroundColor Yellow
    exit 0
}
if (-not $BackupRoot) { $BackupRoot = Join-Path $env:USERPROFILE '.dsh\patches-backup' }
if (-not $Manifest) { $Manifest = Join-Path $PSScriptRoot '自动载入清单-manifest.json' }
if (-not (Test-Path -LiteralPath $Manifest)) {
    Write-Host "错误：找不到清单 $Manifest" -ForegroundColor Red
    exit 1
}

$lib = Join-Path $PSScriptRoot '补丁引擎-公共库.ps1'
if (-not (Test-Path -LiteralPath $lib)) {
    Write-Host "错误：找不到补丁公共库 $lib" -ForegroundColor Red
    exit 1
}

$manifestText = [System.IO.File]::ReadAllText($Manifest, [System.Text.Encoding]::UTF8)
$parsedManifest = $manifestText | ConvertFrom-Json
$patches = @($parsedManifest.patches | Where-Object { $_ -ne $null })

if ($patches.Count -eq 0) {
    Write-Host '清单中没有补丁，无需处理。' -ForegroundColor Green
    exit 0
}

Write-Host "DSH profile : $ProfileDir"
Write-Host "备份根      : $BackupRoot"
Write-Host "清单        : $Manifest（补丁数：$($patches.Count)）"

# ---------- 当前 DSH 版本（补丁兼容性检查用） ----------
$currentDshVersion = ''
$dshPkg = Join-Path $ProfileDir '@deepseek-ai\dsh\package.json'
if (Test-Path -LiteralPath $dshPkg) {
    try { $currentDshVersion = [string](([System.IO.File]::ReadAllText($dshPkg, [System.Text.Encoding]::UTF8)) | ConvertFrom-Json).version } catch {}
}
if ($currentDshVersion) { Write-Host "当前 DSH 版本 : $currentDshVersion" }

if ($Restore) {
    Step '还原全部已应用补丁（逆序）...'
    for ($i = $patches.Count - 1; $i -ge 0; $i--) {
        $p = $patches[$i]
        # 还原判断依据「是否已应用」（备份清单存在），不受 enabled 影响：
        # SKILL.md 升级流程要求先置 enabled=false 挂起，此时还原必须仍能回滚
        $backupDir = Join-Path $BackupRoot $p.id
        $backupManifest = Join-Path $backupDir 'backup-manifest.json'
        $wasApplied = (Test-Path -LiteralPath $backupDir) -and (Test-Path -LiteralPath $backupManifest)
        if (-not $wasApplied) {
            Write-Host "  跳过还原（未应用过）：$($p.id)" -ForegroundColor Yellow
            continue
        }
        $patchName = if ($p.dir) { $p.dir } else { $p.id }
        $patchDir = Join-Path $PSScriptRoot $patchName
        $restoreScript = Join-Path $patchDir $p.restore
        if (-not (Test-Path -LiteralPath $restoreScript)) {
            Write-Host "  跳过还原（无 restore 脚本）：$($p.id)" -ForegroundColor Yellow
            continue
        }
        Write-Host "  还原补丁：$($p.id)（$($p.name)）"
        if ($CheckOnly) { continue }   # CheckOnly：只列出计划，不真正还原
        $env:DSH_PATCH_BACKUP_DIR = Join-Path $BackupRoot $p.id
        $env:DSH_PATCH_PROFILE_DIR = $ProfileDir
        try {
            & $restoreScript
            # $LASTEXITCODE 陷阱：PowerShell 脚本调用不设置该变量（全新进程为 $null），
            # 只有脚本内显式 exit <非0> 才应中断；用 truthy 判断避免 $null -ne 0 恒真
            if ($LASTEXITCODE) { exit $LASTEXITCODE }
        } catch {
            Write-Host "  还原失败：$($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
    }
    Step '还原完成。'
    exit 0
}

Step '按清单应用补丁...'
foreach ($p in $patches) {
    if (-not $p.enabled) {
        Write-Host "  跳过（清单未启用）：$($p.id)" -ForegroundColor Yellow
        continue
    }
    # 兼容性检查：补丁声明了适配的 DSH 版本，当前版本不在列表则跳过并提醒（防旧 DSH 装新适配补丁导致冲突）
    if ($p.compatibleDsh) {
        $compat = @($p.compatibleDsh)
        if (-not $currentDshVersion) {
            Write-Host "  跳过（无法确定当前 DSH 版本，按不兼容处理）：$($p.id) 适配 DSH $($compat -join ' / ')" -ForegroundColor Yellow
            continue
        }
        if ($compat -notcontains $currentDshVersion) {
            Write-Host "  跳过（兼容性不符）：$($p.id) 适配 DSH $($compat -join ' / ')，当前 DSH 为 $currentDshVersion" -ForegroundColor Yellow
            Write-Host "    → 如需使用本补丁，请先升级 DSH 到 $($compat -join ' / ')，或将补丁适配到 $currentDshVersion" -ForegroundColor Yellow
            continue
        }
    }
    $patchName = if ($p.dir) { $p.dir } else { $p.id }
    $patchDir = Join-Path $PSScriptRoot $patchName
    if (-not (Test-Path -LiteralPath $patchDir)) {
        Write-Host "  错误：补丁目录不存在 $patchDir" -ForegroundColor Red
        exit 1
    }
    $install = Join-Path $patchDir $p.install
    if (-not (Test-Path -LiteralPath $install)) {
        Write-Host "  错误：补丁缺少 install 脚本 $install" -ForegroundColor Red
        exit 1
    }
    $backupDir = Join-Path $BackupRoot $p.id
    if (-not $CheckOnly) {
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    }
    Write-Host "  补丁：$($p.name)（$($p.version)）"
    if ($p.description) { Write-Host "    $($p.description)" -ForegroundColor DarkGray }
    if ($p.requiresRestart) { Write-Host "    注意：本补丁需要重启 dsh web 才完全生效。" -ForegroundColor Magenta }
    if ($CheckOnly) { continue }
    $env:DSH_PATCH_BACKUP_DIR = $backupDir
    $env:DSH_PATCH_PROFILE_DIR = $ProfileDir
    try {
        & $install
        # $LASTEXITCODE 陷阱同还原分支：truthy 判断，仅脚本显式 exit 非 0 才中断
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
    } catch {
        Write-Host "  补丁应用失败：$($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
Step '补丁应用完成。'
