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
