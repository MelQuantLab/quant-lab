Attribute VB_Name = "AutoMonitor"
' ============================================================================
' AutoMonitor — VBA control panel for the FTSE AUTO.L basket monitor.
'
' Runs the Python engine (market_monitor.py) via a helper AppleScript, then
' opens/refreshes the Excel dashboard it writes (basket_dashboard.xlsx).
'
' Modern Excel for Mac is sandboxed, so VBA can't shell out directly (the old
' "Shell" and "MacScript" commands are deprecated/broken). The supported route
' is AppleScriptTask, which calls a handler in an .applescript file that must
' live in ~/Library/Application Scripts/com.microsoft.Excel/  — see README.md
' section 4 for the full setup, including that folder and permissions.
'
' SETUP (one-time): edit the three constants below to match where you put the
' market_basket_monitor folder on your Mac.
' ============================================================================

Const PYTHON_PATH As String = "/Users/your-username/market_basket_monitor/venv/bin/python3"
Const SCRIPT_DIR As String = "/Users/your-username/market_basket_monitor"
Const DASHBOARD_PATH As String = "/Users/your-username/market_basket_monitor/basket_dashboard.xlsx"

Sub RefreshNow()
    RunMonitor "check", "Prices refreshed."
End Sub

Sub RunWeeklyDigestNow()
    RunMonitor "weekly", "Weekly digest sent and dashboard refreshed."
End Sub

Private Sub RunMonitor(mode As String, doneMessage As String)
    Dim cmd As String
    Dim result As String

    On Error GoTo ErrHandler

    Application.StatusBar = "Running AUTO Monitor (" & mode & ")..."

    CloseDashboardIfOpen

    cmd = "cd " & Chr(34) & SCRIPT_DIR & Chr(34) & " && " & _
          Chr(34) & PYTHON_PATH & Chr(34) & " market_monitor.py --mode " & mode

    result = AppleScriptTask("RunPythonMonitor.applescript", "runShellCommand", cmd)

    OpenDashboard
    Application.StatusBar = False
    MsgBox doneMessage & vbCrLf & vbCrLf & result, vbInformation, "AUTO Monitor"
    Exit Sub

ErrHandler:
    Application.StatusBar = False
    MsgBox "Something went wrong: " & Err.Description & vbCrLf & _
           "Check that the paths at the top of the AutoMonitor module are correct, " & _
           "and that RunPythonMonitor.applescript is in " & _
           "~/Library/Application Scripts/com.microsoft.Excel/ (see README.md).", _
           vbExclamation, "AUTO Monitor"
End Sub

Sub OpenDashboard()
    CloseDashboardIfOpen
    Workbooks.Open DASHBOARD_PATH
End Sub

Private Sub CloseDashboardIfOpen()
    Dim wb As Workbook
    For Each wb In Workbooks
        If wb.FullName = DASHBOARD_PATH Then
            wb.Close SaveChanges:=False
            Exit For
        End If
    Next wb
End Sub
