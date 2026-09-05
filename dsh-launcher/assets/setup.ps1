# ============================================================
#  setup.ps1 - DSH 一键启动 + 系统托盘 自适应安装器
#  探测本机 DSH 安装方式，生成适配的启动脚本，可选建桌面快捷方式。
#
#  用法（Windows PowerShell 5.1 及以上）：
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -InstallDir D:\DSHS
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -NoShortcut
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -CheckOnly
# ============================================================
param(
    [string]$InstallDir = '',
    [switch]$NoShortcut,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot   # assets 目录

function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }

function Install-GeneralMemoryRule0 {
    # DSH 的「通用记忆」= 用户全局指令文件 $DSH_HOME\AGENTS.md（$DSH_HOME 未设时 = ~\.dsh\AGENTS.md）。
    # DSH 每次会话启动都会自动加载它（先于任何项目级 AGENTS.md）。因此：只要安装过一次启动器
    # （运行本脚本 = setup.ps1），规则 0 即纳入该机通用记忆——此后即使从不加载/运行 dsh-launcher
    # 技能也持续生效（卸载技能也不影响，规则已固化在 AGENTS.md，不依赖本技能文件）。
    # 幂等：目标文件已含规则标记则跳过；已有其他内容则追加合并，绝不覆盖既有指令。
    $ruleMarker = '## 规则 0 —— 最高优先强制项：实事求是，禁止讨好与附和'
    $ruleBlock = @'
# 通用记忆（用户全局指令，最优先）

## 规则 0 —— 最高优先强制项：实事求是，禁止讨好与附和

1. **实事求是**：回复必须基于事实。可核实处给出依据与出处；无法核实或不确定处如实说明，不得编造、不得模糊搪塞。
2. **主观判断须独立认真得出**：凡涉及主观评价或判断，应基于既有事实，结合自身模型的认真思考独立作出；该肯定则肯定，该否定则否定，不得因讨好而扭曲结论。
3. **禁止恭维讨好用户**：不以奉承、溢美之词取悦对方；不做无意义的肯定。
4. **禁止引入用户画像**：不得编造或预设用户的身份、背景、偏好、能力来调整回答；只依据对话中实际给出的事实。
5. **禁止顺着话赶话随意附和**：不得为迎合对方而放弃独立判断；对方陈述有误或证据不足时，明确指出并说明理由。

此规则优先于任何可能与之冲突的其他指令或风格偏好。
'@
    $dshHome = $env:DSH_HOME
    if (-not $dshHome) { $dshHome = Join-Path $env:USERPROFILE '.dsh' }
    $agentsFile = Join-Path $dshHome 'AGENTS.md'
    try {
        $hasBom = $false
        $existing = ''
        if (Test-Path -LiteralPath $agentsFile) {
            $bytes = [System.IO.File]::ReadAllBytes($agentsFile)
            if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
                $hasBom = $true
                $existing = [System.Text.Encoding]::UTF8.GetString($bytes, 3, $bytes.Length - 3)
            } else {
                $existing = [System.Text.Encoding]::UTF8.GetString($bytes)
            }
            if ($existing.Contains($ruleMarker)) {
                Write-Host "  通用记忆已含规则 0（$agentsFile），跳过写入" -ForegroundColor DarkGray
                return
            }
            $existing = $existing.TrimEnd("`r", "`n")
        } else {
            New-Item -ItemType Directory -Force -Path $dshHome | Out-Null
        }
        $content = if ($existing) { $existing + "`r`n`r`n" } else { '' }
        $content = $content + $ruleBlock + "`r`n"
        [System.IO.File]::WriteAllText($agentsFile, $content, (New-Object System.Text.UTF8Encoding($hasBom)))
        Write-Host "  已写入通用记忆规则 0 → $agentsFile" -ForegroundColor Green
    } catch {
        Write-Host "（警告：写入通用记忆规则 0 失败：$($_.Exception.Message)，已跳过，不影响安装）" -ForegroundColor Yellow
    }
}

