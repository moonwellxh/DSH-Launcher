# check-env.ps1 -- dependency self-check + one-shot install for pdf-parse-v3.
#   . (Join-Path $PSScriptRoot 'lib.ps1') is dot-sourced inside.
# Usage:
#   powershell -File assets\check-env.ps1            # check only
#   powershell -File assets\check-env.ps1 -Install   # check + pip install missing packages
# Prints ASCII [OK]/[MISS]/[WARN] lines and a final RESULT.
# Exit code: 0 = ready (warnings allowed), 2 = critical missing (python or a package).
param(
  [switch]$Install
)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lib.ps1')

$ok = 0; $warn = 0; $fail = 0
function Say([string]$tag, [string]$msg) {
  if ($tag -eq 'OK') { $script:ok++ } elseif ($tag -eq 'WARN') { $script:warn++ } else { $script:fail++ }
  Write-Output ("[{0}] {1}" -f $tag, $msg)
}

$PIP_MIRROR = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$REQUIRED = @('pypdf', 'rapidocr_onnxruntime', 'pymupdf', 'pdfplumber')

# ---- python ----
$py = Find-Py
if (-not $py) {
  Say 'FAIL' 'python: not found (need %USERPROFILE%\.dsh\runtime\python*\python.exe or set $env:DSH_PYTHON)'
} else {
  Say 'OK' ("python: {0}" -f $py)
  foreach ($m in $REQUIRED) {
    $chk = Invoke-Capture $py @('-c', "import $m")
    if ($chk.ExitCode -eq 0) {
      Say 'OK' ("package: {0}" -f $m)
    } elseif ($Install) {
      Say 'INFO' ("installing {0} (tsinghua mirror)..." -f $m)
      $r1 = Invoke-Capture $py @('-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-q', '-i', $PIP_MIRROR, $m)
      if ($r1.ExitCode -ne 0) {
        $r2 = Invoke-Capture $py @('-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-q', $m)
        if ($r2.ExitCode -ne 0) {
          Say 'FAIL' ("package: {0} (install failed)" -f $m)
          continue
        }
      }
      $re = Invoke-Capture $py @('-c', "import $m")
      if ($re.ExitCode -eq 0) { Say 'OK' ("package: {0} (installed)" -f $m) }
      else { Say 'FAIL' ("package: {0} (still not importable after install)" -f $m) }
    } else {
      Say 'MISS' ("package: {0} (run with -Install to auto-install)" -f $m)
    }
  }
}

# ---- windows runtime deps ----
$ps51 = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (Test-Path $ps51) {
  Say 'OK' 'powershell 5.1: present (WinRT render/OCR)'
  $probe = '[void][Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]; $l=[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }; ($l -join '','')'
  $r = & $ps51 -NoProfile -Command $probe 2>$null | Out-String
  if ($r -match 'zh-Hans') { Say 'OK' 'OCR language: zh-Hans-CN available' }
  else { Say 'WARN' 'OCR language: zh-Hans not installed (RapidOCR still works; WinRT zh degraded)' }
} else {
  Say 'WARN' 'powershell 5.1: missing (WinRT render/OCR unavailable; use external OCR input)'
}
$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) { Say 'OK' 'curl.exe: present (official-source search skill)' }
else { Say 'WARN' 'curl.exe: missing (std-official-search needs it)' }

Write-Output ("RESULT ok={0} warn={1} fail={2}" -f $ok, $warn, $fail)
if ($fail -gt 0) { exit 2 }
exit 0
