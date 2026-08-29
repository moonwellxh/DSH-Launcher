# ============================================================
#  dsh-sync.ps1 - DSH 启动器 GitHub 同步 CLI
#  支持 source / path 两种安装模式，统一发布级同步能力。
# ============================================================
param(
    [ValidateSet('source', 'path')][string]$Mode = 'path',
    [string]$SkillDir = '',
    [string]$InstallDir = '',
    [string]$GhRepo = 'moonwellxh/DSH-Launcher',
    [string]$GhBranch = 'main',
    [string]$GhToken = '',
    [ValidateSet('auto', 'upload', 'pull')][string]$Direction = 'auto',
    [switch]$NoRestart,
    [switch]$NoUI
)

$ErrorActionPreference = 'Stop'

# ---------- 配置优先级：环境变量 > ~/.dsh/gh-sync/config.json > 默认值 ----------
$ghSyncConfigPath = Join-Path $env:USERPROFILE '.dsh\gh-sync\config.json'
if ($env:DSH_SYNC_REPO)   { $GhRepo   = $env:DSH_SYNC_REPO }
if ($env:DSH_SYNC_BRANCH) { $GhBranch = $env:DSH_SYNC_BRANCH }
if ($env:DSH_SYNC_TOKEN)  { $GhToken  = $env:DSH_SYNC_TOKEN }
try {
    if (Test-Path -LiteralPath $ghSyncConfigPath) {
        $cfg = Get-Content -LiteralPath $ghSyncConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.repo   -and -not $env:DSH_SYNC_REPO)   { $GhRepo   = [string]$cfg.repo }
        if ($cfg.branch -and -not $env:DSH_SYNC_BRANCH) { $GhBranch = [string]$cfg.branch }
        if ($cfg.token  -and -not $env:DSH_SYNC_TOKEN)  { $GhToken  = [string]$cfg.token }
    }
} catch {}

$ghCache = Join-Path $env:USERPROFILE '.dsh\gh-sync\DSH-Launcher'
if (-not $SkillDir) { $SkillDir = Join-Path $env:USERPROFILE '.agents\skills\dsh-launcher' }
if (-not $InstallDir) { $InstallDir = Split-Path -Parent $PSCommandPath }

# ---------- 状态输出（JSON，便于托盘脚本解析） ----------
function Write-SyncStatus([string]$Level, [string]$Message, [hashtable]$Extra = @{}) {
    $o = [ordered]@{ level = $Level; message = $Message }
    foreach ($k in $Extra.Keys) { $o[$k] = $Extra[$k] }
    $json = $o | ConvertTo-Json -Compress -Depth 5
    Write-Output $json
    if (-not $NoUI -and $Level -in @('result', 'warning', 'error')) {
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
            $icon = [System.Windows.Forms.MessageBoxIcon]::Information
            if ($Level -eq 'warning') { $icon = [System.Windows.Forms.MessageBoxIcon]::Warning }
            elseif ($Level -eq 'error') { $icon = [System.Windows.Forms.MessageBoxIcon]::Error }
            [System.Windows.Forms.MessageBox]::Show($Message, 'DSH 启动脚本同步', [System.Windows.Forms.MessageBoxButtons]::OK, $icon) | Out-Null
        } catch {}
    }
}

