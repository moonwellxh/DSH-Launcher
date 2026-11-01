$ErrorActionPreference = 'Stop'

if (-not ('Elev' -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Elev {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr OpenProcess(int access, bool inherit, int pid);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool OpenProcessToken(IntPtr proc, int access, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool GetTokenInformation(IntPtr token, int cls, out int buf, int len, out int ret);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr h);

    public static int IsElevated(int pid) {
        IntPtr p = OpenProcess(0x1000, false, pid);
        if (p == IntPtr.Zero) { return -1; }
        IntPtr t;
        if (!OpenProcessToken(p, 0x0008, out t)) { CloseHandle(p); return -2; }
        int val; int ret;
        bool ok = GetTokenInformation(t, 20, out val, 4, out ret);
        CloseHandle(t);
        CloseHandle(p);
        if (!ok) { return -3; }
        return val;
    }
}
"@
}

function Show-Token([int]$procId, [string]$label) {
    $r = [Elev]::IsElevated($procId)
    $txt = switch ($r) {
        1  { 'ELEVATED' }
        0  { 'NOT-elevated' }
        -1 { 'OPEN_FAILED(access)' }
        -2 { 'TOKEN_FAILED' }
        -3 { 'INFO_FAILED' }
        default { "UNKNOWN($r)" }
    }
    Write-Output ("{0,-12} pid={1,-7} token_elevated={2}" -f $label, $procId, $txt)
}

$tray = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -match '-File\s+.*DSH-tray\.ps1' }
foreach ($t in $tray) { Show-Token ([int]$t.ProcessId) 'DSH-TRAY' }

$web = Get-NetTCPConnection -LocalPort 3080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($web) { Show-Token ([int]$web.OwningProcess) 'DSH-WEB' }

Show-Token $PID 'THIS-SHELL'
foreach ($e in (Get-Process explorer -ErrorAction SilentlyContinue | Select-Object -First 1)) { Show-Token ([int]$e.Id) 'explorer' }
