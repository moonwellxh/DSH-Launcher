# std-search.ps1 -- official-source standard query (China national standards).
#   Modes:
#     samr        authoritative status registry: 全国标准信息公共服务平台 GB 库
#                 (JSON endpoint gbQueryPage) -- covers GB/GB/T/GBZ incl.
#                 withdrawn & upcoming versions side by side. NOT covering
#                 engineering-construction GB 5xxxx (they are managed by MOHURD).
#     openstd     search 国家标准全文公开系统 (full-text archive; excludes
#                 engineering/food-safety/env-protection standards) -> rows w/ hcno.
#     info        openstd metadata detail by hcno (status, dates, download flags).
#   . (Join-Path $PSScriptRoot 'lib-search.ps1') is dot-sourced inside.
# Usage examples:
#   pwsh std-search.ps1 -Mode samr    -Query "GB/T 14253"
#   pwsh std-search.ps1 -Mode samr    -Query "电动自行车"
#   pwsh std-search.ps1 -Mode openstd -Query "电动自行车" -Status PUBLISHED
#   pwsh std-search.ps1 -Mode info    -Hcno <32hex>
#   every mode: [-OutFile x.json]  (default <workdir>\std_search_out.json)
param(
  [ValidateSet('samr', 'openstd', 'info')][string]$Mode = 'samr',
  [string]$Query = '',
  [string]$Hcno = '',
  [ValidateSet('', 'PUBLISHED', 'TOBEIMP', 'WITHDRAWN', 'NOTIMP')][string]$Status = '',
  [ValidateSet('', '0', '1', '2', '3')][string]$Type = '0',
  [string]$OutFile = '',
  [int]$Max = 8
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib-search.ps1')

if (-not $OutFile) { $OutFile = Join-Path (Get-Location) 'std_search_out.json' }
$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0'
$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
if (-not $curl) { Write-Output 'ERROR curl_not_found'; exit 2 }
$tmp = Join-Path $env:TEMP ('gbstd_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

function Strip-Tags([string]$s) {
  $s = [regex]::Replace($s, '<[^>]+>', '')
  $s = $s -replace '&nbsp;', ' ' -replace '&amp;', '&' -replace '&lt;', '<' -replace '&gt;', '>'
  $s = [regex]::Replace($s, '\s+', ' ').Trim()
  return $s
}

function Trim-Date([string]$s) {
  $s = $s.Trim()
  $i = $s.IndexOf(' ')
  if ($i -gt 0) { $s = $s.Substring(0, $i) }
  return $s
}

function Get-Web([string]$url) {
  $out = Join-Path $tmp 'resp.bin'
  & $curl -s -L --max-time 45 -A $UA -o $out $url
  if ($LASTEXITCODE -ne 0) { throw "curl_exit $LASTEXITCODE" }
  if (-not (Test-Path $out)) { throw 'empty_response' }
  return Read-Utf8 $out
}

function New-Result {
  param([string]$code, [string]$name, [string]$state, [string]$pub, [string]$impl,
        [string]$nature, [string]$hcno, [string]$source, [string]$note)
  return [ordered]@{
    std_code = $code; name = $name; state = $state; publish_date = $pub
    impl_date = $impl; nature = $nature; hcno = $hcno; source = $source; note = $note
  }
}

$outRows = New-Object System.Collections.Generic.List[object]
$note = ''

try {
switch ($Mode) {
  'samr' {
    if (-not $Query) { Write-Output 'ERROR samr needs -Query'; exit 2 }
    $url = 'https://std.samr.gov.cn/gb/search/gbQueryPage?searchText=' +
           [uri]::EscapeDataString($Query) + '&ics=&state=&ISSUE_DATE='
    $raw = Get-Web $url
    $j = $null
    try { $j = $raw | ConvertFrom-Json } catch {}
    if (-not $j -or -not $j.rows) {
      $note = 'samr_parse_failed_raw_head=' + $raw.Substring(0, [Math]::Min(120, $raw.Length))
    } else {
      foreach ($row in (@($j.rows) | Select-Object -First $Max)) {
        $code = Strip-Tags ([string]$row.C_STD_CODE)
        $outRows.Add((New-Result $code ([string]$row.C_C_NAME) ([string]$row.STATE) `
          ([string]$row.ISSUE_DATE) ([string]$row.ACT_DATE) ([string]$row.STD_NATURE) '' 'samr' ''))
      }
      $note = "total_in_db=$($j.total)"
    }
    break
  }
  'openstd' {
    if (-not $Query) { Write-Output 'ERROR openstd needs -Query'; exit 2 }
    $url = 'https://openstd.samr.gov.cn/bzgk/gb/std_list?r=0.123&page=1&pageSize=10&p.p1=' +
           $Type + '&p.p2=' + [uri]::EscapeDataString($Query) + '&p.p5=' + $Status +
           '&p.p6=&p.p7=&p.p90=&p.p91='
    $html = Get-Web $url
    # only parse rows inside the first result_list table (page footer total is unreliable)
    $tm = [regex]::Match($html, '<table[^>]*class="[^"]*result_list[^"]*"[^>]*>([\s\S]*?)</table>')
    $tbl = if ($tm.Success) { $tm.Groups[1].Value } else { $html }
    $rowMatches = [regex]::Matches($tbl, '<tr[^>]*>([\s\S]*?)</tr>')
    foreach ($rm in $rowMatches) {
      $rowHtml = $rm.Groups[1].Value
      $hc = [regex]::Match($rowHtml, "showInfo\('([0-9A-F]{32})'\)")
      if (-not $hc.Success) { continue }
      $cells = [regex]::Matches($rowHtml, '<td[^>]*>([\s\S]*?)</td>')
      $vals = @()
      foreach ($c in $cells) { $vals += (Strip-Tags $c.Groups[1].Value) }
      if ($vals.Count -lt 9) { continue }
      $isRef = ($vals[3] -eq '采')
      $outRows.Add((New-Result $vals[1] $vals[4] $vals[6] `
        (Trim-Date $vals[7]) (Trim-Date $vals[8]) $vals[5] $hc.Groups[1].Value 'openstd' `
        $(if ($isRef) { '采标' } else { '' })))
      if ($outRows.Count -ge $Max) { break }
    }
    $note = "rows_parsed=$($outRows.Count)"
    break
  }
  'info' {
    if ($Hcno -notmatch '^[0-9A-F]{32}$') {
      Write-Output 'ERROR info needs -Hcno <32 hex> (get from openstd search)'
      exit 2
    }
    $html = Get-Web ('https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=' + $Hcno)
    $plain = [regex]::Replace($html, '<script[\s\S]*?</script>', ' ')
    $plain = [regex]::Replace($plain, '<[^>]+>', '')
    $plain = $plain -replace '&nbsp;', ' ' -replace '&times;', 'x' -replace '\s+', ' '
    $inArchive = $plain -match '标准号[:：]\s*\S'
    if (-not $inArchive) { $note = 'not_in_openstd (engineering/food/env codes or not archived)' }

    function Pick([string]$pat) {
      $m = [regex]::Match($plain, $pat)
      if ($m.Success) { return $m.Groups[1].Value.Trim() }
      return ''
    }
    $code   = Pick '标准号[:：]\s*(\S+(?:\s+\S+)?)'
    $nameCn = Pick '中文标准名称[:：]\s*(.+?)\s*英文标准名称[:：]'
    $state  = Pick '标准状态[:：]\s*(现行|即将实施|废止|暂不实施)'
    $pub    = Pick '发布日期\s*(\d{4}-\d{2}-\d{2})'
    $impl   = Pick '实施日期\s*(\d{4}-\d{2}-\d{2})'
    $hasView = $html -match 'ck_btn'
    $hasDown = $html -match 'xz_btn'
    $outRows.Add((New-Result $code $nameCn $state $pub $impl '' $Hcno 'openstd' `
      ("in_archive=$inArchive;view_btn=$hasView;download_btn=$hasDown")))
    break
  }
}
} catch {
  Write-Output ("ERROR request_failed: " + $_.Exception.Message)
  exit 2
}

$report = [ordered]@{
  mode = $Mode; query = $Query; note = $note; rows = $outRows
}
$json = $report | ConvertTo-Json -Depth 5
Save-Utf8 $OutFile $json
Write-Output ("mode={0} query='{1}' rows={2} note={3}" -f $Mode, $Query, $outRows.Count, $note)
foreach ($row in $outRows) {
  Write-Output ("  [{0}] {1} | {2} | 发布{3} | {4}" -f $row.source, $row.std_code, $row.state, $row.publish_date, $row.name)
}
Write-Output ("out=" + $OutFile)
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
