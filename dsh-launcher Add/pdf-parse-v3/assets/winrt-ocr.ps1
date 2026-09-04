#requires -version 5.1
<#
  winrt-ocr.ps1 -- Windows-native PDF page render + OCR (zh-Hans / en) using
  Windows.Data.Pdf + Windows.Media.Ocr. MUST run under Windows PowerShell 5.1
  (pwsh 7 has no WinRT projection). Invoke via powershell.exe -File.

  Modes:
    - Pdf    <file.pdf>  -Pages "1-3,5,7-9"   render pages then OCR
    - Images "a.png,b.jpg"                    OCR image files directly

  Writes one UTF-8 text file per page/image into -OutDir:
      page_0001.txt
  Console prints ASCII-only status lines.

  Zero external dependency: uses OS WinRT. OCR language zh-Hans-CN preferred,
  falls back to en-US / user profile languages.
#>
param(
  [string]$Pdf = '',
  [string]$Pages = '',
  [string]$Images = '',
  [string]$ListFile = '',   # UTF-8 text file, one image path per line
  [Parameter(Mandatory = $true)][string]$OutDir
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Register WinRT projections so type literals resolve (PS 5.1 requirement).
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
[void][Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime]
[void][Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType=WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]

# ---- WinRT async plumbing (PS 5.1) ----
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
})[0]

function AwaitOp($op, [Type]$resultType) {
  $m = $asTaskGeneric.MakeGenericMethod($resultType)
  $task = $m.Invoke($null, @($op))
  $null = $task.Wait(-1)
  return $task.Result
}

function AwaitAction($op) {
  $task = $asTaskAction.Invoke($null, @($op))
  $null = $task.Wait(-1)
}

function Expand-Pages([string]$spec, [int]$count) {
  $out = New-Object System.Collections.Generic.List[int]
  if ([string]::IsNullOrWhiteSpace($spec)) { return $out }
  foreach ($part in ($spec -split ',')) {
    $part = $part.Trim()
    if ($part -match '^(\d+)-(\d+)$') {
      $a = [int]$Matches[1]; $b = [int]$Matches[2]
      if ($a -gt $b) { $t = $a; $a = $b; $b = $t }
      for ($p = $a; $p -le $b -and $p -le $count; $p++) { $out.Add($p) }
    } elseif ($part -match '^\d+$') {
      $p = [int]$part
      if ($p -ge 1 -and $p -le $count) { $out.Add($p) }
    }
  }
  return $out
}

function New-OcrEngine {
  $pref = @('zh-Hans-CN', 'zh-Hans', 'en-US')
  foreach ($tag in $pref) {
    try {
      $lang = New-Object Windows.Globalization.Language $tag
      $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
      if ($eng) { return $eng }
    } catch {}
  }
  return [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}

function Ocr-Bitmap($engine, $softwareBitmap) {
  $res = AwaitOp ($engine.RecognizeAsync($softwareBitmap)) ([Windows.Media.Ocr.OcrResult])
  $sb = New-Object System.Text.StringBuilder
  foreach ($line in $res.Lines) { [void]$sb.AppendLine($line.Text) }
  return $sb.ToString().TrimEnd("`r", "`n")
}

function Ocr-ImageFile($engine, [string]$path) {
  $file = AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
  $stream = AwaitOp ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = AwaitOp ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bmp = AwaitOp ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  return Ocr-Bitmap $engine $bmp
}

function Write-Out([string]$path, [string]$text) {
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

# ---- main ----
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

if ($Pdf -and (Test-Path $Pdf)) {
  $pdfFile = AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $Pdf).Path)) ([Windows.Storage.StorageFile])
  $doc = AwaitOp ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($pdfFile)) ([Windows.Data.Pdf.PdfDocument])
  $engine = New-OcrEngine
  if (-not $engine) { Write-Output 'ERROR no_ocr_engine'; exit 3 }
  $count = [int]$doc.PageCount
  $wanted = Expand-Pages $Pages $count
  if ($wanted.Count -eq 0) { for ($p = 1; $p -le $count; $p++) { $wanted.Add($p) } }
  Write-Output "pdf pages=$count ocr_lang=$($engine.RecognizerLanguage.LanguageTag) to_ocr=$($wanted.Count)"
  foreach ($pno in $wanted) {
    $page = $doc.GetPage($pno - 1)
    try {
      $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
      $options.DestinationWidth = [uint32]2200   # upscale for better OCR
      $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
      AwaitAction ($page.RenderToStreamAsync($stream, $options))
      $null = $stream.Seek(0)
      $decoder = AwaitOp ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
      $bmp = AwaitOp ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
      $text = Ocr-Bitmap $engine $bmp
      $outPath = Join-Path $OutDir ('page_{0:d4}.txt' -f $pno)
      Write-Out $outPath $text
      Write-Output ("ok page {0} chars {1}" -f $pno, $text.Length)
    } catch {
      Write-Output ("FAIL page {0}: {1}" -f $pno, $_.Exception.Message)
    } finally {
      try { $page.Dispose() } catch {}
    }
  }
} elseif ($Images -or $ListFile) {
  $engine = New-OcrEngine
  if (-not $engine) { Write-Output 'ERROR no_ocr_engine'; exit 3 }
  Write-Output "images ocr_lang=$($engine.RecognizerLanguage.LanguageTag)"
  $imgPaths = New-Object System.Collections.Generic.List[string]
  if ($ListFile) {
    foreach ($line in [System.IO.File]::ReadAllLines($ListFile, [System.Text.Encoding]::UTF8)) {
      $line = $line.Trim()
      if ($line) { $imgPaths.Add($line) }
    }
  } else {
    foreach ($img in ($Images -split ',')) {
      $img = $img.Trim().Trim('"')
      if ($img) { $imgPaths.Add($img) }
    }
  }
  $idx = 0
  foreach ($img in $imgPaths) {
    if (-not (Test-Path $img)) { Write-Output "SKIP missing $img"; continue }
    $idx++
    $text = Ocr-ImageFile $engine (Resolve-Path $img).Path
    $name = [System.IO.Path]::GetFileNameWithoutExtension($img)
    $outPath = Join-Path $OutDir ("img_{0}_{1}.txt" -f $idx, $name)
    Write-Out $outPath $text
    Write-Output ("ok img {0} chars {1}" -f $name, $text.Length)
  }
} else {
  Write-Output 'ERROR need -Pdf or -Images'
  exit 2
}
Write-Output 'DONE'
