$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $root 'data\cur_sample.csv'
$outputPath = Join-Path $root 'reports\monthly_finops_report.xlsm'
$rows = @(Import-Csv -LiteralPath $sourcePath)
$headers = @('usage_date', 'usage_month', 'service', 'region', 'usage_type', 'unblended_cost',
             'usage_quantity', 'Environment', 'Owner', 'CostCenter', 'Application', 'tag_compliant')
$values = [System.Array]::CreateInstance([object], $rows.Count + 1, $headers.Count)
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$numberStyle = [System.Globalization.NumberStyles]::Float
for ($column = 0; $column -lt $headers.Count; $column++) {
    $values[0, $column] = $headers[$column]
}
$validTags = @{
    Environment = @('Production', 'Staging', 'Development', 'Shared')
    Owner = @('team-platform', 'team-data', 'team-commerce', 'team-analytics')
    CostCenter = @('CC-1001', 'CC-2042', 'CC-3057', 'CC-4108')
    Application = @('billing', 'catalog', 'payments', 'analytics')
}
for ($index = 0; $index -lt $rows.Count; $index++) {
    $item = $rows[$index]
    $row = $index + 1
    $date = [datetime]::ParseExact($item.usage_date, 'yyyy-MM-dd', $culture)
    $values[$row, 0] = $date.ToOADate()
    $values[$row, 1] = $item.usage_date.Substring(0, 7)
    $values[$row, 2] = $item.service
    $values[$row, 3] = $item.region
    $values[$row, 4] = $item.usage_type
    $values[$row, 5] = [double]::Parse($item.unblended_cost, $numberStyle, $culture)
    $values[$row, 6] = [double]::Parse($item.usage_quantity, $numberStyle, $culture)
    $isCompliant = $true
    foreach ($tagName in @('Environment', 'Owner', 'CostCenter', 'Application')) {
        $tagValue = $item.$tagName
        $tagColumn = 7 + [array]::IndexOf(@('Environment', 'Owner', 'CostCenter', 'Application'), $tagName)
        $values[$row, $tagColumn] = $tagValue
        if ([string]::IsNullOrWhiteSpace($tagValue) -or $validTags[$tagName] -notcontains $tagValue) {
            $isCompliant = $false
        }
    }
    $values[$row, 11] = [int]$isCompliant
}

