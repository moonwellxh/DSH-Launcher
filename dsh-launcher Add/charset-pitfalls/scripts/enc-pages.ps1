# NOTE: this file is dot-sourced as a LIBRARY (by enc-decide.ps1 and
# enc-write-check.ps1), so it must NOT declare a param() block. A mandatory
# parameter here made every dot-source throw "missing mandatory parameters:
# File", which silently disabled the decide/confirm half of the G0 gate
# (detect kept working, so the breakage looked like a per-file problem).
# Shared encoding page table + an explicit "can this page be a WRITE TARGET?" policy.
#
# The v4 review found that decide could authorise a rewrite onto a page it had
# merely GUESSED (measured: legal GBK bytes -> page=utf-16be, CONVERT-OK), and that
# confirm could not even accept the pages decide emitted (unknown page: big5).
# Both come from having two different page tables and from treating a scored guess
# as a fact. This module unifies the table and separates:
#   - pages that can be DETECTED (used for evidence/reporting), from
#   - pages that may be a WRITE TARGET (only ones the bytes prove: BOM, or UTF-8).
#
# Pure ASCII.

$script:PageTable = @{
  'ascii'        = [Text.Encoding]::ASCII
  'utf-8'        = (New-Object Text.UTF8Encoding($false, $true))
  'utf-8-bom'    = (New-Object Text.UTF8Encoding($true, $true))
  'utf-16le'     = (New-Object Text.UnicodeEncoding($false, $true, $true))
  'utf-16be'     = (New-Object Text.UnicodeEncoding($true, $true, $true))
  'gbk'          = [Text.Encoding]::GetEncoding(936, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback)
  'big5'         = [Text.Encoding]::GetEncoding(950, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback)
  'shift_jis'    = [Text.Encoding]::GetEncoding(932, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback)
  'windows-1252' = [Text.Encoding]::GetEncoding(1252, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback)
  'iso-8859-1'   = [Text.Encoding]::GetEncoding(28591, [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback)
}

# Pages whose identity the BYTES prove, so writing back in them is lossless by
# construction: a BOM states the page, ASCII has no non-ASCII bytes to lose, and
# valid UTF-8 with enough multi-byte evidence cannot be a single-byte page (the
# probability of a legacy page coincidentally producing many valid sequences is
# negligible). Everything else is an ASSUMPTION and must never be a write target.
$script:ProvableWritePages = @('ascii', 'utf-8', 'utf-8-bom', 'utf-16le', 'utf-16be')

function Get-PageEncoding([string]$name) {
  $key = $name.ToLowerInvariant()
  if (-not $script:PageTable.ContainsKey($key)) { throw "unknown page: $name" }
  return $script:PageTable[$key]
}
function Test-ProvableWritePage([string]$name) {
  return ($script:ProvableWritePages -contains $name.ToLowerInvariant())
}
function Get-AllPageNames() { return @($script:PageTable.Keys | Sort-Object) }

function Test-RoundTrip([string]$name, [byte[]]$bytes) {
  try { $enc = Get-PageEncoding $name } catch { return $null }
  try { $text = $enc.GetString($bytes) } catch { return $null }
  try { $rt = $enc.GetBytes($text) } catch { return $null }
  if ($rt.Length -ne $bytes.Length) { return $null }
  for ($i = 0; $i -lt $bytes.Length; $i++) { if ($bytes[$i] -ne $rt[$i]) { return $null } }
  return $text
}

# Plausibility of decoded text. Halfwidth katakana (U+FF61-FF9F) is the classic
# signature of a WRONG page (a double-byte page read as Shift_JIS), so it scores
# NEGATIVE -- scoring it positive was what made real GBK look like Shift_JIS.
function Get-TextScore([string]$text) {
  $cjk = 0; $latin = 0; $bad = 0; $halfKana = 0; $total = 0
  foreach ($ch in $text.ToCharArray()) {
    $c = [int]$ch; $total++
    if ($c -lt 0x80) { continue }
    if ($c -ge 0xFF61 -and $c -le 0xFF9F) { $halfKana++; continue }
    if (($c -ge 0x4E00 -and $c -le 0x9FFF) -or ($c -ge 0x3400 -and $c -le 0x4DBF)) { $cjk++; continue }
    if ($c -ge 0x3000 -and $c -le 0x303F) { $cjk++; continue }
    if (($c -ge 0xFF01 -and $c -le 0xFF60) -or ($c -ge 0xFFE0 -and $c -le 0xFFE6)) { $cjk++; continue }
    if ($c -ge 0xC0 -and $c -le 0x24F) { $latin++; continue }
    $bad++
  }
  if ($total -eq 0) { return -1000 }
  return [int](100 * ($cjk + $latin) / $total) - [int](150 * $bad / $total) - [int](150 * $halfKana / $total)
}
