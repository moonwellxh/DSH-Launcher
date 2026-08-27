@echo off
rem ======================================================================
rem compile.bat - TZ3Converter dual-target build script (v2)
rem Produces:
rem   TZ3Converter.fx48.dll  (.NET Framework 4.8, for AutoCAD <=2024)
rem   TZ3Converter.net8.dll  (.NET 8, for AutoCAD >=2025; only if SDK found)
rem   TZ3Converter.sha256    (hash manifest for silent-register validation)
rem
rem v2 changes: AutoCAD install dir is located by PURE filesystem probing
rem (no reg/wmic/system tools, which may be blocked). Scans common install
rem dirs from newest to oldest and picks the first that has acmgd.dll.
rem ======================================================================
setlocal EnableDelayedExpansion
set "LOG=%~dp0compile_log.txt"
set "SRC=%~dp0TZ3Converter.cs"
set "OUTFX48=%~dp0TZ3Converter.fx48.dll"
set "OUTNET8=%~dp0TZ3Converter.net8.dll"
set "HASHFILE=%~dp0TZ3Converter.sha256"

echo ============================================ > "%LOG%"
echo  TZ3Converter dual-target compile log          >> "%LOG%"
echo  %DATE% %TIME%                                >> "%LOG%"
echo ============================================ >> "%LOG%"

rem ------------------------------------------------------------------
rem [1] locate csc.exe (.NET Framework 4.8)
rem ------------------------------------------------------------------
set "CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
echo [1] csc.exe: %CSC% >> "%LOG%"
if not exist "%CSC%" (
  echo ERROR: csc.exe NOT FOUND, install .NET Framework 4.8 Developer Pack >> "%LOG%"
  goto :nonet8
)

rem ------------------------------------------------------------------
rem [2] locate AutoCAD dir by filesystem probing (newest -> oldest)
rem ------------------------------------------------------------------
set "ACAD="
for %%V in (2026 2025 2024 2023 2022 2021 2020 2019 2018 2017 2016 2015 2014 2013 2012) do (
  if not defined ACAD if exist "C:\Program Files\Autodesk\AutoCAD %%V\acmgd.dll" set "ACAD=C:\Program Files\Autodesk\AutoCAD %%V"
)
if not defined ACAD (
  for %%V in (2026 2025 2024 2023 2022 2021 2020 2019 2018 2017 2016 2015 2014 2013 2012) do (
    if not defined ACAD if exist "C:\Program Files (x86)\Autodesk\AutoCAD %%V\acmgd.dll" set "ACAD=C:\Program Files (x86)\Autodesk\AutoCAD %%V"
  )
)
rem other drives (D/E/F/G) as last resort
if not defined ACAD (
  for %%L in (D E F G) do (
    if not defined ACAD for %%V in (2026 2025 2024 2023 2022 2021 2020 2019 2018) do (
      if not defined ACAD if exist "%%L:\Program Files\Autodesk\AutoCAD %%V\acmgd.dll" set "ACAD=%%L:\Program Files\Autodesk\AutoCAD %%V"
    )
  )
)
echo [2] AutoCAD dir: %ACAD% >> "%LOG%"
if not defined ACAD (
  echo ERROR: AutoCAD install dir NOT FOUND >> "%LOG%"
  echo        edit compile.bat and set ACAD manually, then re-run >> "%LOG%"
  goto :end
)
if not exist "%ACAD%\acmgd.dll" (
  echo ERROR: acmgd.dll NOT FOUND in %ACAD% >> "%LOG%"
  goto :end
)
if not exist "%ACAD%\acdbmgd.dll" (
  echo ERROR: acdbmgd.dll NOT FOUND >> "%LOG%"
  goto :end
)
if not exist "%ACAD%\accoremgd.dll" (
  echo ERROR: accoremgd.dll NOT FOUND >> "%LOG%"
  goto :end
)
echo      refs OK >> "%LOG%"

rem ------------------------------------------------------------------
rem [3] source check
rem ------------------------------------------------------------------
if not exist "%SRC%" (
  echo ERROR: TZ3Converter.cs NOT FOUND >> "%LOG%"
  goto :end
)
echo [3] source OK >> "%LOG%"

rem ------------------------------------------------------------------
rem [4] build fx48 (always)
rem ------------------------------------------------------------------
echo [4] compiling TZ3Converter.fx48.dll ... >> "%LOG%"
"%CSC%" /nologo /target:library /platform:x64 /out:"%OUTFX48%" /r:"%ACAD%\accoremgd.dll" /r:"%ACAD%\acdbmgd.dll" /r:"%ACAD%\acmgd.dll" "%SRC%" >> "%LOG%" 2>&1
echo [4] csc exit code: %errorlevel% >> "%LOG%"
if exist "%OUTFX48%" (
  echo      SUCCESS: %OUTFX48% >> "%LOG%"
) else (
  echo      FAILED: fx48 dll NOT generated, see errors above >> "%LOG%"
)

:nonet8
rem ------------------------------------------------------------------
rem [5] build net8 (optional; needs dotnet SDK + AutoCAD 2025+ refs)
rem ------------------------------------------------------------------
where dotnet >nul 2>nul
if errorlevel 1 (
  echo [5] dotnet SDK NOT FOUND, skip net8 target >> "%LOG%"
  goto :hash
)
set "ACADNET8="
for %%V in (2026 2025) do (
  if not defined ACADNET8 if exist "C:\Program Files\Autodesk\AutoCAD %%V\acmgd.dll" set "ACADNET8=C:\Program Files\Autodesk\AutoCAD %%V"
)
if not defined ACADNET8 (
  echo [5] AutoCAD 2025+ NOT FOUND, skip net8 target >> "%LOG%"
  goto :hash
)
echo [5] compiling TZ3Converter.net8.dll (refs: %ACADNET8%) ... >> "%LOG%"
set "ACAD_PATH=%ACADNET8%"
dotnet build "%~dp0TZ3Converter.net8.csproj" -c Release -o "%~dp0" >> "%LOG%" 2>&1
if exist "%OUTNET8%" (
  echo      SUCCESS: %OUTNET8% >> "%LOG%"
) else (
  echo      net8 build via csproj failed (see log) >> "%LOG%"
)

:hash
rem ------------------------------------------------------------------
rem [6] hash manifest
rem ------------------------------------------------------------------
echo [6] generating %HASHFILE% ... >> "%LOG%"
echo # TZ3Converter SHA-256 manifest (generated %DATE% %TIME%) > "%HASHFILE%"
if exist "%OUTFX48%" (
  for /f "skip=1 tokens=1" %%h in ('certutil -hashfile "%OUTFX48%" SHA256') do (
    if not "%%h"=="" (
      echo %%h  TZ3Converter.fx48.dll >> "%HASHFILE%"
      goto :h1
    )
  )
)
:h1
if exist "%OUTNET8%" (
  for /f "skip=1 tokens=1" %%h in ('certutil -hashfile "%OUTNET8%" SHA256') do (
    if not "%%h"=="" (
      echo %%h  TZ3Converter.net8.dll >> "%HASHFILE%"
      goto :h2
    )
  )
)
:h2
if exist "%HASHFILE%" (
  echo      manifest: >> "%LOG%"
  type "%HASHFILE%" >> "%LOG%"
)

:end
echo. >> "%LOG%"
echo ==== end of log ==== >> "%LOG%"
echo.
echo Done. Please check the log:
echo   %LOG%
echo.
pause
