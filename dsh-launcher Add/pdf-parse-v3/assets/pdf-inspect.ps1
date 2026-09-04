# pdf-inspect.ps1 -- PDF triage: classify document as text / scanned / hybrid.
#   . (Join-Path $PSScriptRoot 'lib.ps1') is dot-sourced inside.
# Usage: pwsh -File pdf-inspect.ps1 -Pdf <file.pdf> [-OutFile report.json]
# Prints ASCII summary; writes UTF-8 JSON report (text + per-page verdicts).
param(
  [Parameter(Mandatory = $true)][string]$Pdf,
  [string]$OutFile = '',
  [int]$Samples = 5
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')

if (-not (Test-Path $Pdf)) { Write-Output "ERROR pdf_not_found: $Pdf"; exit 2 }
$pdfAbs = (Resolve-Path $Pdf).Path
if (-not $OutFile) { $OutFile = $pdfAbs + '.triage.json' }

$py = Find-Py
if (-not $py) { Write-Output 'ERROR python_not_found (set DSH_PYTHON or install ~/.dsh/runtime/python*)'; exit 3 }
if (-not (Ensure-PyPdf $py)) { Write-Output 'ERROR pypdf_unavailable_after_auto_install'; exit 3 }
$probe = Join-Path $PSScriptRoot 'pdf_text_probe.py'
$r = Invoke-Capture $py @($probe, $pdfAbs, '--samples', "$Samples")
if ($r.ExitCode -ne 0) {
  Write-Output ("ERROR probe_exit {0}: {1}" -f $r.ExitCode, $r.Stderr.Trim())
  exit 4
}
$data = $null
try { $data = $r.Stdout | ConvertFrom-Json } catch {}
if (-not $data -or $data.error) {
  Write-Output ("ERROR probe_json: {0}" -f ($r.Stdout.Trim()))
  exit 4
}

$textPages = @(); $imagePages = @(); $pseudoPages = @()
foreach ($pg in $data.pages) {
  switch ($pg.verdict) {
    'text'  { $textPages += $pg.page; break }
    'pseudo' { $pseudoPages += $pg.page; break }
    default { $imagePages += $pg.page }
  }
}
$sampled = @($data.pages).Count
$nText = $textPages.Count
$nImg = $imagePages.Count + $pseudoPages.Count

if ($sampled -eq 0) { $verdict = 'unreadable' }
elseif ($nImg -eq 0) { $verdict = 'text' }
elseif ($nText -eq 0) { $verdict = 'scanned' }
else { $verdict = 'hybrid' }

$report = [ordered]@{
  file      = $pdfAbs
  page_count = $data.page_count
  encrypted = $data.encrypted
  producer  = $data.producer
  verdict   = $verdict
  sampled   = $sampled
  text_pages_sampled = ($textPages -join ',')
  image_pages_sampled = (($imagePages + $pseudoPages) -join ',')
  pages     = $data.pages
  note      = 'Sampled pages only. Use pdf-extract for exact per-page routing.'
}
$json = $report | ConvertTo-Json -Depth 6
Save-Utf8 $OutFile $json
Write-Output ("VERDICT {0} | pages={1} sampled={2} text={3} image+pseudo={4} | out={5}" -f `
  $verdict, $data.page_count, $sampled, $nText, $nImg, $OutFile)
if ($data.encrypted) { Write-Output 'WARN pdf_encrypted (text probe may be partial)' }
if ($data.producer)  { Write-Output ("producer: {0}" -f $data.producer) }
