# ============================================================
#  补丁引擎-应用还原检查.ps1 - DSH 补丁自动载入引擎
#  读取 自动载入清单-manifest.json，按顺序应用或还原补丁。
#
#  用法：
#    powershell -NoProfile -ExecutionPolicy Bypass -File 补丁引擎-应用还原检查.ps1                 # 应用清单中启用的补丁
#    powershell -NoProfile -ExecutionPolicy Bypass -File 补丁引擎-应用还原检查.ps1 -Restore        # 还原所有已应用补丁
#    powershell -NoProfile -ExecutionPolicy Bypass -File 补丁引擎-应用还原检查.ps1 -CheckOnly      # 只列出将做什么
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

# ---------- 警告级环境检查（仅提示风险，不阻断；引擎会被 setup.ps1 非交互调用） ----------
# ① dsh web 正在运行时打补丁/还原，运行中的进程可能缓存旧文件或持锁，导致补丁不生效或状态不一致；
# ② profile 的 @deepseek-ai 若为 junction/reparse point（2026-08-23 事故根因环境：指向源码树
#    构建产物），打补丁会同时改坏其指向的目标目录。
try {
    $dshWebProcs = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -match '(^|\s|""|/|\\)dsh([^\s""]*)?\s+web(\s|$)|bin\.js[^\r\n]*\sweb(\s|$)' })
    if ($dshWebProcs.Count -gt 0) {
        Write-Host '警告：检测到 dsh web 进程正在运行，应用/还原补丁前建议先停止 dsh web，' -ForegroundColor Yellow
        Write-Host '      否则补丁可能不生效或造成运行状态不一致（仅警告，不阻断）。' -ForegroundColor Yellow
    }
} catch {}
try {
    $dsAiDir = Join-Path $ProfileDir '@deepseek-ai'
    if (Test-Path -LiteralPath $dsAiDir) {
        $dsAiItem = Get-Item -LiteralPath $dsAiDir -Force -ErrorAction Stop
        $isReparse = ($null -ne $dsAiItem.LinkType) -or [bool]($dsAiItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        if ($isReparse) {
            $linkKind = if ($dsAiItem.LinkType) { $dsAiItem.LinkType } else { 'ReparsePoint' }
            Write-Host "警告：profile 的 @deepseek-ai 是 $linkKind（重解析点，可能指向源码树构建产物）——" -ForegroundColor Yellow
            Write-Host '      打补丁/还原会同时改动其指向的目标目录，请确认这是预期行为（仅警告，不阻断）。' -ForegroundColor Yellow
        }
    }
} catch {}

if ($Restore) {
    Step '还原全部已应用补丁（逆序）...'
    for ($i = $patches.Count - 1; $i -ge 0; $i--) {
        $p = $patches[$i]
        # 还原判断依据「是否已应用」（备份清单存在），不受 enabled 影响：
        # SKILL.md 升级流程要求先置 enabled=false 挂起，此时还原必须仍能回滚
        $backupDir = Join-Path $BackupRoot $p.id
        $backupManifest = Join-Path $backupDir 'backup-manifest.json'
        # 「是否已应用」口径收紧：备份目录存在 + 备份清单存在 + 清单解析后非空（含备份条目），
        # 三者齐备才算已应用。还原成功后清单被清空为 {}、备份目录被删除，仅凭目录/清单存在不再可靠。
        $wasApplied = (Test-Path -LiteralPath $backupDir) -and (Test-Path -LiteralPath $backupManifest)
        if ($wasApplied) {
            try {
                $bmObj = [System.IO.File]::ReadAllText($backupManifest, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                $wasApplied = (@($bmObj.PSObject.Properties).Count -gt 0)
            } catch {
                $wasApplied = $false
            }
        }
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
            # 清零上游残留的 $LASTEXITCODE（如 setup.ps1 同会话调用时上游 cmd 的退出码），
            # 防止脚本执行完读到非 0 残留而把补丁误判失败
            $global:LASTEXITCODE = $null
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
        # 同还原分支：调用前清零 $LASTEXITCODE，避免上游残留污染失败判断
        $global:LASTEXITCODE = $null
        & $install
        # $LASTEXITCODE 陷阱同还原分支：truthy 判断，仅脚本显式 exit 非 0 才中断
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
    } catch {
        Write-Host "  补丁应用失败：$($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
Step '补丁应用完成。'
