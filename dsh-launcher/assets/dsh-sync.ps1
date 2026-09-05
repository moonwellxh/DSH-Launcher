# ============================================================
#  dsh-sync.ps1 - DSH 启动器 GitHub 同步 CLI
#  支持 source / path 两种安装模式，统一发布级同步能力。
# ============================================================
param(
    [ValidateSet('source', 'path')][string]$Mode = 'path',
    [string]$SkillDir = '',
    [string]$InstallDir = '',
    [string]$GhRepo = '__GH_REPO__',
    [string]$GhBranch = '__GH_BRANCH__',
    [string]$GhToken = '',
    [ValidateSet('auto', 'upload', 'pull')][string]$Direction = 'auto',
    [switch]$NoRestart,
    [switch]$NoUI
)

$ErrorActionPreference = 'Stop'

# ---------- 清理宿主 agent（kimi daimon）注入的 git 配置变量，防 git 报 missing config key（2026-08-30） ----------
Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_CONFIG_*' } | Remove-Item -ErrorAction SilentlyContinue

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
function Compare-SyncVersion {
    # Semantic version compare: 1(a>b) / -1(a<b) / 0 (fallback to string compare if unparseable)
    param([string]$A, [string]$B)
    $av = $null; $bv = $null
    [void][version]::TryParse($A, [ref]$av)
    [void][version]::TryParse($B, [ref]$bv)
    if ($av -and $bv) { return [Math]::Sign($av.CompareTo($bv)) }
    return [string]::Compare($A, $B, [System.StringComparison]::OrdinalIgnoreCase)
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
function Is-SyncIgnored {
    # 分发安全红线（2026-08-30）：机器特定文件与一切凭证类文件一律不进打包/上传/下载——
    # 即使误把 config.json / credentials / .dsh / *.token 放进技能目录，也会被这里拦下，绝不外泄。
    param([string]$Rel)
    if ($Rel -in @('install-dir.txt', 'assets/install-dir.txt')) { return $true }
    if ($Rel -match '(^|/)(config\.json|credentials[^/]*|\.dsh[^/]*|[^/]*\.token[^/]*)$') { return $true }
    return $false
}
function Get-SyncFileHash {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    # .bat/.cmd 是 GBK 编码的脚本：直接按原始字节哈希，不做文本归一化（配合仓库 .gitattributes 固定换行）
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($bytes -contains 0 -or $ext -in @('.bat', '.cmd')) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    # 其余文本文件：先严格 UTF-8 解码（失败则回退 GBK/936），归一化 CRLF→LF 后按 UTF-8 字节哈希
    try { $text = [System.Text.UTF8Encoding]::new($false, $true).GetString($bytes) }
    catch { $text = [System.Text.Encoding]::GetEncoding(936).GetString($bytes) }
    $norm = [System.Text.Encoding]::UTF8.GetBytes(($text -replace "`r`n", "`n"))
    $ms = New-Object System.IO.MemoryStream(, $norm)
    try { return (Get-FileHash -InputStream $ms -Algorithm SHA256).Hash } finally { $ms.Dispose() }
}
# ---------- 配套技能同步（1.1.81+：配套目录纳入比对，版本变化自动检测推送） ----------
# 配套清单 = assets\配套技能\ 目录即事实源（2026-09-05 归一）：扫描目录内全部
# *__skillhub.zip 推导 slug，与 setup.ps1 安装同源——增删配套只需放/删 zip，引擎零改动。
$script:CompanionSkills = @(Get-ChildItem -LiteralPath (Join-Path $SkillDir 'assets\配套技能') -Filter '*__skillhub.zip' -File -ErrorAction SilentlyContinue | ForEach-Object { $_.BaseName -replace '__skillhub$','' } | Sort-Object -Unique)
function Read-MetaObject {
    param([string]$MetaFile)
    if (-not (Test-Path -LiteralPath $MetaFile)) { return $null }
    try { return (Get-Content -LiteralPath $MetaFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}
function Read-ZipMetaObject {
    param([string]$ZipPath, [string]$RootName)
    if (-not (Test-Path -LiteralPath $ZipPath)) { return $null }
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
        $z = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        try {
            $e = $z.Entries | Where-Object { $_.FullName -eq "$RootName/_meta.json" } | Select-Object -First 1
            if (-not $e) { return $null }
            $sr = New-Object System.IO.StreamReader($e.Open())
            try { return ($sr.ReadToEnd() | ConvertFrom-Json) } finally { $sr.Close() }
        } finally { $z.Dispose() }
    } catch { return $null }
}
function Get-CompanionSyncState {
    # 比对：已装配套（~/.agents/skills/<c>） vs 本地主树内嵌 zip vs GitHub 主树内嵌 zip
    # 返回：changed / localNewer / remoteNewer / notes / refresh（上传时需自动刷新内嵌 zip 的配套列表）
    param([string]$SkillDir, [string]$RemoteBase, [string]$UserHome = $env:USERPROFILE)
    $state = @{ changed = $false; localNewer = $false; remoteNewer = $false; notes = @(); refresh = @() }
    foreach ($c in $script:CompanionSkills) {
        $instMeta = Join-Path $UserHome ".agents\skills\$c\_meta.json"
        $localEmb = Join-Path $SkillDir "assets\配套技能\$c`__skillhub.zip"
        $remoteEmb = Join-Path $RemoteBase "assets\配套技能\$c`__skillhub.zip"
        $lm = Read-MetaObject $instMeta
        if (-not $lm) { continue }
        $rm = Read-ZipMetaObject $remoteEmb $c
        $le = Read-ZipMetaObject $localEmb $c
        $lv = [string]$lm.version; $lp = [long]$lm.publishedAt
        $rv = if ($rm) { [string]$rm.version } else { '' }
        $rp = if ($rm) { [long]$rm.publishedAt } else { 0 }
        $lev = if ($le) { [string]$le.version } else { '' }
        if ($lv -eq $rv -and $lv -eq $lev) { continue }
        $state.changed = $true
        $dir2 = 'upload'
        if ($rv) {
            $vc2 = Compare-SyncVersion $lv $rv
            if ($vc2 -gt 0) { $dir2 = 'upload' }
            elseif ($vc2 -lt 0) { $dir2 = 'pull' }
            elseif ($lp -ne $rp) { $dir2 = if ($lp -gt $rp) { 'upload' } else { 'pull' } }
            else { $dir2 = 'upload' }
        }
        if ($dir2 -eq 'upload') { $state.localNewer = $true } else { $state.remoteNewer = $true }
        if ($lv -ne $lev) { $state.refresh += $c }
        $state.notes += "$c：本机 $lv vs GitHub $(if ($rv) { $rv } else { '无' })"
    }
    return $state
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
            if (Is-SyncIgnored $rel) { return }
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
function Get-ContentDiffAnalysis {
    # 真实文件 diff 分析：逐文件对比 本地修改时间 vs GitHub 该文件最近提交时间（只用于给建议）
    param([string]$SkillDir, [string]$RemoteBase, [string]$GhCache, [string[]]$DiffFiles)
    $localNewer = 0; $remoteNewer = 0
    $samples = @()
    foreach ($k in $DiffFiles) {
        $samples += (($k -replace '^.*?([^/]+)$', '$1'))
        $rf = Join-Path $RemoteBase ($k -replace '/', '\')
        $rt = [datetime]::MinValue
        if (Test-Path -LiteralPath $rf) {
            $cl = (Invoke-SyncGit @('log', '-1', '--format=%ct', '--', $k) $GhCache).text
            if ($cl -match '\d+') { $ct = [long]$Matches[0]; if ($ct -gt 0) { $rt = [datetimeoffset]::FromUnixTimeSeconds($ct).UtcDateTime } }
        }
        $lf = Join-Path $SkillDir ($k -replace '/', '\')
        $lt = if (Test-Path -LiteralPath $lf) { (Get-Item -LiteralPath $lf).LastWriteTimeUtc } else { [datetime]::MinValue }
        if ($lt -gt $rt) { $localNewer++ } elseif ($rt -gt $lt) { $remoteNewer++ }
    }
    $sug = 'mixed'
    if ($localNewer -gt 0 -and $remoteNewer -eq 0) { $sug = 'upload' }
    elseif ($remoteNewer -gt 0 -and $localNewer -eq 0) { $sug = 'pull' }
    $cnt = @($DiffFiles).Count
    $sample = (($samples | Select-Object -First 5) -join '、')
    if ($cnt -gt 5) { $sample += ' 等' }
    return @{ count = $cnt; localNewer = $localNewer; remoteNewer = $remoteNewer; suggest = $sug; sample = $sample }
}

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
    # S6/阶段C复审(2026-09-05): helper 内路径用单引号字面量($trayRaw 撇号翻倍) + 运行时 '"'+raw+'"' 构造；
    # 直启 $helper 也包双引号——防安装目录/TEMP 含空格时 powershell -File exit -196608
    $trayRaw = $TrayPath.Replace("'", "''")
    @"
Start-Sleep -Seconds 2
`$trayRaw = '$trayRaw'
`$trayArg = '"' + `$trayRaw + '"'
Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',`$trayArg -WindowStyle Hidden
Remove-Item -LiteralPath `$MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"@ | Set-Content -LiteralPath $helper -Encoding UTF8
    Start-Process powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('"' + $helper + '"')) -WindowStyle Hidden
    return $true
}

# ---------- 主同步流程 ----------
function Sync-LauncherScript {
    Write-SyncStatus 'info' '正在同步启动脚本…'
    if (-not (Get-SyncLock)) { throw '同步正在进行中，请稍后再试。' }
    try {
        if (-not (Test-Path -LiteralPath $SkillDir)) { throw "本机技能目录不存在：$SkillDir" }
        # 兜底探测：宿主注入环境可能精简了 PATH，找不到 git 时探测常见安装位置并补入 PATH（2026-08-30）
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            $gitDirs = @(
                'C:\Program Files\Git\cmd',
                "$env:ProgramFiles\Git\cmd",
                (Join-Path $env:LOCALAPPDATA 'Programs\MinGit\cmd'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd')
            )
            $ghApp = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'GitHubDesktop') -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
                     Sort-Object Name -Descending | Select-Object -First 1
            if ($ghApp) { $gitDirs += (Join-Path $ghApp.FullName 'resources\app\git\cmd') }
            foreach ($d in $gitDirs) {
                if ($d -and (Test-Path -LiteralPath (Join-Path $d 'git.exe'))) {
                    $env:Path = $d + ';' + $env:Path
                    break
                }
            }
        }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw '未找到 git：请先安装 Git（https://git-scm.com）；读取公开仓库无需凭据，写入需配置 token。' }
        Repair-SyncCache $ghCache $GhBranch
        $remoteBase = Join-Path $ghCache 'dsh-launcher'
        if (-not (Test-SyncRemoteTree $remoteBase)) { throw "GitHub 仓库结构异常：分支 `"$GhBranch`" 缺少 dsh-launcher/ 源树（SKILL.md/_meta.json）。请检查 branch 是否指向含源树的分支。" }


        $localMap = @{}
        Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
            $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
            if (Is-SyncIgnored $rel) { return }
            $localMap[$rel] = Get-SyncFileHash $_.FullName
        }
        $remoteMap = @{}
        Get-ChildItem -LiteralPath $remoteBase -Recurse -File | ForEach-Object {
            $rel = ($_.FullName.Substring($remoteBase.Length + 1) -replace '\\','/')
            if (Is-SyncIgnored $rel) { return }
            $remoteMap[$rel] = Get-SyncFileHash $_.FullName
        }
        $diff = @()
        foreach ($k in @(($localMap.Keys + $remoteMap.Keys) | Select-Object -Unique)) {
            if ($localMap[$k] -ne $remoteMap[$k]) { $diff += $k }
        }
        $compState = Get-CompanionSyncState $SkillDir $remoteBase
        if ($diff.Count -eq 0 -and -not $compState.changed) {
            Write-SyncStatus 'result' '启动脚本与 GitHub 完全一致，无需同步。' @{ action = 'none' }
            return
        }

        $lm = Get-Content -LiteralPath (Join-Path $SkillDir '_meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $rm = Get-Content -LiteralPath (Join-Path $remoteBase '_meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $lp = [long]$lm.publishedAt; $rp = [long]$rm.publishedAt
        $chosenDirection = $Direction
        # 方向判定仅用于【建议】：绝不自动执行方向（2026-09-05 用户规则）
        if ($Direction -eq 'auto') {
            $mainDir = ''
            $vc = Compare-SyncVersion ([string]$lm.version) ([string]$rm.version)
            if ($vc -gt 0) { $mainDir = 'upload' }
            elseif ($vc -lt 0) { $mainDir = 'pull' }
            elseif ($lp -ne $rp) { $mainDir = if ($lp -gt $rp) { 'upload' } else { 'pull' } }
            $compDir = ''
            if ($compState.changed) {
                if ($compState.localNewer -and -not $compState.remoteNewer) { $compDir = 'upload' }
                elseif ($compState.remoteNewer -and -not $compState.localNewer) { $compDir = 'pull' }
                else { $compDir = 'mixed' }
            }
            # 完全一致：无需同步
            if (-not $mainDir -and -not $compDir -and @($diff).Count -eq 0) {
                Write-SyncStatus 'result' '启动脚本与 GitHub 完全一致，无需同步。' @{ action = 'none' }
                return
            }
            # 组织建议文本（含真实文件 diff 分析；建议措辞与按钮一致）
            $rec = ''
            $signals = @()
            if ($mainDir) {
                $mainLabel = if ($mainDir -eq 'upload') { '上传到 GitHub' } else { '拉取 GitHub 版本' }
                $signals += ('主启动器（版本/时间戳）：本机 v' + $lm.version + ' vs GitHub v' + $rm.version + ' → 建议 ' + $mainLabel)
            }
            if ($compDir) { $signals += ('配套技能：本机与 GitHub 内嵌包方向=' + $compDir) }
            $cf = $null
            if (@($diff).Count -gt 0) { $cf = Get-ContentDiffAnalysis $SkillDir $remoteBase $ghCache $diff }
            if ($cf) {
                $signals += ('内容 diff：' + $cf.count + ' 个文件（' + $cf.sample + '）；本机较新 ' + $cf.localNewer + '，GitHub 较新 ' + $cf.remoteNewer)
            }
            if ($mainDir) { $rec = if ($mainDir -eq 'upload') { '上传到 GitHub' } else { '拉取 GitHub 版本' } }
            elseif ($compDir -and $compDir -ne 'mixed') { $rec = if ($compDir -eq 'upload') { '上传到 GitHub' } else { '拉取 GitHub 版本' } }
            elseif ($compDir) { $rec = '（配套技能双向更新，需人工判断）' }
            elseif ($cf) {
                if ($cf.suggest -eq 'upload') { $rec = '上传到 GitHub' }
                elseif ($cf.suggest -eq 'pull') { $rec = '拉取 GitHub 版本' }
                else { $rec = '（双向均有更新，需人工判断）' }
            } else { $rec = '（未检测到明确差异，需人工判断）' }
            $dlg = '同步方向选择（系统只给建议，绝不自动判定方向）：'
            foreach ($sg in $signals) { $dlg += "`n- " + $sg }
            $dlg += "`n`n建议选择：" + $rec
            $dlg += '。请点选要执行的方向（与按钮一致）：上传到 GitHub / 拉取 GitHub 版本 / 取消（上传会提交到 GitHub，git 历史会保留旧版本）'

            $dir = Show-SyncDirectionDialog $dlg
            if ($dir -eq 'upload') {
                $chosenDirection = 'upload'
            } elseif ($dir -eq 'pull') {
                $chosenDirection = 'pull'
            } else {
                Write-SyncStatus 'result' '已取消同步，未做任何更改。' @{ action = 'cancelled' }
                return
            }
        }
        if ($chosenDirection -eq 'pull') {
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
                if (Is-SyncIgnored $rel) { return }
                $dst = Join-Path $SkillDir ($rel -replace '/','\')
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
                if (Is-SyncIgnored $rel) { return }
                if (-not $remoteMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
            $setupOut = (& (Join-Path $PSHome 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SkillDir 'assets\setup.ps1') -InstallDir $InstallDir -NoShortcut 2>&1 | ForEach-Object { "$_" }) -join "`n"
            if ($LASTEXITCODE -ne 0) {
                Write-SyncStatus 'error' "已从 GitHub 拉取启动脚本（$($rm.version)），但更新后重装失败（setup.ps1 退出码 $LASTEXITCODE），启动器可能未刷新、补丁可能未打。`n--- setup.ps1 输出 ---`n$setupOut"
                return
            }
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
        } elseif ($chosenDirection -eq 'upload' -or ($Direction -eq 'auto' -and $lp -gt $rp)) {
                # 配套技能内嵌 zip 自动刷新（已装目录 → 主树 assets\配套技能\，保证发布主包内嵌一致）
            foreach ($c in $compState.refresh) {
                $instDir = Join-Path $env:USERPROFILE ".agents\skills\$c"
                $emb = Join-Path $SkillDir "assets\配套技能\$c`__skillhub.zip"
                if (Test-Path -LiteralPath $instDir) {
                    if (Publish-SkillZip $instDir $emb $c) { Write-SyncStatus 'info' "配套技能 $c 内嵌包已自动刷新" }
                }
            }
            $srcTree = Join-Path $ghCache 'dsh-launcher'
            Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
                if (Is-SyncIgnored $rel) { return }
                $dst = Join-Path $srcTree ($rel -replace '/','\')
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            Get-ChildItem -LiteralPath $srcTree -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($srcTree.Length + 1) -replace '\\','/')
                if (Is-SyncIgnored $rel) { return }
                if (-not $localMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
                # 配套技能源树同步到仓库 dsh-launcher Add\<技能名>\（与 releases zip 一起归档）
            foreach ($c in $script:CompanionSkills) {
                $instDir = Join-Path $env:USERPROFILE ".agents\skills\$c"
                if (-not (Test-Path -LiteralPath $instDir)) { continue }
                $addTree = Join-Path $ghCache ("dsh-launcher Add\" + $c)
                Get-ChildItem -LiteralPath $instDir -Recurse -File | ForEach-Object {
                    $rel = ($_.FullName.Substring($instDir.Length + 1) -replace '\\','/')
                    if (Is-SyncIgnored $rel) { return }
                    $dst = Join-Path $addTree ($rel -replace '/','\')
                    New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                    Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
                }
                Get-ChildItem -LiteralPath $addTree -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                    $rel = ($_.FullName.Substring($addTree.Length + 1) -replace '\\','/')
                    if (Is-SyncIgnored $rel) { return }
                    $src = Join-Path $instDir ($rel -replace '/','\')
                    if (-not (Test-Path -LiteralPath $src)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
                }
            }
            $releaseDir = Join-Path $ghCache ("releases\v" + $lm.version)
            New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
            $published = @()
            if (Publish-SkillZip $SkillDir (Join-Path $releaseDir 'dsh-launcher__skillhub.zip') 'dsh-launcher') { $published += 'dsh-launcher' }
            foreach ($c in $script:CompanionSkills) {
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
    }
}

Sync-LauncherScript
