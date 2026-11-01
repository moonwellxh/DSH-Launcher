# dsh-toast.ps1 —— 右下角自绘提示窗 + 结构化留痕（2026-10-26）
# 为什么不用系统通知：本机 HKCU\...\Explorer\Advanced\EnableBalloonTips = 0，NotifyIcon 气泡一律不显示；
# WinRT Toast 在本机也不落地。故改为自绘无边框窗口：置顶、尽量不抢焦点、N 秒后自动消失。
# 单实例：同一安装目录同时只显示一张卡片，新消息顶掉旧的（避免叠在一起）。
# 日志：每张卡片写一行 key=value 到 <安装目录>\dsh-tray.log；写不进时降级到 %TEMP%\dsh-tray-fallback.log
#       并在降级日志里留 event=log.fallback（H9：禁空 catch，捕获必留上下文）。
# 调用：powershell -NoProfile -ExecutionPolicy Bypass -File dsh-toast.ps1 -InstallDir <安装目录> [-Title .. -Text .. -Kind Info|Warning|Error -Seconds 5]
param(
    [string]$InstallDir = $PSScriptRoot,
    [string]$Title = 'DSH 正在重启',
    [string]$Text = '正在重跑安装脚本并重启托盘，完成后会自动打开 DSH 窗口，请稍候…',
    [string]$Kind = 'Info',
    [int]$Seconds = 5
)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# $PSScriptRoot 在非 -File 上下文为空；兜底到脚本自身目录，避免整段提示与留痕失效
if (-not $InstallDir) { $InstallDir = Split-Path -Parent ([string]$PSCommandPath) }
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:logLost = 0

