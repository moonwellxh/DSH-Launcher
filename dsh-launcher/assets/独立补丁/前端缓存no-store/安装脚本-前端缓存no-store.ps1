$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '补丁引擎-公共库.ps1')
$files = @(
  '@deepseek-ai\dsh-host-frontend-static\lib\index.js'
)
foreach ($rel in $files) {
  Install-PatchedFile $rel (Join-Path $PSScriptRoot ('载荷文件\' + $rel))
}