$excel = $null
$workbook = $null
$securityPath = 'HKCU:\Software\Microsoft\Office\16.0\Excel\Security'
$policyPath = 'HKCU:\Software\Policies\Microsoft\Office\16.0\Excel\Security'
if (Test-Path $policyPath) {
    $policyValue = Get-ItemProperty -Path $policyPath -Name AccessVBOM -ErrorAction SilentlyContinue
    if ($policyValue -and $policyValue.AccessVBOM -ne 1) {
        throw 'Excel policy disables VBA project access; refusing to override policy. The .xlsx fallback remains available.'
    }
}
$securityKeyExisted = Test-Path $securityPath
$accessVbomExisted = $false
$previousAccessVbom = $null
if ($securityKeyExisted) {
    $securityKey = Get-Item -Path $securityPath
    $accessVbomExisted = @($securityKey.GetValueNames()) -contains 'AccessVBOM'
    if ($accessVbomExisted) {
        $previousAccessVbom = [int]$securityKey.GetValue('AccessVBOM')
    }
}
if (-not $securityKeyExisted) {
    New-Item -Path $securityPath -Force | Out-Null
}
Set-ItemProperty -Path $securityPath -Name AccessVBOM -Value 1 -Type DWord
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AutomationSecurity = 1
    $workbook = $excel.Workbooks.Add()
    $raw = $workbook.Worksheets.Item(1)
    $raw.Name = 'Raw Data'
    $lastRow = $rows.Count + 1
    $lastColumn = $headers.Count
    $rawRange = $raw.Cells.Item(1, 1).Resize($lastRow, $lastColumn)
    $rawRange.Value2 = $values
    $raw.Rows.Item(1).Font.Bold = $true
    $raw.Rows.Item(1).Interior.Color = 5918756
    $raw.Columns.AutoFit() | Out-Null
    $raw.Activate() | Out-Null
    $raw.Range('A2').Select() | Out-Null
    $excel.ActiveWindow.FreezePanes = $true
    $sourceRange = $raw.Range($raw.Cells.Item(1, 1), $raw.Cells.Item($lastRow, $lastColumn))

    $metadata = $workbook.Worksheets.Add()
    $metadata.Name = 'Report Metadata'
    $metadata.Range('A1').Value2 = 'Report'
    $metadata.Range('B1').Value2 = 'Monthly FinOps Report'
    $metadata.Range('A2').Value2 = 'Last refreshed'
    $metadata.Range('B2').Value2 = (Get-Date).ToOADate()
    $metadata.Range('B2').NumberFormat = 'yyyy-mm-dd hh:mm:ss'
    $metadata.Rows.Item(1).Font.Bold = $true

    function Add-PivotSheet($book, $source, $sheetName, $pivotName, $rowField, $columnField, $dataField, $caption, $aggregate, $numberFormat) {
        $sheet = $book.Worksheets.Add()
        $sheet.Name = $sheetName
        $cache = $book.PivotCaches().Create(1, $source)
        $pivot = $cache.CreatePivotTable($sheet.Range('A3'), $pivotName)
        $pivot.ManualUpdate = $true
        $pivot.PivotFields($rowField).Orientation = 1
        if ($columnField) {
            $pivot.PivotFields($columnField).Orientation = 2
        }
        $functionCode = if ($aggregate -eq 'Average') { -4106 } else { -4157 }
        $measure = $pivot.AddDataField($pivot.PivotFields($dataField), $caption, $functionCode)
        $measure.NumberFormat = $numberFormat
        $pivot.TableStyle2 = 'PivotStyleMedium2'
        $pivot.ManualUpdate = $false
        $pivot.RefreshTable() | Out-Null
        $sheet.Columns.AutoFit() | Out-Null
        return $pivot
    }

    $serviceMonth = Add-PivotSheet $workbook $sourceRange 'Spend by Service Month' 'SpendByServiceMonth' `
        'service' 'usage_month' 'unblended_cost' 'Spend USD' 'Sum' '$#,##0.00'
    $regionSpend = Add-PivotSheet $workbook $sourceRange 'Spend by Region' 'SpendByRegion' `
        'region' $null 'unblended_cost' 'Spend USD' 'Sum' '$#,##0.00'
    $tagCompliance = Add-PivotSheet $workbook $sourceRange 'Tag Compliance' 'TagComplianceByService' `
        'service' $null 'tag_compliant' 'Tag Compliance' 'Average' '0.0%'

    $macro = @'
Public Sub RefreshFinOpsReport()
    Dim ws As Worksheet
    Dim pt As PivotTable
    Application.ScreenUpdating = False
    ThisWorkbook.RefreshAll
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
'@
    $module = $workbook.VBProject.VBComponents.Add(1)
    $module.Name = 'FinOpsRefresh'
    $module.CodeModule.AddFromString($macro)
    $workbook.SaveAs($outputPath, 52)
    $excel.Run("'monthly_finops_report.xlsm'!RefreshFinOpsReport") | Out-Null
    $workbook.Save()
    $pivotCount = 0
    foreach ($sheet in $workbook.Worksheets) {
        $pivotCount += $sheet.PivotTables().Count
    }
    if ($pivotCount -ne 3) {
        throw "Expected 3 native PivotTables, found $pivotCount."
    }
    $macroLines = $workbook.VBProject.VBComponents.Item('FinOpsRefresh').CodeModule.CountOfLines
    if ($macroLines -lt 10) {
        throw 'Embedded VBA module is empty or incomplete.'
    }
    Write-Output "Created reports\monthly_finops_report.xlsm with $pivotCount native PivotTables and an embedded refresh macro."
} finally {
    if ($workbook) {
        try { $workbook.Close($false) | Out-Null } catch {}
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    try {
        if ($accessVbomExisted) {
            Set-ItemProperty -Path $securityPath -Name AccessVBOM -Value $previousAccessVbom -Type DWord
        } else {
            Remove-ItemProperty -Path $securityPath -Name AccessVBOM -ErrorAction SilentlyContinue
            if (-not $securityKeyExisted -and @((Get-Item -Path $securityPath).GetValueNames()).Count -eq 0) {
                Remove-Item -Path $securityPath -Force
            }
        }
    } catch {
        Write-Error "Failed to restore Excel AccessVBOM to its original state: $($_.Exception.Message)"
        throw
    }
}