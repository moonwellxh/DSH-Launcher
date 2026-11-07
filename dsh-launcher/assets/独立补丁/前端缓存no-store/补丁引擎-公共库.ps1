# ============================================================
#  补丁引擎-公共库.ps1 - 补丁引擎公共库（被各补丁的 安装脚本-*.ps1 / 还原脚本-*.ps1 dot-source）
#  提供：带备份的文件安装、按备份清单还原。
#  约定：
#    - ProfileDir：DSH web profile 的 node_modules（补丁目标根）
#    - BackupDir ：本次补丁的备份目录（已由引擎创建）
#    - 备份清单：$BackupDir\backup-manifest.json
#       键 = 目标相对路径（相对 ProfileDir）
#       值 = 备份文件绝对路径（原文件已备份）；null 表示该文件为补丁新增
# ============================================================
$ErrorActionPreference = 'Stop'

# 被 install.ps1 / restore.ps1 dot-source 时，从引擎注入的环境变量取默认值。
if (-not $ProfileDir) { $ProfileDir = $env:DSH_PATCH_PROFILE_DIR }
if (-not $BackupDir) { $BackupDir = $env:DSH_PATCH_BACKUP_DIR }

function Assert-PatchTargetRoot {
    # 0.2.x 没有 profile node_modules：只要 DSH 根可用即视为有目标根
    $hasProfile = ($ProfileDir -and (Test-Path -LiteralPath $ProfileDir))
    $hasRoot = ($env:DSH_PATCH_DSH_ROOT -and (Test-Path -LiteralPath $env:DSH_PATCH_DSH_ROOT))
    if (-not $hasProfile -and -not $hasRoot) {
        throw "补丁目标根无效：ProfileDir='$ProfileDir' DSH_ROOT='$env:DSH_PATCH_DSH_ROOT'"
    }
}

function Backup-ManifestPath {
    return Join-Path $BackupDir 'backup-manifest.json'
}

function Read-BackupManifest {
    $p = Backup-ManifestPath
    if (-not (Test-Path -LiteralPath $p)) { return @{} }
    $txt = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
    $obj = $txt | ConvertFrom-Json
    $map = @{}
    foreach ($prop in $obj.PSObject.Properties) { $map[$prop.Name] = $prop.Value }
    return $map
}

function Write-BackupManifest([hashtable]$map) {
    $sorted = @{}
    foreach ($k in ($map.Keys | Sort-Object)) { $sorted[$k] = $map[$k] }
    $json = $sorted | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText((Backup-ManifestPath), $json, (New-Object System.Text.UTF8Encoding($false)))
}

# ---------- 目标定位（2026-10-31 适配 DSH 0.2.x） ----------
# 旧布局 0.1.x：<profile>\node_modules\@deepseek-ai\<包>\lib\*.js
# 新布局 0.2.x：profile 不再携带 @deepseek-ai 包（bundles 改由源码树提供），
#              目标是 <DSH 根>\packages\<任意层级>\<包目录>\lib\*.js，
#              因此按 package.json 的 name 反查包目录。
$script:DshPackageMap = $null

function Get-DshPackageMap {
    if ($script:DshPackageMap) { return $script:DshPackageMap }
    $map = @{}
    $root = $env:DSH_PATCH_DSH_ROOT
    if ($root -and (Test-Path -LiteralPath $root)) {
        $pkgs = Join-Path $root 'packages'
        if (Test-Path -LiteralPath $pkgs) {
            Get-ChildItem -LiteralPath $pkgs -Recurse -Depth 3 -Filter 'package.json' -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch '[\\/](node_modules|lib|dist)[\\/]' } |
                ForEach-Object {
                    try {
                        $j = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                        $n = [string]$j.name
                        if ($n -and -not $map.ContainsKey($n)) { $map[$n] = [System.IO.Path]::GetDirectoryName($_.FullName) }
                    } catch {}
                }
        }
    }
    $script:DshPackageMap = $map
    return $map
}

function Resolve-PatchTarget([string]$RelPath) {
    # ① 旧布局优先：profile 里真有这个文件或它所在目录时，保持原行为
    if ($ProfileDir -and (Test-Path -LiteralPath $ProfileDir)) {
        $p = Join-Path $ProfileDir $RelPath
        $d = Split-Path -Parent $p
        if ((Test-Path -LiteralPath $p) -or (($RelPath -notmatch '^@deepseek-ai[\\/]') -and (Test-Path -LiteralPath $d))) { return $p }
    }
    # ② 新布局：@deepseek-ai\<包>\<剩余> → 源码树里同名包的目录
    if ($RelPath -match '^@deepseek-ai[\\/]([^\\/]+)[\\/](.+)$') {
        $pkgName = '@deepseek-ai/' + $Matches[1]
        $rest = $Matches[2]
        $map = Get-DshPackageMap
        if ($map.ContainsKey($pkgName)) { return (Join-Path $map[$pkgName] $rest) }
    }
    return $null
}
# 把补丁载荷文件安装到目标：
#   - 目标已存在：先备份原文件（同一文件只备份一次），再覆盖；
#   - 目标不存在：直接复制，并在清单里记为新增（值 null）。
#   RelPath      ：相对 ProfileDir 的目标路径，如 @deepseek-ai\dsh-client-ui-workspace\lib\client.js
#   PayloadFile  ：补丁目录内载荷文件的绝对路径
function Install-PatchedFile([string]$RelPath, [string]$PayloadFile) {
    Assert-PatchTargetRoot
    $dest = Resolve-PatchTarget $RelPath
    if (-not $dest) { throw "无法定位补丁目标: $RelPath（DSH 根='$env:DSH_PATCH_DSH_ROOT'，profile='$ProfileDir'）" }
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path -LiteralPath $destDir)) {
        throw "目标目录不存在: $destDir"
    }
    $map = Read-BackupManifest
    if (-not $map.ContainsKey($RelPath)) {
        if (Test-Path -LiteralPath $dest) {
            $relSafe = ($RelPath -replace '[\\/]+', '__')
            $backupFile = Join-Path $BackupDir ("orig__{0}" -f $relSafe)
            Copy-Item -LiteralPath $dest -Destination $backupFile -Force
            $map[$RelPath] = $backupFile
            Write-Host "    备份: $RelPath" -ForegroundColor DarkGray
        } else {
            $map[$RelPath] = $null
            Write-Host "    新增: $RelPath" -ForegroundColor DarkGray
        }
        Write-BackupManifest $map
    }
    Copy-Item -LiteralPath $PayloadFile -Destination $dest -Force
    Write-Host "    安装: $RelPath" -ForegroundColor Green
}

