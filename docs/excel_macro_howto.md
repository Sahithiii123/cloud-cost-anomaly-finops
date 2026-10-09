# Excel Macro Setup

On Windows with desktop Excel installed, `python run_all.py` generates `reports/monthly_finops_report.xlsm` through Excel COM. It contains three native PivotTables: spend by service x month, spend by region, and average tag compliance by service. The VBA module `FinOpsRefresh` is embedded and the build invokes `RefreshFinOpsReport` once to refresh pivots, apply number formats, and write the refresh timestamp. No manual module import is needed on that compatible build path.

The pipeline also always generates `reports/monthly_finops_report.xlsx` as a fallback with formula-driven summary tables and native Excel charts. It is not a PivotTable workbook and has no embedded macro. Budget inputs remain blank until an approved budget is supplied.

## Refreshing the XLSM Later

1. Open the generated `.xlsm` in desktop Excel.
2. If allowed by local policy, enable macros and press `Alt+F8` to run `RefreshFinOpsReport`; this refreshes connections and all pivots, reapplies formats, and updates `Report Metadata!B2`.
3. Save the workbook after refresh.

The COM build temporarily enables the current user's Excel `AccessVBOM` value to inject the VBA project and restores the original registry value/state in a `finally` block. A machine policy that disables VBA project access is never overridden; in that case the builder reports the failure and leaves the `.xlsx` fallback. On non-Windows systems or without desktop Excel, only the `.xlsx` is produced. Macro execution may still be blocked by Excel Trust Center or endpoint policy; subsequent refresh is manual.