# ---------- 通用工具 ----------
function Get-SystemProxy {
    try {
        $is = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        if ($is.ProxyEnable -and $is.ProxyServer) {
            $ps = [string]$is.ProxyServer
            if ($ps -match '(^|;)(?:http=)?(https?://[^;]+)') { return $Matches[2] }
            if ($ps -notmatch '^https?://') { return 'http://' + $ps }
            return $ps
        }
    } catch {}
    return ''
}
function Get-SyncAuthArgs {
    if ($GhToken) {
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes("x-access-token:$GhToken"))
        return @('-c', "http.extraheader=AUTHORIZATION: basic $b64")
    }
    return @()
}
function Test-GitErrorIsAuth {
    param([string]$Text)
    return [bool]($Text -match 'could not read Username|terminal prompts disabled|Authentication failed|Invalid username|Bad credentials|Repository not found|fatal: repository|401|403')
}
function Invoke-SyncGit {
    param([string[]]$GitArgs, [string]$WorkDir)
    $ErrorActionPreference = 'Continue'
    $sysProxy = Get-SystemProxy
    $strategies = New-Object System.Collections.ArrayList
    [void]$strategies.Add(@())
    if ($sysProxy) { [void]$strategies.Add(@('-c', "http.proxy=$sysProxy", '-c', "https.proxy=$sysProxy")) }
    $authArgs = Get-SyncAuthArgs
    $last = @{ code = 1; text = '' }
    foreach ($st in $strategies) {
        $cmd = @()
        if ($WorkDir) { $cmd += @('-C', $WorkDir) }
        $cmd += $st
        $cmd += $authArgs
        $cmd += $GitArgs
        $env:GIT_TERMINAL_PROMPT = '0'
        try { $env:GCM_INTERACTIVE = 'Never' } catch {}
        $txt = (& git @cmd 2>&1 | ForEach-Object { "$_" }) -join "`n"
        $code = $LASTEXITCODE
        if ($code -eq 0) { return @{ code = 0; text = $txt } }
        $last = @{ code = $code; text = $txt }
        if (Test-GitErrorIsAuth $txt) { break }
    }
    return $last
}
function Format-SyncError {
    param([int]$Code, [string]$Text, [string]$Step)
    if ($GhToken) { $Text = $Text -replace [regex]::Escape($GhToken), '***' }
    $Text = $Text -replace 'x-access-token:[^\s]+', '***' -replace 'basic [A-Za-z0-9+/=]+', 'basic ***'
    $tail = (($Text -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 8) -join "`n"
    $msg = "步骤「$Step」失败（exit $Code）。"
    if ($Text -match 'could not read Username|terminal prompts disabled|Authentication failed|Invalid username|Bad credentials') {
        $msg += "`n原因：GitHub 认证未通过（仓库私有或凭据缺失/失效）。读取公开仓库无需凭据；写入需配置 PAT："
        $msg += "`n  1) 在 $ghSyncConfigPath 加 `"token`" 字段，或 2) 设环境变量 DSH_SYNC_TOKEN。"
    } elseif ($Text -match 'Repository not found|fatal: repository|404') {
        $msg += "`n原因：仓库/分支不存在或无权访问（检查 config.json 的 repo/branch 拼写；私有仓库需配 token）。"
    } elseif ($Text -match 'Remote branch .*not found|couldn.t find remote ref') {
        $msg += "`n原因：分支 `"$GhBranch`" 不存在或未推送（检查 config.json 的 branch）。"
    } elseif ($Text -match 'Could not resolve host|Couldn.t resolve|Connection timed out|Connection was reset|Recv failure|Failed to connect|unable to access|schannel') {
        $msg += "`n原因：网络不通（已依次尝试直连与系统代理 `"$(Get-SystemProxy)`"）。请检查网络/代理。"
    } elseif ($Text -match 'shallow update not allowed|non-fast-forward|fetch first|diverged') {
        $msg += "`n原因：远端已有更新的提交（非快进）。处理：先执行「拉取 GitHub 版本」合并后再重试上传。"
    }
    if ($tail) { $msg += "`n`n--- git 输出（末 8 行）---`n$tail" }
    return $msg
}
function Get-SyncIgnoreSet {
    return @{ 'assets/install-dir.txt' = $true; 'install-dir.txt' = $true }
}
function Get-SyncFileHash {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes -contains 0) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    $norm = [System.Text.Encoding]::UTF8.GetBytes(([System.Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n"))
    $ms = New-Object System.IO.MemoryStream(, $norm)
    try { return (Get-FileHash -InputStream $ms -Algorithm SHA256).Hash } finally { $ms.Dispose() }
}
function Test-SyncRemoteTree {
    param([string]$Base)
    foreach ($n in @('SKILL.md', '_meta.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Base $n))) { return $false }
    }
    return $true
}
function Repair-SyncCache {
    param([string]$Cache, [string]$Branch)
    $parent = Split-Path $Cache -Parent
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    if (Test-Path -LiteralPath $Cache -PathType Leaf) { Remove-Item -LiteralPath $Cache -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath (Join-Path $Cache '.git')) {
        $ok = $false
        try { git -C $Cache rev-parse --is-inside-work-tree 2>$null | Out-Null; $ok = ($LASTEXITCODE -eq 0) } catch {}
        if (-not $ok) { Remove-Item -LiteralPath $Cache -Recurse -Force -ErrorAction SilentlyContinue }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Cache '.git'))) {
        $r = Invoke-SyncGit @('clone', '-b', $Branch, '--depth', '1', "https://github.com/$GhRepo.git", $Cache)
        if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git clone') }
    } else {
        $r = Invoke-SyncGit @('fetch','origin',"+refs/heads/$Branch:refs/remotes/origin/$Branch") $Cache
        if ($r.code -ne 0) {
            Remove-Item -LiteralPath $Cache -Recurse -Force -ErrorAction SilentlyContinue
            $r = Invoke-SyncGit @('clone', '-b', $Branch, '--depth', '1', "https://github.com/$GhRepo.git", $Cache)
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git clone（缓存修复后重试）') }
        } else {
            $r = Invoke-SyncGit @('reset', '--hard', "refs/remotes/origin/$Branch") $Cache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git reset') }
        }
    }
}
function Publish-SkillZip {
    param([string]$SkillDir, [string]$OutZip, [string]$RootName)
    try { Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop } catch {}
    try { Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop } catch {}
    if (-not (Test-Path -LiteralPath $SkillDir)) { return $false }
    if (Test-Path -LiteralPath $OutZip) { Remove-Item -LiteralPath $OutZip -Force }
    $zip = [System.IO.Compression.ZipFile]::Open($OutZip, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($SkillDir.Length).TrimStart('\') -replace '\\','/'
            if ($rel -in @('install-dir.txt', 'assets/install-dir.txt')) { return }
            $entry = $zip.CreateEntry(($RootName + '/' + $rel), [System.IO.Compression.CompressionLevel]::Optimal)
            $es = $entry.Open()
            try { $bytes = [System.IO.File]::ReadAllBytes($_.FullName); $es.Write($bytes, 0, $bytes.Length) } finally { $es.Close() }
        }
    } finally { $zip.Dispose() }
    return $true
}
function Get-SyncLock {
    $lockDir = Join-Path $env:USERPROFILE '.dsh\gh-sync'
    New-Item -ItemType Directory -Path $lockDir -Force | Out-Null
    $script:syncLock = $null
    try {
        $script:syncLock = [System.IO.File]::Open((Join-Path $lockDir '.lock'), [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        return $true
    } catch { return $false }
}
function Release-SyncLock {
    try { if ($script:syncLock) { $script:syncLock.Close(); $script:syncLock = $null } } catch {}
}

# ---------- DSH 版本探测（source/path 双模式） ----------
function Get-CurrentDshVersion {
    if ($Mode -eq 'source') {
        try {
            $dsRoot = $env:DSH_ROOT
            if (-not $dsRoot) {
                $cand = Join-Path $env:USERPROFILE 'deepseek-harness'
                if (Test-Path -LiteralPath (Join-Path $cand 'apps\cli\lib\bin.js')) { $dsRoot = $cand }
            }
            if (-not $dsRoot) { return '' }
            $pkg = Join-Path $dsRoot 'apps\cli\package.json'
            if (Test-Path -LiteralPath $pkg) { return [string](Get-Content -LiteralPath $pkg -Raw | ConvertFrom-Json).version }
            $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
            if (-not $nodeExe) { return '' }
            $v = & $nodeExe (Join-Path $dsRoot 'apps\cli\lib\bin.js') '--version' 2>&1
            return (($v | Select-Object -First 1) -as [string]).Trim()
        } catch { return '' }
    } else {
        try {
            $v = & dsh --version 2>&1
            return (($v | Select-Object -First 1) -as [string]).Trim()
        } catch { return '' }
    }
}

# ---------- 方向确认弹窗（独立运行时使用） ----------
function Show-SyncDirectionDialog([string]$text) {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop
    $f = New-Object System.Windows.Forms.Form
    $f.Text = 'DSH 启动脚本同步方向确认'
    $f.StartPosition = 'CenterScreen'
    $f.FormBorderStyle = 'FixedDialog'
    $f.MaximizeBox = $false
    $f.MinimizeBox = $false
    $f.ClientSize = New-Object System.Drawing.Size(560, 215)
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = $text
    $lbl.SetBounds(16, 16, 528, 125)
    $lbl.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
    $script:dialogResult = 'cancel'
    $bUp = New-Object System.Windows.Forms.Button
    $bUp.Text = '上传到 GitHub'
    $bUp.SetBounds(16, 152, 160, 38)
    $bUp.Add_Click({ $script:dialogResult = 'upload'; $f.Close() })
    $bPull = New-Object System.Windows.Forms.Button
    $bPull.Text = '拉取 GitHub 版本'
    $bPull.SetBounds(190, 152, 170, 38)
    $bPull.Add_Click({ $script:dialogResult = 'pull'; $f.Close() })
    $bCancel = New-Object System.Windows.Forms.Button
    $bCancel.Text = '取消'
    $bCancel.SetBounds(374, 152, 100, 38)
    $bCancel.Add_Click({ $script:dialogResult = 'cancel'; $f.Close() })
    $f.Controls.Add($lbl)
    $f.Controls.Add($bUp)
    $f.Controls.Add($bPull)
    $f.Controls.Add($bCancel)
    [void]$f.ShowDialog()
    $f.Dispose()
    return $script:dialogResult
}

# ---------- 拉取后重启托盘 ----------
function Restart-DshTray([string]$TrayPath) {
    if (-not (Test-Path -LiteralPath $TrayPath)) { return $false }
    try { $null = [scriptblock]::Create((Get-Content -LiteralPath $TrayPath -Raw -Encoding UTF8)); } catch { return $false }
    $helper = Join-Path $env:TEMP ("dsh-restart-" + [guid]::NewGuid().ToString('N') + '.ps1')
    @"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','$TrayPath' -WindowStyle Hidden
"@ | Set-Content -LiteralPath $helper -Encoding UTF8
    Start-Process powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$helper) -WindowStyle Hidden
    return $true
}

# ---------- 主同步流程 ----------
function Sync-LauncherScript {
    Write-SyncStatus 'info' '正在同步启动脚本…'
    if (-not (Get-SyncLock)) { throw '同步正在进行中，请稍后再试。' }
    $tmpZip = $null
    try {
        if (-not (Test-Path -LiteralPath $SkillDir)) { throw "本机技能目录不存在：$SkillDir" }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw '未找到 git：请先安装 Git（https://git-scm.com）；读取公开仓库无需凭据，写入需配置 token。' }
        Repair-SyncCache $ghCache $GhBranch
        $remoteBase = Join-Path $ghCache 'dsh-launcher'
        if (-not (Test-SyncRemoteTree $remoteBase)) { throw "GitHub 仓库结构异常：分支 `"$GhBranch`" 缺少 dsh-launcher/ 源树（SKILL.md/_meta.json）。请检查 branch 是否指向含源树的分支。" }

        $ignore = Get-SyncIgnoreSet
        $localMap = @{}
        Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
            $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
            if ($ignore.ContainsKey($rel)) { return }
            $localMap[$rel] = Get-SyncFileHash $_.FullName
        }
        $remoteMap = @{}
        Get-ChildItem -LiteralPath $remoteBase -Recurse -File | ForEach-Object {
            $rel = ($_.FullName.Substring($remoteBase.Length + 1) -replace '\\','/')
            if ($ignore.ContainsKey($rel)) { return }
            $remoteMap[$rel] = Get-SyncFileHash $_.FullName
        }
        $diff = @()
        foreach ($k in @(($localMap.Keys + $remoteMap.Keys) | Select-Object -Unique)) {
            if ($localMap[$k] -ne $remoteMap[$k]) { $diff += $k }
        }
        if ($diff.Count -eq 0) {
            Write-SyncStatus 'result' '启动脚本与 GitHub 完全一致，无需同步。' @{ action = 'none' }
            return
        }

        $lm = Get-Content -LiteralPath (Join-Path $SkillDir '_meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $rm = Get-Content -LiteralPath (Join-Path $remoteBase '_meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $lp = [long]$lm.publishedAt; $rp = [long]$rm.publishedAt
        $chosenDirection = $Direction
        if ($lp -eq $rp -and $Direction -eq 'auto') {
            $localNewer = $false; $remoteNewer = $false
            foreach ($k in $diff) {
                $rf = Join-Path $remoteBase ($k -replace '/','\')
                $rt = [datetime]::MinValue
                if (Test-Path -LiteralPath $rf) {
                    $cl = (Invoke-SyncGit @('log', '-1', '--format=%ct', '--', $k) $ghCache).text
                    if ($cl -match '\d+') {
                        $ct = [long]$Matches[0]
                        if ($ct -gt 0) { $rt = [datetimeoffset]::FromUnixTimeSeconds($ct).LocalDateTime }
                    }
                }
                $lf = Join-Path $SkillDir ($k -replace '/','\')
                $lt = if (Test-Path -LiteralPath $lf) { (Get-Item -LiteralPath $lf).LastWriteTimeUtc } else { [datetime]::MinValue }
                if ($lt -gt $rt) { $localNewer = $true } elseif ($rt -gt $lt) { $remoteNewer = $true }
                if ($localNewer -and $remoteNewer) { break }
            }
            $sug = '双向都有更新，无法自动判定，请人工确认合并方向'
            if ($localNewer -and -not $remoteNewer) { $sug = '本机较新（推荐：上传本机版本到 GitHub）' }
            elseif ($remoteNewer -and -not $localNewer) { $sug = 'GitHub 较新（推荐：拉取 GitHub 版本到本机）' }
            $showFiles = ($diff | Select-Object -First 5) -join '，'
            if ($diff.Count -gt 5) { $showFiles += ' 等' }
            $dlg = "启动脚本：本机与 GitHub 内容不同（$($diff.Count) 个文件：$showFiles）。`n按修改时间分析：$sug。`n`n请选择同步方向（上传会提交到 GitHub，git 历史会保留旧版本）："
            $dir = Show-SyncDirectionDialog $dlg
            if ($dir -eq 'upload') {
                $lm.publishedAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
                [System.IO.File]::WriteAllText((Join-Path $SkillDir '_meta.json'), ($lm | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
                $lp = [long]$lm.publishedAt
                $chosenDirection = 'upload'
            } elseif ($dir -eq 'pull') {
                $rp = $lp + 1
                $chosenDirection = 'pull'
            } else {
                Write-SyncStatus 'result' '已取消同步，未做任何更改。' @{ action = 'cancelled' }
                return
            }
        }

        if ($rp -gt $lp -or $chosenDirection -eq 'pull') {
            $curDsh = Get-CurrentDshVersion
            if ($rm.compatibleDsh) {
                $compat = @($rm.compatibleDsh)
                if ($curDsh -and ($compat -notcontains $curDsh)) {
                    Write-SyncStatus 'warning' "GitHub 上的启动器要求 DSH $($compat -join ' / ')，当前为 $curDsh，请先升级 DSH 再同步。"
                    return
                }
            }
            Get-ChildItem -LiteralPath $remoteBase -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($remoteBase.Length + 1) -replace '\\','/'
                if ($ignore.ContainsKey($rel)) { return }
                $dst = Join-Path $SkillDir ($rel -replace '/','\')
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
                if ($ignore.ContainsKey($rel)) { return }
                if (-not $remoteMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SkillDir 'assets\setup.ps1') -InstallDir $InstallDir -NoShortcut 2>&1 | Out-Null
            if (-not $NoRestart) {
                $newTray = Join-Path $InstallDir 'DSH-tray.ps1'
                if (Restart-DshTray $newTray) {
                    Write-SyncStatus 'result' "已从 GitHub 更新启动脚本（$($rm.version)），托盘即将重启。" @{ action = 'pulled'; version = [string]$rm.version; restarted = $true }
                    return
                } else {
                    Write-SyncStatus 'result' "已从 GitHub 更新启动脚本（$($rm.version)），但新脚本解析失败，请手动重启托盘。" @{ action = 'pulled'; version = [string]$rm.version; restarted = $false }
                    return
                }
            }
            Write-SyncStatus 'result' "已从 GitHub 更新启动脚本（$($rm.version)）。" @{ action = 'pulled'; version = [string]$rm.version }
        } elseif ($lp -gt $rp -or $chosenDirection -eq 'upload') {
            $srcTree = Join-Path $ghCache 'dsh-launcher'
            Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
                if ($ignore.ContainsKey($rel)) { return }
                $dst = Join-Path $srcTree ($rel -replace '/','\')
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            Get-ChildItem -LiteralPath $srcTree -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($srcTree.Length + 1) -replace '\\','/')
                if ($ignore.ContainsKey($rel)) { return }
                if (-not $localMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
            $releaseDir = Join-Path $ghCache ("releases\v" + $lm.version)
            New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
            $published = @()
            if (Publish-SkillZip $SkillDir (Join-Path $releaseDir 'dsh-launcher__skillhub.zip') 'dsh-launcher') { $published += 'dsh-launcher' }
            foreach ($c in @('zip-archive-ops','batch-files','charset-pitfalls','skill-install-ops')) {
                $cd = Join-Path $env:USERPROFILE (".agents\skills\$c")
                $out = Join-Path $releaseDir ($c + '__skillhub.zip')
                if (-not (Publish-SkillZip $cd $out $c)) {
                    $embedded = Join-Path $SkillDir "assets\配套技能\$($c)__skillhub.zip"
                    if (Test-Path -LiteralPath $embedded) { Copy-Item -LiteralPath $embedded -Destination $out -Force; $published += $c }
                    else { Write-SyncStatus 'warning' "配套技能 $c 目录缺失，跳过发布。" }
                } else { $published += $c }
            }
            foreach ($p in $published) {
                $zp = Join-Path $releaseDir ($p + '__skillhub.zip')
                try { $z = [System.IO.Compression.ZipFile]::OpenRead($zp); $z.Dispose() } catch { throw "打包校验失败（$p）：$($_.Exception.Message)" }
            }
            $r = Invoke-SyncGit @('add','-A') $ghCache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git add') }
            $r = Invoke-SyncGit @('status','--porcelain') $ghCache
            if (-not $r.text.Trim()) {
                Write-SyncStatus 'result' '内容已同步，无新变更需要推送。' @{ action = 'none' }
                return
            }
            $r = Invoke-SyncGit @('commit','-m',"dsh-launcher v$($lm.version) 同步（$([DateTimeOffset]::Now.ToString('yyyy-MM-dd HH:mm'))）") $ghCache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git commit') }
            $r = Invoke-SyncGit @('push','origin',"HEAD:$GhBranch") $ghCache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git push') }
            Write-SyncStatus 'result' "已将本机启动脚本上传到 GitHub（v$($lm.version)，发布 $($published.Count) 个 zip）。" @{ action = 'uploaded'; version = [string]$lm.version; published = $published }
        } else {
            Write-SyncStatus 'result' '启动脚本与 GitHub 完全一致，无需同步。' @{ action = 'none' }
        }
    } catch {
        Write-SyncStatus 'error' "同步失败：$($_.Exception.Message)"
    } finally {
        Release-SyncLock
        if ($tmpZip) { Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue }
    }
}

Sync-LauncherScript
