# run-tests.ps1 -- four-layer self test for pdf-parse-v3 skill (ASCII only).
# Layers: L1 syntax/imports, L2 environment probes, L3 offline unit (PDFs),
#         L4 live smoke (official standard sites; SKIP on network failure).
# Usage:  powershell -NoProfile -File tests\run-tests.ps1
$ErrorActionPreference = 'Continue'
$skill = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $skill 'assets'
$pass = 0; $fail = 0; $skip = 0
function Report([string]$name, [bool]$ok, [string]$detail = '') {
  $tag = if ($ok) { 'PASS' } else { 'FAIL' }
  if (-not $ok) { $script:fail++ } else { $script:pass++ }
  Write-Output ("[{0}] {1} {2}" -f $tag, $name, $detail)
}
function ReportSkip([string]$name, [string]$detail) {
  $script:skip++
  Write-Output ("[SKIP] {0} {1}" -f $name, $detail)
}

# ---------- environment helpers ----------
$wbpy = $null
if ($env:DSH_PYTHON -and (Test-Path $env:DSH_PYTHON)) { $wbpy = $env:DSH_PYTHON }
if (-not $wbpy) {
  $rtDir = Join-Path $env:USERPROFILE '.dsh\runtime'
  if (Test-Path $rtDir) {
    $ver = Get-ChildItem $rtDir -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'python*' } | Sort-Object Name -Descending | Select-Object -First 1
    if ($ver) { $cand = Join-Path $ver.FullName 'python.exe'; if (Test-Path $cand) { $wbpy = $cand } }
  }
}
if (-not $wbpy) { $cmd = Get-Command python -ErrorAction SilentlyContinue; if ($cmd) { $wbpy = $cmd.Source } }
$ps51 = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$work = Join-Path $env:TEMP ('gbstd_test_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null

# ---------- L1: syntax ----------
$psScripts = @('pdf-inspect.ps1', 'pdf-extract.ps1', 'winrt-ocr.ps1', 'render-pages.ps1', 'lib.ps1')
foreach ($s in $psScripts) {
  $p = Join-Path $assets $s
  try { $null = [scriptblock]::Create((Get-Content -Raw -LiteralPath $p)); Report "syntax $s" $true } catch { Report "syntax $s" $false $_.Exception.Message }
}
if ($wbpy) {
  & $wbpy -m py_compile (Join-Path $assets 'pdf_text_probe.py') 2>$null
  Report 'py_compile pdf_text_probe' ($LASTEXITCODE -eq 0)
} else { ReportSkip 'py_compile' 'python not found' }

# ---------- L2: environment ----------
$pyOk = $false
if ($wbpy) { & $wbpy -c "import pypdf" 2>$null; $pyOk = ($LASTEXITCODE -eq 0) }
Report 'pypdf importable' $pyOk
$ce = & (Join-Path $skill 'assets\check-env.ps1') 2>&1 | Out-String
Report 'check-env self-check (fail=0)' (($ce -match 'RESULT ok=.* fail=0'))
$rapidOk = $false
if ($wbpy) { & $wbpy -c "import rapidocr_onnxruntime" 2>$null; $rapidOk = ($LASTEXITCODE -eq 0) }
Report 'RapidOCR importable (production engine)' $rapidOk
$ocrLang = ''
if (Test-Path $ps51) {
  $probe = '[void][Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]; $l=[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }; $l -join '','''
  $ocrLang = (& $ps51 -NoProfile -Command $probe 2>$null | Out-String).Trim()
  Report 'WinRT OCR zh-Hans' ($ocrLang -match 'zh-Hans')
} else { ReportSkip 'WinRT OCR' 'PS 5.1 not found' }

# v3.0 structured builder unit tests (pdf2v3.py)
if ($wbpy) {
  $v3out = & $wbpy (Join-Path $skill 'tests\test_pdf2v3.py') 2>&1 | Out-String
  Report 'pdf2v3 unit tests' (($v3out -match 'RESULT pass all') -and ($v3out -notmatch 'FAIL'))
  if ($v3out -match 'FAIL') { $v3out -split "`n" | Where-Object { $_ -match '^FAIL' } | Select-Object -First 8 | ForEach-Object { Write-Output ('    ' + $_) } }
  $lout = & $wbpy (Join-Path $skill 'tests\test_layout.py') 2>&1 | Out-String
  Report 'layout engine tests (pymupdf)' (($lout -match 'RESULT pass all') -and ($lout -notmatch 'FAIL'))
  if ($lout -match 'FAIL') { $lout -split "`n" | Where-Object { $_ -match '^FAIL' } | Select-Object -First 8 | ForEach-Object { Write-Output ('    ' + $_) } }
  if ($rapidOk) {
    $rres = & $wbpy (Join-Path $skill 'tests\test_rapid_resume.py') 2>&1 | Out-String
    Report 'rapid resume/checkpoint tests' (($rres -match 'RESULT pass all') -and ($rres -notmatch 'FAIL'))
    if ($rres -match 'FAIL') { $rres -split "`n" | Where-Object { $_ -match '^FAIL' } | Select-Object -First 8 | ForEach-Object { Write-Output ('    ' + $_) } }
  }
}

# RapidOCR functional smoke: recognize a digit image (production engine)
if ($rapidOk) {
  $digPng = Join-Path $work 'rapid_digits.png'
  try {
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap 900, 300
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)
    $f = New-Object System.Drawing.Font('Arial', 120, [System.Drawing.FontStyle]::Bold)
    $g.DrawString('24680', $f, [System.Drawing.Brushes]::Black, 60, 60)
    $g.Dispose()
    $bmp.Save($digPng, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
  } catch { }
  if (Test-Path $digPng) {
    $ro = & $wbpy (Join-Path $skill 'tests\test_rapid_ocr.py') $digPng 2>&1 | Out-String
    Report 'RapidOCR single-image smoke' (($ro -match 'PASS') -and ($ro -notmatch 'FAIL'))
  } else { ReportSkip 'RapidOCR smoke' 'png not created' }
}

# ---------- L3: offline PDF unit tests ----------
if ($wbpy) {
  & $wbpy (Join-Path $skill 'tests\make_test_pdfs.py') $work 2>$null
  # image source for t_img.pdf
  try {
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap 900, 500
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)
    $f = New-Object System.Drawing.Font('Arial', 64)
    $g.DrawString('Hello OCR 12345', $f, [System.Drawing.Brushes]::Black, 60, 180)
    $g.Dispose()
    $bmp.Save((Join-Path $work 't_img_src.jpg'), [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $bmp.Dispose()
    & $wbpy (Join-Path $skill 'tests\make_test_pdfs.py') $work 2>$null
  } catch { }
  foreach ($case in @(@('t_text', 'text'), @('t_hybrid', 'hybrid'), @('t_img', 'scanned'), @('t_short', 'text'))) {
    $pdf = Join-Path $work ($case[0] + '.pdf')
    if (Test-Path $pdf) {
      $o = & (Join-Path $assets 'pdf-inspect.ps1') -Pdf $pdf -OutFile (Join-Path $work ($case[0] + '.json')) 2>&1 | Out-String
      Report "triage $($case[0]) = $($case[1])" ($o -match ("VERDICT " + $case[1]))
    }
  }
  $tS = Join-Path $work 't_short.pdf'
  if (Test-Path $tS) {
    $o = & (Join-Path $assets 'pdf-extract.ps1') -Pdf $tS -OutTxt (Join-Path $work 'short.txt') -OutJson (Join-Path $work 'short.json') 2>&1 | Out-String
    $txt = [IO.File]::ReadAllText((Join-Path $work 'short.txt'), [Text.Encoding]::UTF8)
    Report 'extract short-text page exact' (($o -match 'DONE text=1 ocr=0') -and ($txt -match 'Short title page'))
  }
  $tH = Join-Path $work 't_hybrid.pdf'
  if (Test-Path $tH) {
    $o = & (Join-Path $assets 'pdf-extract.ps1') -Pdf $tH -OutTxt (Join-Path $work 'hy.txt') -OutJson (Join-Path $work 'hy.json') 2>&1 | Out-String
    Report 'extract hybrid text=1 ocr=1' ($o -match 'DONE text=1 ocr=1')
    $txt = [IO.File]::ReadAllText((Join-Path $work 'hy.txt'), [Text.Encoding]::UTF8)
    Report 'extract page1 content hello' ($txt -match 'Hello PDF 2026')
  }
  $tI = Join-Path $work 't_img.pdf'
  if (Test-Path $tI) {
    $o = & (Join-Path $assets 'pdf-extract.ps1') -Pdf $tI -OutTxt (Join-Path $work 'img.txt') -OutJson (Join-Path $work 'img.json') 2>&1 | Out-String
    $txt = if (Test-Path (Join-Path $work 'img.txt')) { [IO.File]::ReadAllText((Join-Path $work 'img.txt'), [Text.Encoding]::UTF8) } else { '' }
    Report 'extract image-only ocr content' (($o -match 'DONE text=0 ocr=1') -and ($txt -match '12345'))
  }
  $tT = Join-Path $work 't_text.pdf'
  if ((Test-Path $tT) -and (Test-Path $ps51)) {
    $ocrOut = Join-Path $work 'ocr'
    New-Item -ItemType Directory -Force -Path $ocrOut | Out-Null
    $o = & $ps51 -NoProfile -ExecutionPolicy Bypass -File (Join-Path $assets 'winrt-ocr.ps1') -Pdf $tT -Pages '1' -OutDir $ocrOut 2>&1 | Out-String
    $f = Get-ChildItem $ocrOut -Filter '*.txt' | Select-Object -First 1
    $t = if ($f) { [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::UTF8) } else { '' }
    Report 'winrt ocr recognizes text' (($o -match 'ok page 1') -and ($t -match 'PDF|Hello|2026'))
  }
} else { ReportSkip 'offline pdf tests' 'python not found' }

# (live official-source smoke moved to skill: std-official-search)

Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
# tidy: python compiles pyc next to sources when tests run
Get-ChildItem (Join-Path $skill 'assets') -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem (Join-Path $skill 'tests') -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Write-Output ("RESULT pass={0} fail={1} skip={2}" -f $pass, $fail, $skip)
if ($fail -gt 0) { exit 1 }
exit 0
