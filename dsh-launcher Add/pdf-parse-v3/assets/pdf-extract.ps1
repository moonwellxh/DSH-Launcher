# pdf-extract.ps1 -- read a PDF with per-page strategy routing:
#   text-layer pages  -> pypdf direct extraction (fast, exact)
#   image/pseudo pages -> Windows-native OCR (zh-Hans-CN via WinRT, PS 5.1)
#   . (Join-Path $PSScriptRoot 'lib.ps1') is dot-sourced inside.
# Usage: pwsh -File pdf-extract.ps1 -Pdf <file.pdf> [-OutTxt out.txt] [-OutJson manifest.json]
param(
  [Parameter(Mandatory = $true)][string]$Pdf,
  [string]$OutTxt = '',
  [string]$OutJson = '',
  [switch]$IncludeText
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib.ps1')

if (-not (Test-Path $Pdf)) { Write-Output "ERROR pdf_not_found: $Pdf"; exit 2 }
$pdfAbs = (Resolve-Path $Pdf).Path
if (-not $OutTxt) { $OutTxt = $pdfAbs + '.extract.txt' }
if (-not $OutJson) { $OutJson = $pdfAbs + '.extract.json' }

$work = Join-Path $env:TEMP ('gbstd_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null
$txtDir = Join-Path $work 'textpages'
$ocrDir = Join-Path $work 'ocrpages'
New-Item -ItemType Directory -Force -Path $txtDir, $ocrDir | Out-Null

$py = Find-Py
if (-not $py) { Write-Output 'ERROR python_not_found (set DSH_PYTHON or install ~/.dsh/runtime/python*)'; exit 3 }
if (-not (Ensure-PyPdf $py)) { Write-Output 'ERROR pypdf_unavailable_after_auto_install'; exit 3 }
$probe = Join-Path $PSScriptRoot 'pdf_text_probe.py'
$r = Invoke-Capture $py @($probe, $pdfAbs, '--all', '--outdir', $txtDir)
if ($r.ExitCode -ne 0) {
  Write-Output ("ERROR probe_exit {0}: {1}" -f $r.ExitCode, $r.Stderr.Trim())
  exit 4
}
$data = $null
try { $data = $r.Stdout | ConvertFrom-Json } catch {}
if (-not $data -or $data.error) { Write-Output 'ERROR probe_failed'; exit 4 }
if ($data.encrypted) {
  # WinRT would need a password too; surface clearly instead of guessing.
  Write-Output 'ERROR pdf_encrypted_no_password_support'
  exit 5
}

$ocrPages = New-Object System.Collections.Generic.List[int]
$perPage = @()
foreach ($pg in $data.pages) {
  $method = if ($pg.verdict -eq 'text') { 'text' } else { 'ocr' }
  if ($method -eq 'ocr') { $ocrPages.Add([int]$pg.page) }
  $perPage += [ordered]@{ page = $pg.page; method = $method; printable = $pg.printable; ratio = $pg.ratio }
}

if ($ocrPages.Count -gt 0) {
  $ps51 = Find-Explorer
  if (-not $ps51) { Write-Output 'ERROR powershell_5.1_not_found_for_ocr'; exit 6 }
  $helper = Join-Path $PSScriptRoot 'winrt-ocr.ps1'
  $pagesSpec = ($ocrPages -join ',')
  $hr = Invoke-Capture $ps51 @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $helper,
                               '-Pdf', $pdfAbs, '-Pages', $pagesSpec, '-OutDir', $ocrDir)
  if ($hr.ExitCode -ne 0) {
    Write-Output ("ERROR ocr_exit {0}: {1}" -f $hr.ExitCode, ($hr.Stderr + $hr.Stdout))
    exit 7
  }
}

# merge in page order
$sb = New-Object System.Text.StringBuilder
$pageTexts = @()
foreach ($entry in $perPage) {
  $pno = $entry.page
  $srcFile = Join-Path $txtDir ('page_{0:d4}.txt' -f $pno)
  if ($entry.method -eq 'ocr') { $srcFile = Join-Path $ocrDir ('page_{0:d4}.txt' -f $pno) }
  $content = ''
  if (Test-Path $srcFile) {
    $content = (Read-Utf8 $srcFile) -replace "`r`n", "`n"
    $content = $content.TrimEnd("`n")
  }
  if ($IncludeText) {
    $pageTexts += [ordered]@{ page = $pno; method = $entry.method; chars = $content.Length; text = $content }
  }
  [void]$sb.AppendLine('')
  [void]$sb.AppendLine(('===== Page {0} | source: {1} =====' -f $pno, $entry.method))
  if ($content) { [void]$sb.AppendLine($content) }
}
$fullText = $sb.ToString()
Save-Utf8 $OutTxt $fullText

$manifest = [ordered]@{
  file      = $pdfAbs
  page_count = $data.page_count
  output    = $OutTxt
  pages     = $perPage
  summary   = [ordered]@{
    text_pages = (@($perPage | Where-Object { $_.method -eq 'text' })).Count
    ocr_pages  = (@($perPage | Where-Object { $_.method -eq 'ocr' })).Count
  }
}
if ($IncludeText) {
  $manifest.full_text = $fullText.TrimEnd("`n")
  $manifest.pages_text = $pageTexts
}
Save-Utf8 $OutJson ($manifest | ConvertTo-Json -Depth 6)
Write-Output ("DONE text={0} ocr={1} out={2}" -f $manifest.summary.text_pages, $manifest.summary.ocr_pages, $OutTxt)
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
