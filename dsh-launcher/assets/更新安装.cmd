@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion
title DSH 技能更新安装

REM ============================================================
REM  更新安装.cmd - 一键更新 dsh-launcher 技能 + 自动应用补丁
REM  用法：
REM    更新安装.cmd                     （zip 放本目录或按提示输入路径）
REM    更新安装.cmd <新zip路径>          （拖拽新 zip 到本脚本上）
REM    更新安装.cmd <zip> <启动器目录>   （可选指定启动器安装目录）
REM  本脚本位于 <技能目录>\assets\ 下，技能目录 = %~dp0..（自身位置定位，无需配置）
REM ============================================================

REM --- 自我保护：先复制到临时再执行，避免覆盖自身导致读取错乱 ---
if "%DSH_UPD_RUNNER%"=="" (
    copy /y "%~f0" "%TEMP%\dsh-update-runner.cmd" >nul
    set "DSH_UPD_RUNNER=1"
    call "%TEMP%\dsh-update-runner.cmd" "%~dp0" %*
    set "_EC=!ERRORLEVEL!"
    del "%TEMP%\dsh-update-runner.cmd" >nul 2>nul
    exit /b !_EC!
)

REM ============ 以下在临时副本中运行 ============
set "ASSETS_DIR=%~1"
set "SKILL_DIR=%ASSETS_DIR%.."
shift

REM --- 获取新 zip：拖拽 %1 → 原 assets 目录 → 提示输入 ---
set "ZIP=%~1"
if not defined ZIP if exist "%ASSETS_DIR%dsh-launcher__skillhub.zip" set "ZIP=%ASSETS_DIR%dsh-launcher__skillhub.zip"
if not defined ZIP set /p "ZIP=请输入新 zip 的完整路径: "
if not exist "%ZIP%" (
    echo 错误：找不到 zip：%ZIP%
    pause
    exit /b 1
)

REM --- 校验 zip（含 dsh-launcher\SKILL.md 才是有效技能包） ---
REM 中文路径坑：bsdtar 对含中文的用户名/路径会失败（乱码），tar 失败则用 PowerShell 降级校验
set "DSH_UPD_ZIP=%ZIP%"
C:\Windows\System32\tar.exe -tf "%ZIP%" 2>nul | findstr /i "dsh-launcher/SKILL.md" >nul
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "exit [int](-not ((& 'C:\Windows\System32\tar.exe' -tf $env:DSH_UPD_ZIP 2>$null) -match 'dsh-launcher/SKILL.md'))"
    if errorlevel 1 (
        echo 错误：%ZIP% 不是有效的 dsh-launcher 技能包（缺少 SKILL.md）。
        pause
        exit /b 1
    )
)

REM --- 解压到临时目录（避免半态） ---
set "UPD=%TEMP%\dsh-skill-update"
if exist "%UPD%" rmdir /s /q "%UPD%"
mkdir "%UPD%"
set "DSH_UPD_DIR=%UPD%"
C:\Windows\System32\tar.exe -xf "%ZIP%" -C "%UPD%"
if errorlevel 1 (
    REM 降级：Expand-Archive 基于 .NET，处理 Unicode/中文路径安全
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath $env:DSH_UPD_ZIP -DestinationPath $env:DSH_UPD_DIR -Force"
    if errorlevel 1 (
        echo 解压失败，请检查 zip 是否完整。
        pause
        exit /b 1
    )
)
if not exist "%UPD%\dsh-launcher\SKILL.md" (
    echo 解压结构异常（缺少 dsh-launcher\SKILL.md）。
    pause
    exit /b 1
)

REM --- 用新内容覆盖技能目录 ---
echo 正在更新技能目录：%SKILL_DIR%
xcopy /e /y /q /i "%UPD%\dsh-launcher\*" "%SKILL_DIR%\" >nul

REM --- 运行新 setup.ps1（自动按清单应用补丁） ---
set "INSTALL_DIR=%~2"
if not defined INSTALL_DIR if exist "%ASSETS_DIR%install-dir.txt" set /p INSTALL_DIR=<"%ASSETS_DIR%install-dir.txt"
if not defined INSTALL_DIR set /p "INSTALL_DIR=请输入安装目录（直接回车使用默认 %USERPROFILE%\DSH）："
if not defined INSTALL_DIR set "INSTALL_DIR=%USERPROFILE%\DSH"
echo 正在运行 setup.ps1（启动器安装目录：%INSTALL_DIR%）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SKILL_DIR%\assets\setup.ps1" -InstallDir "%INSTALL_DIR%"
if errorlevel 1 (
    echo.
    echo [错误] setup.ps1 运行失败（退出码 %ERRORLEVEL%），请查看上方输出。
    echo 常见原因：未检测到 DSH 安装（dsh 不在 PATH 且找不到源码树）——请先装好 DSH 再更新。
    pause
    exit /b 1
)

REM --- 更新完成：自动启动托盘（就绪后自动打开浏览器一次） ---
echo 正在启动托盘（就绪后自动打开浏览器）...
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%INSTALL_DIR%\DSH-tray.ps1" -OpenBrowser
echo.
echo 更新完成：技能已更新，补丁已按清单应用（兼容检查自动跳过不匹配的补丁），托盘已启动，桌面快捷方式已刷新。
echo 若 5 秒后托盘图标未出现：请先结束残留的 DSH-tray 进程（任务管理器结束 powershell），再双击 "%INSTALL_DIR%\启动DSH-托盘.cmd"。
pause



