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
    [switch]$NoUI,
    [switch]$AllowPurge
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
    # 运行期留痕目录 var/（2026-09-19 用户裁决）：adversarial-review 等技能的 var/ 存放本机审查快照/台账/任务脚本（曾把 archify-install 的 patch-docs-*.ps1 与含本机用户名的路径带进 releases 提交）。这类状态属「每台机器各自的运行期产物」，不进包、不进源树；技能脚本按三级回落自建目录，故新机器缺 var/ 不影响可用。备案：var/registry/guide-clauses.json（沉淀条款）也因此不再跨机传播——如需跨机共享条款，改成只排除 var/ 下的 task-scripts|backup|snapshots|tmp|queue。
    if ($Rel -match '(^|[\\/])var[\\/]') { return $true }
    if ($Rel -in @('install-dir.txt', 'assets/install-dir.txt')) { return $true }
    if ($Rel -match '(^|/)(config\.json|credentials[^/]*|\.dsh[^/]*|[^/]*\.token[^/]*)$') { return $true }
    # 重型测试语料（2026-09-12）：pdf-parse-v3 的 tests/vision_shootout（385 文件 / 138.8 MiB，含
    # 24.9 MB 规范 PDF 与 180 张页面 PNG）整目录打包会把技能包顶到 129.21 MB，触发 GitHub 单文件
    # 100 MB 硬上限致推送被 pre-receive 拒收。此类样本语料不进包、不进源树（技能自身测试仍用本机文件）。
    if ($Rel -match '(^|[\\/])tests[\\/]vision_shootout[\\/]') { return $true }
    # 备份目录（2026-10-12 用户裁决）：各技能根/子目录下的 _backup\ 存放秒级时间戳的改前备份
    # （全树 15 个目录 / 308 文件 / 171.6 MB）。这是本机回退点，不进包、不进源树。
    # 注意：只加在这里（阻止复制）；**不要**加进 Test-SyncPurgePath——否则带 -AllowPurge 时
    # 会把仓库里已提交的历史备份整目录删除（GitHub 侧不可逆）。备案见 changelog 321 行。
    if ($Rel -match '(^|[\\/])_backup([\\/]|$)') { return $true }
    if ($Rel -match '(^|[\\/])_bak([\\/]|$)') { return $true }
    return $false
}

function Test-SyncPurgePath {
    # 清理用谓词（2026-09-12）：这些路径在仓库源树里『不允许存在』，历史遗留必须删除。
    # 与 Is-SyncIgnored（只阻止复制、不负责清理）分开，避免误删其它合法的被忽略文件。
    param([string]$Rel)
    if ($Rel -match '(^|[\\/])var[\\/]') { return $true }   # 2026-09-19：历史遗留的 var/ 留痕从仓库源树清除
    if ($Rel -match '(^|[\\/])tests[\\/]vision_shootout[\\/]') { return $true }
    return $false
}

