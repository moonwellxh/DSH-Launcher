' run-hidden.vbs - relaunch a .cmd/.bat with a hidden window (avoids console flash on double-click)
Set sh = CreateObject("WScript.Shell")
sh.Run """" & WScript.Arguments(0) & """", 0, False
