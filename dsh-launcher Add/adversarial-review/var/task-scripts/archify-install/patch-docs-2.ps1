$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$home_ = $env:USERPROFILE
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$enc8  = New-Object System.Text.UTF8Encoding($false)
$skillRoot = Join-Path $home_ '.agents\skills\archify'
$skillMd   = Join-Path $skillRoot 'SKILL.md'
$bakDir    = Join-Path $home_ '.agents\skills\_backup\archify_pre-backups_20260917-235537'

$t = [System.IO.File]::ReadAllText($skillMd, $enc8)
$i = $t.IndexOf('# Archify')
if ($i -lt 2) { throw 'anchor "# Archify" not found' }
$before = $t.Substring($i - 2, 2)
Write-Output ("chars before '# Archify' = " + ($before -replace "`r", 'CR' -replace "`n", 'LF'))

if ($before -eq "`n`n") {
  Write-Output 'already separated by a blank line, skip'
} else {
  New-Item -ItemType Directory -Force -Path $bakDir | Out-Null
  $bk = Join-Path $bakDir ('SKILL.md_' + $stamp)
  Copy-Item -LiteralPath $skillMd -Destination $bk -Force
  Write-Output "backup: $bk"
  $new = $t.Substring(0, $i) + "`n" + $t.Substring($i)
  [System.IO.File]::WriteAllText($skillMd, $new, $enc8)
  Write-Output 'inserted blank line before "# Archify"'
}

$t2 = [System.IO.File]::ReadAllText($skillMd, $enc8)
$j = $t2.IndexOf('# Archify')
Write-Output ("now chars before       = " + ($t2.Substring($j - 2, 2) -replace "`r", 'CR' -replace "`n", 'LF'))
Write-Output ("bytes = " + $enc8.GetByteCount($t2) + "  loneLF = " + (([regex]::Matches($t2, "`n")).Count - ([regex]::Matches($t2, "`r`n")).Count) + "  crlf = " + ([regex]::Matches($t2, "`r`n")).Count + "  fffd = " + ([regex]::Matches($t2, '\uFFFD')).Count)
Write-Output ("frontmatter intact     = " + ($t2.StartsWith("---`n") -and $t2.Contains('name: archify')))
Write-Output 'DONE'
