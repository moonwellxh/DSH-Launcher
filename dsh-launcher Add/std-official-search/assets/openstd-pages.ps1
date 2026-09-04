# openstd-pages.ps1 -- best-effort full-text page download from 国家标准全文公开系统.
#   openstd serves scanned page images through a JS viewer (anti-bot). This script
#   replays the browser URL chain with a cookie jar and parses page image URLs.
#   If the viewer refuses (returns an error page), it fails with a clear message
#   and writes the canonical viewer URL so a human can open it manually.
#   . (Join-Path $PSScriptRoot 'lib-search.ps1') is dot-sourced inside.
# Usage: pwsh openstd-pages.ps1 -Hcno <32hex> [-OutDir dir]
param(
  [Parameter(Mandatory = $true)][string]$Hcno,
  [string]$OutDir = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib-search.ps1')
if ($Hcno -notmatch '^[0-9A-F]{32}$') { Write-Output 'ERROR hcno must be 32 hex (openstd search -> hcno)'; exit 2 }
if (-not $OutDir) { $OutDir = Join-Path (Get-Location) ('stdpages_' + $Hcno.Substring(0, 8)) }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0'
$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
$jar = Join-Path $OutDir 'cookies.txt'
$work = Join-Path $OutDir '_tmp'
New-Item -ItemType Directory -Force -Path $work | Out-Null

# 1) seed cookies from detail page
& $curl -s -L --max-time 45 -A $UA -c $jar -o (Join-Path $work 'info.html') `
  ("https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=" + $Hcno) | Out-Null
$viewer = "https://openstd.samr.gov.cn/bzgk/std/showGb?type=online&hcno=$Hcno&request_locale=zh-CN"
$ref = "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=$Hcno"

$cands = @(
  $viewer,
  "https://openstd.samr.gov.cn/bzgk/std/showGb?type=download&hcno=$Hcno&request_locale=zh-CN",
  "http://c.gb688.cn/bzgk/std/showGb?type=online&hcno=$Hcno",
  "https://c.gb688.cn/bzgk/std/showGb?type=online&hcno=$Hcno"
)

$got = $null
foreach ($u in $cands) {
  $f = Join-Path $work ('viewer_' + $cands.IndexOf($u) + '.html')
  & $curl -s -L --max-time 60 -A $UA -b $jar -e $ref -o $f $u | Out-Null
  if (-not (Test-Path $f)) { continue }
  $html = Read-Utf8 $f
  if ($html -match 'class="page"' -or $html -match 'pdfImg') {
    $got = @{ url = $u; html = $html }
    break
  }
}

if (-not $got) {
  $msg = 'openstd viewer refused automated access (JS anti-bot). Open manually: ' + $viewer
  Save-Utf8 (Join-Path $OutDir 'status.json') (@{ ok = $false; hcno = $Hcno; message = $msg; viewer_url = $viewer } | ConvertTo-Json)
  Write-Output ("ERROR " + $msg)
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
  exit 3
}

# parse page background tokens (one per div.page opening tag)
$pages = @()
foreach ($dm in [regex]::Matches($got.html, '<div\b[^>]*\bclass="page"[^>]*>')) {
  $tag = $dm.Value
  $idM = [regex]::Match($tag, '\bid="(\d+)"')
  $bgM = [regex]::Match($tag, '\bbg="([^"]+)"')
  if (-not $bgM.Success) { continue }
  $pages += [ordered]@{
    no = if ($idM.Success) { [int]$idM.Groups[1].Value } else { $pages.Count + 1 }
    token = $bgM.Groups[1].Value
  }
}
$pages = @($pages | Sort-Object no)

if ($pages.Count -eq 0) {
  $msg = 'viewer page parse found no images; open manually: ' + $viewer
  Save-Utf8 (Join-Path $OutDir 'status.json') (@{ ok = $false; hcno = $Hcno; message = $msg; viewer_url = $viewer } | ConvertTo-Json)
  Write-Output ("ERROR " + $msg)
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
  exit 4
}

# image endpoint is relative to the viewer: <origin>/bzgk/std/viewGbImg?fileName=<token>
$base = [regex]::Match($got.url, '^(https?://[^/]+/[^/]+/)').Groups[1].Value

function Test-ImageBytes([string]$path) {
  # RIFF(webp) FF D8(jpg) 89 50 4E 47(png) else HTML/error body
  try {
    $b = [System.IO.File]::ReadAllBytes($path)
    if ($b.Length -lt 12) { return $false }
    if ($b[0] -eq 0x52 -and $b[1] -eq 0x49 -and $b[2] -eq 0x46 -and $b[3] -eq 0x46) { return $true }
    if ($b[0] -eq 0xFF -and $b[1] -eq 0xD8) { return $true }
    if ($b[0] -eq 0x89 -and $b[1] -eq 0x50 -and $b[2] -eq 0x4E -and $b[3] -eq 0x47) { return $true }
    return $false
  } catch { return $false }
}

$okFiles = New-Object System.Collections.Generic.List[string]
$failPages = 0
foreach ($p in $pages) {
  $out = Join-Path $OutDir ('page_{0:d4}.img' -f $p.no)
  $u = $base + 'viewGbImg?fileName=' + $p.token
  & $curl -s -L --max-time 90 -A $UA -b $jar -e $got.url -H "Cache-Alive: chunked" -o $out $u | Out-Null
  $sz = (Get-Item $out -ErrorAction SilentlyContinue).Length
  if ($sz -gt 0 -and (Test-ImageBytes $out)) {
    $okFiles.Add($out)
    Write-Output ("page {0} ok {1}b" -f $p.no, $sz)
  } else {
    Remove-Item $out -Force -ErrorAction SilentlyContinue
    $failPages++
    Write-Output ("page {0} BLOCKED-or-error (not an image; anti-bot likely)" -f $p.no)
  }
  Start-Sleep -Milliseconds 350
}

# OCR step moved to skill pdf-parse-v3 (winrt-ocr.ps1 lives there).
# Hand off: write ocr_images.txt so the user/agent can run:
#   pdf-parse-v3: powershell.exe -File winrt-ocr.ps1 -ListFile ocr_images.txt -OutDir ocr
if ($okFiles.Count -gt 0) {
  $listFile = Join-Path $OutDir 'ocr_images.txt'
  Save-Utf8 $listFile (($okFiles -join "`r`n"))
  Write-Output ("hint: OCR 页图请用 pdf-parse-v3: winrt-ocr.ps1 -ListFile " + $listFile)
}

$allFail = ($pages.Count -gt 0 -and $okFiles.Count -eq 0)
$meta = @{ ok = (-not $allFail); hcno = $Hcno; page_count = $pages.Count; downloaded_ok = $okFiles.Count; fail_or_blocked = $failPages; viewer_url = $got.url; pages = $pages }
Save-Utf8 (Join-Path $OutDir 'pages.json') ($meta | ConvertTo-Json -Depth 4)
if ($allFail) {
  Write-Output ("WARN openstd viewer blocked bulk image fetch (anti-bot). Open manually: " + $viewer)
  Write-Output ("  OCR 已下载页可用: powershell.exe -File winrt-ocr.ps1 -ListFile <out>\ocr_images.txt -OutDir <out>\ocr")
}
Write-Output ("DONE pages=" + $pages.Count + " ok=" + $okFiles.Count + " fail=" + $failPages + " out=" + $OutDir)
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
