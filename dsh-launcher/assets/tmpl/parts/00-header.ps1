param(
    [switch]$OpenBrowser,
    [switch]$CheckOnly
)

# DSH Web 系统托盘（__MODE_HEADER_COMMENT__）：右键菜单（顶部分隔线上方三行：DSH 现有版本/最新版本/脚本版本）+ 双击开浏览器。
# 就绪检查用非阻塞 Timer（不再阻塞消息循环，避免菜单假死）。
$ErrorActionPreference = 'Stop'

$webUrl  = 'http://127.0.0.1:3080'
$port    = 3080
__MODE_NODE_VARS__$logOut  = Join-Path $PSScriptRoot 'dsh-web.log'
$logErr  = Join-Path $PSScriptRoot 'dsh-web.err.log'
$launchBat = Join-Path $PSScriptRoot '启动DSH.bat'
$upgradeDir = Join-Path $PSScriptRoot '升级'
$npmLatestUrl = 'https://registry.npmjs.org/@deepseek-ai%2Fdsh/latest'
$skillDir = Join-Path $env:USERPROFILE '.agents\skills\dsh-launcher'
__MODE_GH_CONFIG__

