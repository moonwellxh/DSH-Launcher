$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$home_ = $env:USERPROFILE
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$enc8  = New-Object System.Text.UTF8Encoding($false)

$skillRoot = Join-Path $home_ '.agents\skills\archify'
$skillMd   = Join-Path $skillRoot 'SKILL.md'
$agentsMd  = Join-Path $home_ '.dsh\AGENTS.md'

function Get-Text([string]$p) { [System.IO.File]::ReadAllText($p, $enc8) }
function Set-Text([string]$p, [string]$t) { [System.IO.File]::WriteAllText($p, $t, $enc8) }
function Stats([string]$t) {
  $crlf = ([regex]::Matches($t, "`r`n")).Count
  $lf   = ([regex]::Matches($t, "`n")).Count
  [pscustomobject]@{
    bytes    = $enc8.GetByteCount($t)
    chars    = $t.Length
    lines    = ($t -split "`n").Count
    crlf     = $crlf
    loneLf   = $lf - $crlf
    fffd     = ([regex]::Matches($t, '\uFFFD')).Count
  }
}

Write-Output "stamp = $stamp"
Write-Output "skillRoot = $skillRoot"

# ---------------- 1) SKILL.md : 正文首个 "# Archify" 之前插入本机绝对路径说明 ----------------
$t = Get-Text $skillMd
Write-Output '--- SKILL.md BEFORE ---'
Stats $t | Format-List | Out-String -Width 120

if ($t.Contains('本机安装说明（DSH')) {
  Write-Output 'SKILL.md: 已含说明，跳过（幂等）'
} else {
  $bk1 = $skillMd + '_' + $stamp
  Copy-Item -LiteralPath $skillMd -Destination $bk1 -Force
  Write-Output "backup: $bk1"

  $anchor = '# Archify'
  $i = $t.IndexOf($anchor)
  if ($i -lt 0) { throw 'SKILL.md anchor "# Archify" not found' }

  $noteTpl = @'
> **本机安装说明（DSH / Windows，2026-09-17 安装会话追加）**：本技能已安装在 `__ROOT__`。
> DSH 的当前目录是**会话工作区**、不是本技能目录，因此下文所有 `node bin/archify.mjs ...`
> 命令都必须换成绝对路径：`node "__ROOT__\bin\archify.mjs" ...`（等效写法
> `node "%USERPROFILE%\.agents\skills\archify\bin\archify.mjs" ...`）；
> `schemas/`、`examples/`、`references/`、`renderers/` 等相对路径同样以技能根目录为基准解析。

'@
  $note = $noteTpl.Replace('__ROOT__', $skillRoot)
  $new = $t.Substring(0, $i) + $note + $t.Substring($i)
  Set-Text $skillMd $new
  Write-Output 'SKILL.md: patched'
}

$t2 = Get-Text $skillMd
Write-Output '--- SKILL.md AFTER ---'
Stats $t2 | Format-List | Out-String -Width 120
Write-Output ("contains note      : " + $t2.Contains('本机安装说明（DSH'))
Write-Output ("contains real root : " + $t2.Contains($skillRoot))
Write-Output ("frontmatter intact : " + ($t2.Contains('name: archify') -and $t2.Contains('# Archify')))

# ---------------- 2) AGENTS.md : §4 指针区在末行「变更记录」之前插入一行 ----------------
$a = Get-Text $agentsMd
Write-Output '--- AGENTS.md BEFORE ---'
Stats $a | Format-List | Out-String -Width 120

if ($a.Contains('载入技能 archify')) {
  Write-Output 'AGENTS.md: 已含指针行，跳过（幂等）'
} else {
  $an = '.dsh/AGENTS-changelog.md'
  $j = $a.IndexOf($an)
  if ($j -lt 0) { throw 'AGENTS.md anchor ".dsh/AGENTS-changelog.md" not found' }
  $lineStart = $a.LastIndexOf("`n", $j) + 1
  if ($lineStart -le 0) { throw 'AGENTS.md: cannot locate line start' }
  if ($lineStart -ge 2 -and $a.Substring($lineStart - 2, 2) -eq "`r`n") { $eol = "`r`n" }
  elseif ($a.Substring($lineStart - 1, 1) -eq "`n") { $eol = "`n" }
  else { throw 'AGENTS.md: cannot determine line ending' }

  $bk2 = $agentsMd + '_' + $stamp
  Copy-Item -LiteralPath $agentsMd -Destination $bk2 -Force
  Write-Output "backup: $bk2"
  Write-Output "insert eol = $(if ($eol -eq "`r`n") { 'CRLF' } else { 'LF' }), at char $lineStart"

  $lineTpl = @'
- 架构图 / 系统地图（Archify：架构 · 工作流 · 时序 · 数据流 · 生命周期图 → 可交互独立 HTML）：载入技能 archify；技能根 `~/.agents/skills/archify/`，CLI 必须用绝对路径 `node %USERPROFILE%\.agents\skills\archify\bin\archify.mjs`（2026-09-17 安装 v2.17.0-dev.1，四层验证通过）。
'@
  $line = $lineTpl.TrimEnd("`r", "`n")
  $newA = $a.Substring(0, $lineStart) + $line + $eol + $a.Substring($lineStart)
  Set-Text $agentsMd $newA
  Write-Output 'AGENTS.md: patched'
}

$a2 = Get-Text $agentsMd
Write-Output '--- AGENTS.md AFTER ---'
Stats $a2 | Format-List | Out-String -Width 120
Write-Output ("contains pointer   : " + $a2.Contains('载入技能 archify'))
Write-Output ("pointer is one line: " + (($a2 -split "`n" | Where-Object { $_ -like '*载入技能 archify*' }).Count -eq 1))
Write-Output ("last line intact   : " + ($a2.TrimEnd().EndsWith('~/.dsh/AGENTS-changelog.md。')))
Write-Output ("sections intact    : " + ($a2.Contains('## 4 指针与触发依据') -and $a2.Contains('## 3 写入规则')))
Write-Output 'DONE'
