# Business Questions and Data Assets

| Business question | KPI / analysis | Data asset | Grain / caveat |
|---|---|---|---|
| Which services have unusual spend changes? | Rolling z-score anomaly rate | `cur_sample`, `anomalies_detected.csv` | Service/day; threshold is absolute z-score > 2.5. |
| Is increased cost explained by more usage? | Unit cost and rolling unit-cost deviation | `cur_sample`, `analysis_summary.json` | Usage units must be comparable within service. |
| Where is tag coverage weakest? | Resource-record and spend compliance | `tag_compliance_by_service_region_month.csv`, `top_untagged_cost_drivers.csv` | Synthetic resource records proxy line items; public FOCUS tag names may differ. |
| Is spend within plan? | Budget vs actual variance | `monthly_finops_report.xlsx` | No approved budget is supplied; workbook inputs are blank. |
| What is the next 30-day spend outlook? | Regression and exponential smoothing; rolling-origin MAPE | `forecast_daily.csv`, `forecast_backtest.csv` | Synthetic demonstration, not a financial commitment. |
| Did remediation realize savings? | Verified post-change baseline-adjusted savings | `savings_estimate.json` | Current output is only simulated counterfactual opportunity, not realized savings. |
| Can billing totals be reconciled? | Source-to-curated amount, date, currency and row-count checks | Data-quality report and source extracts | Public sample is anonymized; this repository does not contain employer billing data. |
| What explains a discrepancy ticket? | Date/service/region, baseline, z-score, unit-cost shift, RCA hypothesis | `tickets/` and `tickets_summary.csv` | Hypotheses require owner validation; synthetic tickets do not represent incidents. |