# 用计划任务启动切换脚本（任务计划服务的进程树不在 dsh web 之下，切换脚本才不会自杀）
# 用法：run-switch3.ps1 -NewHome "D:\YongY\DSH_HOME_date" [-Now] [-DryRun]
param(
    [Parameter(Mandatory = $true)][string]$NewHome,
    [switch]$Now,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
$taskName = 'DSH-Home-Switch'
$target = 'D:\DSHS\_tools\switch-dsh-home3.ps1'
$user = "$env:USERDOMAIN\$env:USERNAME"

$wi = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object -TypeName Security.Principal.WindowsPrincipal -ArgumentList $wi).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Output '错误：注册 Highest 任务需要管理员权限，请以管理员身份运行本脚本。'; exit 1 }
if (-not (Test-Path -LiteralPath $target)) { Write-Output ('错误：找不到 ' + $target); exit 1 }
if (-not (Test-Path -LiteralPath (Join-Path $NewHome 'profiles\web\package.json'))) {
    Write-Output ('错误：目标目录不像 DSH 家目录（缺少 profiles\web\package.json）：' + $NewHome); exit 1
}

$args = '-NoProfile -ExecutionPolicy Bypass -File "' + $target + '" -NewHome "' + $NewHome + '"'
if ($DryRun) { $args += ' -DryRun' }

$act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $args -WorkingDirectory 'D:\DSHS'
$prin = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

$old = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($old) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; Write-Output '旧的同名任务已移除' }
Register-ScheduledTask -TaskName $taskName -Action $act -Principal $prin -Settings $set `
    -Description '切换 DSH 家目录（一次性，脚本结束后自行注销）' | Out-Null
Write-Output ('task_registered=' + $taskName)
Write-Output ('target=' + $NewHome)

if ($Now) {
    Start-ScheduledTask -TaskName $taskName
    Write-Output 'task_started — 切换在后台进行，本会话的 web 会被停掉'
} else {
    Write-Output '仅注册未执行（加 -Now 才跑）'
}
