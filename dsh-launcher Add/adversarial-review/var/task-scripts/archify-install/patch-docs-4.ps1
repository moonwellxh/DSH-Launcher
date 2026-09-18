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
$baseSkill = Join-Path $bakDir 'SKILL.md_20260917-235537'
$baseAgents = Join-Path $home_ '.dsh\AGENTS.md_20260917-235537'

function Get-Text([string]$p) { [System.IO.File]::ReadAllText($p, $enc8) }
function Set-Text([string]$p, [string]$t) { [System.IO.File]::WriteAllText($p, $t, $enc8) }
function Stats([string]$t) {
  $crlf = ([regex]::Matches($t, "`r`n")).Count
  $lf   = ([regex]::Matches($t, "`n")).Count
  "bytes=$($enc8.GetByteCount($t)) lines=$(($t -split "`n").Count) crlf=$crlf loneLF=$($lf-$crlf) fffd=$(([regex]::Matches($t,'\uFFFD')).Count)"
}

# ---------- 1) AGENTS.md：把上轮误留的孤立 LF 回正为 CRLF ----------
$a = Get-Text $agentsMd
Write-Output "AGENTS.md BEFORE  $(Stats $a)"
Copy-Item -LiteralPath $agentsMd -Destination ($agentsMd + '_' + $stamp) -Force
$idx = $a.IndexOf('载入技能 archify')
if ($idx -lt 0) { throw 'pointer line not found' }
$ls = $a.LastIndexOf("`n", $idx) + 1
$le = $a.IndexOf("`n", $idx)
$line = $a.Substring($ls, $le - $ls)
if ($line.EndsWith("`r")) { $line = $line.Substring(0, $line.Length - 1) }
$a2 = $a.Substring(0, $ls) + $line + "`r`n" + $a.Substring($le + 1)
Set-Text $agentsMd $a2
Write-Output "AGENTS.md AFTER   $(Stats $a2)"

# ---------- 2) SKILL.md：整块重写说明块（上轮少替换一行，留下残余） ----------
$t = Get-Text $skillMd
Write-Output "SKILL.md BEFORE   $(Stats $t)"
Copy-Item -LiteralPath $skillMd -Destination (Join-Path $bakDir ('SKILL.md_' + $stamp)) -Force
$ns = $t.IndexOf('本机安装说明（DSH')
if ($ns -lt 0) { throw 'note block start not found' }
$ns = $t.LastIndexOf("`n", $ns) + 1
$na = $t.IndexOf('# Archify')
if ($na -lt 0) { throw '# Archify not found' }
if ($na -le $ns) { throw 'unexpected order' }
$noteTpl = @'
> **本机安装说明（DSH / Windows，2026-09-17 安装会话追加）**：本技能已安装在 `__ROOT__`。
> DSH 的当前目录是**会话工作区**、不是本技能目录，因此下文所有 `node bin/archify.mjs ...` 命令都必须
> 换成绝对路径：`node "__ROOT__\bin\archify.mjs" ...`；便携写法
> （PowerShell 5.1 / pwsh 直接可用，cmd.exe 下改用 `%USERPROFILE%`）：`node "$env:USERPROFILE\.agents\skills\archify\bin\archify.mjs" ...`。
> `schemas/`、`examples/`、`references/`、`renderers/` 等相对路径同样以技能根目录为基准解析。

'@
$note = $noteTpl.Replace('__ROOT__', $skillRoot).TrimEnd("`r", "`n")
$t2 = $t.Substring(0, $ns) + $note + "`n`n" + $t.Substring($na)
Set-Text $skillMd $t2
Write-Output "SKILL.md AFTER    $(Stats $t2)"
Write-Output ("  broken form left : " + $t2.Contains('node "%USERPROFILE%'))

# ---------- 3) 强校验：删去新增段后必须与基线逐字节相同 ----------
$curA = Get-Text $agentsMd
$idx = $curA.IndexOf('载入技能 archify')
$ls = $curA.LastIndexOf("`n", $idx) + 1
$le = $curA.IndexOf("`n", $idx) + 1
$derivedA = $curA.Remove($ls, $le - $ls)
$baseA = Get-Text $baseAgents
Write-Output ("AGENTS.md  derived-minus-new-line == baseline : " + ($derivedA -ceq $baseA))

$curS = Get-Text $skillMd
$ns2 = $curS.IndexOf('本机安装说明（DSH'); $ns2 = $curS.LastIndexOf("`n", $ns2) + 1
$na2 = $curS.IndexOf('# Archify')
$derivedS = $curS.Substring(0, $ns2) + $curS.Substring($na2)
$baseS = Get-Text $baseSkill
Write-Output ("SKILL.md   derived-minus-note     == baseline : " + ($derivedS -ceq $baseS))

# ---------- 4) changelog：把体积数字回填为最终实测值 ----------
$c = Get-Text $clog
Copy-Item -LiteralPath $clog -Destination ($clog + '_' + $stamp) -Force
$finalS = $enc8.GetByteCount($t2)
$finalA = $enc8.GetByteCount($a2)
$c2 = $c.Replace('SKILL.md 16396→16968 B', "SKILL.md 16396→$finalS B").Replace('AGENTS.md 5727→6069 B', "AGENTS.md 5727→$finalA B")
if ($c2 -ceq $c) { Write-Output 'changelog: nothing to backfill (already final?)' } else { Set-Text $clog $c2; Write-Output "changelog: backfilled final sizes (SKILL=$finalS, AGENTS=$finalA)" }
Write-Output "changelog NOW     $(Stats (Get-Text $clog))"

Write-Output '--- final note block ---'
$i = 0; Get-Content $skillMd -Encoding UTF8 | ForEach-Object { $i++; if ($i -ge 10 -and $i -le 18) { "$i : $_" } }
Write-Output '--- final pointer line ---'
$i = 0; Get-Content $agentsMd -Encoding UTF8 | ForEach-Object { $i++; if ($_ -like '*载入技能 archify*') { "$i : $_" } }
Write-Output 'DONE'
