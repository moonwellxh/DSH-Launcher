Option Explicit
Dim token, json, fso, sh, configDir, configPath, stream

token = Trim(InputBox("请输入 GitHub fine-grained PAT（粘贴后点确定）：" & vbCrLf & vbCrLf & "创建：GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens -> 只选本仓库 -> Contents: Read and write", "DSH GitHub 凭据配置", ""))

If token = "" Then
    MsgBox "已取消，未做任何更改。", vbInformation, "DSH 凭据配置"
    WScript.Quit 1
End If

If Left(token, 11) <> "github_pat_" Then
    MsgBox "输入的不是 github_pat_ 开头的 fine-grained token，已退出。", vbExclamation, "DSH 凭据配置"
    WScript.Quit 1
End If

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
configDir = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.dsh\gh-sync"
configPath = configDir & "\config.json"

If Not fso.FolderExists(configDir) Then
    fso.CreateFolder(configDir)
End If

json = "{""repo"":""__GH_REPO__"",""branch"":""__GH_BRANCH__"",""token"":""" & token & """}"

Set stream = CreateObject("ADODB.Stream")
stream.Type = 2
stream.Charset = "UTF-8"
stream.Open
stream.WriteText json
stream.SaveToFile configPath, 2
stream.Close

MsgBox "配置完成：" & vbCrLf & configPath & vbCrLf & vbCrLf & "托盘第四行将变为「魔偶Git版本（单击双向同步）」。", vbInformation, "DSH 凭据配置"
WScript.Quit 0
