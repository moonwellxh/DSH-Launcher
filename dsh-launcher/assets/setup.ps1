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

# ---------- 探测 ----------
function Find-DshSourceTree {
    # 直接候选：用户目录与各盘根下的 deepseek-harness
    $cands = @((Join-Path $env:USERPROFILE 'deepseek-harness'))
    foreach ($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
        if ($d.Name -match '^[A-Za-z]$') { $cands += (Join-Path $d.Root 'deepseek-harness') }
    }
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
    $n = Get-Command node -ErrorAction SilentlyContinue
    if ($n -and $n.Source) { return $n.Source }
    $wb = Get-ChildItem "$env:USERPROFILE\.workbuddy\binaries\node\versions\*\node.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wb) { return $wb.FullName }
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
    if (-not $dshCmdPath) { $dshCmdPath = $dshPath }
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
    Write-Host '错误：未检测到 DSH 安装。' -ForegroundColor Red
    Write-Host '请确认以下任一成立：'
    Write-Host '  1) dsh 已在 PATH（npm 全局安装）；或'
    Write-Host '  2) 存在 deepseek-harness 源码树（含 apps\cli\lib\bin.js）且有 node。'
    Write-Host '可用 -CheckOnly 查看探测细节。'
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
[System.IO.File]::WriteAllText((Join-Path $scriptDir 'install-dir.txt'), $InstallDir, (New-Object System.Text.UTF8Encoding($false)))

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
    $map = @{ '__DSH_ROOT__' = $dsRoot; '__NODE_EXE__' = $nodeExe }
    $dshCmd  = Render 'dsh.cmd.tmpl' $map
    $trayPs1 = Render-Tray 'source' $map
} else {
    # 禁止回退裸 'dsh'：工作目录含本地 dsh.cmd 时会被劫持导致递归（2026-08-23 事故教训）
    if (-not $dshCmdPath) {
        Write-Host '错误：PATH 模式但无法解析 dsh.cmd 的绝对路径（Get-Command dsh.cmd 失败）。' -ForegroundColor Red
        Write-Host '      为避免裸命令名递归陷阱，中止生成。请检查 PATH 中的 dsh 安装后重试。' -ForegroundColor Red
        exit 1
    }
    $map = @{ '__DSH_CMD__' = $dshCmdPath }
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
    [System.IO.File]::WriteAllBytes($path, ([byte[]](0xEF,0xBB,0xBF)) + $u8.GetBytes($content))
}

Write-Cmd  (Join-Path $InstallDir 'dsh.cmd')     $dshCmd
Write-Ps1  (Join-Path $InstallDir 'DSH-tray.ps1') $trayPs1
Copy-Item  (Join-Path $scriptDir '启动DSH.bat')       (Join-Path $InstallDir '启动DSH.bat')       -Force
Copy-Item  (Join-Path $scriptDir '启动DSH-托盘.cmd')  (Join-Path $InstallDir '启动DSH-托盘.cmd')  -Force
Copy-Item  (Join-Path $scriptDir '启动DSH-托盘.vbs')  (Join-Path $InstallDir '启动DSH-托盘.vbs')  -Force
Copy-Item  (Join-Path $scriptDir 'run-hidden.vbs')    (Join-Path $InstallDir 'run-hidden.vbs')    -Force
Copy-Item  (Join-Path $scriptDir 'tray.ico')          (Join-Path $InstallDir 'tray.ico')          -Force
Copy-Item  (Join-Path $scriptDir 'whale.ico')          (Join-Path $InstallDir 'whale.ico')          -Force
Copy-Item  (Join-Path $scriptDir 'dsh-sync.ps1')      (Join-Path $InstallDir 'dsh-sync.ps1')      -Force
Copy-Item  (Join-Path $scriptDir 'whale-white.png')         (Join-Path $InstallDir 'whale-white.png')         -Force
Copy-Item  (Join-Path $scriptDir 'whale-white.ico')         (Join-Path $InstallDir 'whale-white.ico')         -Force
Step '已生成启动脚本'
# 写入启动器版本（托盘「版本信息」面板显示用）
$metaPath = Join-Path (Join-Path $scriptDir '..') '_meta.json'
try {
    $meta = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
    [System.IO.File]::WriteAllText((Join-Path $InstallDir 'launcher.version'), [string]$meta.version, (New-Object System.Text.UTF8Encoding($false)))
    Step "启动器版本：$($meta.version)"
} catch {
    Write-Host "（警告：读取启动器版本失败：$($_.Exception.Message)）" -ForegroundColor Yellow
}

# ---------- 桌面快捷方式 ----------
if (-not $NoShortcut) {
    try {
        $sh = New-Object -ComObject WScript.Shell
        $desktop = [Environment]::GetFolderPath('Desktop')
        $lnk = $sh.CreateShortcut((Join-Path $desktop '启动DSH.lnk'))
        # 直接指向隐藏 powershell 启动托盘，避免 .cmd 闪烁
        $lnk.TargetPath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
        $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $InstallDir 'DSH-tray.ps1')`" -OpenBrowser"
        $lnk.WorkingDirectory = $InstallDir
        $lnk.IconLocation = (Join-Path $InstallDir 'whale-white.ico')
        $lnk.Save()
        Step '已创建桌面快捷方式 启动DSH.lnk'
        # 附加：若装了 Edge，建 DSH应用.lnk 双击直接打开已安装的 PWA 主应用（聚焦不开多个）
        $edgePath = $null
        foreach ($c in @((Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'), (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'))) {
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
    & $patchEngine -Manifest (Join-Path $scriptDir '补丁管理\自动载入清单-manifest.json')
    # $LASTEXITCODE 陷阱：脚本调用不设该变量（全新进程为 $null）；仅显式非 0 退出码才算失败
    if ($LASTEXITCODE) {
        Write-Host '补丁应用失败，请查看上方输出。' -ForegroundColor Yellow
    }
} else {
    Write-Host '（未找到补丁引擎 assets\补丁管理\补丁引擎-应用还原检查.ps1，跳过补丁步骤）' -ForegroundColor DarkGray
}

# ---------- 配套技能自动安装（zip-archive-ops / batch-files / charset-pitfalls） ----------
$companionDir = Join-Path $scriptDir '配套技能'
if (Test-Path -LiteralPath $companionDir) {
    Step '安装配套技能（zip-archive-ops / batch-files / charset-pitfalls / skill-install-ops）...'
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
            try {
                $z = [System.IO.Compression.ZipFile]::OpenRead($zip)
                $e = $z.Entries | Where-Object { $_.FullName -eq "$slug/_meta.json" }
                $pkg = $null
                if ($e) { $sr = New-Object System.IO.StreamReader($e.Open()); $pkg = $sr.ReadToEnd() | ConvertFrom-Json; $sr.Close() }
                $z.Dispose()
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
            } catch { $need = $false }
        }
        if (-not $need) { Write-Host "  已是最新：$slug"; return }
        & 'C:\Windows\System32\tar.exe' -xf $zip -C $skillsRoot
        if ($LASTEXITCODE -ne 0) { try { Expand-Archive -LiteralPath $zip -DestinationPath $skillsRoot -Force -ErrorAction Stop } catch {} }
        if (Test-Path -LiteralPath (Join-Path $dest 'SKILL.md')) {
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


