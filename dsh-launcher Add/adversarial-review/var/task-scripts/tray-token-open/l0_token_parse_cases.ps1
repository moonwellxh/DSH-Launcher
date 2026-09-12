# l0_token_parse_cases.ps1 -- offline observation harness for the DESIGNED Get-DshTokenUrl / Get-DshHttpStatus.
# Prints observations only: it holds NO expected values and NO assertions (expected values live in the design
# doc's V-table and are checked by an independent reviewer against this output).
# v3 alignment: the mtime prefilter veto was REMOVED (round-2 review A: it cancelled the probe), so the parse
# function takes no ListenerPid; validity is decided solely by the 303 probe.
# Run with Windows PowerShell 5.1:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File l0_token_parse_cases.ps1
# Groups: A parse (V1/V2), B probe verdicts (V3b), C probe latency (V3c).
$ErrorActionPreference = 'Stop'

function Read-TextFile {
    param([string]$Path)
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        $sr = New-Object System.IO.StreamReader($fs)
        $t = $sr.ReadToEnd(); $sr.Close(); $fs.Close()
        return $t
    } catch { return '' }
}

function Get-DshTokenUrl {
    param([string]$LogPath = $logOut, [int]$Port = $port)
    if (-not (Test-Path -LiteralPath $LogPath)) { return $null }
    $text = Read-TextFile $LogPath
    if (-not $text) { return $null }
    $ms = [regex]::Matches($text, "http://127\.0\.0\.1:$Port/\?token=([A-Za-z0-9_-]+)")
    if ($ms.Count -eq 0) { return $null }
    for ($i = $ms.Count - 1; $i -ge 0; $i--) {   # last startup line first
        if ($ms[$i].Groups[1].Value.Length -ge 20 -and $ms[$i].Groups[1].Value.Length -le 128) {
            return $ms[$i].Value
        }
    }
    return $null
}

function Get-DshHttpStatus {
    param([string]$Url, [int]$TimeoutMs = 1200)
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Method = 'GET'
        $req.AllowAutoRedirect = $false
        $req.Proxy = $null            # loopback must bypass any system proxy
        $req.Timeout = $TimeoutMs
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return $code
    } catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) { $code = [int]$r.StatusCode; $r.Close(); return $code }
        return 0
    } catch { return 0 }
}

function Test-DshTokenUrl {
    param([string]$Url)
    return ((Get-DshHttpStatus -Url $Url) -eq 303)
}

function Get-DshProbeHeaders {
    param([string]$Url, [string]$CookieValue = '', [int]$TimeoutMs = 1200)
    # Observes which request headers the stub actually received (contract: the probe must send no Cookie).
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Method = 'GET'
        $req.AllowAutoRedirect = $false
        $req.Proxy = $null
        $req.Timeout = $TimeoutMs
        if ($CookieValue -ne '') { $req.CookieContainer = New-Object System.Net.CookieContainer }
        if ($CookieValue -ne '') { $req.CookieContainer.Add((New-Object System.Uri($Url)), (New-Object System.Net.Cookie('dsh-probe', $CookieValue))) }
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $body = $reader.ReadToEnd(); $reader.Close(); $resp.Close()
        return $body
    } catch { return "ERR: $($_.Exception.Message)" }
}

function Resolve-DshOpenAction {
    # Pure routing function for the click flow (no I/O): inputs -> exit id. Total by construction.
    param([int]$RootStatus, [bool]$HasCandidate, [int]$CandidateStatus)
    if ($RootStatus -eq 0) { return 'EXIT-NOT-RUNNING' }
    if ($RootStatus -eq 200) { return 'EXIT-NO-AUTH' }
    if ($RootStatus -eq 401) {
        if (-not $HasCandidate) { return 'EXIT-NO-TOKEN' }
        if ($CandidateStatus -eq 303) { return 'EXIT-TOKEN-OK' }
        if ($CandidateStatus -eq 0) { return 'EXIT-TOKEN-UNREACHABLE' }
        return 'EXIT-TOKEN-REJECTED'
    }
    return 'EXIT-ROOT-ANOMALY'
}

$tok43 = 'QC_FS2iYkKhjNUVZK3S30aL6lTSeS3sivytuL24ncUg'
$dir = Join-Path $env:TEMP 'dsh-token-cases'
if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'fake-dsh-web.log'
$u8 = New-Object System.Text.UTF8Encoding($false)

function Show([string]$name, $value) {
    "{0,-30} => {1}" -f $name, ($(if ($null -ne $value -and "$value" -ne '') { "$value" } else { '<null>' }))
}

function Case([string]$name, [string]$content, [switch]$skipWrite, [string]$eol) {
    if ($skipWrite) { Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue }
    elseif ($null -ne $eol) { [System.IO.File]::WriteAllBytes($log, $u8.GetBytes(($content -replace "`r`n", $eol))) }
    else { [System.IO.File]::WriteAllText($log, $content, $u8) }
    Show $name (Get-DshTokenUrl -LogPath $log -Port 3080)
}

