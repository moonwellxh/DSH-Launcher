# l0_tray_artifact_check.ps1 -- V4 deterministic checker for the generated tray script.
# Run with Windows PowerShell 5.1:
#   powershell.exe -NoProfile -File l0_tray_artifact_check.ps1 -Path <file> -MarkersCsv "标记1,标记2" -MinMenuItems 13
# Checks: UTF-8 BOM present; CRLF-only line endings; syntax parses (Parser API); required
#         Chinese markers present; no U+FFFD replacement char; menu-item count floor.
# -MarkersCsv is a single comma-separated string on purpose: passing a PowerShell array through
# `powershell.exe -File` flattens/joins args unpredictably (verified: array arrived comma-joined as one value).
# Output: one ASCII JSON line; exit 0 = pass, 1 = fail.
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$MarkersCsv = '',
    [int]$MinMenuItems = 0
)
$ErrorActionPreference = 'Stop'

$result = [ordered]@{
    path = $Path; exists = $false; bom = $false; crlf_only = $false
    syntax_errors = -1; markers_ok = @(); markers_missing = @()
    replacement_chars = -1; menu_items = -1; size = -1; exit = 1
}

if (-not (Test-Path -LiteralPath $Path)) { $result | ConvertTo-Json -Compress; exit 1 }
$result.exists = $true
$bytes = [System.IO.File]::ReadAllBytes($Path)
$result.size = $bytes.Length
$result.bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
$text = [System.Text.Encoding]::UTF8.GetString($bytes)
if ($result.bom) { $text = $text.Substring(1) }   # drop the BOM char so CRLF/marker checks are clean

$result.crlf_only = -not (($text -replace "`r`n", '') -match "`n")

$tokens = $null; $parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$parseErrors)
$result.syntax_errors = @($parseErrors).Count

$result.replacement_chars = ([regex]::Matches($text, [char]0xFFFD)).Count
$result.menu_items = ([regex]::Matches($text, '\$menu\.Items\.Add')).Count

$markers = @($MarkersCsv -split ',' | Where-Object { $_ -ne '' })
$ok = @(); $missing = @()
foreach ($m in $markers) { if ($text.Contains($m)) { $ok += $m } else { $missing += $m } }
$result.markers_ok = $ok
$result.markers_missing = $missing

$pass = $result.bom -and $result.crlf_only -and ($result.syntax_errors -eq 0) `
    -and ($result.replacement_chars -eq 0) -and ($missing.Count -eq 0) `
    -and ($MinMenuItems -eq 0 -or $result.menu_items -ge $MinMenuItems)
$result.exit = if ($pass) { 0 } else { 1 }
$result | ConvertTo-Json -Compress
exit $result.exit
