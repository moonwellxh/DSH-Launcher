# ================= GitHub 同步基础设施（发布级：代理/认证/错误分类/锁/打包） =================
function Get-SystemProxy {
    # 读系统代理（HKCU Internet Settings）；返回 http://host:port 或空串
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
    # token 已配置 → http.extraheader 内存注入（不落盘、不打印）；否则空数组（公开仓库读取无需凭据）
    if ($ghToken) {
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes("x-access-token:$ghToken"))
        return @('-c', "http.extraheader=AUTHORIZATION: basic $b64")
    }
    return @()
}
function Test-GitErrorIsAuth {
    # 认证/仓库类错误特征：此类错误不换代理重试（避免浪费与误导）
    param([string]$Text)
    return [bool]($Text -match 'could not read Username|terminal prompts disabled|Authentication failed|Invalid username|Bad credentials|Repository not found|fatal: repository|401|403')
}
function Invoke-SyncGit {
    # 统一 git 调用：直连优先，失败且非认证类错误时自动换系统代理重试一次；返回 @{code; text}
    param([string[]]$GitArgs, [string]$WorkDir)
    # 本函数内放宽 ErrorAction：git 正常把进度/提示写 stderr（已 2>&1 合并进文本），Stop 策略下会误抛 NativeCommandError
    $ErrorActionPreference = 'Continue'
    $sysProxy = Get-SystemProxy
    $strategies = New-Object System.Collections.ArrayList
    [void]$strategies.Add(@())                                             # 策略1：直连
    if ($sysProxy) { [void]$strategies.Add(@('-c', "http.proxy=$sysProxy", '-c', "https.proxy=$sysProxy")) }  # 策略2：系统代理
    $authArgs = Get-SyncAuthArgs
    $last = @{ code = 1; text = '' }
    foreach ($st in $strategies) {
        $cmd = @()
        if ($WorkDir) { $cmd += @('-C', $WorkDir) }
        $cmd += $st
        $cmd += $authArgs
        $cmd += $GitArgs
        $env:GIT_TERMINAL_PROMPT = '0'
        try { $env:GCM_INTERACTIVE = 'Never' } catch {}                     # 防 GCM 弹窗挂起
        $txt = (& git @cmd 2>&1 | ForEach-Object { "$_" }) -join "`n"
        $code = $LASTEXITCODE
        if ($code -eq 0) { return @{ code = 0; text = $txt } }
        $last = @{ code = $code; text = $txt }
        if (Test-GitErrorIsAuth $txt) { break }                             # 认证/仓库类：不换代理重试，直接归类
    }
    return $last
}
function Format-SyncError {
    # 把 git 失败分类成可操作提示（stderr 脱敏 token）
    param([int]$Code, [string]$Text, [string]$Step)
    if ($ghToken) { $Text = $Text -replace [regex]::Escape($ghToken), '***' }
    $Text = $Text -replace 'x-access-token:[^\s]+', '***' -replace 'basic [A-Za-z0-9+/=]+', 'basic ***'
    $tail = (($Text -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 8) -join "`n"
    $msg = "步骤「$Step」失败（exit $Code）。"
    if ($Text -match 'could not read Username|terminal prompts disabled|Authentication failed|Invalid username|Bad credentials') {
        $msg += "`n原因：GitHub 认证未通过（仓库私有或凭据缺失/失效）。读取公开仓库无需凭据；私有仓库或写入需配置 PAT："
        $msg += "`n  1) 在 $ghSyncConfigPath 加 `"token`" 字段，或 2) 设环境变量 DSH_SYNC_TOKEN，或 3) 用 git credential approve 配置机器凭据。"
    } elseif ($Text -match 'Repository not found|fatal: repository|404') {
        $msg += "`n原因：仓库/分支不存在或无权访问（检查 config.json 的 repo/branch 拼写；私有仓库需配 token）。"
    } elseif ($Text -match 'Remote branch .*not found|couldn.t find remote ref') {
        $msg += "`n原因：分支 `"$ghBranch`" 不存在或未推送（检查 config.json 的 branch）。"
    } elseif ($Text -match 'Could not resolve host|Couldn.t resolve|Connection timed out|Connection was reset|Recv failure|Failed to connect|unable to access|schannel') {
        $msg += "`n原因：网络不通（已依次尝试直连与系统代理 `"$(Get-SystemProxy)`"）。请检查网络/代理，或设置系统代理后重试。"
    } elseif ($Text -match 'shallow update not allowed|non-fast-forward|fetch first|diverged') {
        $msg += "`n原因：远端已有更新的提交（非快进）。处理：先执行「拉取 GitHub 版本」合并后再重试上传。"
    }
    if ($tail) { $msg += "`n`n--- git 输出（末 8 行）---`n$tail" }
    return $msg
}
function Get-SyncIgnoreSet {
    # 机器特定/临时文件：比对、上传、清理时一律跳过（不参与同步）
    return @{ 'assets/install-dir.txt' = $true; 'install-dir.txt' = $true }
}
function Get-SyncFileHash {
    # 内容哈希：文本文件先归一化 CRLF→LF（避免 git core.autocrlf 检出 CRLF 与 zip 内 LF 造成"同内容不同哈希"），
    # 二进制（含 0x00 字节，如 zip/ico/png）保持原始字节哈希
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes -contains 0) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    $norm = [System.Text.Encoding]::UTF8.GetBytes(([System.Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n"))
    $ms = New-Object System.IO.MemoryStream(, $norm)
    try { return (Get-FileHash -InputStream $ms -Algorithm SHA256).Hash } finally { $ms.Dispose() }
}
function Test-SyncRemoteTree {
    # 结构契约校验：远端须含 dsh-launcher/ 源树（SKILL.md + _meta.json）
    param([string]$Base)
    foreach ($n in @('SKILL.md', '_meta.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Base $n))) { return $false }
    }
    return $true
}
function Repair-SyncCache {
    # 缓存完整性自检：.git 异常/拉取失败 → 删除后重新 clone（最多一次）
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
        $r = Invoke-SyncGit @('clone', '-b', $Branch, '--depth', '1', "https://github.com/$ghRepo.git", $Cache)
        if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git clone') }
    } else {
        $r = Invoke-SyncGit @('fetch','origin',"+refs/heads/$Branch:refs/remotes/origin/$Branch") $Cache
        if ($r.code -ne 0) {
            Remove-Item -LiteralPath $Cache -Recurse -Force -ErrorAction SilentlyContinue
            $r = Invoke-SyncGit @('clone', '-b', $Branch, '--depth', '1', "https://github.com/$ghRepo.git", $Cache)
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git clone（缓存修复后重试）') }
        } else {
            $r = Invoke-SyncGit @('reset', '--hard', "refs/remotes/origin/$Branch") $Cache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git reset') }
        }
    }
}
function Publish-SkillZip {
    # .NET ZipArchive 打包技能目录为 <name>__skillhub.zip（正斜杠条目名、UTF-8、排除机器特定文件）；成功返回 $true
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
    # 同步互斥锁：防止并发触发；成功占锁返回 $true
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
function Sync-LauncherScript {
    # 一键启动脚本与 GitHub 双向同步（发布级）：
    # 配置（repo/branch/token）→ 缓存同步（直连↔代理回退、损坏自愈）→ 结构契约校验 →
    # 内容级比对（忽略机器特定文件）→ 方向按双方 _meta 时间戳判定（相等时按 git 提交时间分析并弹窗确认）→ 拉取/上传
    $notify.ShowBalloonTip(2000, 'DSH 升级', '正在同步启动脚本…', 'Info')
    if (-not (Get-SyncLock)) { throw '同步正在进行中，请稍后再试。' }
    $tmpZip = $null
    try {
        if (-not (Test-Path -LiteralPath $skillDir)) { throw "本机技能目录不存在：$skillDir" }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw '未找到 git：请先安装 Git（https://git-scm.com）；读取公开仓库无需凭据，写入需配置 token（见配置说明）' }
        # 0) 同步仓库工作副本（缓存损坏自动重建）
        Repair-SyncCache $ghCache $ghBranch
        $remoteBase = Join-Path $ghCache 'dsh-launcher'
        if (-not (Test-SyncRemoteTree $remoteBase)) { throw "GitHub 仓库结构异常：分支 `"$ghBranch`" 缺少 dsh-launcher/ 源树（SKILL.md/_meta.json）。请检查 config.json 的 branch 是否指向含源树的分支。" }
        # 1) 内容级比对（跳过机器特定文件）
        $ignore = Get-SyncIgnoreSet
        $localMap = @{}
        Get-ChildItem -LiteralPath $skillDir -Recurse -File | ForEach-Object {
            $rel = ($_.FullName.Substring($skillDir.Length + 1) -replace '\\','/')
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
            $notify.ShowBalloonTip(3000, 'DSH 升级', '启动脚本与 GitHub 完全一致，无需同步。', 'Info')
            return
        }
        # 2) 方向判定：双方 _meta.json publishedAt（真实内容，非记忆值）
        $lm = Get-Content -LiteralPath (Join-Path $skillDir '_meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $rm = Get-Content -LiteralPath (Join-Path $remoteBase '_meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $lp = [long]$lm.publishedAt; $rp = [long]$rm.publishedAt
        if ($lp -eq $rp) {
            # 时间戳相同但内容不同：按「git 提交时间 vs 本地修改时间」分析建议，弹窗由用户确认方向——绝不自动覆盖远端良包
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
                $lf = Join-Path $skillDir ($k -replace '/','\')
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
                [System.IO.File]::WriteAllText((Join-Path $skillDir '_meta.json'), ($lm | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
                $lp = [long]$lm.publishedAt
            } elseif ($dir -eq 'pull') {
                $rp = $lp + 1
            } else {
                $notify.ShowBalloonTip(3000, 'DSH 升级', '已取消同步，未做任何更改。', 'Info')
                return
            }
        }
        if ($rp -gt $lp) {
            # 兼容性检查：远端启动器声明的 compatibleDsh；本机不满足则提醒先升级 DSH，不更新
            $curDsh = Get-CurrentDshVersion
            if ($rm.compatibleDsh) {
                $compat = @($rm.compatibleDsh)
                if ($curDsh -and ($compat -notcontains $curDsh)) {
                    $notify.ShowBalloonTip(6000, 'DSH 升级', "GitHub 上的启动器要求 DSH $($compat -join ' / ')，当前为 $curDsh，请先升级 DSH 再同步。", 'Warning')
                    return
                }
            }
            # 远端新 → 更新本地技能目录（跳过机器特定文件）
            Get-ChildItem -LiteralPath $remoteBase -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($remoteBase.Length + 1) -replace '\\','/'
                if ($ignore.ContainsKey($rel)) { return }
                $dst = Join-Path $skillDir ($rel -replace '/','\')
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            Get-ChildItem -LiteralPath $skillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($skillDir.Length + 1) -replace '\\','/')
                if ($ignore.ContainsKey($rel)) { return }
                if (-not $remoteMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
            # 重跑 setup 重新生成启动器并重打补丁（补丁引擎内部有 compatibleDsh 校验，不兼容补丁自动跳过）
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $skillDir 'assets\setup.ps1') -InstallDir $PSScriptRoot -NoShortcut 2>&1 | Out-Null
            $newTray = Join-Path $PSScriptRoot 'DSH-tray.ps1'
            $okParse = $false
            try { $null = [scriptblock]::Create((Get-Content -LiteralPath $newTray -Raw -Encoding UTF8)); $okParse = $true } catch {}
            if ($okParse) {
                $helper = Join-Path $env:TEMP ("dsh-restart-" + [guid]::NewGuid().ToString('N') + '.ps1')
                # helper 含中文安装路径：必须 UTF8（PS5.1 的 UTF8 即带 BOM），ASCII 会把中文写成 '?'
                @"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','$newTray' -WindowStyle Hidden
"@ | Set-Content -LiteralPath $helper -Encoding UTF8
                # helper 自身也需 Bypass：Restricted 策略机器上 -File 直接跑临时 .ps1 会被拦
                Start-Process powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$helper) -WindowStyle Hidden
                $notify.ShowBalloonTip(3000, 'DSH 升级', "已从 GitHub 更新启动脚本（$($rm.version)），托盘即将重启。", 'Info')
                [System.Windows.Forms.Application]::Exit()
            } else {
                $notify.ShowBalloonTip(4000, 'DSH 升级', "已从 GitHub 更新启动脚本（$($rm.version)），但新脚本解析失败，请手动重启托盘。", 'Error')
            }
        } elseif ($lp -gt $rp) {
            # 本地新 → 上传：更新源树 + 发布 5 个 zip 到 releases\<版本>\ + 提交推送
            $srcTree = Join-Path $ghCache 'dsh-launcher'
            # ① 同步源树（跳过机器特定文件，清理远端多余文件）
            Get-ChildItem -LiteralPath $skillDir -Recurse -File | ForEach-Object {
                $rel = ($_.FullName.Substring($skillDir.Length + 1) -replace '\\','/')
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
            # ② 发布 zip：主包 + 4 配套（从本机已装配套技能目录打包；缺失用主包内嵌旧包兜底）
            $releaseDir = Join-Path $ghCache ("releases\v" + $lm.version)
            New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
            $published = @()
            if (Publish-SkillZip $skillDir (Join-Path $releaseDir 'dsh-launcher__skillhub.zip') 'dsh-launcher') { $published += 'dsh-launcher' }
            foreach ($c in @('zip-archive-ops','batch-files','charset-pitfalls','skill-install-ops')) {
                $cd = Join-Path $env:USERPROFILE (".agents\skills\$c")
                $out = Join-Path $releaseDir ($c + '__skillhub.zip')
                if (-not (Publish-SkillZip $cd $out $c)) {
                    $embedded = Join-Path $skillDir "assets\配套技能\$($c)__skillhub.zip"
                    if (Test-Path -LiteralPath $embedded) { Copy-Item -LiteralPath $embedded -Destination $out -Force; $published += $c }
                    else { $notify.ShowBalloonTip(4000, 'DSH 升级', "配套技能 $c 目录缺失，跳过发布。", 'Warning') }
                } else { $published += $c }
            }
            # ③ 校验全部发布 zip
            foreach ($p in $published) {
                $zp = Join-Path $releaseDir ($p + '__skillhub.zip')
                try { $z = [System.IO.Compression.ZipFile]::OpenRead($zp); $z.Dispose() } catch { throw "打包校验失败（$p）：$($_.Exception.Message)" }
            }
            # ④ git 提交并推送（git 历史 = 旧版本天然备份，无需手工备份旧包）
            $r = Invoke-SyncGit @('add','-A') $ghCache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git add') }
            $r = Invoke-SyncGit @('status','--porcelain') $ghCache
            if (-not $r.text.Trim()) {
                $notify.ShowBalloonTip(3000, 'DSH 升级', '内容已同步，无新变更需要推送。', 'Info')
                return
            }
            $r = Invoke-SyncGit @('commit','-m',"dsh-launcher v$($lm.version) 同步（$([DateTimeOffset]::Now.ToString('yyyy-MM-dd HH:mm'))）") $ghCache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git commit') }
            $r = Invoke-SyncGit @('push','origin',"HEAD:$ghBranch") $ghCache
            if ($r.code -ne 0) { throw (Format-SyncError $r.code $r.text 'git push') }
            $notify.ShowBalloonTip(3000, 'DSH 升级', "已将本机启动脚本上传到 GitHub（v$($lm.version)，发布 $($published.Count) 个 zip）。", 'Info')
        }
    } catch {
        $notify.ShowBalloonTip(5000, 'DSH 升级', "同步失败：$($_.Exception.Message)", 'Error')
    } finally {
        Release-SyncLock
        if ($tmpZip) { Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue }
    }
}