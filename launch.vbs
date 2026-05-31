' MeetScribe — launch without a console window (desktop shortcut).
Option Explicit

Dim fso, shell, appDir, pythonw, envVenv

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

pythonw = FindPythonw()
If pythonw = "" Then
    MsgBox "Python not found." & vbCrLf & vbCrLf & "Run install.bat once.", vbCritical, "MeetScribe"
    WScript.Quit 1
End If

If Not HasDependencies(pythonw) Then
    Dim answer
    answer = MsgBox( _
        "MeetScribe dependencies are not installed yet." & vbCrLf & vbCrLf & _
        "Run install.bat now? (opens a setup window)", _
        vbYesNo Or vbQuestion, "MeetScribe")
    If answer = vbYes Then
        shell.Run "cmd /c """ & appDir & "\install.bat""", 1, True
    Else
        WScript.Quit 1
    End If
    If Not HasDependencies(pythonw) Then
        MsgBox "Dependencies are still missing. Run install.bat manually.", vbCritical, "MeetScribe"
        WScript.Quit 1
    End If
End If

shell.Run """" & pythonw & """ """ & appDir & "\main.py""", 0, False

Function FindPythonw()
    Dim candidates(), index, path

    ReDim candidates(5)
    envVenv = shell.ExpandEnvironmentStrings("%MEETSCRIBE_VENV%")
    If envVenv <> "%MEETSCRIBE_VENV%" Then candidates(0) = envVenv & "\Scripts\pythonw.exe"
    envVenv = shell.ExpandEnvironmentStrings("%TRANSCRIPTOR_VENV%")
    If envVenv <> "%TRANSCRIPTOR_VENV%" Then candidates(1) = envVenv & "\Scripts\pythonw.exe"
    candidates(2) = appDir & "\.venv\Scripts\pythonw.exe"
    candidates(3) = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.venvs\meet-scribe\Scripts\pythonw.exe"
    candidates(4) = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.venvs\my-transcriptor\Scripts\pythonw.exe"

    For index = 0 To UBound(candidates)
        path = candidates(index)
        If Len(path) > 0 Then
            If fso.FileExists(path) Then
                FindPythonw = path
                Exit Function
            End If
        End If
    Next

    FindPythonw = ""
End Function

Function HasDependencies(pythonwPath)
    Dim pythonExe, result
    pythonExe = Replace(pythonwPath, "pythonw.exe", "python.exe")
    If Not fso.FileExists(pythonExe) Then pythonExe = pythonwPath
    result = shell.Run("""" & pythonExe & """ -c ""import customtkinter""", 0, True)
    HasDependencies = (result = 0)
End Function
