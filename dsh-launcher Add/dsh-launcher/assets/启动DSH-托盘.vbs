' DSH tray launcher vbs - one-click DSH Web tray start (no console window at all)
' Place this file next to DSH-tray.ps1 in the launcher install folder.
Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
trayPs1 = fso.BuildPath(baseDir, "DSH-tray.ps1")
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & trayPs1 & """ -OpenBrowser", 0, False
