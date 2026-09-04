# lib.ps1 -- shared helpers for pdf-parse-v3 skill scripts (ASCII only).
# Dot-source:  . (Join-Path $PSScriptRoot 'lib.ps1')

function Ensure-PyPdf([string]$py) {
  # Make sure pypdf is importable in the given interpreter; auto-install once
  # if missing (WorkBuddy python gets upgraded in place and can lose packages).
  $chk = Invoke-Capture $py @('-c', 'import pypdf')
  if ($chk.ExitCode -eq 0) { return $true }
  $net = Test-NetConnection 127.0.0.1 -Port 7897 -WarningAction SilentlyContinue -InformationLevel Quiet
  $envOld = $env:NO_PROXY
  if ($net) { $env:NO_PROXY = '*' }
  try {
    $r1 = Invoke-Capture $py @('-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-q', '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple', 'pypdf')
    if ($r1.ExitCode -ne 0) {
      $r2 = Invoke-Capture $py @('-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-q', 'pypdf')
      if ($r2.ExitCode -ne 0) { return $false }
    }
  } finally {
    if ($null -eq $envOld) { Remove-Item env:NO_PROXY -ErrorAction SilentlyContinue } else { $env:NO_PROXY = $envOld }
  }
  return ((Invoke-Capture $py @('-c', 'import pypdf')).ExitCode -eq 0)
}

function Find-Py {
  # DSH-dedicated / neutral Python runtime, in priority order:
  #   1) $env:DSH_PYTHON (explicit override)
  #   2) %USERPROFILE%\.dsh\runtime\python*\python.exe   (DSH-owned install)
  #   3) plain 'python' on PATH
  # NOTE: deliberately does NOT probe app-bundled runtimes (WorkBuddy,
  # kimi-desktop, etc.) - they get upgraded in place and lose packages.
  if ($env:DSH_PYTHON -and (Test-Path $env:DSH_PYTHON)) { return $env:DSH_PYTHON }
  $rtDir = Join-Path $env:USERPROFILE '.dsh\runtime'
  if (Test-Path $rtDir) {
    $ver = Get-ChildItem $rtDir -Directory -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -like 'python*' } |
           Sort-Object Name -Descending | Select-Object -First 1
    if ($ver) {
      $cand = Join-Path $ver.FullName 'python.exe'
      if (Test-Path $cand) { return $cand }
    }
  }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Find-Explorer {
  # Path to Windows PowerShell 5.1 (needed for WinRT PDF render + OCR).
  $p = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
  if (Test-Path $p) { return $p }
  return $null
}

function Save-Utf8([string]$path, [string]$text) {
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Read-Utf8([string]$path) {
  return [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
}

function Invoke-Capture([string]$exe, [string[]]$argsList) {
  # Run exe, capture stdout as UTF-8 text, return trimmed string.
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $exe
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $quoted = @($argsList | ForEach-Object {
    if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
  })
  $psi.Arguments = $quoted -join ' '
  $p = [System.Diagnostics.Process]::Start($psi)
  $stdout = $p.StandardOutput.ReadToEnd()
  $stderr = $p.StandardError.ReadToEnd()
  $p.WaitForExit()
  return @{ ExitCode = $p.ExitCode; Stdout = $stdout; Stderr = $stderr }
}
