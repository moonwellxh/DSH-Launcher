@echo off
chcp 936 >nul
REM 一键召唤 DSH Web 系统托盘（服务已在运行则直接附着，不重复启动）
REM 双击本文件不再闪命令行窗口：首次进入经 run-hidden.vbs 以隐藏窗口重入本脚本
REM （__DSH_HIDDEN=1 标记防重入），隐藏窗口内执行真正的托盘启动逻辑；
REM 若本脚本已由隐藏方式调用（__DSH_HIDDEN 已定义）则直接执行，不重复重入。
if not defined __DSH_HIDDEN (
    set "__DSH_HIDDEN=1"
    if exist "%~dp0run-hidden.vbs" (
        wscript.exe "%~dp0run-hidden.vbs" "%~f0"
        exit /b 0
    )
)
REM 自动定位 DSH-tray.ps1：本目录 → 技能记录的安装目录(install-dir.txt) → %USERPROFILE%\DSH
set "TRAY=%~dp0DSH-tray.ps1"
if not exist "%TRAY%" if exist "%~dp0install-dir.txt" set /p TRAYDIR=<"%~dp0install-dir.txt"
if not exist "%TRAY%" if defined TRAYDIR if exist "%TRAYDIR%\DSH-tray.ps1" set "TRAY=%TRAYDIR%\DSH-tray.ps1"
if not exist "%TRAY%" if exist "%USERPROFILE%\DSH\DSH-tray.ps1" set "TRAY=%USERPROFILE%\DSH\DSH-tray.ps1"
if not exist "%TRAY%" (
    echo 错误：找不到 DSH-tray.ps1。请先运行 setup.ps1 生成启动脚本。
    echo 请先运行 setup.ps1 生成启动脚本，再从安装目录启动托盘。
    if not defined __DSH_HIDDEN pause
    exit /b 1
)
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%TRAY%" -OpenBrowser
exit /b 0
