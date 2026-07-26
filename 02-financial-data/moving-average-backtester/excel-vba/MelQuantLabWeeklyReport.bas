Attribute VB_Name = "MelQuantLabWeeklyReport"
Option Explicit

Public Sub RefreshWeeklyReport()
    Dim wsData As Worksheet
    Dim wsSettings As Worksheet
    Dim csvPath As String
    Dim query As QueryTable

    Set wsData = ThisWorkbook.Worksheets("Data")
    Set wsSettings = ThisWorkbook.Worksheets("Settings")
    csvPath = Trim$(wsSettings.Range("B6").Value)

    If Len(csvPath) = 0 Or Dir$(csvPath) = vbNullString Then
        MsgBox "The CSV path on Settings!B6 does not exist.", vbExclamation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    wsData.Cells.Clear

    Set query = wsData.QueryTables.Add( _
        Connection:="TEXT;" & csvPath, _
        Destination:=wsData.Range("A1"))

    With query
        .TextFileParseType = xlDelimited
        .TextFileCommaDelimiter = True
        .TextFilePlatform = xlMacintosh
        .TextFileColumnDataTypes = Array(xlYMDFormat)
        .Refresh BackgroundQuery:=False
        .Delete
    End With

    wsData.Rows(1).Font.Bold = True
    wsData.Rows(1).Interior.Color = RGB(23, 54, 93)
    wsData.Rows(1).Font.Color = RGB(255, 255, 255)
    wsData.Columns("A:N").AutoFit
    wsSettings.Range("B10").Value = Now
    wsSettings.Range("B10").NumberFormat = "yyyy-mm-dd hh:mm"
    Application.CalculateFull
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True

    MsgBox "Weekly data refreshed successfully.", vbInformation
End Sub

Public Sub CreateWeeklyPDFAndEmail()
    Dim wsSettings As Worksheet
    Dim recipient As String
    Dim outputFolder As String
    Dim subjectText As String
    Dim reportLabel As String
    Dim pdfPath As String
    Dim payload As String

    Set wsSettings = ThisWorkbook.Worksheets("Settings")
    recipient = Trim$(wsSettings.Range("B5").Value)
    outputFolder = Trim$(wsSettings.Range("B7").Value)
    subjectText = Trim$(wsSettings.Range("B8").Value)
    reportLabel = Trim$(wsSettings.Range("B9").Value)

    If Len(recipient) = 0 Then
        MsgBox "Enter your email address in Settings!B5.", vbExclamation
        Exit Sub
    End If

    If Len(outputFolder) = 0 Then
        MsgBox "Enter a PDF output folder in Settings!B7.", vbExclamation
        Exit Sub
    End If

    If Dir$(outputFolder, vbDirectory) = vbNullString Then MkDir outputFolder
    pdfPath = outputFolder & Application.PathSeparator & _
        reportLabel & "_" & Format$(Date, "yyyy-mm-dd") & ".pdf"

    ThisWorkbook.Worksheets("Dashboard").ExportAsFixedFormat _
        Type:=xlTypePDF, _
        Filename:=pdfPath, _
        Quality:=xlQualityStandard, _
        IncludeDocProperties:=True, _
        IgnorePrintAreas:=False, _
        OpenAfterPublish:=False

    payload = recipient & "||" & subjectText & "||" & pdfPath

#If Mac Then
    AppleScriptTask "MelQuantLabEmail.scpt", "createDraft", payload
#Else
    CreateOutlookDraft recipient, subjectText, pdfPath
#End If

    MsgBox "The PDF was created and an email draft was opened for review.", vbInformation
End Sub

#If Not Mac Then
Private Sub CreateOutlookDraft(ByVal recipient As String, _
                               ByVal subjectText As String, _
                               ByVal pdfPath As String)
    Dim outlookApp As Object
    Dim message As Object

    Set outlookApp = CreateObject("Outlook.Application")
    Set message = outlookApp.CreateItem(0)
    With message
        .To = recipient
        .Subject = subjectText
        .Body = "Attached is the latest MelQuantLab weekly research report." & _
                vbCrLf & vbCrLf & _
                "Historical research only — not investment advice."
        .Attachments.Add pdfPath
        .Display
    End With
End Sub
#End If

