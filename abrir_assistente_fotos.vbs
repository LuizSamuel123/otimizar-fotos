Option Explicit
Dim shell, fso, pasta, script, pythonw, comando, resultado
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(pasta, "assistente_fotos.py")
pythonw = fso.BuildPath(pasta, ".venv\Scripts\pythonw.exe")
If Not fso.FileExists(script) Then
    MsgBox "Nao encontrei a interface na pasta do projeto.", 16, "Organizar Fotos"
    WScript.Quit 1
End If
If Not fso.FileExists(pythonw) Then
    On Error Resume Next
    Set resultado = shell.Exec("where.exe pythonw.exe")
    If Err.Number = 0 Then
        pythonw = Trim(Split(resultado.StdOut.ReadAll, vbCrLf)(0))
    Else
        pythonw = ""
    End If
    On Error GoTo 0
End If
If Len(pythonw) = 0 Or Not fso.FileExists(pythonw) Then
    MsgBox "Prepare o ambiente .venv ou adicione pythonw.exe ao PATH.", 16, "Organizar Fotos"
    WScript.Quit 1
End If
shell.CurrentDirectory = pasta
comando = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & script & Chr(34)
shell.Run comando, 0, False
