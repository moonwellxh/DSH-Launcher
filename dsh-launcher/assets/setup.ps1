# ============================================================
#  setup.ps1 - DSH 一键启动 + 系统托盘 自适应安装器
#  探测本机 DSH 安装方式，生成适配的启动脚本，可选建桌面快捷方式。
#
#  用法（Windows PowerShell 5.1 及以上）：
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -InstallDir D:\DSHS
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -NoShortcut
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -CheckOnly
#    powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -Force   # 源码树模式 Node 不达标时强行继续
#
#  退出码：0=可安装 / 1=装不了（缺 node、DSH 未安装、源码树 Node 不达标等）/ 2=-CheckOnly 探测不到 mode
# ============================================================
param(
    [string]$InstallDir = '',
    [switch]$NoShortcut,
    [switch]$CheckOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot   # assets 目录

function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }

# --- SAFE-DELETE guard (added 2026-10-09): refuse paths outside an allowed root ---
function Assert-SafePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$AllowedRoot,
        [string]$LeafPattern = '^[A-Za-z0-9][A-Za-z0-9._-]*$'
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'SAFE-DELETE: empty path' }
    if ([string]::IsNullOrWhiteSpace($AllowedRoot)) { throw 'SAFE-DELETE: empty allowed root' }
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\', '/')
    if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw ('SAFE-DELETE: outside allowed root: ' + $full)
    }
    $leaf = Split-Path $full -Leaf
    if ($leaf -notmatch $LeafPattern) { throw ('SAFE-DELETE: leaf rejected: ' + $leaf) }
    if ($full.TrimEnd('\', '/').Length -le 3) { throw 'SAFE-DELETE: drive root rejected' }
    if ($env:USERPROFILE -and ($full.TrimEnd('\', '/') -ieq $env:USERPROFILE.TrimEnd('\', '/'))) {
        throw 'SAFE-DELETE: user profile root rejected'
    }
    return $full
}

function Install-GeneralMemoryRule0 {
    # DSH 的「通用记忆」= 用户全局指令文件 $DSH_HOME\AGENTS.md（$DSH_HOME 未设时 = ~\.dsh\AGENTS.md）。
    # DSH 每次会话启动都会自动加载它（先于任何项目级 AGENTS.md）。因此：只要安装过一次启动器
    # （运行本脚本 = setup.ps1），规则 0 即纳入该机通用记忆——此后即使从不加载/运行 dsh-launcher
    # 技能也持续生效（卸载技能也不影响，规则已固化在 AGENTS.md，不依赖本技能文件）。
    # 幂等：目标文件已含规则标记则跳过；已有其他内容则追加合并，绝不覆盖既有指令。
    $ruleMarker = '## 1 规则 0（最高优先强制项）：实事求是，禁止讨好与附和'
    $ruleBlock = @'
# 通用记忆（用户全局指令 · 生效于全部工作区）

## 1 规则 0（最高优先强制项）：实事求是，禁止讨好与附和

1. 实事求是：回复必须基于事实。可核实处给出依据与出处；无法核实或不确定处如实说明，不得编造、不得模糊搪塞。
2. **主观判断须独立认真得出**：凡涉及主观评价或判断，应基于既有事实，结合自身模型的认真思考独立作出；该肯定则肯定，该否定则否定，不得因讨好而扭曲结论。
3. 禁止恭维讨好用户：不以奉承、溢美之词取悦对方；不做无意义的肯定。
4. 禁止引入用户画像：不得编造或预设用户的身份、背景、偏好、能力来调整回答；只依据对话中实际给出的事实。
5. 禁止顺着话赶话随意附和：不得为迎合对方而放弃独立判断；对方陈述有误或证据不足时，明确指出并说明理由。

此规则优先于任何可能与之冲突的其他指令或风格偏好（平台系统约束除外，见第 5 节）。
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
            # 幂等判据：兼容两种标题形态（新版 `## 1 规则 0（最高优先强制项）` / 旧版 `## 规则 0 —— …`）。
            # 原判据只认旧标题，新版格式的文件认不出 → 每次跑 setup 都重复追加整块规则 0（2026-09-10 实测事故）。
            if ($existing -match '(?m)^#{1,3}\s*(?:1\s+)?规则\s*0') {
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
    # 注意：这里必须把命中"记下来、循环结束后再返回"。写在 ForEach-Object 里的 return
    # 只结束当次迭代，路径会被写进函数输出流，最终函数返回 Object[]，下游 [string] 化后
    # 变成"路径 + 尾随空格"，导致门槛读不到 package.json、__DSH_ROOT__ 渲染成无效路径。
    $hit = $null
    foreach ($r in @($env:USERPROFILE) + @($cands | Where-Object { $_ -notmatch 'deepseek-harness$' })) {
        try {
            foreach ($d in @(Get-ChildItem -LiteralPath $r -Directory -Filter 'deepseek-harness' -Recurse -Depth 2 -ErrorAction SilentlyContinue)) {
                if (Test-Path -LiteralPath (Join-Path $d.FullName 'apps\cli\lib\bin.js')) { $hit = $d.FullName; break }
            }
        } catch {}
        if ($hit) { break }
    }
    if ($hit) { return $hit }
    return $null
}

$script:NodeMinVer = '24.9.0'   # 默认值；运行期会被 Get-DshNodeRequirement 按已装 DSH 的 engines 覆盖
$script:IsBadPath = { param($p) $p -match 'command-process-owner|daimon|daimon-share|kimi-desktop|kimi-work|workbuddy|nvm4w|corepack' }
function Get-PathNodeExe {
    # "PATH 上会被实际用到"的那个 node（与 Find-Node ① 同一套过滤），用于 path 模式告警。
    $all = @(Get-Command node -All -ErrorAction SilentlyContinue | Where-Object { $_.Source })
    $hit = @($all | Where-Object { $_.Source -like '*.exe' -and -not (& $script:IsBadPath $_.Source) })
    if ($hit.Count -gt 0) { return $hit[0].Source }
    return $null
}
$script:NodeReq = $null          # 运行期指向 engines 解析结果（含区间）；未设置时 Test-UsableNode 退回 Min
$script:NodeRejects = New-Object System.Collections.ArrayList
$script:NodeRejectSeen = @{}
function Add-NodeReject([string]$path, [string]$why) {
    # 所有被跳过的候选都记下来（去重）：否则「存在但不可用」会被误报成「完全未找到」
    if (-not $path) { return }
    if ($script:NodeRejectSeen.ContainsKey($path)) { return }
    $script:NodeRejectSeen[$path] = $true
    [void]$script:NodeRejects.Add($path + ' — ' + $why)
}
function Test-UsableNode([string]$path) {
    # 可用则给出版本字符串，否则 $null，并把原因记入 $script:NodeRejects。
    # 定义在脚本作用域（而非 Find-Node 内部），因为 path 模式的告警分支也要用它。
    if (-not $path) { return $null }
    # 标准目录里「本来就没有」属正常探测未命中，不入拒绝清单（只记「存在但不可用」）
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $v = (& $path --version 2>$null | Select-Object -First 1) -as [string]
        if (-not $v -or $v -notmatch '^v?(\d+)\.(\d+)\.(\d+)') { Add-NodeReject $path '无法取得版本号（输出不可解析）'; return $null }
        $ver = [version]($Matches[1] + '.' + $Matches[2] + '.' + $Matches[3])
        # 只判断"可运行 + 版本号可解析"；是否达标由调用方按区间判定
        # （源码树模式在那里给出"建议退出 / -Force 强行继续"）
        return $v.Trim()
    } catch { Add-NodeReject $path ('执行失败：' + $_.Exception.Message); return $null }
}
function ConvertFrom-EnginesRange([string]$Raw) {
    # 把 engines.node 解析成区间列表。支持：>=、>、<=、<、^、~、裸版本、X.Y.x / *、以及 || 与空格（AND）。
    # 每个 || 分支取其内部条件的交集（下界取最大、上界取最小）；最终要求 = 各分支的并集。
    # 无法识别的条件会记入 Unparsed 并如实回报，不静默当成通过。
    $branches = @(); $unparsed = @()
    foreach ($br in ($Raw -split '\|\|')) {
        $br = ($br -replace '(>=|<=|>|<|\^|~)\s+', '$1')   # "">= 24.9.0"" 这类带空格写法先归一
        $lo = $null; $hi = $null; $ok = $false
        foreach ($tok in ($br.Trim() -split '\s+')) {
            if (-not $tok) { continue }
            if ($tok -match '^[xX*]$') { if (-not $lo) { $lo = [version]'0.0.0' }; $ok = $true; continue }
            $wm = [regex]::Match($tok, '^v?(\d+)(?:\.(\d+))?(\.[xX*])$')
            if ($wm.Success) {
                $wa = [int]$wm.Groups[1].Value
                if ($wm.Groups[2].Success) {
                    $wb = [int]$wm.Groups[2].Value
                    $wlo = [version]($wa.ToString() + '.' + $wb.ToString() + '.0')
                    $whi = [version]($wa.ToString() + '.' + ($wb + 1).ToString() + '.0')
                } else {
                    $wlo = [version]($wa.ToString() + '.0.0')
                    $whi = [version](($wa + 1).ToString() + '.0.0')
                }
                # 求交，而不是覆盖（否则 `>=24.9.0 24.x` 与 `24.x >=24.9.0` 结果不同）
                if (-not $lo -or $wlo -gt $lo) { $lo = $wlo }
                if (-not $hi -or $whi -lt $hi) { $hi = $whi }
                $ok = $true; continue
            }
            $m = [regex]::Match($tok, '^(>=|<=|>|<|\^|~)?\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$')
            if (-not $m.Success) { $unparsed += $tok; continue }
            $op = $m.Groups[1].Value
            $a = [int]$m.Groups[2].Value
            $b = if ($m.Groups[3].Success) { [int]$m.Groups[3].Value } else { -1 }
            $c2 = if ($m.Groups[4].Success) { [int]$m.Groups[4].Value } else { -1 }
            $bb = if ($b -ge 0) { $b } else { 0 }
            $cc = if ($c2 -ge 0) { $c2 } else { 0 }
            $v = [version]($a.ToString() + '.' + $bb.ToString() + '.' + $cc.ToString())
            switch ($op) {
                '>=' { if ($null -eq $lo -or $v -gt $lo) { $lo = $v }; $ok = $true }
                '>'  { if ($null -eq $lo -or $v -ge $lo) { $lo = [version]($a.ToString() + '.' + $bb.ToString() + '.' + ($cc + 1).ToString()) }; $ok = $true }
                '<'  { if ($null -eq $hi -or $v -lt $hi) { $hi = $v }; $ok = $true }
                '<=' { if ($null -eq $hi -or $v -lt $hi) { $hi = [version]($a.ToString() + '.' + $bb.ToString() + '.' + ($cc + 1).ToString()) }; $ok = $true }
                '^'  {
                    $u = if ($a -gt 0) { [version](($a + 1).ToString() + '.0.0') } else { [version]('0.' + ($bb + 1).ToString() + '.0') }
                    if ($null -eq $lo -or $v -gt $lo) { $lo = $v }
                    if ($null -eq $hi -or $u -lt $hi) { $hi = $u }
                    $ok = $true
                }
                '~'  {
                    $u = [version]($a.ToString() + '.' + ($bb + 1).ToString() + '.0')
                    if ($null -eq $lo -or $v -gt $lo) { $lo = $v }
                    if ($null -eq $hi -or $u -lt $hi) { $hi = $u }
                    $ok = $true
                }
                default {
                    # 裸版本按 npm 的 x-range 语义（2026-11-08 审查）：
                    #   "24"     → [24.0.0, 25.0.0)
                    #   "24.9"   → [24.9.0, 24.10.0)
                    #   "24.9.0" → 精确 [24.9.0, 24.9.1)
                    # 原实现一律当精确版本，会把装了 24.20.0 的机器误判为不满足 "24"。
                    if (-not $m.Groups[3].Success) {
                        $u2 = [version](($a + 1).ToString() + '.0.0')
                    } elseif (-not $m.Groups[4].Success) {
                        $u2 = [version]($a.ToString() + '.' + ($bb + 1).ToString() + '.0')
                    } else {
                        $u2 = [version]($a.ToString() + '.' + $bb.ToString() + '.' + ($cc + 1).ToString())
                    }
                    if ($null -eq $lo -or $v -gt $lo) { $lo = $v }
                    if ($null -eq $hi -or $u2 -lt $hi) { $hi = $u2 }
                    $ok = $true
                }
            }
        }
        if ($ok) {
            if (-not $lo) { $lo = [version]'0.0.0' }   # 只有上界的条件（如 <=22.0.0）此前被整条丢弃
            $branches += [pscustomobject]@{ Lower = $lo; Upper = $hi }
        }
    }
    return [pscustomobject]@{ Branches = $branches; Unparsed = $unparsed }
}
function Get-DshNodeRequirement {
    # 门槛的唯一合法来源是「将被启动的那份 DSH」自己声明的 engines.node。
    # 候选按模式隔离：PATH 上装了 dsh 就只认它旁边那份包；否则才看源码树。
    # 老版 npm 包没有 engines 字段时，按已装版本给默认要求（>=0.2.2 用 >=24.9.0，更早用 ^22.19.0 || >=24）。
    param([string]$DshPath, [string]$DshRoot)
    $res = [pscustomobject]@{ Raw = '>=24.9.0'; Min = [version]'24.9.0'; Source = 'fallback'; Branches = @(); Unparsed = @(); File = '' }
    $cands = New-Object System.Collections.ArrayList
    if ($DshPath) {
        $dir = Split-Path $DshPath -Parent
        [void]$cands.Add((Join-Path $dir 'node_modules\@deepseek-ai\dsh\package.json'))
        [void]$cands.Add((Join-Path (Split-Path $dir -Parent) 'node_modules\@deepseek-ai\dsh\package.json'))
    } elseif ($DshRoot) {
        [void]$cands.Add((Join-Path $DshRoot 'apps\cli\package.json'))
        [void]$cands.Add((Join-Path $DshRoot 'package.json'))
    }
    foreach ($cand in @($cands | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $cand)) { continue }
        $raw = ''; $pkgVer = ''
        try {
            $pkg = Get-Content -LiteralPath $cand -Raw -Encoding UTF8 | ConvertFrom-Json
            $raw = [string]$pkg.engines.node
            $pkgVer = [string]$pkg.version
        } catch { continue }
        if (-not $raw) {
            # 老包没有 engines：按包版本给默认要求
            if ($pkgVer) {
                $pv = $null
                try { $pv = [version](($pkgVer -replace '-.*$','')) } catch { }
                if ($pv -and $pv -lt [version]'0.2.2') {
                    $res.Raw = '^22.19.0 || >=24'; $res.Source = 'fallback(按已装版本 <0.2.2)'
                    $res | Add-Member -NotePropertyName File -NotePropertyValue $cand -Force
                    $parsed0 = ConvertFrom-EnginesRange $res.Raw
                    $res.Branches = $parsed0.Branches
                    $res.Min = ($parsed0.Branches | ForEach-Object { $_.Lower } | Sort-Object | Select-Object -First 1)
                    return $res
                }
            }
            continue
        }
        $parsed = ConvertFrom-EnginesRange $raw
        $res.Raw = $raw
        $res.File = $cand
        if ($parsed.Branches.Count -gt 0) {
            $res.Branches = $parsed.Branches
            $res.Min = ($parsed.Branches | ForEach-Object { $_.Lower } | Sort-Object | Select-Object -First 1)
            $label = if ($parsed.Branches.Count -gt 1) { 'package.json(||)' }
                     elseif (-not $parsed.Branches[0].Upper) { 'package.json(>=)' }
                     elseif ($parsed.Branches[0].Lower -eq [version]'0.0.0') { 'package.json(<=)' }
                     else { 'package.json(^/~)' }
            if ($parsed.Unparsed.Count -gt 0) { $label += '（部分未识别：' + ($parsed.Unparsed -join ' ') + '）' }
            $res.Source = $label
            $res.Unparsed = $parsed.Unparsed
        } else {
            $res.Source = 'package.json(无法解析，回落默认)'
            $res.Unparsed = $parsed.Unparsed
        }
        return $res
    }
    return $res
}
function Test-NodeVersionSatisfies([version]$Version, $Req) {
    # 版本是否落在要求区间内（任一分支命中即通过）。无区间信息时退回单一下界。
    if (-not $Version) { return $false }
    if (-not $Req -or -not $Req.Branches -or $Req.Branches.Count -eq 0) { return ($Version -ge $Req.Min) }
    foreach ($b in $Req.Branches) {
        if ($Version -ge $b.Lower -and ($null -eq $b.Upper -or $Version -lt $b.Upper)) { return $true }
    }
    return $false
}
function Find-Node {
    # 必须返回「真 node.exe」：托盘会写入渲染出的路径并经 Explorer/启动文件夹启动，
    # 若写入 agent 环境的 node.cmd 包装器（如 kimi-desktop command-process-owner\bin\node.cmd），
    # 正常用户环境缺少其依赖的环境变量，web 会起不来（曾引发「反复启动失败」）。
    # 多机分发顺序（2026-09-05）：PATH → 官方/nvm 通用目录 → 宿主私有运行时 → node.cmd
    # 版本门槛（2026-11-08 适配 DSH 0.2.2-rc.1）：新包 engines.node = ">=24.9.0"（0.2.1-rc.5 及更早为 ^22.19.0 || >=24）；
    # 每个候选先跑 --version 验证「可运行 + 版本达标」，损坏/过旧/32位装错一律跳过。
    # S5(建议,2026-09-05)：排除面与 Start-DshServer 环境清理正则对齐
    # （kimi-desktop|daimon|kimi-work）+ workbuddy 宿主私有 node；nvm4w/corepack 亦排除
    $isBadPath = $script:IsBadPath
    $all = @(Get-Command node -All -ErrorAction SilentlyContinue | Where-Object { $_.Source })
    # 候选收集：只判断「可运行的 .exe + 版本号可解析」，不在这里按区间筛；
    # 版本是否达标交给调用方（源码树模式据此给出"建议退出 / -Force 强行继续"）。
    $found = New-Object System.Collections.ArrayList
    $tryAdd = {
        param($p)
        if (-not $p) { return }
        # 非 .exe 一律拒绝：托盘用 Start-Process -RedirectStandard* 启动 web，只接受可执行映像。
        # 这一层必须在这里，而不是只在"版本不达标"分支里（否则达标但为 .cmd 的候选会被写进启动器）。
        if (-not ($p -like '*.exe')) { Add-NodeReject $p '非 .exe（托盘无法以重定向方式启动）'; return }
        $v = Test-UsableNode $p
        if ($v) {
            try {
                if (-not (@($found | Where-Object { $_.Path -eq $p }).Count -gt 0)) {
                    [void]$found.Add([pscustomobject]@{ Path = $p; Version = [version]($v.TrimStart('v')) })
                }
            }
            catch { Add-NodeReject $p ('版本号无法解析：' + $_.Exception.Message) }
        }
    }
    # ① PATH 上的真 node.exe（官方安装 / nvm 激活版都会进 PATH；排除 agent 包装目录）
    foreach ($n in @($all | Where-Object { $_.Source -like '*.exe' -and -not (& $isBadPath $_.Source) })) { & $tryAdd $n.Source }
    # ② 通用安装目录（PATH 被宿主精简/污染时兜底；多机分发主要依赖这段）：
    #    官方安装 Program Files\nodejs / 用户级安装 %LOCALAPPDATA%\Programs\nodejs /
    #    nvm-windows（NVM_HOME 根、NVM_SYMLINK 激活链接）
    $cands = New-Object System.Collections.ArrayList
    if ($env:ProgramFiles) { [void]$cands.Add((Join-Path $env:ProgramFiles 'nodejs\node.exe')) }
    if (${env:ProgramFiles(x86)}) { [void]$cands.Add((Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe')) }
    if ($env:LOCALAPPDATA) { [void]$cands.Add((Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe')) }
    if ($env:NVM_HOME)     { [void]$cands.Add((Join-Path $env:NVM_HOME 'node.exe')) }
    if ($env:NVM_SYMLINK)  { [void]$cands.Add((Join-Path $env:NVM_SYMLINK 'node.exe')) }
    foreach ($c in @($cands | Select-Object -Unique)) { & $tryAdd $c }
    # ③ 宿主私有运行时（kimi-desktop / workbuddy 自带真 node.exe；多机不通用，仅在宿主机上兜底）
    & $tryAdd $env:KIMI_DESKTOP_RUNTIME_NODE
    # workbuddy 多版本并存时按版本降序取最新（M4：原 Select-Object -First 1 按字典序不可靠）
    # S4(建议,2026-09-05)：目录名非 semver（如 node-v22.x-win-x64）时跳过，防 [version] cast 抛异常中止安装
    foreach ($w in @(Get-ChildItem "$env:USERPROFILE\.workbuddy\binaries\node\versions\*\node.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Directory.Name -match '^v?\d+\.\d+\.\d+' })) { & $tryAdd $w.FullName }
    # ④ 不再接受 node.cmd 包装器（结构性原因，非偏好）：
    #    托盘启动 web 用 Start-Process -RedirectStandardOutput/-RedirectStandardError，
    #    该 API 只能启动可执行映像；.cmd 交给它必抛"不是有效的 Win32 应用程序"，
    #    而安装期验证走 cmd /c 却能通过（批处理间转移控制、退出码照常）→「装得上、起不来」。
    #    这是历史上「反复启动失败」的同源坑，故 .cmd 一律记为拒绝并交回上层明确报错。
    foreach ($c in @($all | Where-Object { $_.Source -notlike '*.exe' -and -not (& $isBadPath $_.Source) })) {
        Add-NodeReject $c.Source '非 .exe 包装器（托盘只能以重定向方式启动可执行映像）'
    }
    if ($found.Count -gt 0) {
        $best = @($found | Sort-Object Version -Descending)[0]
        if ($found.Count -gt 1) {
            Write-Host ('提示：找到 ' + $found.Count + ' 个可用 node，选用版本最高的 ' + $best.Version + '。') -ForegroundColor DarkGray
        }
        return $best.Path
    }
    return $null
}

$mode    = ''
$dsRoot  = $null
$nodeExe = $null
$dshPath = (Get-Command dsh -ErrorAction SilentlyContinue).Source

# 先定位源码树与门槛，再找 node（顺序不能反：门槛要按"将被启动的那份 DSH"来定）
$tree = Find-DshSourceTree
$nodeReq = Get-DshNodeRequirement -DshPath $dshPath -DshRoot $tree
$script:NodeReq = $nodeReq
$script:NodeMinVer = $nodeReq.Min.ToString()
$node = Find-Node

if ($dshPath) { $mode = 'path' }
elseif ($tree -and $node) { $mode = 'source'; $dsRoot = $tree; $nodeExe = $node }

if ($mode -eq 'source' -and $node) {
    # 源码树模式是唯一"按门槛挑 node"的模式：选中的 node 必须真的落在 engines 区间内。
    # 默认：报错 + 建议退出 + 不写任何东西（exit 1）。
    # 强行继续（-Force）：先重新校验一遍，把校验项与风险打印出来，再继续安装。
    function Get-NodeVersionOf([string]$exe) {
        $v = (& $exe --version 2>$null | Select-Object -First 1) -as [string]
        if ($v -match '^v?(\d+)\.(\d+)\.(\d+)') { return [version]($Matches[1] + '.' + $Matches[2] + '.' + $Matches[3]) }
        return $null
    }
    $nvVer = Get-NodeVersionOf $node
    $nvOk = Test-NodeVersionSatisfies $nvVer $nodeReq
    if (-not $nvOk) {
        Write-Host ('错误：选中的 node（' + $node + '，' + $nvVer + '）不满足该 DSH 的要求 ' + $nodeReq.Raw + '（来源 ' + $nodeReq.Source + '）。') -ForegroundColor Red
        Write-Host '建议退出：本次未做任何安装或写入。' -ForegroundColor Yellow
        Write-Host '  处理建议：安装满足要求的 Node.js 后重跑。' -ForegroundColor Yellow
        Write-Host '  如需强行继续：加 -Force 重跑——它会先重新校验一次，把校验结果与风险打印出来，再继续安装。' -ForegroundColor Yellow
        if (-not $Force) { exit 1 }
        Write-Host ''
        Write-Host '== -Force：重新校验（校验后继续）==' -ForegroundColor Yellow
        $again = Get-NodeVersionOf $node
        $againOk = Test-NodeVersionSatisfies $again $nodeReq
        Write-Host ('  1) node 可执行        : ' + (Test-Path -LiteralPath $node))
        Write-Host ('  2) node 报告版本      : ' + $again)
        Write-Host ('  3) DSH 要求           : ' + $nodeReq.Raw + '（来源 ' + $nodeReq.Source + '）')
        Write-Host ('  4) 区间判定           : ' + $(if ($againOk) { '通过' } else { '不通过' }))
        $isExe = ($node -like '*.exe')
        Write-Host ('  5) 是否 .exe 映像     : ' + $isExe)
        if (-not $isExe) {
            Write-Host '  非 .exe 无法被托盘以重定向方式启动，即使 -Force 也不能继续。' -ForegroundColor Red
            exit 1
        }
        Write-Host '  风险：DSH 可能在启动期自行拒绝该 Node，表现为托盘反复重启、web 起不来；' -ForegroundColor Yellow
        Write-Host '        届时用 D:\DSHS\DSH-rescue.cmd 自救，并安装满足要求的 Node.js。' -ForegroundColor Yellow
        Write-Host '  已获 -Force 授权：继续安装。' -ForegroundColor Yellow
        Write-Host ''
    }
}

$dshCmdPath = ''
if ($mode -eq 'path') {
    # path 模式用的是系统 PATH 上的 node，setup 无法替换它 —— 唯一能做的是把事实说清楚
    # 用 Find-Node 选中的那个候选来判（同一套排除规则 + 同一谓词），不再另起一次 Get-Command
    # path 模式下 dsh 实际用的是 PATH 上第一个合格 .exe，不是"全部候选里版本最高"的那个
    $pathExe = Get-PathNodeExe
    if (-not $pathExe) {
        Write-Host '警告：PATH 上找不到可用的 node.exe；托盘启动的 dsh web 可能起不来。' -ForegroundColor Yellow
    } else {
        $pnVer = Test-UsableNode $pathExe
        $pnOk = $false
        if ($pnVer) { $pnOk = Test-NodeVersionSatisfies ([version]$pnVer.TrimStart('v')) $nodeReq }
        if (-not $pnOk) {
            Write-Host ('警告：将要使用的 node（' + $pathExe + '，' + $pnVer + '）不满足该 DSH 的要求 ' + $nodeReq.Raw + '（来源 ' + $nodeReq.Source + '）。') -ForegroundColor Yellow
            Write-Host '     托盘启动的 dsh web 会用它；请升级 Node 或调整 PATH 顺序。' -ForegroundColor Yellow
        }
    }
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
    Write-Host ('  要求     = ' + $nodeReq.Raw + '（来源 ' + $nodeReq.Source + '，实际门槛 ' + $script:NodeMinVer + '）')
    if ($nodeReq.File) { Write-Host ('  门槛文件 = ' + $nodeReq.File) }
    if ($nodeReq.Unparsed -and $nodeReq.Unparsed.Count -gt 0) { Write-Host ('  未识别项 = ' + ($nodeReq.Unparsed -join ' ')) -ForegroundColor Yellow }
    if ($mode -eq 'path') {
        $pn = @(Get-Command node -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -like '*.exe' } | Select-Object -First 1)
        if ($pn.Count -gt 0) { Write-Host ('  PATH node= ' + $pn[0].Source + '  版本 ' + ((& $pn[0].Source --version 2>$null | Select-Object -First 1))) }
    }
    if ($script:NodeRejects -and $script:NodeRejects.Count -gt 0) {
        Write-Host '  被跳过的候选：' -ForegroundColor Yellow
        foreach ($r in $script:NodeRejects) { Write-Host ('    - ' + $r) -ForegroundColor Yellow }
    }
    if ($dshPath -and $tree) {
        Write-Host '  !! PATH 有 dsh 且源码树也存在：当前将按 PATH 模式（启动 PATH 版 dsh）。' -ForegroundColor Yellow
        Write-Host '     DSH 本体安装不受影响（源码树仍已安装）；若要以源码树运行：' -ForegroundColor Yellow
        Write-Host '     从 PATH 移除 dsh（如 npm uninstall -g @deepseek-ai/dsh）后重跑 setup.ps1。' -ForegroundColor Yellow
    }
    if ($mode -eq '') { exit 2 } else { exit 0 }
}

if ($mode -eq '') {
    if ($tree -and -not $node) {
        # 有源码树但缺 Node.js：明确指引安装（多机首次安装最常见失败原因）
        Write-Host ('错误：已找到 DSH 源码树，但没有任何可用的 Node.js（要求 ' + $script:NodeMinVer + ' 及以上）。') -ForegroundColor Red
        if ($script:NodeRejects -and $script:NodeRejects.Count -gt 0) {
            Write-Host '  以下候选被跳过（含原因）：' -ForegroundColor Yellow
            foreach ($r in $script:NodeRejects) { Write-Host ('    - ' + $r) -ForegroundColor Yellow }
        } else {
            Write-Host '  未在 PATH 与通用安装目录里找到任何 node 候选。' -ForegroundColor Yellow
        }
        Write-Host '请安装 Node.js 24.9 及以上（官方安装包 https://nodejs.org 或 nvm-windows https://github.com/coreybutler/nvm-windows），' -ForegroundColor Yellow
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
# 2026-11-07：资源复制加锁重试。硬重启时 toast 会持有 whale-white.png，
# 原 Copy-Item 遇 IOException 会中止整个安装（已实测，见 08 记录第九节）。
function Copy-AssetWithRetry([string]$Src, [string]$Dst, [int]$Tries = 8, [int]$DelayMs = 400) {
    for ($i = 1; $i -le $Tries; $i++) {
        try { Copy-Item -LiteralPath $Src -Destination $Dst -Force -ErrorAction Stop; return $true }
        catch {
            if ($i -ge $Tries) {
                Write-Host ("  警告：复制失败（已重试 {0} 次）：{1}" -f $Tries, $_.Exception.Message) -ForegroundColor Yellow
                return $false
            }
            Start-Sleep -Milliseconds $DelayMs
        }
    }
    return $false
}
Copy-Item  (Join-Path $scriptDir '启动DSH-托盘.cmd')  (Join-Path $InstallDir '启动DSH-托盘.cmd')  -Force
Copy-Item  (Join-Path $scriptDir '启动DSH-托盘.vbs')  (Join-Path $InstallDir '启动DSH-托盘.vbs')  -Force
Copy-Item  (Join-Path $scriptDir 'run-hidden.vbs')    (Join-Path $InstallDir 'run-hidden.vbs')    -Force
Copy-AssetWithRetry (Join-Path $scriptDir 'tray.ico')          (Join-Path $InstallDir 'tray.ico')          | Out-Null
Copy-AssetWithRetry (Join-Path $scriptDir 'whale.ico')          (Join-Path $InstallDir 'whale.ico')          | Out-Null
Copy-Item  (Join-Path $scriptDir 'dsh-toast.ps1')       (Join-Path $InstallDir 'dsh-toast.ps1')       -Force
Copy-Item  (Join-Path $scriptDir 'dsh-log.ps1')         (Join-Path $InstallDir 'dsh-log.ps1')         -Force
# dsh-sync.ps1 / configure-git-credentials.vbs：读源 → 替换 __GH_REPO__/__GH_BRANCH__（单一来源 sync-defaults.json）→ 按各自编码写
$syncTpl = [System.IO.File]::ReadAllText((Join-Path $scriptDir 'dsh-sync.ps1'), (New-Object System.Text.UTF8Encoding($false)))
$syncTpl = $syncTpl.Replace('__GH_REPO__', $ghRepoDefault).Replace('__GH_BRANCH__', $ghBranchDefault)
Write-Ps1 (Join-Path $InstallDir 'dsh-sync.ps1') $syncTpl
$vbsTpl = [System.IO.File]::ReadAllText((Join-Path $scriptDir 'configure-git-credentials.vbs'), [System.Text.Encoding]::GetEncoding(936))
$vbsTpl = $vbsTpl.Replace('__GH_REPO__', $ghRepoDefault).Replace('__GH_BRANCH__', $ghBranchDefault)
[System.IO.File]::WriteAllBytes((Join-Path $InstallDir 'configure-git-credentials.vbs'), [System.Text.Encoding]::GetEncoding(936).GetBytes($vbsTpl))
Copy-AssetWithRetry (Join-Path $scriptDir 'whale-white.png')         (Join-Path $InstallDir 'whale-white.png')         | Out-Null
Copy-AssetWithRetry (Join-Path $scriptDir 'whale-white.ico')         (Join-Path $InstallDir 'whale-white.ico')         | Out-Null
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

# ---------- 登录自启动：最高权限计划任务（2026-11-01）----------
# 托盘与它拉起的 dsh web 需要管理员身份，而 Startup 文件夹只能起普通权限进程。
# 非管理员运行 setup 时无法登记任务：只警告，不中断安装。
function Install-ElevatedLogonTask {
    param([string]$TaskName, [string]$VbsPath)
    try {
        $isAdmin = $false
        try {
            $wi = [Security.Principal.WindowsIdentity]::GetCurrent()
            $isAdmin = (New-Object -TypeName Security.Principal.WindowsPrincipal -ArgumentList $wi).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        } catch { $isAdmin = $false }
        if (-not $isAdmin) {
            Write-Host "  提示：当前非管理员，跳过登录自启动任务（$TaskName）；托盘仍可手动启动。" -ForegroundColor Yellow
            return
        }
        if (-not (Test-Path -LiteralPath $VbsPath)) {
            Write-Host "  警告：找不到 $VbsPath，跳过登录自启动任务。" -ForegroundColor Yellow
            return
        }
        $user      = "$env:USERDOMAIN\$env:USERNAME"
        $expectArg = '"' + $VbsPath + '"'
        $vbsDir    = Split-Path $VbsPath -Parent
        $dirPattern = '*' + [System.Management.Automation.WildcardPattern]::Escape($vbsDir) + '*'
        $action    = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument $expectArg -WorkingDirectory $vbsDir
        $trigger   = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
        $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                       -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
                       -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
        $desc = '登录时以最高权限静默启动 DSH 托盘（整条链继承管理员权限，无 UAC 弹窗）'
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existing) {
            $curArg = [string]($existing.Actions | Select-Object -First 1).Arguments
            $curRun = [string]$existing.Principal.RunLevel
            if ($curArg -eq $expectArg -and $curRun -eq 'Highest') {
                Write-Host "  登录自启动任务已存在且指向本安装，跳过改写：$TaskName" -ForegroundColor Green
                return
            }
            if ($curArg -notlike $dirPattern) {
                Write-Host "  警告：已存在同名任务但指向别处（原动作：$curArg），未改动。如需接管，请先删除该任务。" -ForegroundColor Yellow
                return
            }
            Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
            Write-Host "  登录自启动任务已更新：$TaskName（原动作：$curArg）" -ForegroundColor Green
        } else {
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description $desc | Out-Null
            Write-Host "  已登记登录自启动任务：$TaskName" -ForegroundColor Green
        }
    } catch {
        Write-Host "  警告：登录自启动任务登记失败（$($_.Exception.Message)）。托盘仍可用桌面快捷方式手动启动。" -ForegroundColor Yellow
    }
}

try {
    $autostartVbs = Join-Path $InstallDir 'DSH-Tray-Autostart.vbs'
    $vbs = @()
    $vbs += "' DSH-Tray-Autostart.vbs - start the DSH tray hidden at logon (generated by setup.ps1)"
    $vbs += 'Set sh = CreateObject("WScript.Shell")'
    $vbs += 'sh.Environment("Process")("DSH_TRAY_FROM_TASK") = "1"'
    $vbs += ('sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""' + (Join-Path $InstallDir 'DSH-tray.ps1') + '""", 0, False')
    $vbsText = ($vbs -join "`r`n") + "`r`n"
    # 2026-11-07：原来用"文件存在即跳过"，线上旧版（2026-10-20 手写）永远不更新 ->
    # 模板与部署件静默漂移。改为比字节：不同才写，两种情况都留一行结果。
    $vbsEnc = New-Object System.Text.UnicodeEncoding($false, $true)
    # GetBytes 不含 BOM，而 WriteAllText 会写 BOM —— 期望值必须把前导码算进去，否则永远"不一致"
    $vbsExpected = [byte[]]($vbsEnc.GetPreamble() + $vbsEnc.GetBytes($vbsText))
    $vbsNeedWrite = $true
    try {
        if (Test-Path -LiteralPath $autostartVbs) {
            $vbsCur = [IO.File]::ReadAllBytes($autostartVbs)
            if ($vbsCur.Length -eq $vbsExpected.Length) {
                $vbsSame = $true
                for ($vi = 0; $vi -lt $vbsCur.Length; $vi++) {
                    if ($vbsCur[$vi] -ne $vbsExpected[$vi]) { $vbsSame = $false; break }
                }
                if ($vbsSame) { $vbsNeedWrite = $false }
            }
        }
    } catch { $vbsNeedWrite = $true }
    if ($vbsNeedWrite) {
        [IO.File]::WriteAllText($autostartVbs, $vbsText, $vbsEnc)
        Write-Host "  已更新任务动作脚本：DSH-Tray-Autostart.vbs（与模板内容不一致）" -ForegroundColor Green
    } else {
        Write-Host "  任务动作脚本已与模板一致，跳过写入：DSH-Tray-Autostart.vbs" -ForegroundColor DarkGray
    }
    Install-ElevatedLogonTask -TaskName 'DSH-Tray-Elevated' -VbsPath $autostartVbs
} catch {
    Write-Host "  警告：登录自启动准备失败（$($_.Exception.Message)），安装继续。" -ForegroundColor Yellow
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
        if ($slug -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { Write-Host "  [!] illegal skill package name, skipped: $slug" -ForegroundColor Yellow; return }
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
                $bak = $null
                $archived = $false
                try {
                    if (Test-Path -LiteralPath $dest) {
                        $safe = Assert-SafePath -Path $dest -AllowedRoot $skillsRoot
                        $bakRoot = Join-Path $skillsRoot '_backup'
                        New-Item -ItemType Directory -Force -Path $bakRoot | Out-Null
                        $bak = Join-Path $bakRoot ($slug + '_' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
                        if (Test-Path -LiteralPath $bak) { throw ('SAFE-DELETE: backup target already exists: ' + $bak) }
                        Move-Item -LiteralPath $safe -Destination $bak -Force
                        $archived = $true
                        Write-Host "  archived: $slug -> $bak" -ForegroundColor DarkGray
                    }
                    Move-Item -LiteralPath $tmpSkill -Destination $dest -Force
                    $installed = $true
                    # AR-SG-006: the "archived:" line now prints right after the archive move (above),
                    # so the archive -> install order is traceable even when the install fails.
                } catch {
                    $why = $_.Exception.Message
                    if ($archived -and $bak -and (Test-Path -LiteralPath $bak) -and -not (Test-Path -LiteralPath $dest)) {
                        try {
                            Move-Item -LiteralPath $bak -Destination $dest -Force
                            Write-Host ('  install failed, previous version restored from backup: ' + $why) -ForegroundColor Red
                        } catch {
                            Write-Host ('  install failed AND rollback failed: ' + $why) -ForegroundColor Red
                            Write-Host ('  previous version kept at: ' + $bak) -ForegroundColor Red
                            Write-Host ('  rollback: Move-Item -LiteralPath "' + $bak + '" -Destination "' + $dest + '" -Force') -ForegroundColor Red
                        }
                    } else {
                        Write-Host ('  install failed: ' + $why) -ForegroundColor Red
                    }
                }
            }
        } finally {
            if ($tmpRoot -and (Test-Path -LiteralPath $tmpRoot)) {
                try {
                    $null = Assert-SafePath -Path $tmpRoot -AllowedRoot ([IO.Path]::GetTempPath())
                    Remove-Item -LiteralPath $tmpRoot -Recurse -Force
                } catch {
                    Write-Host ('  temp cleanup skipped: ' + $_.Exception.Message) -ForegroundColor Yellow
                }
            }
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


