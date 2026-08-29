@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion
title DSH 启动器

REM ============================================================
REM  Script: 启动DSH.bat
REM  Purpose: DSH 菜单启动器（DSH Launcher 生成）
REM  选项 1：后台启动/附着 DSH Web 并驻留系统托盘，就绪后自动开浏览器。
REM ============================================================

set "dshCmd="
set "dshWebUrl=http://127.0.0.1:3080"

REM --- 定位 dsh 命令：仅同目录 dsh.cmd（绝对路径，禁止裸命令名） ---
if exist "%~dp0dsh.cmd" set "dshCmd=%~dp0dsh.cmd"
if not defined dshCmd (
    REM 禁止回退裸 dsh：工作目录含本地 dsh.cmd 时会被劫持（递归陷阱）
    echo 错误：无法解析 dsh.cmd 绝对路径。
    echo 请先运行 setup.ps1 生成启动脚本。
    echo.
    pause
    exit /b 1
)

cls
echo ========================================
echo       DeepSeek Harness (DSH) 启动器
echo ========================================
set "dshVer="
for /f "delims=" %%v in ('call "%dshCmd%" --version 2^>nul') do set "dshVer=%%v"
if not defined dshVer set "dshVer=未知（请检查 DSH 安装）"
echo   当前版本: !dshVer!
echo.
echo   1. 启动 DSH Web UI（默认，驻留托盘）
echo   2. 启动 DSH 终端界面 (TUI)
echo   3. 启动 DSH 无界面模式 (Headless)
echo   0. 退出
echo.
echo ========================================
REM --- 默认选项：%1 传入则预选（托盘菜单 TUI=2 / Headless=3 用） ---
set "defChoice=1"
set "defText=启动 DSH Web UI（默认，驻留托盘）"
if /i "%~1"=="2" ( set "defChoice=2" & set "defText=启动 DSH 终端界面 (TUI)" )
if /i "%~1"=="3" ( set "defChoice=3" & set "defText=启动 DSH 无界面模式 (Headless)" )
if /i "%~1"=="0" ( set "defChoice=0" & set "defText=退出" )
set "choice="
set /p "choice=请输入编号 [回车=%defChoice%（%defText%）]: "
set "choice=%choice: =%"

if not defined choice set "choice=%defChoice%"

if "%choice%"=="1" goto :opt1
if "%choice%"=="2" goto :opt2
if "%choice%"=="3" goto :opt3
if "%choice%"=="0" exit /b 0

echo 无效输入，请重新运行脚本。
timeout /t 2 >nul
exit /b 1

:opt1
echo 正在后台启动/附着 DSH Web 并驻留系统托盘 ...
echo 服务就绪后将自动打开浏览器：%dshWebUrl%
set "TRAY=%~dp0DSH-tray.ps1"
if not exist "%TRAY%" if exist "%~dp0install-dir.txt" set /p TRAYDIR=<"%~dp0install-dir.txt"
if not exist "%TRAY%" if defined TRAYDIR if exist "%TRAYDIR%\DSH-tray.ps1" set "TRAY=%TRAYDIR%\DSH-tray.ps1"
if not exist "%TRAY%" if exist "%USERPROFILE%\DSH\DSH-tray.ps1" set "TRAY=%USERPROFILE%\DSH\DSH-tray.ps1"
if not exist "%TRAY%" (
    echo 错误：找不到 DSH-tray.ps1，请先运行 setup.ps1 生成启动脚本。
    pause
    exit /b 1
)
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%TRAY%" -OpenBrowser
exit /b 0

:opt2
echo 正在启动 DSH 终端界面 ...
start "" "%dshCmd%" --profile tui
exit /b 0

:opt3
set /p "task=请输入要执行的任务描述: "
if "!task!"=="" (
    echo 任务描述为空，取消启动。
    timeout /t 2 >nul
    exit /b 0
)
echo 正在启动 DSH 无界面模式 ...
start "" "%dshCmd%" --profile headless "!task!"
exit /b 0





