param(
  [Parameter(Mandatory=$true)][string]$Path,
  [int]$MinBytesForConvert = 64,
  [int]$MinScoreMargin = 15
)
# Decision stage. Conservative by construction:
#   CONVERT-OK  is issued ONLY for a page the bytes PROVE (BOM / ASCII / strong
#               UTF-8). A scored guess is NEVER a write target -- the v4 review
#               showed decide authorising a rewrite onto a guessed page
#               (legal GBK bytes -> page=utf-16be, CONVERT-OK).
#   REPORT      everything else, with the ranked candidates handed to the human.
# Exit: 0 = safe to write in the reported page, 2 = report only, 3 = input error.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'enc-pages.ps1')
if (-not (Test-Path -LiteralPath $Path)) { Write-Output 'decision=INPUT-ERROR | file not found'; exit 3 }
$b = [IO.File]::ReadAllBytes($Path); $len = $b.Length
if ($len -eq 0) { Write-Output 'decision=REPORT | page= | empty file, nothing to decide'; exit 2 }

$nul = 0; $non = 0
foreach ($x in $b) { if ($x -eq 0) { $nul++ }; if ($x -gt 0x7F) { $non++ } }
$nulPct = 100.0 * $nul / $len

$decision = 'REPORT'; $page = ''; $why = ''

if ($len -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
  $decision = 'CONVERT-OK'; $page = 'utf-8-bom'; $why = 'BOM proves the page'
} elseif ($len -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) {
  $decision = 'CONVERT-OK'; $page = 'utf-16le'; $why = 'BOM proves the page'
} elseif ($len -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) {
  $decision = 'CONVERT-OK'; $page = 'utf-16be'; $why = 'BOM proves the page'
} elseif ($nulPct -gt 20) {
  # Must precede the ASCII test: BOM-less UTF-16 that is all ASCII has zero bytes
  # above 0x7F, so an "ASCII" verdict would be catastrophic (v4 review finding).
  $decision = 'REPORT'; $page = ''
  $why = ("null-byte density {0}% indicates BOM-less UTF-16; endianness unproven" -f [math]::Round($nulPct,1))
} elseif ($non -eq 0) {
  $decision = 'CONVERT-OK'; $page = 'ascii'; $why = 'no byte above 0x7F and no NULs'
} else {
  $utf8text = Test-RoundTrip 'utf-8' $b
  $mb = 0
  if ($null -ne $utf8text) {
    $i = 0
    while ($i -lt $len) {
      $c = $b[$i]
      if ($c -lt 0x80) { $i++; continue }
      $n = if (($c -band 0xE0) -eq 0xC0) { 2 } elseif (($c -band 0xF0) -eq 0xE0) { 3 } elseif (($c -band 0xF8) -eq 0xF0) { 4 } else { 0 }
      if ($n -eq 0) { break }
      if ($n -ge 3) { $mb++ }
      $i += $n
    }
  }
  if ($null -ne $utf8text -and $mb -ge 2 -and $len -ge 16) {
    $decision = 'CONVERT-OK'; $page = 'utf-8'
    $why = ("valid UTF-8 with {0} multi-byte sequences (no single-byte page can fake this)" -f $mb)
  } else {
    # Everything here is an ASSUMPTION. Report ranked evidence; never write.
    $cands = New-Object System.Collections.Generic.List[object]
    foreach ($name in @('gbk','big5','shift_jis','windows-1252','iso-8859-1','utf-16le','utf-16be')) {
      $txt = Test-RoundTrip $name $b
      if ($null -eq $txt) { continue }
      $cands.Add([pscustomobject]@{ Page = $name; Score = (Get-TextScore $txt) })
    }
    if ($cands.Count -eq 0) { $why = 'no candidate decodes strictly AND round-trips' }
    else {
      $ranked = @($cands | Sort-Object -Property Score -Descending)
      $top = ($ranked | Select-Object -First 3 | ForEach-Object { "{0}({1})" -f $_.Page, $_.Score }) -join ' > '
      $page = $ranked[0].Page
      $why = ("assumed page only, ranked: {0}; a guess is never a write target" -f $top)
      if ($len -lt $MinBytesForConvert) { $why = ("sample too small ({0} < {1} bytes); {2}" -f $len, $MinBytesForConvert, $why) }
    }
  }
}
'decision={0} | page={1} | bytes={2} | {3}' -f $decision, $page, $len, $why
if ($decision -eq 'INPUT-ERROR') { exit 3 }
if ($decision -eq 'REPORT') { exit 2 }
if (-not (Test-ProvableWritePage $page)) { Write-Output 'decision=REPORT | page= | internal guard: page is not provable'; exit 2 }
exit 0
