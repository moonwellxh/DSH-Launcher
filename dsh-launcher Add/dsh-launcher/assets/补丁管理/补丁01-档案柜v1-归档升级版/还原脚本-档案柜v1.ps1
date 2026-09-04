$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\补丁引擎-公共库.ps1')
Restore-AllBackups
