' Double-click to open the PDF//SCOPE control page.
' First run (or after requirements.txt changes): runs launcher\setup.ps1, which finds or
' installs Python, builds venv\ and installs the packages.
' Then starts the control helper hidden (no console window) and opens its page.
' The helper does not start at boot or login.
'
' If something goes wrong, the user sees an error code (PS-xxx) and the full report is
' copied to the clipboard and saved to logs\last-error.txt. The README lists every code.
Option Explicit
Dim fso, sh, dir, pyw, rc, state
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = dir & "\venv\Scripts\pythonw.exe"

If Not fso.FolderExists(dir & "\logs") Then fso.CreateFolder dir & "\logs"

If Not fso.FileExists(pyw) Or ReadText(dir & "\requirements.txt") <> ReadText(dir & "\venv\.requirements.installed") Then
  rc = sh.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & dir & "\launcher\setup.ps1""", 1, True)
  ' setup.ps1 has already shown its own error (and copied the report) when rc = 1
  If rc = 1 Then WScript.Quit 1
  If rc <> 0 Then Fail "PS-201", "The setup window closed before finishing (exit code " & rc & ")." & vbCrLf & _
    "If Windows showed a 'Smart App Control' or 'blocked' message, see the README section 'Smart App Control'.", "setup.log"
  If Not fso.FileExists(pyw) Then Fail "PS-201", "Setup finished but the Python environment is missing:" & vbCrLf & pyw, "setup.log"
End If

sh.CurrentDirectory = dir
sh.Run """" & pyw & """ """ & dir & "\launcher\control.py""", 0, False

' Wait up to 15 s for the control helper to answer.
Dim i
For i = 1 To 30
  WScript.Sleep 500
  state = HelperState()
  If state <> "down" Then Exit For
Next

If state = "ours" Then
  sh.Run "http://127.0.0.1:8100/"
ElseIf state = "other" Then
  Fail "PS-204", "Port 8100 is used by another program, so the PDF//SCOPE launcher cannot start." & vbCrLf & _
    "Restart the computer, then double-click Start PDF Scope again.", "launcher.log"
Else
  Dim tail : tail = TailText(dir & "\logs\launcher.log", 30)
  If InStr(1, tail, "Application Control policy", 1) > 0 Or InStr(1, tail, "PS-401", 1) > 0 Then
    Fail "PS-401", "Windows Smart App Control blocked a file PDF//SCOPE needs." & vbCrLf & _
      "See the README section 'Smart App Control' for how to fix it.", "launcher.log"
  Else
    Fail "PS-202", "The PDF//SCOPE launcher did not start within 15 seconds.", "launcher.log"
  End If
End If

' "ours" = our helper answered, "other" = something else holds port 8100, "down" = nothing answered.
Function HelperState()
  Dim http
  HelperState = "down"
  On Error Resume Next
  Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  http.setTimeouts 1000, 1000, 1000, 1000
  http.Open "GET", "http://127.0.0.1:8100/api/status", False
  http.Send
  If Err.Number = 0 Then
    If http.Status = 200 And InStr(http.responseText, """running""") > 0 Then
      HelperState = "ours"
    Else
      HelperState = "other"
    End If
  End If
  On Error GoTo 0
End Function

' Shows the error, saves the report to logs\last-error.txt and copies it to the clipboard.
Sub Fail(code, message, logName)
  Dim report, path, f
  report = "PDF//SCOPE error " & code & vbCrLf & message & vbCrLf & vbCrLf & _
    "Time:    " & Now & vbCrLf & _
    "Windows: " & WindowsVersion() & vbCrLf & _
    "Folder:  " & dir & vbCrLf & vbCrLf & _
    "--- last lines of logs\" & logName & " ---" & vbCrLf & TailText(dir & "\logs\" & logName, 30)
  path = dir & "\logs\last-error.txt"
  On Error Resume Next
  Set f = fso.CreateTextFile(path, True, False)
  f.Write report
  f.Close
  sh.Run "cmd.exe /c clip < """ & path & """", 0, True
  On Error GoTo 0
  MsgBox "Error " & code & vbCrLf & vbCrLf & message & vbCrLf & vbCrLf & _
    "The full error report has been COPIED. Paste it (Ctrl+V) into a message to the person who gave you PDF//SCOPE." & vbCrLf & _
    "(It is also saved in logs\last-error.txt.)", vbCritical, "PDF//SCOPE - error " & code
  WScript.Quit 1
End Sub

Function WindowsVersion()
  WindowsVersion = "unknown"
  On Error Resume Next
  Dim os
  For Each os In GetObject("winmgmts:\\.\root\cimv2").ExecQuery("SELECT Caption, Version FROM Win32_OperatingSystem")
    WindowsVersion = os.Caption & " " & os.Version
  Next
  On Error GoTo 0
End Function

' Last n lines of a text file ("" if it does not exist).
Function TailText(path, n)
  Dim lines, start, k
  TailText = ""
  If Not fso.FileExists(path) Then Exit Function
  lines = Split(Replace(ReadText(path), vbCrLf, vbLf), vbLf)
  start = UBound(lines) - n
  If start < 0 Then start = 0
  For k = start To UBound(lines)
    TailText = TailText & lines(k) & vbCrLf
  Next
End Function

Function ReadText(path)
  ReadText = ""
  If fso.FileExists(path) Then
    If fso.GetFile(path).Size > 0 Then ReadText = fso.OpenTextFile(path, 1).ReadAll
  End If
End Function
