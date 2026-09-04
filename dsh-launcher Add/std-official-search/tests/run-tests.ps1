# run-tests.ps1 -- self test for std-official-search skill (ASCII + minimal).
# L1 syntax; L2 live official-source smoke (skip on network failure).
$ErrorActionPreference = 'Continue'
$skill = Split-Path -Parent $PSScriptRoot
$pass = 0; $fail = 0; $skip = 0
function Report([string]$name, [bool]$ok, [string]$detail = '') {
  $tag = if ($ok) { 'PASS' } else { 'FAIL' }
  if (-not $ok) { $script:fail++ } else { $script:pass++ }
  Write-Output ("[{0}] {1} {2}" -f $tag, $name, $detail)
}
function ReportSkip([string]$name, [string]$detail) { $script:skip++; Write-Output ("[SKIP] {0} {1}" -f $name, $detail) }

foreach ($s in @('std-search.ps1', 'openstd-pages.ps1', 'lib-search.ps1')) {
  $p = Join-Path $skill "assets\$s"
  try { $null = [scriptblock]::Create((Get-Content -Raw -LiteralPath $p)); Report "syntax $s" $true } catch { Report "syntax $s" $false $_.Exception.Message }
}
$tmp = Join-Path $env:TEMP ('stdsearch_test_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
  $o = & (Join-Path $skill 'assets\std-search.ps1') -Mode samr -Query 'GB/T 14253' -OutFile (Join-Path $tmp 's.json') 2>&1 | Out-String
  $j = Get-Content (Join-Path $tmp 's.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  $hit = @($j.rows | Where-Object { $_.std_code -like '*14253*' -and $_.state -eq '现行' })
  Report 'live samr status truth' ($hit.Count -gt 0)
} catch { ReportSkip 'live samr' $_.Exception.Message }
try {
  $o = & (Join-Path $skill 'assets\std-search.ps1') -Mode openstd -Query '电动自行车' -OutFile (Join-Path $tmp 'o.json') 2>&1 | Out-String
  $j = Get-Content (Join-Path $tmp 'o.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  Report 'live openstd search' (@($j.rows).Count -gt 0)
} catch { ReportSkip 'live openstd' $_.Exception.Message }
try {
  $o = & (Join-Path $skill 'assets\std-search.ps1') -Mode info -Hcno 'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF' -OutFile (Join-Path $tmp 'i.json') 2>&1 | Out-String
  Report 'live openstd info not-found path' ($o -match 'not_in_openstd')
} catch { ReportSkip 'live openstd info' $_.Exception.Message }
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Output ("RESULT pass={0} fail={1} skip={2}" -f $pass, $fail, $skip)
if ($fail -gt 0) { exit 1 }
exit 0
