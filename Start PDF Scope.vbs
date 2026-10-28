' Double-click to open the PDF//SCOPE control page.
' Starts the control helper hidden (no console window), then opens its page.
' The helper does not start at boot or login.
Option Explicit
Dim fso, sh, dir, pyw
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = dir & "\venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
  MsgBox "Python environment not found:" & vbCrLf & pyw & vbCrLf & vbCrLf & _
         "Create it once: python -m venv venv" & vbCrLf & _
         "then: venv\Scripts\pip install -r requirements.txt", vbExclamation, "PDF//SCOPE"
  WScript.Quit 1
End If
sh.CurrentDirectory = dir
sh.Run """" & pyw & """ """ & dir & "\launcher\control.py""", 0, False
WScript.Sleep 1500
sh.Run "http://127.0.0.1:8100/"
