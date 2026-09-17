# Encoding PROBE (protocol step "detect"): confidence-based, never guesses from a
# single byte pair. Mirrors the established approach in chardet (staged pipeline +
# UTF-8 confidence scaled by multi-byte ratio + CJK gating) and ICU (ranked
# candidates with confidence, "detection is at best an imprecise operation").
#
# Emits one line per file:  enc / confidence / evidence counts
# Pure ASCII; call with -Path <file>. No Chinese literals.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Path,
  # Minimum number of 3/4-byte UTF-8 sequences (CJK etc.) before the UTF-8
  # hypothesis is considered STRONG. ASCII+Latin-1 text has none, so a legacy
  # single-byte file can never reach STRONG via a stray valid pair.
  [int]$MinCjkSeq = 2
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path)) { 'EXISTS=False'; exit 0 }
$b = [IO.File]::ReadAllBytes($Path)
$len = $b.Length

function Detect-EolInterpreted([byte[]]$bytes, [int]$unit, [bool]$bigEndian) {
  # Count line breaks after interpreting the bytes in the given unit size.
  $cr = 0; $lf = 0
  for ($i = 0; $i + $unit -le $bytes.Length; $i += $unit) {
    $v = if ($unit -eq 1) { $bytes[$i] } else {
      if ($bigEndian) { ([int]$bytes[$i] -shl 8) -bor $bytes[$i+1] } else { ([int]$bytes[$i+1] -shl 8) -bor $bytes[$i] }
    }
    if ($v -eq 0x0D) { $cr++ } elseif ($v -eq 0x0A) { $lf++ }
  }
  if ($cr -eq 0 -and $lf -eq 0) { return 'NONE' }
  if ($cr -gt 0 -and $lf -eq 0) { return 'CR' }
  if ($cr -eq 0 -and $lf -gt 0) { return 'LF' }
  return 'CRLF-or-MIXED'
}

$enc = 'UNKNOWN'; $conf = 'none'; $mb = 0; $cjk = 0; $nul = 0; $non = 0; $eol = 'NONE'

if ($len -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
  $enc = 'UTF8-BOM'; $conf = 'definitive'
  $eol = Detect-EolInterpreted $b 1 $false
} elseif ($len -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) {
  $enc = 'UTF16-LE'; $conf = 'definitive'; $eol = Detect-EolInterpreted $b 2 $false
} elseif ($len -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) {
  $enc = 'UTF16-BE'; $conf = 'definitive'; $eol = Detect-EolInterpreted $b 2 $true
} else {
  foreach ($x in $b) { if ($x -eq 0) { $nul++ }; if ($x -gt 0x7F) { $non++ } }
  $nulPct = if ($len -gt 0) { [math]::Round(100.0 * $nul / $len, 1) } else { 0 }
  if ($nulPct -gt 20) {
    # chardet step 2: interleaved nulls indicate BOM-less UTF-16. Density is the
    # only reliable structural signal; the endianness cannot be proven, so we stop.
    $enc = 'UNKNOWN'; $conf = 'ambiguous'; $eol = 'NONE'
  } elseif ($non -eq 0) {
    $enc = 'ASCII'; $conf = 'definitive'; $eol = Detect-EolInterpreted $b 1 $false
  } else {
    # Stage: strict UTF-8 validation, counting sequence widths (chardet step 8/9).
    $validUtf8 = $true; $i = 0
    while ($i -lt $len) {
      $c = $b[$i]
      if ($c -lt 0x80) { $i++ ; continue }
      $n = if (($c -band 0xE0) -eq 0xC0) { 2 } elseif (($c -band 0xF0) -eq 0xE0) { 3 } elseif (($c -band 0xF8) -eq 0xF0) { 4 } else { 0 }
      if ($n -eq 0 -or $i + $n -gt $len) { $validUtf8 = $false; break }
      for ($k = 1; $k -lt $n; $k++) { if (($b[$i+$k] -band 0xC0) -ne 0x80) { $validUtf8 = $false; break } }
      if (-not $validUtf8) { break }
      $mb++
      if ($n -ge 3) { $cjk++ }
      $i += $n
    }
    $eol = Detect-EolInterpreted $b 1 $false
    if (-not $validUtf8) {
      # Not UTF-8 at all -> a legacy single/double-byte code page. On a zh-CN
      # Windows box that is overwhelmingly GBK/CP936, but it is an assumption:
      # report it as such, and verify by round-trip before ever writing.
      $enc = 'LEGACY-8BIT'; $conf = 'assumed(GBK)'
    } elseif ($cjk -ge $MinCjkSeq -and $len -ge 16) {
      $enc = 'UTF8-NOBOM'; $conf = 'strong'
    } else {
      # Valid UTF-8 but too little multi-byte evidence: chardet rates such input
      # low-confidence, and ICU warns short samples are unreliable. Do NOT convert.
      $enc = 'UTF8-WEAK'; $conf = 'low'
    }
  }
}
'enc={0} | conf={1} | bytes={2} | nonAscii={3} | nulPct={4} | multiByteSeq={5} | cjkSeq={6} | eol={7}' -f `
  $enc, $conf, $len, $non, $(if ($null -eq $nulPct) { 0 } else { $nulPct }), $mb, $cjk, $eol
