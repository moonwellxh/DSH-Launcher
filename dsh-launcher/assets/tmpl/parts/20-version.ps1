__MODE_DSH_VERSION_BODY____MODE_DSH_VERSION_SUFFIX__function Get-LauncherVersion {
    $vf = Join-Path $PSScriptRoot 'launcher.version'
    if (Test-Path -LiteralPath $vf) { return ([System.IO.File]::ReadAllText($vf)).Trim() }
    return ''
}