function Write-DshRecord {
    # 一个记录写到主日志；失败降级 TEMP；再失败计数（技能 H9 允许遥测降级以计数替代）。
    param([string]$Primary, [string]$Record)
    $nl = [Environment]::NewLine
    $now = { (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') }
    $clean = { param($s) ((([string]$s) -replace '"', "'") -replace "`r`n", ' ') -replace "`n", ' ' }

    # ① 轮转（失败不阻断写入，单独记一条 WARN）
    $rotateErr = ''
    try {
        if ((Test-Path -LiteralPath $Primary) -and ((Get-Item -LiteralPath $Primary).Length -gt 1MB)) {
            Move-Item -LiteralPath $Primary -Destination ($Primary + '.1') -Force -ErrorAction Stop
        }
    } catch { $rotateErr = $_.Exception.GetType().Name + ': ' + $_.Exception.Message }
    $payload = $Record
    if ($rotateErr) {
        $payload = $Record + $nl + '[dsh-tray] ts=' + (& $now) + ' level=WARN event=log.rotate_failed primary="' + (& $clean $Primary) + '" error="' + (& $clean $rotateErr) + '"'
    }

    # ② 主日志
    try {
        [IO.File]::AppendAllText($Primary, ($payload + $nl), $utf8NoBom)
        return $true
    } catch {
        $err = $_.Exception.GetType().Name + ': ' + $_.Exception.Message
    }

    # ③ 降级到 %TEMP%（同一行记录 + 一条 log.fallback 说明原因）
    $fb = Join-Path $env:TEMP 'dsh-tray-fallback.log'
    $fbRec = '[dsh-tray] ts=' + (& $now) + ' level=WARN event=log.fallback sink=temp primary="' + (& $clean $Primary) + '" error="' + (& $clean $err) + '"'
    try {
        [IO.File]::AppendAllText($fb, ($fbRec + $nl + $payload + $nl), $utf8NoBom)
        return $true
    } catch {
        $err2 = $_.Exception.GetType().Name + ': ' + $_.Exception.Message
    }

    # ④ 两条路都不通：计数（每条失败 +1），并尽力把原因抛到宿主 stderr 供调试
    $script:logLost++
    try { Write-Warning ('dsh-tray 日志两处都写不进（已丢 ' + $script:logLost + ' 条）：' + $err + ' / ' + $err2) } catch { $script:logLost++ }
    return $false
}

# ---- 留痕：每张卡片一行（ts/level/event/src/pid/title/text）----
try {
    $lvl = 'INFO'
    if ($Kind -eq 'Warning') { $lvl = 'WARN' } elseif ($Kind -eq 'Error') { $lvl = 'ERROR' }
    $cleanTx = { param($s) ((([string]$s) -replace '"', "'") -replace "`r`n", ' ') -replace "`n", ' ' }
    $rec = '[dsh-tray] ts=' + (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') +
           ' level=' + $lvl + ' event=notify src=card pid=' + $PID +
           ' title="' + (& $cleanTx $Title) + '" text="' + (& $cleanTx $Text) + '"'
    [void](Write-DshRecord -Primary (Join-Path $InstallDir 'dsh-tray.log') -Record $rec)
} catch {
    # 构造记录本身出错（理论上只有参数异常）：计数并告警，不静默
    $script:logLost++
    try { Write-Warning ('dsh-tray 日志记录构造失败：' + $_.Exception.GetType().Name + ': ' + $_.Exception.Message) } catch { $script:logLost++ }
}

# ---- 单实例：把本进程 PID 写到固定文件；若上一个卡片还活着就先结束它 ----
$key = ([string]$InstallDir).ToLowerInvariant()
$hash = [BitConverter]::ToString([System.Security.Cryptography.SHA1]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($key))).Replace('-', '').Substring(0, 12).ToLowerInvariant()
$pidFile = Join-Path $env:TEMP ("dsh-toast-" + $hash + ".pid")
try {
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = 0
        try { $oldPid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim() } catch { $oldPid = 0 }
        if ($oldPid -gt 0 -and $oldPid -ne $PID) { Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue }
    }
    Set-Content -LiteralPath $pidFile -Value ([string]$PID) -Encoding ASCII
} catch {
    # 单实例登记失败：不阻断提示，只记一行（否则会出现两张卡片叠着，可人工发现）
    try { [IO.File]::AppendAllText((Join-Path $InstallDir 'dsh-tray.log'), ('[dsh-tray] ts=' + (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') + ' level=WARN event=log.singleinstance_failed error="' + ($_.Exception.Message -replace '"', "'") + '"' + [Environment]::NewLine), $utf8NoBom) } catch { $script:logLost++ }
}

# 2026-10-26 实测：只 Add-Type -AssemblyName 加载 WinForms 后，Add-Type -TypeDefinition 仍会报
# "命名空间 System.Windows.Forms 中不存在类型 Form" —— 必须显式 -ReferencedAssemblies。
# 编译不成就退化成普通 Form（会短暂抢焦点，但提示一定出得来）。
if (-not ('DshToastForm' -as [type])) {
    $cs = @(
        'using System;'
        'using System.Windows.Forms;'
        'public class DshToastForm : Form {'
        '    protected override bool ShowWithoutActivation { get { return true; } }'
        '    protected override CreateParams CreateParams {'
        '        get {'
        '            var cp = base.CreateParams;'
        '            cp.ExStyle |= 0x08000000;'
        '            cp.ExStyle |= 0x00000080;'
        '            return cp;'
        '        }'
        '    }'
        '}'
    ) -join "`r`n"
    try {
        Add-Type -TypeDefinition $cs -ReferencedAssemblies 'System.Windows.Forms', 'System.Drawing' -Language CSharp -ErrorAction Stop
    } catch {
        # 退化为普通 Form（已知后果：会抢焦点）；记一行便于排查环境差异
        try { [IO.File]::AppendAllText((Join-Path $InstallDir 'dsh-tray.log'), ('[dsh-tray] ts=' + (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') + ' level=WARN event=ui.noactivate_fallback error="' + ($_.Exception.Message -replace '"', "'") + '"' + [Environment]::NewLine), $utf8NoBom) } catch { $script:logLost++ }
    }
}

$isCustom = [bool]('DshToastForm' -as [type])
$wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$w  = 380
$h  = $(if (([string]$Text).Length -gt 78) { 112 } else { 92 })
$titleColor = [System.Drawing.Color]::White
if ($Kind -eq 'Warning') { $titleColor = [System.Drawing.Color]::FromArgb(255, 193, 7) }
elseif ($Kind -eq 'Error') { $titleColor = [System.Drawing.Color]::FromArgb(255, 107, 107) }

$form = $(if ($isCustom) { New-Object DshToastForm } else { New-Object System.Windows.Forms.Form })
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition   = [System.Windows.Forms.FormStartPosition]::Manual
$form.Size            = New-Object System.Drawing.Size($w, $h)
$form.Location        = New-Object System.Drawing.Point(($wa.Right - $w - 16), ($wa.Bottom - $h - 16))
$form.BackColor       = [System.Drawing.Color]::FromArgb(30, 30, 30)
$form.Opacity         = 0.97
$form.TopMost         = $true
$form.ShowInTaskbar   = $false
$form.Add_Paint({
    param($s, $e)
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(72, 72, 72)), 1
    $e.Graphics.DrawRectangle($pen, 0, 0, ($s.ClientSize.Width - 1), ($s.ClientSize.Height - 1))
    $pen.Dispose()
})

$img = $null
foreach ($n in @('whale-white.png', 'whale.png')) {
    $p = Join-Path $InstallDir $n
    if (Test-Path -LiteralPath $p) { try { $img = [System.Drawing.Image]::FromFile($p) } catch { $img = $null } ; if ($img) { break } }
}
if ($img) {
    $pb = New-Object System.Windows.Forms.PictureBox
    $pb.Image     = $img
    $pb.SizeMode  = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $pb.Size      = New-Object System.Drawing.Size(44, 44)
    $pb.Location  = New-Object System.Drawing.Point(18, 24)
    $pb.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($pb)
}

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text      = $Title
$lblTitle.ForeColor = $titleColor
$lblTitle.Font      = New-Object System.Drawing.Font('Microsoft YaHei UI', 11, [System.Drawing.FontStyle]::Bold)
$lblTitle.AutoSize  = $true
$lblTitle.Location  = New-Object System.Drawing.Point(74, 20)
$lblTitle.BackColor = [System.Drawing.Color]::Transparent
$form.Controls.Add($lblTitle)

$lblText = New-Object System.Windows.Forms.Label
$lblText.Text      = $Text
$lblText.ForeColor = [System.Drawing.Color]::FromArgb(178, 178, 178)
$lblText.Font      = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$lblText.AutoSize  = $false
$lblText.Size      = New-Object System.Drawing.Size(($w - 92), ($h - 48))
$lblText.Location  = New-Object System.Drawing.Point(74, 44)
$lblText.BackColor = [System.Drawing.Color]::Transparent
$form.Controls.Add($lblText)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = ($Seconds * 1000)
$timer.Add_Tick({ $timer.Stop(); $form.Close() })
$timer.Start()

[void]$form.Show()
[System.Windows.Forms.Application]::Run($form)
if ($img) { $img.Dispose() }
$timer.Dispose()
$form.Dispose()
$pidLeft = $null
try { $pidLeft = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction Stop) } catch { $pidLeft = $null }
if ($pidLeft -and $pidLeft.Trim() -eq [string]$PID) { Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue }
