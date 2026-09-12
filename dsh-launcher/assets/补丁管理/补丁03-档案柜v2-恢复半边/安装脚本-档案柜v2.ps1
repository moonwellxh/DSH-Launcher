$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\补丁引擎-公共库.ps1')
$files = @(
  '@deepseek-ai\dsh-workspace\lib\index.js',
  '@deepseek-ai\dsh-api-workspace-controller\lib\index.js',
  '@deepseek-ai\dsh-api-workspace-controller\lib\client.js',
  '@deepseek-ai\dsh-api-workspace-controller\lib\typert.host.js',
  '@deepseek-ai\dsh-api-workspace-controller\lib\typert.remote-client.js',
  '@deepseek-ai\dsh-client-ui-workspace\lib\client.js'
)
foreach ($rel in $files) {
  Install-PatchedFile $rel (Join-Path $PSScriptRoot ('载荷文件\' + $rel))
}
