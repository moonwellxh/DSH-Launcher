function Get-DshListenerPid {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return 0
}
function Test-DshListenerIdentity {
    # 2026-10-26（对抗性审查 S6）：判断 3080 的属主到底是不是 DSH。判不准就返回 Ok=$false
    # —— 宁可不结束进程，也不误杀别人的进程树。判定链：进程名 → 命令行（bin.js/dsh/源码树名）
    # → 父进程是不是托盘（实测源码树模式的命令行是 "node.exe apps/cli/lib/bin.js web --no-open"，
    #   不含 dsh 字样，所以必须看 bin.js 与父进程）。
    param([int]$ProcessId)
    $r = [pscustomobject]@{ Ok = $false; Name = ''; ProcessId = $ProcessId }
    if ($ProcessId -le 0) { return $r }
    try { $p = Get-Process -Id $ProcessId -ErrorAction Stop } catch { return $r }
    $r.Name = [string]$p.ProcessName
    if ($r.Name -notmatch '^(node|dsh)(\.exe)?$') { return $r }
    $cl = ''
    $parentId = 0
    try {
        $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        $cl = [string]$ci.CommandLine
        $parentId = [int]$ci.ParentProcessId
    } catch {}
    # 2026-11-01 审查：补 bin.ts（源码树的 --import tsx/esm ... bin.ts 形态），去掉裸 'dsh' 子串
    # （会把 C:\tools\dsh-helper\ 这类无关进程误认成 DSH）。
    if ($cl -and ($cl -match 'bin\.js|bin\.ts|deepseek-harness|dsh\.(exe|cmd)')) { $r.Ok = $true; return $r }
    if ($parentId -gt 0) {
        try {
            $par = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction Stop
            if ([string]$par.CommandLine -match 'DSH-tray\.ps1') { $r.Ok = $true; return $r }
        } catch {}
    }
    # 仍判不准时用启动令牌兜底探测：读不到 CommandLine（非管理员看提权进程）时，
    # 避免把正常运行中的 DSH 误判成外来进程。
    # 2026-11-01 复审严重项：这里只能接受 302/303——真 DSH 用令牌换 cookie 必然重定向；
    # 而别家 HTTP 服务对 GET / 一般直接回 200，若接受 200 就会把外来服务判成 DSH（进而误杀或误附着）。
    try {
        $tok = Get-DshLaunchToken
        if ($tok) {
            $probeCode = 0
            $probeCookie = ''
            try {
                $pr = Invoke-WebRequest -Uri "$webUrl/?token=$tok" -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 0 -Proxy $null
                $probeCode = [int]$pr.StatusCode
                $probeCookie = [string]$pr.Headers['Set-Cookie']
            } catch {
                try {
                    $resp = $_.Exception.Response
                    $probeCode = [int]$resp.StatusCode
                    $probeCookie = [string]$resp.Headers['Set-Cookie']
                } catch { $probeCode = 0; $probeCookie = '' }
            }
            # 只认「带 DSH 认证 cookie（dsh-auth-）」的重定向：别的 node 项目尾斜杠/登录跳转也返 302，
            # 但那不会下发 dsh-auth-。读不到 cookie 头时退一步只认 303（DSH 的令牌换 cookie 固定 303）。
            if ($probeCookie -match 'dsh-auth-') {
                if ($probeCode -eq 302 -or $probeCode -eq 303) { $r.Ok = $true }
            } elseif ($probeCode -eq 303) {
                $r.Ok = $true
            }
        }
    } catch {}
    return $r
}
function Read-TextFile {
    param([string]$Path)
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        $sr = New-Object System.IO.StreamReader($fs)
        $t = $sr.ReadToEnd(); $sr.Close(); $fs.Close()
        return $t
    } catch { return '' }
}
function Test-DshReady {
    if (-not (Test-Path -LiteralPath $logOut)) { return $false }
    return (Read-TextFile $logOut) -match 'dsh web: http://'
}
function Get-DshLaunchToken {
    # 从 dsh web 启动日志取最近一次启动令牌（DSH 0.1.5 起根路径与 /api 都需浏览器认证，令牌是唯一的免 cookie 入口）
    if (-not (Test-Path -LiteralPath $logOut)) { return '' }
    $m = [regex]::Matches((Read-TextFile $logOut), 'dsh web: https?://[^\s]*[?&]token=([A-Za-z0-9_\-]+)')
    if ($m.Count -eq 0) { return '' }
    return $m[$m.Count - 1].Groups[1].Value
}
function Test-DshTokenFresh([string]$Token) {
    # 令牌是否仍被当前服务接受：有效令牌 GET /?token=… 返回 303（PS 5.1 在 -MaximumRedirection 0 下对 3xx 抛异常，
    # 故从异常里取状态码）；失效/旧日志残留的令牌返回 401。
    if (-not $Token) { return $false }
    try {
        $r = Invoke-WebRequest -Uri "$webUrl/?token=$Token" -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 0
        # 2026-11-01 复审：不再接受 200——别家服务对 GET / 直接回 200 会被当成"令牌有效"。
        return ($r.StatusCode -eq 302 -or $r.StatusCode -eq 303)
    } catch {
        $code = 0
        try { $code = [int]$_.Exception.Response.StatusCode } catch {}
        return ($code -eq 302 -or $code -eq 303)
    }
}
function Get-DshOpenUrl {
    # 带令牌的入口 URL（浏览器首次访问 303 换 cookie，默认 30 天）；令牌缺失或已失效（日志残留旧行）时
    # 回退裸 URL——此时依赖浏览器里既有的 cookie，并交由调用方给出可操作提示，绝不静默假装成功。
    $tok = Get-DshLaunchToken
    if ($tok -and (Test-DshTokenFresh $tok)) { return "$webUrl/?token=$tok" }
    return $webUrl
}
function Get-DshWebSession {
    # 懒登录：用启动令牌兑换 /api 所需 cookie 并缓存（令牌变化=服务重启过 → 自动重登）。
    # 说明：服务端 cookie 名是 dsh-auth-<令牌摘要>，按令牌命名，因此旧 cookie 不会"顶掉"新会话，
    # 也不会卡死 RPC——真过期时 /api 返回 401，Invoke-DshRpc 会清缓存重登一次（实测）。
    $tok = Get-DshLaunchToken
    if (-not $tok) { return $null }
    if ($script:dshWebSession -and $script:dshWebToken -eq $tok) { return $script:dshWebSession }
    try {
        $s = $null
        Invoke-WebRequest -Uri "$webUrl/?token=$tok" -UseBasicParsing -TimeoutSec 10 -SessionVariable s | Out-Null
        $script:dshWebSession = $s
        $script:dshWebToken = $tok
        return $s
    } catch { return $null }
}
function Test-DshWebAuthed {
    # 唯一就绪判据：带认证会话 GET / 恰好 200。DSH 0.1.5 起裸 URL 无 cookie 是 401，
    # 因此 401/4xx/5xx 一律不算就绪（旧实现把 200..599 全当成功，会把 401 页当"已就绪"推给用户）。
    try {
        $prm = @{ Uri = $webUrl; UseBasicParsing = $true; TimeoutSec = 3 }
        $sess = Get-DshWebSession
        if ($sess) { $prm['WebSession'] = $sess }
        $r = Invoke-WebRequest @prm
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}
function Invoke-DshRpc {
    # DSH 0.1.5-rc.1 起的 RPC 约定：端点用斜杠（如 session/list）、payload 必须包成
    # { args = { <形参名> = ... } }（形参名如 _request / request），且 /api 走浏览器认证（需 cookie）。
    # 旧约定（点号端点 session.list + 裸 payload + 无凭据）在新版会 404 / 401。
    param([string]$Method, [hashtable]$RpcArgs = @{})
    $rpcId = [guid]::NewGuid().ToString('N')
    $json = @{ type = 'client-request'; rpcId = $rpcId; method = $Method; payload = @{ args = $RpcArgs } } | ConvertTo-Json -Depth 12 -Compress
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $prm = @{ Uri = "$webUrl/api/$Method"; Method = 'Post'; ContentType = 'application/json'; Body = $bodyBytes; TimeoutSec = 20; UseBasicParsing = $true }
        $sess = Get-DshWebSession
        if ($sess) { $prm['WebSession'] = $sess }
        try { $resp = Invoke-WebRequest @prm } catch {
            $code = 0
            try { $code = [int]$_.Exception.Response.StatusCode } catch {}
            # 401 = 会话缺失/过期（服务重启换了签名）→ 清缓存重登一次
            if ($code -eq 401 -and $attempt -eq 0) { $script:dshWebSession = $null; $script:dshWebToken = ''; continue }
            throw
        }
        $txt = [System.Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
        $obj = $txt | ConvertFrom-Json
        if (-not $obj.result.ok) { throw "RPC ${Method} 失败: $($obj.result.error.message)" }
        return $obj.result.value
    }
}

function Get-SystemProxy {
    # 读系统代理（HKCU Internet Settings）；返回 http://host:port 或空串
    try {
        $is = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        if ($is.ProxyEnable -and $is.ProxyServer) {
            $ps = [string]$is.ProxyServer
            if ($ps -match '(^|;)(?:http=)?(https?://[^;]+)') { return $Matches[2] }
            if ($ps -notmatch '^https?://') { return 'http://' + $ps }
            return $ps
        }
    } catch {}
    return ''
}

# 带超时的 WebClient 子类（WebClient 本身无 Timeout 属性，重写 GetWebRequest 注入请求超时）
if (-not ('DshTimeoutWebClient' -as [type])) {
    Add-Type @"
using System;
using System.Net;
public class DshTimeoutWebClient : WebClient {
    public int TimeoutMs = 15000;
    protected override WebRequest GetWebRequest(Uri address) {
        WebRequest req = base.GetWebRequest(address);
        req.Timeout = TimeoutMs;
        return req;
    }
}
"@
}

function Invoke-DshHttp {
    # 统一 HTTP 请求：直连优先，失败则回退系统代理，最后回退 Invoke-RestMethod
    param([string]$Uri, [int]$TimeoutSec = 15)
    try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 } catch {}
    try {
        $wc = New-Object DshTimeoutWebClient
        $wc.TimeoutMs = $TimeoutSec * 1000
        $wc.Proxy = $null
        $wc.Encoding = [System.Text.Encoding]::UTF8
        $wc.Headers.Add('User-Agent', 'DSH-tray')
        return $wc.DownloadString($Uri)
    } catch {}
    $sysProxy = Get-SystemProxy
    if ($sysProxy) {
        try {
            $wc = New-Object DshTimeoutWebClient
            $wc.TimeoutMs = $TimeoutSec * 1000
            $wc.Proxy = New-Object System.Net.WebProxy($sysProxy)
            $wc.Encoding = [System.Text.Encoding]::UTF8
            $wc.Headers.Add('User-Agent', 'DSH-tray')
            return $wc.DownloadString($Uri)
        } catch {}
    }
    return Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSec
}
function Write-DshTrayLog {
    # 三层写入（coding-log-monitor H9）：主日志 → %TEMP% 降级（留 event=log.fallback）→ 计数 + stderr 告警。
    # 任何一层失败都要留痕，不允许空 catch。
    param([string]$Level = 'INFO', [string]$Event = 'tray.event', [hashtable]$Fields = @{})
    # $PSScriptRoot 只在 -File 上下文有值；取不到就退到脚本自身目录，再取不到就计数放弃（不静默）
    $base = [string]$PSScriptRoot
    if (-not $base) { $base = Split-Path -Parent ([string]$PSCommandPath) }
    if (-not $base) { $script:dshLogLost = 1 + [int]$script:dshLogLost; return $false }
    $primary = Join-Path $base 'dsh-tray.log'
    $fbPath = Join-Path $env:TEMP 'dsh-tray-fallback.log'
    $enc = New-Object System.Text.UTF8Encoding($false)
    $nl = [Environment]::NewLine
    $stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz')
    $recParts = @('[dsh-tray]', ('ts=' + $stamp), ('level=' + $Level), ('event=' + $Event))
    foreach ($k in $Fields.Keys) {
        $v = ((([string]$Fields[$k]) -replace '"', "'") -replace "`r`n", ' ') -replace "`n", ' '
        $recParts += ($k + '="' + $v + '"')
    }
    $rec = ($recParts -join ' ')
    try { [IO.File]::AppendAllText($primary, ($rec + $nl), $enc); return $true }
    catch { $err1 = $_.Exception.GetType().Name + ': ' + $_.Exception.Message }
    $fbRec = '[dsh-tray] ts=' + $stamp + ' level=WARN event=log.fallback sink=temp primary="' + ($primary -replace '"', "'") + '" error="' + ($err1 -replace '"', "'") + '"'
    try { [IO.File]::AppendAllText($fbPath, ($fbRec + $nl + $rec + $nl), $enc); return $true }
    catch {
        $script:dshLogLost = 1 + [int]$script:dshLogLost
        try { Write-Warning ('dsh 日志两处都写不进（累计丢 ' + $script:dshLogLost + ' 条）：' + $_.Exception.Message) } catch { $script:dshLogLost = 1 + [int]$script:dshLogLost }
        return $false
    }
}function Show-DshNotice {
    # 2026-10-26（用户要求）：本机 HKCU\...\Explorer\Advanced\EnableBalloonTips = 0，托盘气泡一律不显示，
    # 故统一改走右下角自绘卡片 dsh-toast.ps1。参数顺序与原 ShowBalloonTip 完全一致（超时毫秒/标题/正文/图标），
    # 便于逐个替换；卡片不可用时再退回气泡（其它机器气泡是好的）。
    # 2026-10-31 修复「托盘一显示就退出」：调用点沿用 ShowBalloonTip 的括号式写法（函数名后直接跟括号），
    # 而 PowerShell 会把整张参数表当成一个 Object[] 交给第一个参数，[int] 转换失败 = 参数绑定异常，
    # 直接终止整个 runspace（托盘图标刚出现就消失）。故第一个参数收 [object]，在函数体内按数组拆回四个参数，
    # 再统一解析成整数毫秒 $tms 供后续使用。
    param([object]$Timeout = 3000, [string]$Title = 'DSH', [string]$Text = '', [string]$Icon = 'Info')
    if ($Timeout -is [array]) {
        $na = @($Timeout)
        if ($na.Count -ge 1) { $Timeout = $na[0] }
        if ($na.Count -ge 2) { $Title = [string]$na[1] }
        if ($na.Count -ge 3) { $Text = [string]$na[2] }
        if ($na.Count -ge 4) { $Icon = [string]$na[3] }
    }
    $tms = 3000
    if (-not [int]::TryParse(([string]$Timeout), [ref]$tms)) { $tms = 3000 }
    $sec = 5
    if ($tms -gt 0) { $sec = [Math]::Max(3, [Math]::Min(10, [int][Math]::Round($tms / 1000))) }
    $kind = 'Info'
    if ($Icon -eq 'Error') { $kind = 'Error' } elseif ($Icon -eq 'Warning') { $kind = 'Warning' }
    $toast = Join-Path $PSScriptRoot 'dsh-toast.ps1'
    if (Test-Path -LiteralPath $toast) {
        try {
            $cmd = "& '" + $toast.Replace("'", "''") + "' -InstallDir '" + $PSScriptRoot.Replace("'", "''") + "' -Title '" + ([string]$Title).Replace("'", "''") + "' -Text '" + ([string]$Text).Replace("'", "''") + "' -Kind '" + $kind + "' -Seconds " + $sec
            $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
            Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-EncodedCommand',$enc -WindowStyle Hidden | Out-Null
            return
        } catch {
            [void](Write-DshTrayLog -Level 'WARN' -Event 'notice.launch_failed' -Fields @{ title = $Title; error = ($_.Exception.GetType().Name + ': ' + $_.Exception.Message) })
        }
    }
    try { $notify.ShowBalloonTip($tms, $Title, $Text, $Icon) }
    catch { [void](Write-DshTrayLog -Level 'WARN' -Event 'notice.balloon_failed' -Fields @{ title = $Title; error = ($_.Exception.GetType().Name + ': ' + $_.Exception.Message) }) }
}
