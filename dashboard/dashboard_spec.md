# Dashboard Specification

No interactive dashboard is included in this repository. The views below can be implemented from `dashboard/data/` without changing the analysis outputs.

## Shared Filters

- `usage_date` or `usage_month` range
- `service`
- `region`
- `classification` (`anomalies.csv` only)
- `Environment`, `Owner`, `CostCenter`, `Application` on the tag compliance view

## KPI Cards

| Card | Source fields | Calculation |
|---|---|---|
| Actual spend | `daily_cost_tidy.cost_usd` | Sum within selected date/service/region filters. |
| Anomaly-days | `anomalies.usage_date`, `anomalies.service` | Count flagged service-day rows; do not call this unique calendar dates. |
| Inefficiency candidates | `anomalies.likely_waste` | Count true values; these are modeled classifications, not confirmed waste. |
| Resource-record tag compliance | `tag_compliance_monthly.compliant_resource_records`, `resource_records` | 100 times compliant records / total records. |
| Spend tag compliance | `total_cost`, `untagged_cost` | 100 times (total cost - untagged cost) / total cost. |
| Forecast next 30 days | `forecast_daily.regression_forecast` | Sum forecast values; label forecast, not actual. |

## Views

| View | Dataset / fields | Calculated fields | Filters |
|---|---|---|---|
| Spend trend | `daily_cost_tidy.csv`: `usage_date`, `service`, `region`, `cost_usd`, `usage_quantity` | 7-day moving spend; unit cost = cost / quantity | Date, service, region |
| Service-region comparison | `daily_cost_wide.csv`: `usage_date` plus `<service>_<region>_cost_usd` columns | Period sum and share of total | Date range; select service/region columns |
| Anomaly triage | `anomalies.csv`: `usage_date`, `service`, `daily_cost`, `roll_mean`, `z_score`, `cpu_pct_dev`, `likely_waste` | Cost variance = daily cost - baseline; classification from `likely_waste` | Date, service, classification |
| Regional unit-cost candidates | `regional_inefficiency_candidates.csv`: date, service, region, regional cost z, regional unit-cost %, regional unit-cost z | Regional candidate requires positive regional cost z > 2.5 and unit-cost z > 2.5; do not interpret the broad regional scan as the primary 33 service-day alert count | Date, service, region |
| Tag compliance | `tag_compliance_monthly.csv`: service, region, month, record counts, total/untagged cost, compliance percentages; `tag_compliance_records.csv`: date, service, region, four tags, cost, compliance flag | Missing/invalid tag rate = 100 - compliance | Month/date, service, region, Environment, Owner, CostCenter, Application |
| Forecast | `forecast_daily.csv`: `usage_date`, regression and exponential-smoothing forecast | 30-day total and method agreement from summary output | Forecast horizon |

## CSV Inventory

- `daily_cost_tidy.csv`: long-form daily service-region cost and quantity.
- `daily_cost_wide.csv`: one row per date with service-region cost columns.
- `tag_compliance_monthly.csv`: service-region-month compliance metrics.
- `tag_compliance_records.csv`: synthetic tag values and row-level compliance flags for filtering and drill-through.
- `anomalies.csv`: actual detector output, including baseline, z-score, unit-cost deviation, and classification flag.
- `regional_anomalies.csv` and `regional_inefficiency_candidates.csv`: independent service-region-day scores and strict regional candidates.
- `forecast_daily.csv`: both daily forecast series.