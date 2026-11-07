# Encoding PROBE (protocol step "detect"): confidence-based, never guesses from a
# single byte pair. Mirrors the established approach in chardet (staged pipeline +
# UTF-8 confidence scaled by multi-byte ratio + CJK gating) and ICU (ranked
# candidates with confidence, "detection is at best an imprecise operation").
#
# Emits one line per file:  enc / confidence / evidence counts
# Pure ASCII; call with -Path <file>. No Chinese literals.
#
# 2026-11-06 fix 1: the evidence counters (nonAscii / multiByteSeq / cjkSeq) used to
# be computed only inside the BOM-less branch, so any UTF8/UTF16 BOM file reported
# 0 for all three. Verdicts stayed right (BOM is definitive) but the evidence line
# was false -- observed on DSH-tray.ps1: 22,230 bytes >0x7F reported as nonAscii=0.
#
# 2026-11-06 fix 2: even after fix 1 the UTF-8 BOM bytes (EF BB BF) were counted as
# one 3-byte sequence and three non-ASCII bytes, so a BOM file reported one extra
# multiByteSeq / cjkSeq versus the same text without a BOM. Counting now starts
# after the BOM, which makes the evidence line genuinely comparable.
#
# 2026-11-06 fix 3: for UTF-16 files the null-density field used to print 0 rather
# than "not applicable" (nul is deliberately not counted there). It now prints n/a.
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

function Measure-Utf8Widths([byte[]]$bytes, [int]$Start = 0) {
  # Strict UTF-8 validation while counting sequence widths (chardet step 8/9).
  # Returns valid flag plus multi-byte / 3-4-byte sequence counts. Stops at the
  # first malformed sequence: one bad byte is enough to reject the page.
  # $Start skips a leading BOM so the counts describe the text, not the marker.
  $valid = $true; $mb = 0; $cjk = 0; $i = $Start
  $n = $bytes.Length
  while ($i -lt $n) {
    $c = $bytes[$i]
    if ($c -lt 0x80) { $i++; continue }
    $w = if (($c -band 0xE0) -eq 0xC0) { 2 } elseif (($c -band 0xF0) -eq 0xE0) { 3 } elseif (($c -band 0xF8) -eq 0xF0) { 4 } else { 0 }
    if ($w -eq 0 -or $i + $w -gt $n) { $valid = $false; break }
    for ($k = 1; $k -lt $w; $k++) { if (($bytes[$i+$k] -band 0xC0) -ne 0x80) { $valid = $false; break } }
    if (-not $valid) { break }
    $mb++
    if ($w -ge 3) { $cjk++ }
    $i += $w
  }
  return [pscustomobject]@{ Valid = $valid; Mb = $mb; Cjk = $cjk }
}

$enc = 'UNKNOWN'; $conf = 'none'; $mb = 0; $cjk = 0; $nul = 0; $non = 0; $eol = 'NONE'

$isBomUtf8 = ($len -ge 3) -and ($b[0] -eq 0xEF) -and ($b[1] -eq 0xBB) -and ($b[2] -eq 0xBF)
$isUtf16 = ($len -ge 2) -and ((($b[0] -eq 0xFF) -and ($b[1] -eq 0xFE)) -or (($b[0] -eq 0xFE) -and ($b[1] -eq 0xFF)))

# ---- evidence counters: byte-oriented encodings only ----
# UTF-16 is excluded from byte-level density: its non-ASCII bytes do not mean what
# they mean in a byte-oriented encoding, and the null-density test owns that
# diagnosis. The UTF-8 BOM (3 bytes) is skipped so counts describe the text.
if (-not $isUtf16) {
  $startAt = 0
  if ($isBomUtf8) { $startAt = 3 }
  for ($ci = $startAt; $ci -lt $len; $ci++) {
    if ($b[$ci] -eq 0) { $nul++ }
    if ($b[$ci] -gt 0x7F) { $non++ }
  }
}

if ($isBomUtf8) {
  $enc = 'UTF8-BOM'; $conf = 'definitive'
  $eol = Detect-EolInterpreted $b 1 $false
  # Same width measurement as the BOM-less UTF-8 path, starting after the BOM,
  # so the evidence line is comparable across the two cases.
  $w = Measure-Utf8Widths $b 3
  if ($w.Valid) { $mb = $w.Mb; $cjk = $w.Cjk }
} elseif ($len -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) {
  $enc = 'UTF16-LE'; $conf = 'definitive'; $eol = Detect-EolInterpreted $b 2 $false
} elseif ($len -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) {
  $enc = 'UTF16-BE'; $conf = 'definitive'; $eol = Detect-EolInterpreted $b 2 $true
} else {
  $nulPct = if ($len -gt 0) { [math]::Round(100.0 * $nul / $len, 1) } else { 0 }
  if ($nulPct -gt 20) {
    # chardet step 2: interleaved nulls indicate BOM-less UTF-16. Density is the
    # only reliable structural signal; the endianness cannot be proven, so we stop.
    $enc = 'UNKNOWN'; $conf = 'ambiguous'; $eol = 'NONE'
  } elseif ($non -eq 0) {
    $enc = 'ASCII'; $conf = 'definitive'; $eol = Detect-EolInterpreted $b 1 $false
  } else {
    $w = Measure-Utf8Widths $b 0
    $mb = $w.Mb; $cjk = $w.Cjk
    $eol = Detect-EolInterpreted $b 1 $false
    if (-not $w.Valid) {
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

# UTF-16 has no meaningful null density in this report; say so instead of "0".
$nulPctText = if ($isUtf16) { 'n/a' } elseif ($null -eq $nulPct) { '0' } else { [string]$nulPct }

'enc={0} | conf={1} | bytes={2} | nonAscii={3} | nulPct={4} | multiByteSeq={5} | cjkSeq={6} | eol={7}' -f `
  $enc, $conf, $len, $non, $nulPctText, $mb, $cjk, $eol
