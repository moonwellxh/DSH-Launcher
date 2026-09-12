function Get-DshListenerPid {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return 0
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
        return ($r.StatusCode -eq 200 -or $r.StatusCode -eq 302 -or $r.StatusCode -eq 303)
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
