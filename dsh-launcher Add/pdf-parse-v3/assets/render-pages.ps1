# render-pages.ps1 -- PDF pages -> PNG files (PS 5.1, WinRT Windows.Data.Pdf).
#   . (Join-Path $PSScriptRoot 'lib.ps1') may be dot-sourced; standalone works too.
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File render-pages.ps1 `
#          -Pdf <file.pdf> -OutDir <dir> [-Pages "1-3,5"] [-TargetWidth 2480]
# Writes page_0001.png ... Console prints ASCII progress lines.
param(
  [Parameter(Mandatory = $true)][string]$Pdf,
  [Parameter(Mandatory = $true)][string]$OutDir,
  [string]$Pages = '',
  [int]$TargetWidth = 2480
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

[void][Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
[void][Windows.Storage.StorageFolder, Windows.Storage, ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
[void][Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime]
[void][Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapEncoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
})[0]

function AwaitOp($op, [Type]$t) { $m = $asTaskGeneric.MakeGenericMethod($t); $task = $m.Invoke($null, @($op)); $null = $task.Wait(-1); $task.Result }
function AwaitAction($op) { $task = $asTaskAction.Invoke($null, @($op)); $null = $task.Wait(-1) }

function Expand-Pages([string]$spec, [int]$count) {
  $out = New-Object System.Collections.Generic.List[int]
  if ([string]::IsNullOrWhiteSpace($spec)) { for ($p = 1; $p -le $count; $p++) { $out.Add($p) }; return $out }
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

if (-not (Test-Path -LiteralPath $Pdf)) { Write-Output 'ERROR pdf_not_found'; exit 2 }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$pdfFile = AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path -LiteralPath $Pdf).Path)) ([Windows.Storage.StorageFile])
$doc = AwaitOp ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($pdfFile)) ([Windows.Data.Pdf.PdfDocument])
$count = [int]$doc.PageCount
$wanted = Expand-Pages $Pages $count
$folder = AwaitOp ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync((Resolve-Path -LiteralPath $OutDir).Path)) ([Windows.Storage.StorageFolder])

foreach ($pno in $wanted) {
  $page = $doc.GetPage($pno - 1)
  try {
    $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $options.DestinationWidth = [uint32]$TargetWidth
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    AwaitAction ($page.RenderToStreamAsync($stream, $options))
    $null = $stream.Seek(0)
    $decoder = AwaitOp ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = AwaitOp ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $name = ('page_{0:d4}.png' -f $pno)
    $file = AwaitOp ($folder.CreateFileAsync($name, [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])
    $fs = AwaitOp ($file.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
    $enc = AwaitOp ([Windows.Graphics.Imaging.BitmapEncoder]::CreateAsync([Windows.Graphics.Imaging.BitmapEncoder]::PngEncoderId, $fs)) ([Windows.Graphics.Imaging.BitmapEncoder])
    $enc.SetSoftwareBitmap($bmp)
    AwaitAction ($enc.FlushAsync())
    $fs.Dispose()
    Write-Output ("ok page {0} {1}x{2}" -f $pno, $bmp.PixelWidth, $bmp.PixelHeight)
  } catch {
    Write-Output ("FAIL page {0}: {1}" -f $pno, $_.Exception.Message)
  } finally {
    try { $page.Dispose() } catch {}
  }
}
Write-Output 'DONE'
