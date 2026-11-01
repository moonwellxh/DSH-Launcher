# dsh-log.ps1 —— 读 dsh-tray.log（2026-10-26，按 coding-log-monitor 技能配套）
# 为什么有它：托盘提示是瞬时卡片、不进通知中心；所有提示与硬重启事件都写在 dsh-tray.log，
# 这个脚本就是给"后续维修的 agent / 用户"读这些记录用的（支持按级别/事件过滤与统计）。
# 用法：
#   powershell -NoProfile -File dsh-log.ps1                    # 最后 30 条
#   powershell -NoProfile -File dsh-log.ps1 -Tail 100
#   powershell -NoProfile -File dsh-log.ps1 -Level WARN,ERROR   # 只看告警/错误
#   powershell -NoProfile -File dsh-log.ps1 -Event restart.start,restart.setup
#   powershell -NoProfile -File dsh-log.ps1 -Summary            # 各级别/事件计数
#   powershell -NoProfile -File dsh-log.ps1 -Raw -Tail 5        # 原样输出（含全部 key=value）
#   powershell -NoProfile -File dsh-log.ps1 -IncludeFallback     # 并入 %TEMP% 降级日志
param(
    [string]$Path = '',
    [int]$Tail = 30,
    [string[]]$Level = @(),
    [string[]]$Event = @(),
    [switch]$Summary,
    [switch]$Raw,
    [switch]$IncludeFallback
)
$ErrorActionPreference = 'Continue'
if (-not $Path) { $Path = Join-Path $PSScriptRoot 'dsh-tray.log' }
if (-not (Test-Path -LiteralPath $Path)) {
    "找不到日志：$Path（说明还没产生过提示，或安装目录不对）"
    exit 0
}
$sources = @($Path)
if ($IncludeFallback) {
    $fbPath = Join-Path $env:TEMP 'dsh-tray-fallback.log'
    if (Test-Path -LiteralPath $fbPath) { $sources += $fbPath }
    else { "（没有降级日志：$fbPath）" }
}
$lines = @()
foreach ($src in $sources) {
    if (-not (Test-Path -LiteralPath $src)) { continue }
    if ($src -ne $Path) { "（含降级日志：$src）" }
    $lines += @(Get-Content -LiteralPath $src -Encoding UTF8 | Where-Object { $_ -and $_.StartsWith('[dsh-tray] ') })
}
# 合并后按 ts 排序（降级日志是另一支写入，天然与主日志乱序）
$lines = @($lines | Sort-Object { $m = [regex]::Match($_, 'ts=(\S+)'); if ($m.Success) { $m.Groups[1].Value } else { '' } })

function Get-Field([string]$line, [string]$name) {
    $m = [regex]::Match($line, '(?:^|\s)' + [regex]::Escape($name) + '=("([^"]*)"|\S+)')
    if (-not $m.Success) { return '' }
    if ($m.Groups[2].Success) { return $m.Groups[2].Value }
    return ($m.Value -replace ('^.*' + [regex]::Escape($name) + '='), '')
}

$sel = $lines
if ($Level.Count -gt 0) { $sel = $sel | Where-Object { $Level -contains (Get-Field $_ 'level') } }
if ($Event.Count -gt 0) { $sel = $sel | Where-Object { $Event -contains (Get-Field $_ 'event') } }

if ($Summary) {
    "文件：$Path（$($lines.Count) 条）"
    '--- 按级别 ---'
    $lines | Group-Object { Get-Field $_ 'level' } | Sort-Object Name | ForEach-Object { "  {0,-6} {1}" -f $_.Name, $_.Count }
    '--- 按事件 ---'
    $lines | Group-Object { Get-Field $_ 'event' } | Sort-Object Name | ForEach-Object { "  {0,-16} {1}" -f $_.Name, $_.Count }
    '--- 最近一条 ---'
    $lines | Select-Object -Last 1
    exit 0
}

$sel = @($sel)
if ($Tail -gt 0 -and $sel.Count -gt $Tail) { $sel = $sel[($sel.Count - $Tail)..($sel.Count - 1)] }
"共 $($sel.Count) 条（文件 $($lines.Count) 条）"
foreach ($l in $sel) {
    if ($Raw) { $l; continue }
    $ts   = (Get-Field $l 'ts')
    $lv   = (Get-Field $l 'level')
    $ev   = (Get-Field $l 'event')
    $run  = (Get-Field $l 'run')
    $disp = if ($ts.Length -ge 19) { $ts.Substring(0, 19).Replace('T', ' ') } else { $ts }
    switch ($ev) {
        'notify'        { $out = (Get-Field $l 'title') + ' | ' + (Get-Field $l 'text') }
        'restart.start' { $out = '硬重启开始 run=' + $run + ' 旧托盘 pid=' + (Get-Field $l 'old_tray_pid') }
        'restart.setup' { $out = '硬重启 setup=' + (Get-Field $l 'state') + ' exit=' + (Get-Field $l 'exit') + ' 耗时=' + (Get-Field $l 'duration_ms') + 'ms run=' + $run + ' notes=' + (Get-Field $l 'notes') }
        'log.fallback'      { $out = '日志降级到 TEMP：主="' + (Get-Field $l 'primary') + '"  原因=' + (Get-Field $l 'error') }
        'log.rotate_failed' { $out = '日志轮转失败（继续写大文件）：' + (Get-Field $l 'error') }
        'status.write_failed' { $out = '状态文件写入失败：' + (Get-Field $l 'path') + '  原因=' + (Get-Field $l 'error') }
        'ui.noactivate_fallback' { $out = '不抢焦点不可用，已退化为普通窗口：' + (Get-Field $l 'error') }
        'log.singleinstance_failed' { $out = '单实例登记失败（可能出现两张卡片）：' + (Get-Field $l 'error') }
        default         { $out = $l }
    }
    "{0}  {1,-5}  {2,-14}  {3}" -f $disp, $lv, $ev, $out
}