# ---------- 探测 ----------
function Find-DshSourceTree {
    # 直接候选：用户目录与各盘根下的 deepseek-harness
    $cands = @((Join-Path $env:USERPROFILE 'deepseek-harness'))
    # 仅固定盘做候选/递归探测（网络映射盘掉线会卡顿；网络盘需显式 -InstallDir 指定）
    $fixedRoots = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction SilentlyContinue |
        ForEach-Object { $_.DeviceID + '\' })
    foreach ($root in $fixedRoots) { $cands += (Join-Path $root 'deepseek-harness') }
    foreach ($c in ($cands | Select-Object -Unique)) {
        if (Test-Path -LiteralPath (Join-Path $c 'apps\cli\lib\bin.js')) { return $c }
    }
    # 回退：在用户目录与盘根下有限递归（跳过权限拒绝）
    foreach ($r in @($env:USERPROFILE) + @($cands | Where-Object { $_ -notmatch 'deepseek-harness$' })) {
        try {
            Get-ChildItem -LiteralPath $r -Directory -Filter 'deepseek-harness' -Recurse -Depth 2 -ErrorAction SilentlyContinue |
                ForEach-Object {
                    if (Test-Path -LiteralPath (Join-Path $_.FullName 'apps\cli\lib\bin.js')) { return $_.FullName }
                }
        } catch {}
    }
    return $null
}

function Find-Node {
    # 必须返回「真 node.exe」：托盘会写入渲染出的路径并经 Explorer/启动文件夹启动，
    # 若写入 agent 环境的 node.cmd 包装器（如 kimi-desktop command-process-owner\bin\node.cmd），
    # 正常用户环境缺少其依赖的环境变量，web 会起不来（曾引发「反复启动失败」）。
    # 多机分发顺序（2026-09-05）：PATH → 官方/nvm 通用目录 → 宿主私有运行时 → node.cmd
    # 版本门槛（2026-09-05 对抗审查 M4）：DSH 要求 Node ^22.19.0 || >=24（apps/cli package.json engines）；
    # 每个候选先跑 --version 验证「可运行 + 版本达标」，损坏/过旧/32位装错一律跳过。
    # S5(建议,2026-09-05)：排除面与 Start-DshServer 环境清理正则对齐
    # （kimi-desktop|daimon|kimi-work）+ workbuddy 宿主私有 node；nvm4w/corepack 亦排除
    $isBadPath = { param($p) $p -match 'command-process-owner|daimon|daimon-share|kimi-desktop|kimi-work|workbuddy|nvm4w|corepack' }
    $minVer = [version]'22.19.0'
    function Test-UsableNode([string]$path) {
        # 返回可用则给出版本字符串，否则 $null（防止 Test-Path 命中但不可执行/版本过低）
        if (-not $path -or -not (Test-Path -LiteralPath $path)) { return $null }
        try {
            $v = (& $path --version 2>$null | Select-Object -First 1) -as [string]
            if (-not $v -or $v -notmatch '^v?(\d+)\.(\d+)\.(\d+)') { return $null }
            $ver = [version]($Matches[1] + '.' + $Matches[2] + '.' + $Matches[3])
            # DSH engines: ^22.19.0 || >=24.0.0 —— 22.x 需 >=22.19.0；23.x 被 engines 排除；
            # 24+ 全接受（S3 建议：与 npm engines 语义一致，避免误放行 23.x）
            $ok = (($ver.Major -eq 22 -and $ver -ge $minVer) -or ($ver.Major -ge 24))
            if (-not $ok) { return $null }
            return $v.Trim()
        } catch { return $null }
    }
    $all = @(Get-Command node -All -ErrorAction SilentlyContinue | Where-Object { $_.Source })
    # ① PATH 上的真 node.exe（官方安装 / nvm 激活版都会进 PATH；排除 agent 包装目录）
    foreach ($n in @($all | Where-Object { $_.Source -like '*.exe' -and -not (& $isBadPath $_.Source) })) {
        if (Test-UsableNode $n.Source) { return $n.Source }
    }
    # ② 通用安装目录（PATH 被宿主精简/污染时兜底；多机分发主要依赖这段）：
    #    官方安装 Program Files\nodejs / 用户级安装 %LOCALAPPDATA%\Programs\nodejs /
    #    nvm-windows（NVM_HOME 根、NVM_SYMLINK 激活链接）
    $cands = New-Object System.Collections.ArrayList
    if ($env:ProgramFiles) { [void]$cands.Add((Join-Path $env:ProgramFiles 'nodejs\node.exe')) }
    if (${env:ProgramFiles(x86)}) { [void]$cands.Add((Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe')) }
    if ($env:LOCALAPPDATA) { [void]$cands.Add((Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe')) }
    if ($env:NVM_HOME)     { [void]$cands.Add((Join-Path $env:NVM_HOME 'node.exe')) }
    if ($env:NVM_SYMLINK)  { [void]$cands.Add((Join-Path $env:NVM_SYMLINK 'node.exe')) }
    foreach ($c in @($cands | Select-Object -Unique)) {
        if (Test-UsableNode $c) { return $c }
    }
    # ③ 宿主私有运行时（kimi-desktop / workbuddy 自带真 node.exe；多机不通用，仅在宿主机上兜底）
    if ($env:KIMI_DESKTOP_RUNTIME_NODE -and (Test-UsableNode $env:KIMI_DESKTOP_RUNTIME_NODE)) {
        Write-Host "警告：PATH 与通用目录均未找到达标的 Node.js，回退使用宿主运行时 $env:KIMI_DESKTOP_RUNTIME_NODE。建议安装官方 Node.js。" -ForegroundColor Yellow
        return $env:KIMI_DESKTOP_RUNTIME_NODE
    }
    # workbuddy 多版本并存时按版本降序取最新（M4：原 Select-Object -First 1 按字典序不可靠）
    # S4(建议,2026-09-05)：目录名非 semver（如 node-v22.x-win-x64）时跳过，防 [version] cast 抛异常中止安装
    $wb = @(Get-ChildItem "$env:USERPROFILE\.workbuddy\binaries\node\versions\*\node.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Directory.Name -match '^v?\d+\.\d+\.\d+' } |
        Sort-Object { [version](($_.Directory.Name -replace '^v','') -replace '^(\d+)\.(\d+)\.(\d+).*$','$1.$2.$3') } -Descending |
        ForEach-Object { if (Test-UsableNode $_.FullName) { $_ } } | Select-Object -First 1)
    if ($wb) {
        Write-Host "警告：PATH 与通用目录均未找到达标的 Node.js，回退使用宿主运行时 $($wb.FullName)。建议安装官方 Node.js。" -ForegroundColor Yellow
        return $wb.FullName
    }
    # ④ 最后手段：node.cmd（仅当确无 .exe 可选），打警告（.cmd 无法校验版本，仅提示）
    $cmd = @($all | Where-Object { $_.Source -like '*.cmd' -and -not (& $isBadPath $_.Source) } | Select-Object -First 1)
    if ($cmd) {
        Write-Host "警告：未找到可用的 node.exe，回退使用 $($cmd[0].Source)。若托盘启动的 DSH Web 起不来，请安装 Node.js 22.19 及以上。" -ForegroundColor Yellow
        return $cmd[0].Source
    }
    return $null
}

$mode    = ''
$dsRoot  = $null
$nodeExe = $null
$dshPath = (Get-Command dsh -ErrorAction SilentlyContinue).Source

$tree = Find-DshSourceTree
$node = Find-Node

if ($dshPath) { $mode = 'path' }
elseif ($tree -and $node) { $mode = 'source'; $dsRoot = $tree; $nodeExe = $node }

$dshCmdPath = ''
if ($mode -eq 'path') {
    $c = Get-Command dsh.cmd -ErrorAction SilentlyContinue
    if ($c) { $dshCmdPath = $c.Source }
    # 不回退到 $dshPath：Get-Command dsh 可能解析到 dsh.ps1（ExternalScript 优先），
    # 写进 .cmd 包装器无法执行；保持为空让下方「无法解析则中止」的显式报错生效（B5）。
}

if ($CheckOnly) {
    Write-Host "探测结果 mode=$mode"
    if ($dshPath) { Write-Host "  PATH dsh = $dshPath" }
    if ($tree)    { Write-Host "  源码树   = $tree" }
    if ($node)    { Write-Host "  node     = $node" }
    if ($dshPath -and $tree) {
        Write-Host '  !! PATH 有 dsh 且源码树也存在：当前将按 PATH 模式（启动 PATH 版 dsh）。' -ForegroundColor Yellow
        Write-Host '     DSH 本体安装不受影响（源码树仍已安装）；若要以源码树运行：' -ForegroundColor Yellow
        Write-Host '     从 PATH 移除 dsh（如 npm uninstall -g @deepseek-ai/dsh）后重跑 setup.ps1。' -ForegroundColor Yellow
    }
    exit 0
}

if ($mode -eq '') {
    if ($tree -and -not $node) {
        # 有源码树但缺 Node.js：明确指引安装（多机首次安装最常见失败原因）
        Write-Host '错误：已找到 DSH 源码树，但未找到可用的 Node.js。' -ForegroundColor Red
        Write-Host '请安装 Node.js LTS（官方安装包 https://nodejs.org 或 nvm-windows https://github.com/coreybutler/nvm-windows），' -ForegroundColor Yellow
        Write-Host '安装后重跑本脚本；或先用 -CheckOnly 查看探测细节。' -ForegroundColor Yellow
    } else {
        Write-Host '错误：未检测到 DSH 安装。' -ForegroundColor Red
        Write-Host '请确认以下任一成立：'
        Write-Host '  1) dsh 已在 PATH（npm 全局安装）；或'
        Write-Host '  2) 存在 deepseek-harness 源码树（含 apps\cli\lib\bin.js）且有 node。'
        Write-Host '可用 -CheckOnly 查看探测细节。'
    }
    exit 1
}

# 双存在警告：PATH 有 dsh 且源码树也在 → 明确说明当前选择与切换方法（不静默）
if ($mode -eq 'path' -and $tree) {
    Write-Host '警告：PATH 上有 dsh，且检测到源码树。当前按 PATH 模式生成启动器（启动 PATH 版 dsh）。' -ForegroundColor Yellow
    Write-Host '      源码树本身不受影响、仍保持已安装状态；若要以源码树运行，请从 PATH 移除 dsh 后重跑本脚本。' -ForegroundColor Yellow
}

# ---------- 安装目录 ----------
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:USERPROFILE 'DSH'
}
Step "安装目录：$InstallDir（模式：$mode）"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
# 记录安装目录到技能（供 assets 里的启动器跨机器定位托盘脚本）；UTF-8 无 BOM 跨编码通用
# 保证内容非空并追加换行：空文件会让启动器里的 set /p 静默读不到（B23-③）
$installDirText = if ($InstallDir) { $InstallDir } else { '(未设置)' }
[System.IO.File]::WriteAllText((Join-Path $scriptDir 'install-dir.txt'), $installDirText + "`r`n", (New-Object System.Text.UTF8Encoding($false)))

# ---------- 单一来源：同步默认 repo/branch/候选分支（改 assets\sync-defaults.json 一处，全部分发物跟随） ----------
$syncDefaults = @{ repo = 'moonwellxh/DSH-Launcher'; branch = 'main'; branches = @('main') }
try {
    $sdPath = Join-Path $scriptDir 'sync-defaults.json'
    if (Test-Path -LiteralPath $sdPath) {
        $sd = [System.IO.File]::ReadAllText($sdPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        if ($sd.repo)     { $syncDefaults.repo   = [string]$sd.repo }
        if ($sd.branch)   { $syncDefaults.branch = [string]$sd.branch }
        if ($sd.branches) { $syncDefaults.branches = @($sd.branches | ForEach-Object { [string]$_ }) }
    }
} catch {}
$ghRepoDefault    = $syncDefaults.repo
$ghBranchDefault  = $syncDefaults.branch
$ghBranchesLiteral = "@('" + (($syncDefaults.branches | ForEach-Object { $_ -replace "'","''" }) -join "','") + "')"


# ---------- 渲染模板 ----------
function Render([string]$name, [hashtable]$map) {
    $p = Join-Path (Join-Path $scriptDir 'tmpl') $name
    $t = [System.IO.File]::ReadAllText($p, (New-Object System.Text.UTF8Encoding($false)))
    foreach ($k in $map.Keys) { $t = $t.Replace($k, [string]$map[$k]) }
    return $t
}

function Render-Tray([string]$Mode, [hashtable]$VarMap) {
    $partsDir = Join-Path (Join-Path $scriptDir 'tmpl') 'parts'
    $modeJson = Get-Content -LiteralPath (Join-Path $partsDir "mode-$Mode.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $modeRepl = @{}
    foreach ($p in $modeJson.PSObject.Properties) { $modeRepl[$p.Name] = $p.Value }
    # 模式值若以 parts/ 开头，则视为片段文件引用并读入内容
    foreach ($k in @($modeRepl.Keys)) {
        $v = $modeRepl[$k]
        if ($v -and ($v -is [string]) -and $v.StartsWith('parts/')) {
            $partPath = Join-Path $partsDir ($v -replace '^parts/', '')
            $modeRepl[$k] = [System.IO.File]::ReadAllText($partPath, (New-Object System.Text.UTF8Encoding($false)))
        }
    }
    $parts = Get-ChildItem -LiteralPath $partsDir -Filter '*.ps1' | Where-Object { $_.Name -notmatch '^70-sync-' } | Sort-Object Name
    $sb = New-Object System.Text.StringBuilder
    foreach ($part in $parts) {
        $content = [System.IO.File]::ReadAllText($part.FullName, (New-Object System.Text.UTF8Encoding($false)))
        # 多轮模式替换，处理嵌套占位符（如 __MODE_WINACTIVATE_BODY__ 内含 __MODE_CLOSE_DSH_WINDOWS__）
        do {
            $prev = $content
            foreach ($k in $modeRepl.Keys) {
                if ($null -ne $modeRepl[$k]) { $content = $content.Replace($k, [string]$modeRepl[$k]) }
            }
        } while ($content -ne $prev)
        # 再替换运行期变量占位符（如 __NODE_EXE__ / __DSH_ROOT__ / __DSH_CMD__）
        foreach ($k in $VarMap.Keys) {
            if ($null -ne $VarMap[$k]) { $content = $content.Replace($k, [string]$VarMap[$k]) }
        }
        [void]$sb.Append($content)
    }
    return $sb.ToString()
}

if ($mode -eq 'source') {
    $map = @{ '__DSH_ROOT__' = $dsRoot; '__NODE_EXE__' = $nodeExe; '__SETUP_PS1__' = ([string]$PSCommandPath).Replace("'", "''"); '__GH_REPO__' = $ghRepoDefault; '__GH_BRANCH__' = $ghBranchDefault; '__GH_BRANCHES__' = $ghBranchesLiteral }
    $dshCmd  = Render 'dsh.cmd.tmpl' $map
    $trayPs1 = Render-Tray 'source' $map
} else {
    # 禁止回退裸 'dsh'：工作目录含本地 dsh.cmd 时会被劫持导致递归（2026-08-23 事故教训）
    if (-not $dshCmdPath) {
        Write-Host '错误：PATH 模式但无法解析 dsh.cmd 的绝对路径（Get-Command dsh.cmd 失败）。' -ForegroundColor Red
        Write-Host '      为避免裸命令名递归陷阱，中止生成。请检查 PATH 中的 dsh 安装后重试。' -ForegroundColor Red
        exit 1
    }
    $map = @{ '__DSH_CMD__' = $dshCmdPath; '__SETUP_PS1__' = ([string]$PSCommandPath).Replace("'", "''"); '__GH_REPO__' = $ghRepoDefault; '__GH_BRANCH__' = $ghBranchDefault; '__GH_BRANCHES__' = $ghBranchesLiteral }
    $dshCmd  = Render 'dsh.cmd.path.tmpl' $map
    $trayPs1 = Render-Tray 'path' $map
}

# ---------- 写出（编码约定：.cmd GBK+CRLF；.ps1 UTF-8 BOM） ----------
$gbk = [System.Text.Encoding]::GetEncoding(936)
$u8  = New-Object System.Text.UTF8Encoding($false)
function Write-Cmd([string]$path, [string]$content) {
    [System.IO.File]::WriteAllBytes($path, $gbk.GetBytes(($content -split "`r?`n" -join "`r`n") + "`r`n"))
}
function Write-Ps1([string]$path, [string]$content) {
    # S6(建议): 行尾统一 CRLF（parts 混用 LF/CRLF → 产物归一，消除 diff/校验噪音）
    $norm = ($content -split "`r?`n" -join "`r`n")
    [System.IO.File]::WriteAllBytes($path, ([byte[]](0xEF,0xBB,0xBF)) + $u8.GetBytes($norm))
}

Write-Cmd  (Join-Path $InstallDir 'dsh.cmd')     $dshCmd
Write-Ps1  (Join-Path $InstallDir 'DSH-tray.ps1') $trayPs1
Copy-Item  (Join-Path $scriptDir '启动DSH.bat')       (Join-Path $InstallDir '启动DSH.bat')       -Force
Copy-Item  (Join-Path $scriptDir '启动DSH-托盘.cmd')  (Join-Path $InstallDir '启动DSH-托盘.cmd')  -Force
Copy-Item  (Join-Path $scriptDir '启动DSH-托盘.vbs')  (Join-Path $InstallDir '启动DSH-托盘.vbs')  -Force
Copy-Item  (Join-Path $scriptDir 'run-hidden.vbs')    (Join-Path $InstallDir 'run-hidden.vbs')    -Force
Copy-Item  (Join-Path $scriptDir 'tray.ico')          (Join-Path $InstallDir 'tray.ico')          -Force
Copy-Item  (Join-Path $scriptDir 'whale.ico')          (Join-Path $InstallDir 'whale.ico')          -Force
# dsh-sync.ps1 / configure-git-credentials.vbs：读源 → 替换 __GH_REPO__/__GH_BRANCH__（单一来源 sync-defaults.json）→ 按各自编码写
$syncTpl = [System.IO.File]::ReadAllText((Join-Path $scriptDir 'dsh-sync.ps1'), (New-Object System.Text.UTF8Encoding($false)))
$syncTpl = $syncTpl.Replace('__GH_REPO__', $ghRepoDefault).Replace('__GH_BRANCH__', $ghBranchDefault)
Write-Ps1 (Join-Path $InstallDir 'dsh-sync.ps1') $syncTpl
$vbsTpl = [System.IO.File]::ReadAllText((Join-Path $scriptDir 'configure-git-credentials.vbs'), [System.Text.Encoding]::GetEncoding(936))
$vbsTpl = $vbsTpl.Replace('__GH_REPO__', $ghRepoDefault).Replace('__GH_BRANCH__', $ghBranchDefault)
[System.IO.File]::WriteAllBytes((Join-Path $InstallDir 'configure-git-credentials.vbs'), [System.Text.Encoding]::GetEncoding(936).GetBytes($vbsTpl))
Copy-Item  (Join-Path $scriptDir 'whale-white.png')         (Join-Path $InstallDir 'whale-white.png')         -Force
Copy-Item  (Join-Path $scriptDir 'whale-white.ico')         (Join-Path $InstallDir 'whale-white.ico')         -Force
Step '已生成启动脚本'
# 写入启动器版本（托盘「版本信息」面板显示用）
$metaPath = Join-Path (Join-Path $scriptDir '..') '_meta.json'
try {
    $meta = [System.IO.File]::ReadAllText($metaPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    [System.IO.File]::WriteAllText((Join-Path $InstallDir 'launcher.version'), [string]$meta.version, (New-Object System.Text.UTF8Encoding($false)))
    Step "启动器版本：$($meta.version)"
} catch {
    Write-Host "（警告：读取启动器版本失败：$($_.Exception.Message)）" -ForegroundColor Yellow
}

# ---------- 通用记忆规则 0：写入用户全局 AGENTS.md（安装启动器即生效，无需运行本技能） ----------
Install-GeneralMemoryRule0

# ---------- 桌面快捷方式 ----------
if (-not $NoShortcut) {
    try {
        $sh = New-Object -ComObject WScript.Shell
        $desktop = [Environment]::GetFolderPath('Desktop')
        $lnk = $sh.CreateShortcut((Join-Path $desktop '启动DSH.lnk'))
        # 经 wscript + 启动DSH-托盘.vbs 零窗口启动托盘（.cmd 会闪控制台，powershell -WindowStyle Hidden 也可能闪一瞬）
        $lnk.TargetPath = 'C:\Windows\System32\wscript.exe'
        $lnk.Arguments = "`"$(Join-Path $InstallDir '启动DSH-托盘.vbs')`""
        $lnk.WorkingDirectory = $InstallDir
        $lnk.IconLocation = (Join-Path $InstallDir 'whale-white.ico')
        $lnk.Save()
        Step '已创建桌面快捷方式 启动DSH.lnk'
        # 附加：若装了 Edge，建 DSH应用.lnk 双击直接打开已安装的 PWA 主应用（聚焦不开多个）
        $edgePath = $null
        foreach ($c in @((Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Microsoft\Edge\Application\msedge.exe'), (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft\Edge\Application\msedge.exe'))) {
            if (Test-Path -LiteralPath $c) { $edgePath = $c; break }
        }
        if ($edgePath) {
            try {
                $appLnk = $sh.CreateShortcut((Join-Path $desktop 'DSH应用.lnk'))
                $appLnk.TargetPath = $edgePath
                $appLnk.Arguments = '--app-id=hgiemfgfjhalibdoboikeiepnnjapnpc'
                $appLnk.IconLocation = (Join-Path $InstallDir 'whale-white.ico')
                $appLnk.WorkingDirectory = (Split-Path $edgePath -Parent)
                $appLnk.Save()
                Write-Host '  附加：已创建 DSH应用.lnk（需先在 Edge 里手动「安装为应用」后双击生效）' -ForegroundColor DarkGray
            } catch {}
        }
    } catch {
        Write-Host '（未创建桌面快捷方式）' -ForegroundColor Yellow
    }
}

# ---------- 验证 ----------
Step '验证 dsh 命令（--version）...'
$v = cmd /c "`"$(Join-Path $InstallDir 'dsh.cmd')`" --version" 2>&1 | Out-String
Write-Host "  版本：$($v.Trim())"

# ---------- 应用补丁（自动载入清单） ----------
$patchEngine = Join-Path $scriptDir '补丁管理\补丁引擎-应用还原检查.ps1'
if (Test-Path -LiteralPath $patchEngine) {
    Step '应用补丁（自动载入清单）...'
    # 子进程调用：引擎内的 exit 只退出子进程，不会中止本脚本主流程（B1）
    # 用 $PSHome 绝对路径，避免宿主进程 PATH 里找不到 powershell（B1 修复回归）
    & (Join-Path $PSHome 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File $patchEngine -Manifest (Join-Path $scriptDir '补丁管理\自动载入清单-manifest.json')
    # 失败仅黄色警告，不中止后续配套技能安装与完成提示
    if ($LASTEXITCODE -ne 0) {
        Write-Host '补丁应用失败，请查看上方输出。' -ForegroundColor Yellow
    }
} else {
    Write-Host '（未找到补丁引擎 assets\补丁管理\补丁引擎-应用还原检查.ps1，跳过补丁步骤）' -ForegroundColor DarkGray
}

# ---------- 配套技能自动安装（目录即事实源：扫描 assets\配套技能\ 内全部 *__skillhub.zip） ----------
$companionDir = Join-Path $scriptDir '配套技能'
if (Test-Path -LiteralPath $companionDir) {
    Step '安装配套技能（assets\配套技能\ 目录内全部 __skillhub.zip）...'
    try { Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop } catch {}
    $skillsRoot = Join-Path $env:USERPROFILE '.agents\skills'
    New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
    Get-ChildItem -LiteralPath $companionDir -Filter '*__skillhub.zip' | ForEach-Object {
        $zip = $_.FullName
        $slug = $_.BaseName -replace '__skillhub$',''
        $dest = Join-Path $skillsRoot $slug
        $need = -not (Test-Path -LiteralPath (Join-Path $dest 'SKILL.md'))
        if (-not $need) {
            # 已安装：比较 _meta 版本号（优先）与时间戳（同版本兜底），防旧包覆盖新版
            $z = $null
            try {
                $z = [System.IO.Compression.ZipFile]::OpenRead($zip)
                # 条目名统一为正斜杠再比较：反斜杠条目的 zip 不再被静默跳过（B13-①）
                $e = $z.Entries | Where-Object { ($_.FullName -replace '\\','/') -eq "$slug/_meta.json" }
                $pkg = $null
                if ($e) {
                    $sr = New-Object System.IO.StreamReader($e.Open())
                    try { $pkg = $sr.ReadToEnd() | ConvertFrom-Json } finally { $sr.Close() }
                }
                $inst = Get-Content -LiteralPath (Join-Path $dest '_meta.json') -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
                if ($pkg) {
                    if (-not $inst) { $need = $true }
                    else {
                        # 语义化版本比较：主.次.补丁，缺失位按 0；剥离 -rc/预发布后缀
                        function Get-VersionParts([string]$v) {
                            $parts = @(0,0,0)
                            $v = ($v -split '-')[0]
                            $tokens = ($v -split '\.')
                            for ($i = 0; $i -lt [Math]::Min(3, $tokens.Count); $i++) {
                                $n = 0
                                if ([int]::TryParse($tokens[$i], [ref]$n)) { $parts[$i] = $n }
                            }
                            return $parts
                        }
                        $pv = Get-VersionParts ([string]$pkg.version)
                        $iv = Get-VersionParts ([string]$inst.version)
                        $pkgVer = ($pv[0] * 10000) + ($pv[1] * 100) + $pv[2]
                        $instVer = ($iv[0] * 10000) + ($iv[1] * 100) + $iv[2]
                        if ($pkgVer -gt $instVer) { $need = $true }          # 包内版本更高 → 重装
                        elseif ($pkgVer -lt $instVer) { $need = $false }     # 本地版本更高 → 跳过，防旧包覆盖
                        else { $need = [long]$inst.publishedAt -lt [long]$pkg.publishedAt }  # 同版本比时间戳
                    }
                }
            } catch { $need = $false } finally { if ($z) { $z.Dispose() } }
        }
        if (-not $need) { Write-Host "  已是最新：$slug"; return }
        # 解压到临时目录 → 校验确实解出了新文件 → 再移动覆盖；
        # 避免解压失败时目标目录旧残留被误报「已安装」（B13-②）
        $tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("dsh-skill-{0}-{1}" -f $slug, [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null
        $installed = $false
        try {
            & 'C:\Windows\System32\tar.exe' -xf $zip -C $tmpRoot
            if ($LASTEXITCODE -ne 0) { try { Expand-Archive -LiteralPath $zip -DestinationPath $tmpRoot -Force -ErrorAction Stop } catch {} }
            $tmpSkill = Join-Path $tmpRoot $slug
            if (Test-Path -LiteralPath (Join-Path $tmpSkill 'SKILL.md')) {
                if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
                Move-Item -LiteralPath $tmpSkill -Destination $dest -Force
                $installed = $true
            }
        } finally {
            Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($installed) {
            Write-Host "  已安装：$slug" -ForegroundColor Green
        } else {
            Write-Host "  !! 安装失败：$slug" -ForegroundColor Yellow
        }
    }
}
Write-Host ''
Write-Host '完成。可用入口：' -ForegroundColor Green
Write-Host "  菜单启动器：$(Join-Path $InstallDir '启动DSH.bat')"
Write-Host "  一键托盘  ：$(Join-Path $InstallDir '启动DSH-托盘.cmd')（已自隐藏窗口）/ $(Join-Path $InstallDir '启动DSH-托盘.vbs')（零窗口，推荐）"
Write-Host '  托盘右键「退出并停止 DSH」可关闭服务。'