"=== group A: parse (V1/V2) ==="
Case 'A1 43-char' ("dsh web: http://127.0.0.1:3080/?token=$tok43")
Case 'A2 no-token-line' 'dsh web: http://127.0.0.1:3080'
Case 'A3 token-19' ("dsh web: http://127.0.0.1:3080/?token=" + ('b' * 19))
Case 'A4 token-20' ("dsh web: http://127.0.0.1:3080/?token=" + ('b' * 20))
Case 'A5 other-port' ("dsh web: http://127.0.0.1:9999/?token=$tok43")
Case 'A6 localhost-host' ("dsh web: http://localhost:3080/?token=$tok43")
Case 'A7 two-lines-CRLF' ("dsh web: http://127.0.0.1:3080/?token=" + ('a' * 43) + "`r`ndsh web: http://127.0.0.1:3080/?token=$tok43")
Case 'A8 two-lines-LF' ("dsh web: http://127.0.0.1:3080/?token=" + ('a' * 43) + "`ndsh web: http://127.0.0.1:3080/?token=$tok43") $null 'LF'
Case 'A9 no-prefix-line' ("http://127.0.0.1:3080/?token=$tok43")
Case 'A10 extra-params' ("dsh web: http://127.0.0.1:3080/?token=$tok43&v=1")
Case 'A11 LAN-suffix' ("dsh web: http://127.0.0.1:3080/?token=$tok43 (LAN: http://192.168.1.5:3080)")
Case 'A12 token-70' ("dsh web: http://127.0.0.1:3080/?token=" + ('c' * 70))
Case 'A13 log-missing' '' -skipWrite
Case 'A14 empty-log' '   '

"=== group B: probe verdicts (V3b, raw TCP stub process) ==="
# The stub runs as a separate powershell.exe process: a TcpListener cannot be handed to Start-Job
# (job arguments are serialized, which silently breaks the listener -- verified 2026-09-10).
$stubScript = Join-Path $dir 'stub.ps1'
$stubText = @'
param([int]$Port, [int]$Status)
$l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
$l.Start()
# Serve up to 3 connections: the harness observes status AND the Test-DshTokenUrl verdict, so a
# single-shot stub would answer the first probe and refuse the second (verified 2026-09-10).
for ($i = 0; $i -lt 3; $i++) {
    try {
        $client = $l.AcceptTcpClient()
        $stream = $client.GetStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $lines = @()
        while ($true) { $line = $reader.ReadLine(); if ($null -eq $line -or $line -eq '') { break }; $lines += $line }
        $body = ($lines -join '|')
        if ($Status -eq 999) { $resp = "HTTP/1.1 200 OK`r`nContent-Type: text/plain`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n$body" }
        elseif ($Status -eq 303) { $resp = "HTTP/1.1 303 See Other`r`nLocation: /`r`nContent-Length: 0`r`nConnection: close`r`n`r`n" }
        elseif ($Status -eq 200) { $resp = "HTTP/1.1 200 OK`r`nContent-Type: text/html`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n$body" }
        else { $resp = "HTTP/1.1 401 Unauthorized`r`nContent-Type: text/plain`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n$body" }
        $bytes = [System.Text.Encoding]::ASCII.GetBytes($resp)
        $stream.Write($bytes, 0, $bytes.Length); $stream.Flush()
        $client.Close()
    } catch { break }
}
$l.Stop()
'@
[System.IO.File]::WriteAllText($stubScript, $stubText, $u8)

function Get-FreePort {
    $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $l.Start(); $p = ([System.Net.IPEndPoint]$l.LocalEndpoint).Port; $l.Stop(); return $p
}

function Start-Stub([int]$status, [string]$stubScript) {
    $p = Get-FreePort
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $stubScript + '"'), '-Port', $p, '-Status', $status -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 700
    return @{ port = $p; proc = $proc }
}

foreach ($status in @(303, 401, 200)) {
    $stub = Start-Stub $status $stubScript
    $url = "http://127.0.0.1:$($stub.port)/?token=$tok43"
    Show ("B stub-$status status") (Get-DshHttpStatus -Url $url)
    Show ("B stub-$status Test-DshTokenUrl") (Test-DshTokenUrl -Url $url)
    try { $stub.proc | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }
}

"=== group C: probe latency (V3c) ==="
$stub = Start-Stub 303 $stubScript
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$null = Get-DshHttpStatus -Url "http://127.0.0.1:$($stub.port)/?token=$tok43"
$sw.Stop()
Show 'C1 stub-303 latency(ms)' $sw.ElapsedMilliseconds
try { $stub.proc | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$null = Get-DshHttpStatus -Url ("http://127.0.0.1:" + (Get-FreePort) + "/?token=$tok43")
$sw.Stop()
Show 'C2 closed-port latency(ms)' $sw.ElapsedMilliseconds

"=== group C3/C4: request headers actually received (contract: probe sends no Cookie) ==="
$stub = Start-Stub 999 $stubScript
$echo = Get-DshProbeHeaders -Url "http://127.0.0.1:$($stub.port)/?token=$tok43"
Show 'C3 no-cookie-mode sent Cookie?' ($echo -match 'Cookie:')
try { $stub.proc | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }
$stub = Start-Stub 999 $stubScript
$echo2 = Get-DshProbeHeaders -Url "http://127.0.0.1:$($stub.port)/?token=$tok43" -CookieValue 'STALECOOKIE'
Show 'C4 preset-cookie sent Cookie?' ($echo2 -match 'Cookie:')
try { $stub.proc | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }

"=== group D: routing table of Resolve-DshOpenAction (pure function, no I/O) ==="
$rootStatuses = @(0, 200, 303, 401, 403, 500)
$candStatuses = @(0, 200, 303, 401, 500)
$rows = 0; $unmatched = 0
foreach ($r in $rootStatuses) {
    foreach ($h in @($true, $false)) {
        foreach ($c in $candStatuses) {
            $exit = Resolve-DshOpenAction -RootStatus $r -HasCandidate $h -CandidateStatus $c
            if ($null -eq $exit -or "$exit" -eq '') { $unmatched++ }
            $rows++
            "{0,-34} => {1}" -f ("R=$r H=$h C=$c"), $exit
        }
    }
}
Show 'D rows enumerated' $rows
Show 'D unmatched (null/empty) exits' $unmatched

Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
"PS $($PSVersionTable.PSVersion)"
