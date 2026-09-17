param(
  [Parameter(Mandatory=$true)][string]$Path,
  [Parameter(Mandatory=$true)][string]$Page,
  [string]$Old = '',
  [string]$New = ''
)
# Write-safety check (protocol step "confirm"): decide whether a rewrite is
# provably lossless, BEFORE touching the file.
#
# Revision note (v4 review): this script previously accepted only gbk/utf8/utf8bom
# while the decision stage emitted big5/shift_jis/utf-16le/..., so step 2 threw
# "unknown page" on exactly the routes that needed it. It now uses the SHARED page
# table (enc-pages.ps1), and it no longer pretends that a strict-GBK decode proves
# a file IS GBK -- the GBK double-byte space covers almost every high-byte pair,
# so that test is reported as ADVISORY, never as proof.
#
# Checks: R1 whole-file round trip; R2 anchor prefix byte identity; R3 the new text
# must re-encode to the same characters.
# Exit: 0 = SAFE, 1 = UNSAFE, 3 = input error.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'enc-pages.ps1')
if (-not (Test-Path -LiteralPath $Path)) { Write-Output 'verdict=INPUT-ERROR'; Write-Output '  - file not found'; exit 3 }
if (-not [string]::IsNullOrEmpty($New) -and [string]::IsNullOrEmpty($Old)) {
  Write-Output 'verdict=INPUT-ERROR'; Write-Output '  - -New given without -Old: nothing to anchor the edit to'; exit 3
}
try { $enc = Get-PageEncoding $Page } catch { Write-Output ("verdict=INPUT-ERROR"); Write-Output ("  - {0}" -f $_.Exception.Message); exit 3 }

$bytes = [IO.File]::ReadAllBytes($Path)
$verdict = 'SAFE'; $reasons = New-Object System.Collections.Generic.List[string]

# ---- R1: whole-file round trip --------------------------------------------
$text = $null
try { $text = $enc.GetString($bytes) } catch { $verdict = 'UNSAFE'; $reasons.Add('decode-failed: bytes are not valid in this page') }
if ($verdict -eq 'SAFE') {
  $rt = $enc.GetBytes($text)
  $same = ($rt.Length -eq $bytes.Length)
  if ($same) { for ($i = 0; $i -lt $bytes.Length; $i++) { if ($bytes[$i] -ne $rt[$i]) { $same = $false; break } } }
  if ($same) { $reasons.Add(("round-trip-identical: {0} bytes preserved" -f $bytes.Length)) }
  else { $verdict = 'UNSAFE'; $reasons.Add(("round-trip-changed-bytes: {0} -> {1}" -f $bytes.Length, $rt.Length)) }
}

# ---- advisory only: strict decode in the assumed page ----------------------
if ($Page -eq 'gbk') {
  try { [void](Get-PageEncoding 'gbk').GetString($bytes); $reasons.Add('advisory strict-gbk-decode: OK (does NOT prove the file is GBK)') }
  catch { $reasons.Add('advisory strict-gbk-decode: FAILED (assumption is definitely wrong)'); $verdict = 'UNSAFE' }
}

# ---- R2/R3: the actual edit ------------------------------------------------
if ($verdict -eq 'SAFE' -and $Old.Length -gt 0) {
  if (-not $text.Contains($Old)) { $verdict = 'UNSAFE'; $reasons.Add('anchor-not-found-in-decoded-text') }
  else {
    $newText = $text.Replace($Old, $New)
    try { $newBytes = $enc.GetBytes($newText) } catch { $verdict = 'UNSAFE'; $reasons.Add('new-text-not-encodable-in-this-page'); $newBytes = $null }
    if ($null -ne $newBytes) {
      $back = $enc.GetString($newBytes)
      if ($back -ne $newText) { $verdict = 'UNSAFE'; $reasons.Add('new-chars-not-representable-in-this-page (text would be mangled)') }
      else {
        $reasons.Add('new-chars-round-trip: OK')
        # Byte-identical regions before AND after the edit prove the surrounding
        # text was not reinterpreted, even when the page was only assumed.
        $at = $text.IndexOf($Old)
        $prefixBytes = $enc.GetBytes($text.Substring(0, $at))
        $okPre = $prefixBytes.Length -le $newBytes.Length
        if ($okPre) { for ($i = 0; $i -lt $prefixBytes.Length; $i++) { if ($prefixBytes[$i] -ne $newBytes[$i]) { $okPre = $false; break } } }
        if ($okPre) { $reasons.Add('prefix-bytes-identical-around-edit') } else { $verdict = 'UNSAFE'; $reasons.Add('prefix-bytes-changed-around-edit') }
        $oldSuffix = $text.Substring($at + $Old.Length)
        $suffixBytes = $enc.GetBytes($oldSuffix)
        $okSuf = $suffixBytes.Length -le $newBytes.Length
        if ($okSuf) {
          $from = $newBytes.Length - $suffixBytes.Length
          for ($i = 0; $i -lt $suffixBytes.Length; $i++) { if ($suffixBytes[$i] -ne $newBytes[$from + $i]) { $okSuf = $false; break } }
        }
        if ($okSuf) { $reasons.Add('suffix-bytes-identical-around-edit') } else { $verdict = 'UNSAFE'; $reasons.Add('suffix-bytes-changed-around-edit') }
      }
    }
  }
}

Write-Output ("verdict={0}" -f $verdict)
foreach ($r in $reasons) { Write-Output ("  - {0}" -f $r) }
if ($verdict -eq 'SAFE') { exit 0 } else { exit 1 }
