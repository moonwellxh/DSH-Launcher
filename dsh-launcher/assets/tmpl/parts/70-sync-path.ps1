function Sync-LauncherScript {
    # 一键启动脚本与 GitHub（moonwellxh/DSH-Launcher）双向同步：
    # 以仓库内解压源树 dsh-launcher/ 为比对对象，逐文件内容哈希比对（不信任缓存/版本号），
    # 方向按双方实际 _meta.json 时间戳判定；上传前先 bump 本地时间戳，绝不自动覆盖远端良包
    $notify.ShowBalloonTip(2000, 'DSH 升级', '正在同步启动脚本…', 'Info')
    if (-not (Test-Path -LiteralPath $skillDir)) { throw "本机技能目录不存在：$skillDir" }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw '未找到 git：请先安装 Git（https://git-scm.com）并配置 GitHub 凭据（HTTPS 推荐 credential manager）' }
    # git 全程非交互：缺凭据立即失败并提示，不在隐藏窗口里挂起等待输入
    $env:GIT_TERMINAL_PROMPT = '0'
    $tmpZip = Join-Path $env:TEMP ("dsh-sync-" + [guid]::NewGuid().ToString('N') + '.zip')
    try {
        # 0) 同步 GitHub 仓库工作副本（~\.dsh\gh-sync\DSH-Launcher）
        New-Item -ItemType Directory -Path (Split-Path $ghCache -Parent) -Force | Out-Null
        if (-not (Test-Path -LiteralPath (Join-Path $ghCache '.git'))) {
            git clone -b $ghBranch --depth 1 "https://github.com/$ghRepo.git" $ghCache
            if ($LASTEXITCODE -ne 0) { throw "git clone 失败（exit $LASTEXITCODE）：请检查网络/代理与仓库地址 $ghRepo" }
        } else {
            git -C $ghCache fetch origin $ghBranch
            if ($LASTEXITCODE -ne 0) { throw "git fetch 失败（exit $LASTEXITCODE）：请检查网络/代理与 GitHub 连通性" }
            git -C $ghCache reset --hard "origin/$ghBranch"
        }
        $remoteBase = Join-Path $ghCache 'dsh-launcher'
        if (-not (Test-Path -LiteralPath $remoteBase)) { throw 'GitHub 仓库缺少 dsh-launcher 源树目录（仓库结构异常）' }
        # 1) 本机技能目录内容清单（相对路径 → SHA256）
        $localMap = @{}
        Get-ChildItem -LiteralPath $skillDir -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($skillDir.Length + 1) -replace '\\','/'
            $localMap[$rel] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
        # 2) GitHub 侧内容清单
        $remoteMap = @{}
        Get-ChildItem -LiteralPath $remoteBase -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($remoteBase.Length + 1) -replace '\\','/'
            $remoteMap[$rel] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
        # 3) 内容级比对
        $diff = @()
        foreach ($k in @(($localMap.Keys + $remoteMap.Keys) | Select-Object -Unique)) {
            if ($localMap[$k] -ne $remoteMap[$k]) { $diff += $k }
        }
        if ($diff.Count -eq 0) {
            $notify.ShowBalloonTip(3000, 'DSH 升级', '启动脚本与 GitHub 完全一致，无需同步。', 'Info')
            return
        }
        # 4) 方向判定：读双方实际 _meta.json 时间戳（真实内容，非记忆值）
        $lm = Get-Content -LiteralPath (Join-Path $skillDir '_meta.json') -Raw | ConvertFrom-Json
        $rm = Get-Content -LiteralPath (Join-Path $remoteBase '_meta.json') -Raw | ConvertFrom-Json
        $lp = [long]$lm.publishedAt; $rp = [long]$rm.publishedAt
        if ($lp -eq $rp) {
            # 时间戳相同但内容不同：按实际文件修改时间分析并给出建议，弹窗由用户确认方向（上传/拉取/取消）后才执行——绝不自动覆盖 GitHub 良包
            $localNewer = $false; $remoteNewer = $false
            foreach ($k in $diff) {
                $lf = Join-Path $skillDir ($k -replace '/','\')
                $rf = Join-Path $remoteBase ($k -replace '/','\')
                $lt = if (Test-Path -LiteralPath $lf) { (Get-Item -LiteralPath $lf).LastWriteTimeUtc } else { [datetime]::MinValue }
                $rt = if (Test-Path -LiteralPath $rf) { (Get-Item -LiteralPath $rf).LastWriteTimeUtc } else { [datetime]::MinValue }
                if ($lt -gt $rt) { $localNewer = $true } elseif ($rt -gt $lt) { $remoteNewer = $true }
                if ($localNewer -and $remoteNewer) { break }
            }
            $sug = '双向都有更新，无法自动判定，请人工确认合并方向'
            if ($localNewer -and -not $remoteNewer) { $sug = '本机较新（推荐：上传本机版本到 GitHub）' }
            elseif ($remoteNewer -and -not $localNewer) { $sug = 'GitHub 较新（推荐：拉取 GitHub 版本到本机）' }
            $showFiles = ($diff | Select-Object -First 5) -join '，'
            if ($diff.Count -gt 5) { $showFiles += ' 等' }
            $dlg = "启动脚本：本机与 GitHub 时间戳相同但内容不同（$($diff.Count) 个文件：$showFiles）。`n按实际修改时间分析：$sug。`n`n请选择同步方向（上传会提交到 GitHub，git 历史会保留旧版本）："
            $dir = Show-SyncDirectionDialog $dlg
            if ($dir -eq 'upload') {
                # 用户确认上传：bump _meta 时间戳（等效本地更新），随后走上传分支（旧版由 git 历史保留，无需手工备份）
                $lm.publishedAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
                [System.IO.File]::WriteAllText((Join-Path $skillDir '_meta.json'), ($lm | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
                $lp = [long]$lm.publishedAt
            } elseif ($dir -eq 'pull') {
                # 用户确认拉取：等效 GitHub 时间戳更大，随后走拉取分支
                $rp = $lp + 1
            } else {
                $notify.ShowBalloonTip(3000, 'DSH 升级', '已取消同步，未做任何更改。', 'Info')
                return
            }
        }
        if ($rp -gt $lp) {
            # 兼容性检查：GitHub 上的启动器声明了兼容的 DSH 版本，本机不满足则提醒先升级 DSH，不更新
            $curDsh = Get-CurrentDshVersion
            if ($rm.compatibleDsh) {
                $compat = @($rm.compatibleDsh)
                if ($curDsh -and ($compat -notcontains $curDsh)) {
                    $notify.ShowBalloonTip(6000, 'DSH 升级', "GitHub 上的启动器要求 DSH $($compat -join ' / ')，当前为 $curDsh，请先升级 DSH 再同步。", 'Warning')
                    return
                }
            }
            # GitHub 新 → 更新本地技能目录
            Get-ChildItem -LiteralPath $remoteBase -Recurse -File | ForEach-Object {
                $dst = Join-Path $skillDir ($_.FullName.Substring($remoteBase.Length + 1))
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            # 按远端清单清理本地多余文件（远端已删除的本地残留 → 否则哈希永远不一致）
            Get-ChildItem -LiteralPath $skillDir -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($skillDir.Length + 1) -replace '\\','/'
                if (-not $remoteMap.ContainsKey($rel)) {
                    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
                }
            }
            # 重跑 setup 重新生成本机启动器并重打补丁（补丁引擎内部有 compatibleDsh 校验，不兼容补丁会自动跳过）
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
            # 本地新 → 上传到 GitHub：更新源树 + 重打包 zip 到 releases\<版本>\ + git 提交推送
            # 加载 ZipFile 程序集（托盘默认不加载，必须在函数内自加载）
            try { Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop } catch {}
            # ① 同步源树 dsh-launcher/
            $srcTree = Join-Path $ghCache 'dsh-launcher'
            Get-ChildItem -LiteralPath $skillDir -Recurse -File | ForEach-Object {
                $dst = Join-Path $srcTree ($_.FullName.Substring($skillDir.Length + 1))
                New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
            }
            Get-ChildItem -LiteralPath $srcTree -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($srcTree.Length + 1) -replace '\\','/'
                if (-not $localMap.ContainsKey($rel)) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
            }
            # ② 重打包 zip 到 releases\<版本>\（zip 集中归档目录，按版本分目录）
            $releaseDir = Join-Path $ghCache ("releases\v" + $lm.version)
            New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
            & 'C:\Windows\System32\tar.exe' -a -cf $tmpZip -C $ghCache 'dsh-launcher'
            if ($LASTEXITCODE -ne 0) { throw "打包失败（exit $LASTEXITCODE）" }
            $relZip = Join-Path $releaseDir 'dsh-launcher__skillhub.zip'
            Copy-Item -LiteralPath $tmpZip -Destination $relZip -Force
            try { $z = [System.IO.Compression.ZipFile]::OpenRead($relZip); $z.Dispose() } catch { throw "打包校验失败：$($_.Exception.Message)" }
            # ③ git 提交并推送（git 历史 = 旧版本天然备份，无需手工备份旧包）
            git -C $ghCache add -A
            if ($LASTEXITCODE -ne 0) { throw "git add 失败（exit $LASTEXITCODE）" }
            if (-not (git -C $ghCache status --porcelain)) {
                $notify.ShowBalloonTip(3000, 'DSH 升级', '内容已同步，无新变更需要推送。', 'Info')
                return
            }
            git -C $ghCache commit -m "dsh-launcher v$($lm.version) 同步（$([DateTimeOffset]::Now.ToString('yyyy-MM-dd HH:mm'))）"
            if ($LASTEXITCODE -ne 0) { throw "git commit 失败（exit $LASTEXITCODE）" }
            git -C $ghCache push origin $ghBranch
            if ($LASTEXITCODE -ne 0) { throw "git push 失败（exit $LASTEXITCODE）：请检查 GitHub 凭据（credential manager / SSH key）" }
            $notify.ShowBalloonTip(3000, 'DSH 升级', "已将本机启动脚本上传到 GitHub（v$($lm.version)）。", 'Info')
        }
    } catch {
        $notify.ShowBalloonTip(5000, 'DSH 升级', "同步失败：$($_.Exception.Message)", 'Error')
    } finally {
        Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
    }
}