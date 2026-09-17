# Encoding RESOLVER (protocol step "detect"): candidate ladder for the cases the
# fast probe could not settle. Mirrors uchardet (report ALL candidates ranked by
# confidence) and ICU detectAll(); rejects a candidate unless it decodes strictly
# AND survives a byte-identical round trip, then scores the survivors by whether
# the decoded text looks like real text (not random phonetics/dingbats).
#
# Only when NO candidate survives does this return REPORT (i.e. "do not touch the
# file, ask the human") -- so "unknown" is the last resort, not the first answer.
# Pure ASCII.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Path, [int]$Top = 3)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path)) { 'EXISTS=False'; exit 0 }
$b = [IO.File]::ReadAllBytes($Path)

function Strict([string]$name) {
  switch ($name) {
    'utf-8'    { return (New-Object Text.UTF8Encoding($false, $true)) }
    'utf-16le' { return (New-Object Text.UnicodeEncoding($false, $true, $true)) }
    'utf-16be' { return (New-Object Text.UnicodeEncoding($true, $true, $true)) }
    'gbk'      { return [Text.Encoding]::GetEncoding(936, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback) }
    'big5'     { return [Text.Encoding]::GetEncoding(950, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback) }
    'shift_jis'{ return [Text.Encoding]::GetEncoding(932, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback) }
    'windows-1252' { return [Text.Encoding]::GetEncoding(1252, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback) }
    'iso-8859-1'   { return [Text.Encoding]::GetEncoding(28591, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback) }
    default { throw "unknown page $name" }
  }
}

# Round-trip a candidate: decode strictly, re-encode, require identical bytes.
function TestCandidate([string]$name, [byte[]]$bytes) {
  $enc = $null; $text = $null
  try { $enc = Strict $name; $text = $enc.GetString($bytes) } catch { return $null }
  # Strip a BOM the decoder consumed, so re-encoding matches the raw bytes.
  $body = $text
  $preamble = $enc.GetPreamble()
  $rt = $enc.GetBytes($body)
  $same = $false
  if ($rt.Length -eq $bytes.Length) {
    $same = $true
    for ($i = 0; $i -lt $bytes.Length; $i++) { if ($bytes[$i] -ne $rt[$i]) { $same = $false; break } }
  }
  if (-not $same) {
    # retry accounting for a BOM the decoder swallowed
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $rt2 = $enc.GetBytes($text) }
    return $null
  }
  return $text
}

# Plausibility: real source text is ASCII + (CJK or common Latin), not phonetics,
# dingbats, private-use or replacement characters.
function Score([string]$text) {
  $cjk = 0; $ascii = 0; $bad = 0; $latin = 0; $total = 0
  foreach ($ch in $text.ToCharArray()) {
    $c = [int]$ch; $total++
    if ($c -lt 0x80) { $ascii++; continue }
    if (($c -ge 0x4E00 -and $c -le 0x9FFF) -or ($c -ge 0x3400 -and $c -le 0x4DBF) -or ($c -ge 0x3000 -and $c -le 0x303F) -or ($c -ge 0xFF00 -and $c -le 0xFFEF)) { $cjk++; continue }
    if ($c -ge 0xC0 -and $c -le 0x24F) { $latin++; continue }
    if ($ch -eq [char]0xFFFD -or ($c -ge 0xE000 -and $c -le 0xF8FF) -or ($c -ge 0x590 -and $c -le 0x5FF) -or ($c -ge 0x2000 -and $c -le 0x2BFF)) { $bad++; continue }
    $bad++
  }
  if ($total -eq 0) { return -1000 }
  # CJK or Latin content is evidence FOR; unassigned/phonetic/dingbat runs are AGAINST.
  return [int](100 * ($cjk + $latin) / $total) - [int](200 * $bad / $total)
}

$ladder = @('utf-8','gbk','big5','shift_jis','windows-1252','iso-8859-1','utf-16le','utf-16be')
$results = New-Object System.Collections.Generic.List[object]
foreach ($name in $ladder) {
  $text = TestCandidate $name $b
  if ($null -eq $text) { continue }
  $results.Add([pscustomobject]@{ Page = $name; Score = (Score $text); Text = $text })
}
if ($results.Count -eq 0) {
  Write-Output 'verdict=REPORT'
  Write-Output '  no candidate decodes strictly AND round-trips byte-identically'
  Write-Output '  action=do not modify this file; ask the human for the encoding'
  exit 0
}
$ranked = $results | Sort-Object -Property Score -Descending
Write-Output ("verdict=RESOLVED candidates={0}" -f $results.Count)
$i = 0
foreach ($r in $ranked) {
  if ($i -ge $Top) { break }
  $preview = ($r.Text -replace "`r?`n", ' ')
  if ($preview.Length -gt 48) { $preview = $preview.Substring(0, 48) }
  Write-Output ("  #{0} {1,-13} score={2,-6} preview={3}" -f ($i + 1), $r.Page, $r.Score, $preview)
  $i++
}
exit 0
