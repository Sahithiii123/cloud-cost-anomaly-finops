# Metrics Definitions

All calculations use USD and the synthetic CUR-like `cur_sample` schema unless a source is named. The file has daily service/region line items; it does not contain a provider resource ID. Synthetic tag compliance therefore uses a line-item/resource-day proxy, not a count of distinct cloud resources.

| KPI | Business definition and exact formula | Grain | Owner | Source | Refresh | Caveats |
|---|---|---|---|---|---|---|
| Unit cost | Regional cost per unit: `SUM(unblended_cost) / NULLIF(SUM(usage_quantity), 0)` at service-region-day grain. Deviation is `100 * (current ratio - prior 14-day regional mean) / prior mean`; strict candidate additionally requires regional cost z-score >2.5 and unit-cost z-score >2.5. Service/day pooled ratio remains secondary. | Primary: service/region/day; secondary: service/day | FinOps analyst | `cur_sample`; `regional_daily_metrics.csv`, `anomalies_detected.csv` | Daily in this demo | Usage quantities can mix unlike units across services; compare only within compatible service/usage type. A strict independent regional score changes candidate counts vs the pooled service/day score. |
| Anomaly rate | `COUNT(flagged service-days) / COUNT(observed service-days)`; a day is flagged when `ABS((daily_cost - prior 7-day mean) / prior 7-day sample stddev) > 2.5`. | Service/day | FinOps analyst | `cur_sample`; anomaly outputs | Daily | Rolling baseline is shifted to exclude the current day; early periods lack a full baseline. |
| Tag compliance % | Resource-record compliance: `100 * compliant line-item/resource-day records / all records`; spend compliance: `100 * (total cost - untagged cost) / total cost`. A record is compliant only if all four tags are present and in policy. | Service/region/month | FinOps + service owner | `cur_sample`; `tag_compliance_by_service_region_month.csv` | Daily, reported monthly | Record count proxies resources because the synthetic schema has no ResourceId. Cost-weighted rates can be affected by credits/negative costs; this fixture has nonnegative costs. |
| Budget vs actuals | `actual USD - approved budget USD`; variance percent is `100 * (actual - budget) / budget`. | Month/service | FinOps | Actual from `cur_sample`; budget must be separately approved and supplied | Monthly | This repo has no approved budgets; workbook budget cells are blank and no variance is asserted. |
| Savings realised | `verified post-remediation baseline-adjusted cost reduction`; the demo instead reports a counterfactual `event actual - prior-14-day daily mean * event days`, labeled simulated opportunity. | Event/service/region | FinOps + service owner | `savings_estimate.json` | After a modeled event | Not realized savings; causality and workload equivalence are not demonstrated. |
| Forecast accuracy / MAPE | `mean(abs((actual - forecast) / actual)) * 100` over rolling-origin 30-day holdouts. Regression uses the preceding 90 daily observations; exponential smoothing uses alpha 0.3 and a flat 30-day level. | 30-day holdout/origin | FinOps analyst | `forecast_backtest.csv`, `analysis_summary.json` | Each pipeline run | MAPE is undefined for zero actuals; zeros are omitted. Synthetic forecast is not a production budget. |
| Forecast agreement | `100 * abs(regression_total - smoothing_total) / mean(regression_total, smoothing_total)`. | Next 30 days | FinOps analyst | `analysis_summary.json` | Each pipeline run | Agreement is not forecast accuracy; use MAPE for historical error. |

## Athena SQL Examples

```sql
-- Unit cost and prior 14-day comparison
WITH daily AS (
  SELECT usage_date, service, region,
         SUM(unblended_cost) AS cost,
         SUM(usage_quantity) AS quantity
  FROM cur_sample
  GROUP BY 1, 2, 3
), ratios AS (
  SELECT *, cost / NULLIF(quantity, 0) AS unit_cost,
         AVG(cost / NULLIF(quantity, 0)) OVER (
           PARTITION BY service, region ORDER BY usage_date
           ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
         ) AS prior_14d_unit_cost
  FROM daily
)
SELECT *, 100 * (unit_cost - prior_14d_unit_cost) / NULLIF(prior_14d_unit_cost, 0) AS unit_cost_change_pct
FROM ratios;
```

```sql
-- Anomaly rate numerator and denominator after applying the z-score rule
WITH daily AS (
  SELECT usage_date, service, SUM(unblended_cost) AS cost
  FROM cur_sample GROUP BY 1, 2
), scored AS (
  SELECT *, AVG(cost) OVER (PARTITION BY service ORDER BY usage_date ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS baseline,
         STDDEV_SAMP(cost) OVER (PARTITION BY service ORDER BY usage_date ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS sigma
  FROM daily
)
SELECT service, COUNT_IF(ABS((cost - baseline) / NULLIF(sigma, 0)) > 2.5) * 100.0 / COUNT(*) AS anomaly_rate_pct
FROM scored WHERE baseline IS NOT NULL GROUP BY service;
```

```sql
-- Tag spend compliance for AWS CUR user-tag columns
SELECT date_trunc('month', line_item_usage_start_date) AS usage_month,
       product_product_name AS service, product_region AS region,
       100.0 * SUM(CASE WHEN resource_tags_user_environment IS NOT NULL
                         AND resource_tags_user_owner IS NOT NULL
                         AND resource_tags_user_costcenter IS NOT NULL
                         AND resource_tags_user_application IS NOT NULL
                        THEN line_item_unblended_cost ELSE 0 END)
         / NULLIF(SUM(line_item_unblended_cost), 0) AS spend_compliance_pct
FROM cur_db.cur_table GROUP BY 1, 2, 3;
```

## Data Dictionary

| Field | Type | Meaning |
|---|---|---|
| `usage_date` | date | Usage/charge day; FOCUS path maps `ChargePeriodStart` to UTC date. |
| `service` | string | Cloud service name. |
| `region` | string | Region identifier/name. |
| `usage_type` | string | Usage unit/type, not comparable across all services. |
| `unblended_cost` | decimal USD | Billed/unblended cost for the line item. |
| `usage_quantity` | decimal | Quantity in `usage_type` units. |
| `Environment`, `Owner`, `CostCenter`, `Application` | nullable strings | Required governance tags; missing or unrecognized values are noncompliant. |