' Double-click to open the PDF//SCOPE control page.
' First run (or after requirements.txt changes): runs launcher\setup.ps1, which finds or
' installs Python, builds venv\ and installs the packages.
' Then starts the control helper hidden (no console window) and opens its page.
' The helper does not start at boot or login.
Option Explicit
Dim fso, sh, dir, pyw, rc
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = dir & "\venv\Scripts\pythonw.exe"

If Not fso.FileExists(pyw) Or ReadText(dir & "\requirements.txt") <> ReadText(dir & "\venv\.requirements.installed") Then
  rc = sh.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & dir & "\launcher\setup.ps1""", 1, True)
  ' setup.ps1 has already told the user what went wrong
  If rc <> 0 Or Not fso.FileExists(pyw) Then WScript.Quit 1
End If

sh.CurrentDirectory = dir
sh.Run """" & pyw & """ """ & dir & "\launcher\control.py""", 0, False
WScript.Sleep 1500
sh.Run "http://127.0.0.1:8100/"

Function ReadText(path)
  ReadText = ""
  If fso.FileExists(path) Then
    If fso.GetFile(path).Size > 0 Then ReadText = fso.OpenTextFile(path, 1).ReadAll
  End If
End Function
