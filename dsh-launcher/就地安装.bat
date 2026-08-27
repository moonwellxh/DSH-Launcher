@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion
title DSH 就地安装
REM ============================================================
REM  就地安装.bat - 解压 dsh-launcher__skillhub.zip 后双击本文件：
REM  ① 把技能注册到 %USERPROFILE%\.agents\skills\dsh-launcher（AI 会话可加载）
REM  ② 就地生成启动器（安装目录 = 本文件所在目录）
REM  不需要提供压缩包地址。
REM ============================================================
set "SKILL_DIR=%~dp0"
if "%SKILL_DIR:~-1%"=="\" set "SKILL_DIR=%SKILL_DIR:~0,-1%"

REM --- ① 注册技能到用户技能目录 ---
set "AGENTS_SKILL=%USERPROFILE%\.agents\skills\dsh-launcher"
echo ① 注册技能到：%AGENTS_SKILL%
if not exist "%USERPROFILE%\.agents\skills" mkdir "%USERPROFILE%\.agents\skills"
xcopy /e /y /q /i "%SKILL_DIR%\*" "%AGENTS_SKILL%\" >nul
REM 清理运行期/生成文件，保持技能目录纯净（重跑时源目录已有生成物）
for %%f in (DSH-tray.ps1 dsh.cmd 启动DSH.bat 启动DSH-托盘.cmd launcher.version dsh-web.log dsh-web.err.log install-dir.txt README.md whale.ico whale-white.ico whale-white.png whale-white.svg whale.png tray.ico) do (
    if exist "%AGENTS_SKILL%\%%f" del /q "%AGENTS_SKILL%\%%f"
)
if exist "%AGENTS_SKILL%\升级" rmdir /s /q "%AGENTS_SKILL%\升级"
echo 技能已注册（DSH AI 会话可加载 dsh-launcher 及配套技能）。
echo.

REM --- ② 就地安装启动器 ---
echo ② 就地生成启动器，安装目录：%SKILL_DIR%
echo 正在运行 setup.ps1（生成启动脚本 + 补丁 + 配套技能 + 桌面快捷方式）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SKILL_DIR%\assets\setup.ps1" -InstallDir "%SKILL_DIR%"
if errorlevel 1 (
    echo.
    echo [错误] setup.ps1 运行失败（退出码 %ERRORLEVEL%）。
    echo 常见原因：未检测到 DSH 安装——请先装好 DSH 再安装启动器。
    pause
    exit /b 1
)
REM --- 同步安装目录标记到技能目录（与 AI 安装/setup 直跑一致，供更新安装.cmd 自动定位） ---
if exist "%SKILL_DIR%\assets\install-dir.txt" copy /y "%SKILL_DIR%\assets\install-dir.txt" "%AGENTS_SKILL%\assets\install-dir.txt" >nul
echo.
echo 就地安装完成：本文件夹已生成启动器，技能已注册到 .agents。
echo   托盘脚本  ：%SKILL_DIR%\DSH-tray.ps1
echo   菜单启动  ：%SKILL_DIR%\启动DSH.bat
echo   一键托盘  ：%SKILL_DIR%\启动DSH-托盘.cmd
echo   技能目录  ：%AGENTS_SKILL%
echo 桌面快捷方式「启动DSH」已指向本目录。
pause
