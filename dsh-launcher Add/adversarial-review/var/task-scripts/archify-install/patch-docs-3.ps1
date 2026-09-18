$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$home_ = $env:USERPROFILE
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$enc8  = New-Object System.Text.UTF8Encoding($false)
$skillRoot = Join-Path $home_ '.agents\skills\archify'
$skillMd   = Join-Path $skillRoot 'SKILL.md'
$agentsMd  = Join-Path $home_ '.dsh\AGENTS.md'
$clog      = Join-Path $home_ '.dsh\AGENTS-changelog.md'
$bakDir    = Join-Path $home_ '.agents\skills\_backup\archify_pre-backups_20260917-235537'

function Get-Text([string]$p) { [System.IO.File]::ReadAllText($p, $enc8) }
function Set-Text([string]$p, [string]$t) { [System.IO.File]::WriteAllText($p, $t, $enc8) }
function Stats([string]$t) {
  $crlf = ([regex]::Matches($t, "`r`n")).Count
  $lf   = ([regex]::Matches($t, "`n")).Count
  "bytes=$($enc8.GetByteCount($t)) lines=$(($t -split "`n").Count) crlf=$crlf loneLF=$($lf-$crlf) fffd=$(([regex]::Matches($t,'\uFFFD')).Count)"
}

# ---------- 1) AGENTS.md：指针行改为纯指针（修严重① + 轻微③） ----------
$a = Get-Text $agentsMd
Write-Output "AGENTS.md BEFORE  $(Stats $a)"
$idx = $a.IndexOf('载入技能 archify')
if ($idx -lt 0) { throw 'AGENTS.md: pointer line not found' }
$ls = $a.LastIndexOf("`n", $idx) + 1
$le = $a.IndexOf("`n", $idx)
if ($le -lt 0) { $le = $a.Length }
$oldLine = $a.Substring($ls, $le - $ls)
if ($a.Substring(0, $le).Contains('载入技能 archify') -and ($a.Substring($le).Contains('载入技能 archify'))) { throw 'AGENTS.md: pointer appears more than once' }
Write-Output "old line: $oldLine"
Copy-Item -LiteralPath $agentsMd -Destination ($agentsMd + '_' + $stamp) -Force
Write-Output "backup: $($agentsMd + '_' + $stamp)"

$newLineTpl = @'
- 架构图 / 系统地图（Archify：架构 · 工作流 · 时序 · 数据流 · 生命周期图 → 可交互独立 HTML）：载入技能 archify（2026-09-17 安装 v2.17.0-dev.1；本机路径与调用方式见技能本体 SKILL.md 首部说明）。
'@
$newLine = $newLineTpl.TrimEnd("`r", "`n")
$a2 = $a.Substring(0, $ls) + $newLine + $a.Substring($le)
Set-Text $agentsMd $a2
Write-Output "AGENTS.md AFTER   $(Stats $a2)"
Write-Output ("  no broken form left : " + (-not $a2.Contains('node "%USERPROFILE%')))
Write-Output ("  pointer count       : " + (([regex]::Matches($a2, '载入技能 archify')).Count))

# ---------- 2) SKILL.md：说明块的第 3~4 行改为 PowerShell 正确写法（修严重①） ----------
$t = Get-Text $skillMd
Write-Output "SKILL.md BEFORE   $(Stats $t)"
$k = $t.IndexOf('等效写法')
if ($k -lt 0) { throw 'SKILL.md: note lines not found' }
$l1s = $t.LastIndexOf("`n", $k) + 1
$l1e = $t.IndexOf("`n", $k)
$l0s = $t.LastIndexOf("`n", $l1s - 2) + 1
if ($l0s -lt 0) { throw 'SKILL.md: cannot locate previous line start' }
$oldBlock = $t.Substring($l0s, $l1e - $l0s)
Write-Output "old block:`n$oldBlock"
if (-not $t.Substring($l0s, $l1e - $l0s).Contains('命令都必须换成绝对路径')) { throw 'SKILL.md: anchor mismatch' }
Copy-Item -LiteralPath $skillMd -Destination (Join-Path $bakDir ('SKILL.md_' + $stamp)) -Force
Write-Output "backup: $(Join-Path $bakDir ('SKILL.md_' + $stamp))"

$newBlockTpl = @'
> 命令都必须换成绝对路径：`node "C:\Users\雍远\.agents\skills\archify\bin\archify.mjs" ...`；
> 便携写法（PowerShell 5.1 / pwsh 直接可用）：`node "$env:USERPROFILE\.agents\skills\archify\bin\archify.mjs" ...`（cmd.exe 下改用 `%USERPROFILE%`）。
'@
$newBlock = $newBlockTpl.TrimEnd("`r", "`n")
$t2 = $t.Substring(0, $l0s) + $newBlock + $t.Substring($l1e)
Set-Text $skillMd $t2
Write-Output "SKILL.md AFTER    $(Stats $t2)"
Write-Output ("  no broken form left : " + (-not $t2.Contains('node "%USERPROFILE%')))
Write-Output ("  frontmatter intact  : " + ($t2.StartsWith("---`n") -and $t2.Contains('name: archify')))
Write-Output '--- new note block ---'
$i = 0; Get-Content $skillMd -Encoding UTF8 | ForEach-Object { $i++; if ($i -ge 11 -and $i -le 18) { "$i : $_" } }

# ---------- 3) changelog：补登（修严重②） ----------
$c = Get-Text $clog
Write-Output "changelog BEFORE  $(Stats $c)"
Copy-Item -LiteralPath $clog -Destination ($clog + '_' + $stamp) -Force
Write-Output "backup: $($clog + '_' + $stamp)"
if ($c.Contains('安装第三方技能 archify')) {
  Write-Output 'changelog: already logged, skip'
} else {
  if (-not $c.EndsWith("`n")) { $c += "`n" }
  $entryTpl = @'

## 2026-09-17 · 安装第三方技能 archify v2.17.0-dev.1（架构图 / 系统地图技能）+ §4 指针登记

- **需求（用户原话）**：「archify skills，本 dsh harness 能安装么？」→ 用户在「A 装到 ~/.agents/skills/archify / B 走 npm 插件 / 先不装」中选定 **A**。
- **判档**：属产物型任务（装第三方技能 + 改 SKILL.md 说明 + AGENTS.md 指针），命中「全局规则变更」→ 走 guide-dev §2A LITE 轻量闭环（L0 确定性检查 + 一次独立子审查，对象=本次增量）。
- **为什么不走 npm 插件**：`@tt-a1i/archify-dsh@0.1.0`（registry 实测唯一版本，tarball 已下载解包核对：`cordis.patch.yml` 只 insert 一个 skill provider + 包内 `skills/archify` 2.14.0）声明兼容 dev-preview `@deepseek-ai/dsh@0.1.0-rc.6`，本机为源码树 `0.1.5-rc.1`，不在兼容范围；能力与路线 A 等价而多一层版本耦合。
- **来源与哈希（可复核）**：上游 GitHub `tt-a1i/archify` 仓库根 `archify.zip`（main 分支）：1,885,058 B，SHA-256 `d2296515b0091fb8f00580ea9e0b665d91ca5839fde651abe3ecd57a3ca178ec`，79 条目、zip 根=`archify/`；用 .NET `ZipFile.ExtractToDirectory` 解到 `~/.agents/skills/`（中文用户名不用 bsdtar）。注意同仓库另有同名 release 资产 `archify.zip`（v2.16.0，1,318,273 B），本次不是它。技能本体版本：`skill-release.json` = 2.17.0-dev.1 / channel=development。
- **改动（2 处，均为只增/只改本行，正文其余不动）**：① `~/.agents/skills/archify/SKILL.md` 首部增 5 行「本机安装说明」块（cwd=会话工作区，相对路径须以技能根为基准；PowerShell 便携写法 `$env:USERPROFILE`）；② `~/.dsh/AGENTS.md` §4 指针区增 1 行（纯指针，细则指向技能本体，遵 §3.2）。
- **验证（L0 实测，命令可复跑）**：36 个 `.mjs` `node --check` 0 失败；`doctor` 15/15 `[ok]` exit 0；`scripts/render-examples.mjs` 5/5 HTML exit 0；`validate architecture examples/web-app.architecture.json --quality showcase --json` exit 0 且 9/9 checks；`deliver` 同参数 exit 0（0 error / 0 warning，artifact 811,809 B，sha256 `426db7bd1842de45916b00233b859dbb6cfb17a0d2fa9c70353c8fe121811d93`）；错误路径（输入不存在）exit 1 且为结构化 JSON（code=`input/read`）非堆栈；宿主已实时发现该技能（会话技能目录出现 `archify`，无需重启）。编码闸门：两文件改前/改后均 UTF8-NOBOM、CONVERT-OK、U+FFFD=0；SKILL.md 16396→16968 B（LF 保持）、AGENTS.md 5727→6069 B（CRLF 46/46，无孤立 LF）。
- **独立子审查（adversarial-review §2：新建 subagent、干净上下文、只喂对象与依据 + 基线文件）**：`阻断 0 / 严重 2 / 轻微 2 / 建议 1`，未达清零；判据「未破坏性」独立复核通过（两文件删去新增段后与基线**逐字节相同**）。处置：
  - **严重①**（文档写法在本机不可用）：`node "%USERPROFILE%\..."` 在 pwsh 5.1 下不展开（实测报 `Cannot find module ...\%USERPROFILE%\...`），且该行复述细则触 §3.2 → **已修**：AGENTS.md 该行改纯指针；SKILL.md 说明块改 `$env:USERPROFILE` 便携写法并注明 cmd 用 `%USERPROFILE%`。
  - **严重②**（变更/来源留痕缺失，changelog 0 命中）→ **本条即留痕**（来源包名 + SHA-256 + 改动清单 + 验证命令 + 回滚点）。
  - **轻微③④**（AGENTS.md 行体例已随①修为纯指针；技能正文 `scripts/check-update.mjs` 同为相对路径调用、未纳入说明块）与**建议⑤**（归档源 zip 到本机留痕目录）→ 按 §2A 口径：轻微搭车不单独开任务、建议须用户确认，见下「遗留」。
- **既知副作用（本次披露）**：技能包 `scripts/check-update.mjs` 首用会联网取 `tt-a1i.github.io` 的更新清单，并在 `%LOCALAPPDATA%\archify-skill\` 写 `state.json`/`owner.json`（≤64 KiB）；技能正文声明只通知、不下载不安装。技能内 `bin\archify.mjs` 不联网（仅 `spawnSync(process.execPath)`），联网仅限 `preview`/`open-artifact` 的 127.0.0.1。
- **回滚点**：① `~/.agents/skills/archify` 整目录（安装前不存在，删除即完全回退）；② `~/.agents/skills/_backup/archify_pre-backups_20260917-235537/` 内 `SKILL.md_20260917-235537`（改前全文）与 `SKILL.md_20260917-235606`（补空行前中间态）；③ `~/.dsh/AGENTS.md_20260917-235537`（改前全文）、`~/.dsh/AGENTS-changelog.md___STAMP__`（本文件改前全文，见同目录带时间戳副本）。
'@
  $entry = $entryTpl.Replace('__STAMP__', $stamp)
  $entry = $entry.TrimStart("`r", "`n")
  $c2 = $c + $entry
  Set-Text $clog $c2
  Write-Output "changelog AFTER   $(Stats $c2)"
  Write-Output ("  entry present     : " + $c2.Contains('安装第三方技能 archify'))
} 
Write-Output 'DONE'
