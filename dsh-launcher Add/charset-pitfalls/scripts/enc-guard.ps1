# Encoding guard entry point (charset-pitfalls G0).
#
# One command, three protocol steps:
#   -Action detect   -> probe + candidate ladder; prints ranked evidence
#   -Action decide   -> choose a pre-decided route; exit 0 = safe to write, 2 = report only
#   -Action confirm  -> byte-level lossless check before writing
#
# Dispatches to sibling scripts resolved from this file's own directory, so the
# whole skill folder can be copied anywhere and still work.
#
# Pure ASCII on purpose: a BOM-less .ps1 carrying Chinese is decoded as GBK by
# Windows PowerShell 5.1 and mangles its own literals -- the failure this gate
# exists to prevent. ($args is a reserved automatic variable and must not be used.)
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('detect','decide','confirm')][string]$Action,
  [Parameter(Mandatory=$true)][string]$Path,
  [string]$Page = '',
  [string]$Old = '',
  [string]$New = '',
  [int]$MinBytesForConvert = 64,
  [int]$MinScoreMargin = 15
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Assert-Sibling([string]$file) {
  $full = Join-Path $root $file
  if (-not (Test-Path -LiteralPath $full)) { throw "missing sibling script: $full" }
  return $full
}

if ($Action -eq 'detect') {
  # Step 1: fast probe. It settles BOM / ASCII / strong-UTF-8 / legacy cases and
  # only leaves the genuinely undecided ones (BOM-less UTF-16, odd legacy pages)
  # for the ladder -- so the expensive resolution runs only when it is needed.
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Assert-Sibling 'enc-probe.ps1') -Path $Path
  $probeOut = @($LASTEXITCODE)
  $rc1 = $LASTEXITCODE
  $needsLadder = $true
  # Re-run the probe capturing its text so the decision is based on its verdict.
  $probeText = (& powershell -NoProfile -ExecutionPolicy Bypass -File (Assert-Sibling 'enc-probe.ps1') -Path $Path 2>&1) -join ' '
  if ($probeText -match 'enc=(ASCII|UTF8-BOM|UTF16-LE|UTF16-BE)') { $needsLadder = $false }
  elseif ($probeText -match 'enc=UTF8-NOBOM') { $needsLadder = $false }
  if ($needsLadder) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Assert-Sibling 'enc-resolve.ps1') -Path $Path
  }
  exit 0
}

if ($Action -eq 'decide') {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Assert-Sibling 'enc-decide.ps1') `
    -Path $Path -MinBytesForConvert $MinBytesForConvert -MinScoreMargin $MinScoreMargin
  exit $LASTEXITCODE
}

if ($Action -eq 'confirm') {
  if ([string]::IsNullOrEmpty($Page)) { throw '-Action confirm requires -Page' }
  # Empty -Old/-New must NOT be forwarded: PowerShell treats '-Old ""' as a
  # missing argument and the child then fails on parameter binding.
  $childArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Assert-Sibling 'enc-write-check.ps1'), '-Path', $Path, '-Page', $Page)
  if (-not [string]::IsNullOrEmpty($Old)) { $childArgs += @('-Old', $Old) }
  if (-not [string]::IsNullOrEmpty($New)) { $childArgs += @('-New', $New) }
  & powershell @childArgs
  exit $LASTEXITCODE
}

exit 1
