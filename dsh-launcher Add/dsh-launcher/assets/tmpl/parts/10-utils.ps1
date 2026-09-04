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
function Invoke-DshRpc {
    param([string]$Method, $Payload)
    $rpcId = [guid]::NewGuid().ToString('N')
    $json = @{ type = 'client-request'; rpcId = $rpcId; method = $Method; payload = $Payload } | ConvertTo-Json -Depth 10 -Compress
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $resp = Invoke-WebRequest -Uri "$webUrl/api/$Method" -Method Post -ContentType 'application/json' -Body $bodyBytes -TimeoutSec 20 -UseBasicParsing
    $txt = [System.Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    $obj = $txt | ConvertFrom-Json
    if (-not $obj.result.ok) { throw "RPC ${Method} 失败: $($obj.result.error.message)" }
    return $obj.result.value
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
