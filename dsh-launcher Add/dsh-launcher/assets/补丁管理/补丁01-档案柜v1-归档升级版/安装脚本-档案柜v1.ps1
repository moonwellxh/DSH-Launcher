$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\补丁引擎-公共库.ps1')
$files = @(
  '@deepseek-ai\dsh-workspace\lib\index.js',
  '@deepseek-ai\dsh-host-apiproxy\lib\index.js',
  '@deepseek-ai\dsh-client-connection\lib\client.js',
  '@deepseek-ai\dsh-client-runtime\lib\client.js',
  '@deepseek-ai\dsh-client-ui-workspace\lib\client.js'
)
foreach ($rel in $files) {
  Install-PatchedFile $rel (Join-Path $PSScriptRoot ('载荷文件\' + $rel))
}