# 按备份清单还原：原文件拷回，补丁新增文件删除。
# 失败项保留在清单（下次可重试）；全部成功才清空清单并删除备份目录。
function Restore-AllBackups {
    $map = Read-BackupManifest
    $failed = @{}
    foreach ($RelPath in ($map.Keys | Sort-Object)) {
        $backupFile = $map[$RelPath]
        $dest = Resolve-PatchTarget $RelPath
        if (-not $dest) { Write-Host "    失败：无法定位 $RelPath（DSH 根='$env:DSH_PATCH_DSH_ROOT'）" -ForegroundColor Yellow; $failed[$RelPath] = $backupFile; continue }
        $ok = $false
        if ($backupFile -ne $null) {
            if (Test-Path -LiteralPath $backupFile) {
                $destDir = Split-Path $dest -Parent
                if (-not (Test-Path -LiteralPath $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
                try {
                    Copy-Item -LiteralPath $backupFile -Destination $dest -Force
                    Write-Host "    还原: $RelPath" -ForegroundColor Green
                    $ok = $true
                } catch {
                    Write-Host "    失败：还原 $RelPath：$($_.Exception.Message)" -ForegroundColor Yellow
                }
            } else {
                Write-Host "    警告：备份文件缺失，跳过还原 $RelPath（$backupFile）" -ForegroundColor Yellow
            }
        } else {
            if (Test-Path -LiteralPath $dest) {
                # 与拷贝分支对称：单文件删除失败（如文件锁）记警告并继续循环，
                # 保证还原循环不被 $ErrorActionPreference='Stop' 中断、清单最终回写
                try {
                    Remove-Item -LiteralPath $dest -Force
                    Write-Host "    移除（补丁新增）: $RelPath" -ForegroundColor Yellow
                    $ok = $true
                } catch {
                    Write-Host "    失败：移除 $RelPath：$($_.Exception.Message)" -ForegroundColor Yellow
                }
            } else {
                $ok = $true
            }
        }
        if (-not $ok) { $failed[$RelPath] = $backupFile }
    }
    if ($failed.Count -gt 0) {
        # 有失败项：保留「完整原始清单」（$map，含成功+失败项），便于下次重试；不删备份目录。
        # 注意：不能只写 $failed——否则成功还原的项会从清单丢失，备份文件成孤儿、状态不一致。
        # 成功项重试时 Copy-Item 覆盖回同样内容（原文件已拷回，备份仍指向它），幂等无害。
        Write-Host "  !! 部分还原失败（$($failed.Count) 项），备份清单与备份目录保留待重试。" -ForegroundColor Yellow
        Write-BackupManifest $map
        return
    }
    if ($map.Count -gt 0) {
        Write-BackupManifest @{}
        # 全部还原成功：删除备份目录，避免「目录存在=已应用」误报
        # safe-delete guard: only drop the patch backup dir we were told to use (containment + manifest)
        $safeDrop = $false
        if (-not [string]::IsNullOrWhiteSpace($BackupDir)) {
            $bd = [IO.Path]::GetFullPath($BackupDir).TrimEnd('\', '/')
            $isDriveRoot = ($bd.Length -le 3)
            $isHome = ($env:USERPROFILE -and ($bd -ieq $env:USERPROFILE.TrimEnd('\', '/')))
            $hasManifest = Test-Path -LiteralPath (Join-Path $bd 'backup-manifest.json')
            $contained = $false
            $root = $env:DSH_PATCH_BACKUP_ROOT
            if (-not [string]::IsNullOrWhiteSpace($root)) {
                $rt = [IO.Path]::GetFullPath($root).TrimEnd('\', '/')
                $contained = $bd.StartsWith($rt + '\', [StringComparison]::OrdinalIgnoreCase)
            }
            $safeDrop = (-not $isDriveRoot) -and (-not $isHome) -and $hasManifest -and $contained
        }
        if ($safeDrop) {
            try { Remove-Item -LiteralPath $BackupDir -Recurse -Force } catch { Write-Host ('    warn: backup dir kept: ' + $_.Exception.Message) -ForegroundColor Yellow }
        } else {
            Write-Host ('    warn: backup dir NOT removed (safe-delete guard): ' + $BackupDir + ' / root=' + $env:DSH_PATCH_BACKUP_ROOT) -ForegroundColor Yellow
        }
    }
}