function Get-OversizeSyncFile {
    # 上传前体积闸门（2026-09-12 立；2026-09-12 修订）：GitHub 单文件上限 100 MiB，超过会被 pre-receive
    # 拒绝；一旦进了本地提交还需改写历史才能推。故在 git add 之前先量体积，超限即中止。
    # 修订要点：① 边界＝严格大于 100 MiB（GitHub 拒的是 >100 MiB）；
    # ② 被 .gitignore 忽略的文件本来就不会进提交，逐候选用 `git check-ignore -q` 只看退出码判定并排除
    #    （不解码任何路径文本，避开中文路径/编码坑），避免误拦；
    # ③ 判定失败（非仓库、git 不可用、路径异常）一律保守按“会提交”处理，并把失败路径放进 .ProbeErrors
    #    回报给调用方——不静默。
    param(
        [string]$Root,
        [long]$BlockBytes = 104857600,
        [long]$WarnBytes = 52428800
    )
    $res = New-Object psobject -Property @{
        Blocked = $false; Scanned = 0; Oversize = @(); Warn = @(); Ignored = @()
        ProbeErrors = @(); Largest = $null
    }
    if (-not (Test-Path -LiteralPath $Root)) { return $res }
    $root = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
    $walkErrs = @()
    $all = @(Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue -ErrorVariable +walkErrs |
             Where-Object { $_.FullName -notmatch '\\\.git\\' })
    $res.Scanned = $all.Count
    foreach ($e in $walkErrs) { $res.ProbeErrors += ('枚举失败: ' + [string]$e) }
    foreach ($f in $all) { if ($null -eq $res.Largest -or $f.Length -gt $res.Largest.Length) { $res.Largest = $f } }

    $candidates = @($all | Where-Object { $_.Length -gt $WarnBytes } | Sort-Object Length -Descending)
    $hasGit = ($null -ne (Get-Command git -ErrorAction SilentlyContinue))
    foreach ($f in $candidates) {
        $state = 'no-git'
        if ($hasGit) {
            $rel = $f.FullName.Substring($root.Length).TrimStart('\')
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & git -C $root check-ignore -q -- $rel 2>$null | Out-Null; $rc = $LASTEXITCODE }
            catch { $rc = 128 }
            finally { $ErrorActionPreference = $prevEap }
            if ($rc -eq 0) { $state = 'ignored' }
            elseif ($rc -eq 1) { $state = 'tracked-or-untracked' }
            else { $state = 'unknown' }
        }
        if ($state -eq 'ignored') { $res.Ignored += $f; continue }
        if ($f.Length -gt $BlockBytes) {
            $res.Oversize += $f
            if ($state -eq 'unknown') { $res.ProbeErrors += $f.FullName }
        } else {
            $res.Warn += $f
        }
    }
    $res.Blocked = ($res.Oversize.Count -gt 0)
    return $res
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
function Backup-SyncCacheDir {
    # 缓存目录里可能有未推送的本地提交：删除/重建之前先整目录改名保留（秒级时间戳，不覆盖旧备份）
    param([string]$Cache)
    if (-not (Test-Path -LiteralPath $Cache)) { return '' }
    $bak = $Cache + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    try { Move-Item -LiteralPath $Cache -Destination $bak -Force -ErrorAction Stop; return $bak }
    catch { return '' }
}
$script:LastBackupBranch = ''
function Save-SyncLocalCommits {
    # 把缓存里未推送的本地提交备份成带秒级时间戳的分支，再允许重置工作树。
    # 备份失败直接抛错中止（绝不"先 reset 再说"）。返回分支名（无需备份时返回空串）。
    param([string]$Cache, [string]$Branch)
    $ahead = -1
    try {
        $o = (& git -C $Cache rev-list --count "refs/remotes/origin/$Branch..HEAD" 2>$null)
        if ($LASTEXITCODE -eq 0) { $ahead = [int](($o -join '').Trim()) }
    } catch { $ahead = -1 }
    if ($ahead -eq 0) { return '' }
    $name = 'local-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    $branchOk = $false
    try {
        & git -C $Cache branch $name HEAD 2>$null | Out-Null
        $branchOk = ($LASTEXITCODE -eq 0)
    } catch { $branchOk = $false }
    if (-not $branchOk) { throw ('缓存中有未推送提交，但备份分支创建失败；已中止，未重置。分支名：' + $name) }
    $script:LastBackupBranch = $name
    $note = if ($ahead -gt 0) { '（领先 ' + $ahead + ' 个提交）' } else { '（提交数未知）' }
    Write-SyncLog ('本地未推送提交已备份为分支 ' + $name + $note)
    return $name
}
function Write-SyncLog {
    param([string]$Message)
    try {
        $lp = Join-Path $env:TEMP 'dsh-sync.log'
        [IO.File]::AppendAllText($lp, ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' ' + $Message + [Environment]::NewLine), (New-Object System.Text.UTF8Encoding($false)))
    } catch {}
}
function Repair-SyncCache {
    param([string]$Cache, [string]$Branch)
    $parent = Split-Path $Cache -Parent
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    # 2026-11-08 事故修复：原实现在用户确认方向之前直接 reset --hard，把未推送提交抹掉了。
    # 现在改为：fetch → 先把未推送提交备份成 local-backup-<ts> 分支（失败即中止）→ 才 reset --hard 对齐，
    # 并 clean -fd 清未跟踪残留。用户技能目录全程不动；取消时提示会点名备份分支。
    if (Test-Path -LiteralPath (Join-Path $Cache '.git')) {
        $ok = $false
        try { git -C $Cache rev-parse --is-inside-work-tree 2>$null | Out-Null; $ok = ($LASTEXITCODE -eq 0) } catch {}
        if (-not $ok) {
            $bk = Backup-SyncCacheDir $Cache
            if (-not $bk) { throw ('缓存仓库不可用，且备份失败；已中止，未删除任何数据：' + $Cache) }
            Write-SyncLog ('缓存仓库不可用，已备份到 ' + $bk)
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Cache '.git'))) {
        if (Test-Path -LiteralPath $Cache) {
            $bk = Backup-SyncCacheDir $Cache
            if (-not $bk) { throw ('缓存目录非空且无 .git，备份失败；已中止，未删除任何数据：' + $Cache) }
            Write-SyncLog ('缓存目录已备份到 ' + $bk)
        }
        $r = Invoke-SyncGit @('clone', '-b', $Branch, '--depth', '1', "https://github.com/$GhRepo.git", $Cache)
        if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git clone') }
        return
    }
    $r = Invoke-SyncGit @('fetch','origin',"+refs/heads/$Branch:refs/remotes/origin/$Branch") $Cache
    if ($r.code -eq 0) {
        # 2026-11-08：对齐工作树到远端（比对/上传都需要干净起点）。对齐前先备份未推送提交。
        $null = Save-SyncLocalCommits $Cache $Branch
        $r0 = Invoke-SyncGit @('reset', '--hard', "refs/remotes/origin/$Branch") $Cache
        if ($r0.code -ne 0) { throw (Format-SyncError $r0.code $r0.text 'git reset（对齐缓存）') }
        # 上一轮中止留下的未跟踪残留会被 upload 的 `git add -A` 带进提交，这里清掉。
        # 不带 -x：.gitignore 里的本地文件（*.bak / install-dir.txt 等）保持不动。
        $rc = Invoke-SyncGit @('clean', '-fd') $Cache
        if ($rc.code -ne 0) {
            Write-SyncLog ('缓存未跟踪残留清理失败：' + $rc.text)
            Write-SyncStatus 'warning' ('缓存里还有未跟踪残留（清理失败），上传时可能把它们带上：' + $rc.text + '。可手动在缓存目录执行 git clean -fd 后重试。')
        }
    }
    if ($r.code -ne 0) {
        $bk = Backup-SyncCacheDir $Cache
        if (-not $bk) { throw ('fetch 失败且备份失败；已中止，未删除任何数据：' + (Format-SyncError $r.code $r.text 'git fetch')) }
        Write-SyncLog ('fetch 失败，原缓存已备份到 ' + $bk)
        $r2 = Invoke-SyncGit @('clone', '-b', $Branch, '--depth', '1', "https://github.com/$GhRepo.git", $Cache)
        if ($r2.code -ne 0) { throw (Format-SyncError $r2.code $r2.text 'git clone（备份后重试）') }
    }
}function Publish-SkillZip {
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
function Get-ZipEntryList {
    # 一致性守卫用（2026-09-19 审查 S1/S2）：条目名 + 解压后大小，用于比较「主树内嵌配套包 vs releases 同版包」是否同内容
    param([string]$ZipPath)
    try {
        $z = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        try { return (($z.Entries | Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)" }) -join "`n") }
        finally { $z.Dispose() }
    } catch { return '' }
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
                $cancelMsg = '已取消同步：缓存已刷新到远端，本地未推送的提交'
                if ($script:LastBackupBranch) { $cancelMsg += ('已备份为分支 ' + $script:LastBackupBranch) } else { $cancelMsg += '本来就没有' }
                Write-SyncStatus 'result' ($cancelMsg + '。') @{ action = 'cancelled' }
                return
            }
        }
        if ($chosenDirection -eq 'pull') {
            # 缓存工作树已在 Repair-SyncCache 里对齐到远端（并在对齐前备份了未推送提交），这里不再重复 reset。
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
            # A-34 guard: reverse deletion (local files absent from the remote manifest) now requires
            # an explicit -AllowPurge AND a remote manifest that is plausibly complete (>=80% of local).
            $localCount = @(Get-ChildItem -LiteralPath $SkillDir -Recurse -File | Where-Object {
                -not (Is-SyncIgnored (($_.FullName.Substring($SkillDir.Length + 1)) -replace '\\','/')) }).Count
            $minRemote = [Math]::Ceiling($localCount * 0.8)
            $purgeOk = $AllowPurge -and ($remoteMap.Count -gt 0) -and ($remoteMap.Count -ge $minRemote)
            if (-not $purgeOk) {
                Write-SyncStatus 'warning' ('反向删除已跳过（安全守卫 A-34）：远端清单 ' + $remoteMap.Count + ' 项，本地 ' + $localCount + ' 项，下限 ' + $minRemote + ' 项，AllowPurge=' + $AllowPurge + '。差异未清理；确认远端清单完整后加 -AllowPurge 重跑。')
            }
            Get-ChildItem -LiteralPath $SkillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($SkillDir.Length + 1) -replace '\\','/')
                if (Is-SyncIgnored $rel) { return }
                if ($purgeOk -and -not $remoteMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
            # PS7 的 $PSHome 里没有 powershell.exe（只有 pwsh.exe），必须回退到系统 Windows PowerShell
            $psExe = Join-Path $PSHome 'powershell.exe'
            if (-not (Test-Path -LiteralPath $psExe)) { $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe' }
            # 5.1 下 EAP=Stop 时原生 stderr 会抛 RemoteException，这里局部降级，避免把"setup 打了警告"误报成同步失败
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $setupOut = (& $psExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SkillDir 'assets\setup.ps1') -InstallDir $InstallDir -NoShortcut 2>&1 | ForEach-Object { "$_" }) -join "`n"
                $setupCode = $LASTEXITCODE
            } finally { $ErrorActionPreference = $prevEap }
            if ($setupCode -ne 0) {
                Write-SyncStatus 'error' "已从 GitHub 拉取启动脚本（$($rm.version)），但更新后重装失败（setup.ps1 退出码 $setupCode），启动器可能未刷新。`n--- setup.ps1 输出 ---`n$setupOut"
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
            # 2026-09-19（审查 S1/S2）：改为对**全部**配套无条件重建。原按「本机版本 ≠ 内嵌版本」门控，且三方版本相等时直接 continue，导致「只改内容、未 bump 版本」的配套（pdf-parse-v3 去本机路径、adversarial-review 内容增长）内嵌包永不刷新，成品包长期发旧件；且旧件与新件 _meta 版本相同时引擎连分叉都检测不到。
            foreach ($c in $script:CompanionSkills) {
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
            # A-35..A-38 guard: purging the repo source tree requires -AllowPurge and a complete local map.
            $srcCount = @(Get-ChildItem -LiteralPath $srcTree -Recurse -File).Count
            $minLocal = [Math]::Ceiling($srcCount * 0.8)
            $purgeOkUp = $AllowPurge -and ($localMap.Count -gt 0) -and ($localMap.Count -ge $minLocal)
            if (-not $purgeOkUp) {
                Write-SyncStatus 'warning' ('推送侧清理已跳过（安全守卫 A-35~A-38）：本地清单 ' + $localMap.Count + ' 项，仓库树 ' + $srcCount + ' 项，下限 ' + $minLocal + ' 项，AllowPurge=' + $AllowPurge + '。')
            }
            Get-ChildItem -LiteralPath $srcTree -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($srcTree.Length + 1) -replace '\\','/')
                    if ($purgeOkUp -and (Test-SyncPurgePath $rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue; return }
                if (Is-SyncIgnored $rel) { return }
                if ($purgeOkUp -and -not $localMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
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
                        if ($purgeOkUp -and (Test-SyncPurgePath $rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue; return }
                if (Is-SyncIgnored $rel) { return }
                    $src = Join-Path $instDir ($rel -replace '/','\')
                    if ($purgeOkUp -and -not (Test-Path -LiteralPath $src)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
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
            # 一致性守卫（2026-09-19，审查 S1/S2）：每个配套的「主树内嵌包」必须与同版 releases 包内容一致；不一致则告警（不阻断上传，避免因单个配套异常卡住发布）。
            foreach ($c in $script:CompanionSkills) {
                $embZ = Join-Path $SkillDir "assets\配套技能\$c`__skillhub.zip"
                $relZ = Join-Path $releaseDir ($c + '__skillhub.zip')
                if ((Test-Path -LiteralPath $embZ) -and (Test-Path -LiteralPath $relZ)) {
                    if ((Get-ZipEntryList $embZ) -ne (Get-ZipEntryList $relZ)) {
                        Write-SyncStatus 'warning' "内嵌配套包与 releases 包内容不一致：$c（请检查 assets\配套技能 是否已刷新）"
                    }
                }
            }
            $sizeGate = Get-OversizeSyncFile -Root $ghCache
            if ($sizeGate.Ignored.Count -gt 0) {
                $igTop = @($sizeGate.Ignored | Select-Object -First 3 | ForEach-Object { $_.FullName.Substring($ghCache.Length).TrimStart('\') }) -join '; '
                Write-SyncStatus 'info' ("有 " + $sizeGate.Ignored.Count + " 个大于 50 MiB 的文件被 .gitignore 忽略，不会进入提交，未计入闸门：" + $igTop)
            }
            if ($sizeGate.Blocked) {
                $top = @($sizeGate.Oversize | Select-Object -First 5)
                $bigList = ($top | ForEach-Object {
                    '  - ' + $_.FullName.Substring($ghCache.Length).TrimStart('\') + ' : ' + [string]([math]::Round($_.Length / 1048576, 1)) + ' MiB'
                }) -join "`r`n"
                if ($sizeGate.Oversize.Count -gt $top.Count) {
                    $bigList += "`r`n  ...另有 " + ($sizeGate.Oversize.Count - $top.Count) + " 个超限文件（本次共 " + $sizeGate.Oversize.Count + " 个）"
                }
                $probeNote = ''
                if ($sizeGate.ProbeErrors.Count -gt 0) {
                    $probeNote = "`r`n注意：另有 " + $sizeGate.ProbeErrors.Count + " 项未能判定是否被 .gitignore 忽略（文件枚举失败，或 git check-ignore 失败/不在仓库内），已按保守策略一并阻止。"
                }
                throw ("检测到超过 GitHub 单文件上限（>100 MiB）的文件，本次共 " + $sizeGate.Oversize.Count + " 个，已阻止本次提交与推送（未提交、未推送，历史未被污染）。`r`n处置：把大文件移出技能目录，或在仓库 .gitignore 中忽略它，或在 dsh-sync.ps1 的 Is-SyncIgnored 中加一条排除规则后重试。`r`n（提示：本次已生成的技能包位于 " + $releaseDir + "，可自行清理。）`r`n" + $bigList + $probeNote)
            }
            if ($sizeGate.Warn.Count -gt 0) {
                Write-SyncStatus 'warning' ("注意：" + $sizeGate.Warn.Count + " 个文件大于 50 MiB（GitHub 提醒阈值，严格大于；恰好 50 MiB 不告警），最大 " + [string]([math]::Round($sizeGate.Warn[0].Length / 1048576, 1)) + " MiB：" + $sizeGate.Warn[0].FullName.Substring($ghCache.Length).TrimStart('\'))
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
