Attribute VB_Name = "RefreshReport"
Option Explicit

Public Sub RefreshFinOpsReport()
    Dim ws As Worksheet
    Dim pt As PivotTable

    Application.ScreenUpdating = False
    ThisWorkbook.RefreshAll
    Application.CalculateFull
    For Each ws In ThisWorkbook.Worksheets
        For Each pt In ws.PivotTables
            pt.RefreshTable
            pt.TableRange1.Rows(1).Font.Bold = True
            If ws.Name = "Tag Compliance" Then
                pt.DataBodyRange.NumberFormat = "0.0%"
            ElseIf ws.Name <> "Report Metadata" And ws.Name <> "Raw Data" Then
                pt.DataBodyRange.NumberFormat = "$#,##0.00"
            End If
        Next pt
        ws.Columns.AutoFit
    Next ws
    With ThisWorkbook.Worksheets("Report Metadata").Range("B2")
        .Value = Now
        .NumberFormat = "yyyy-mm-dd hh:mm:ss"
    End With
    Application.ScreenUpdating = True
End Sub