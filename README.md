# Cloud Cost Anomaly Finder (FinOps)

Replicates the type of cost-anomaly analysis I do professionally, using public sample AWS billing data instead of proprietary client data.

Simulates 14 months of AWS Cost & Usage Report (CUR)-style data across 7 services and 4 regions, then finds spend anomalies, forecasts next month's bill, and turns both into a written FinOps recommendation — not just a chart.

## Repo layout

```
data/           synthetic CUR data + detected anomalies output
sql/            Athena-style SQL (CTEs + window functions) for MoM/QoQ trends
scripts/        generate_data.py, analyze.py (anomaly detection + forecast + charts)
charts/         3 output charts
```

## Method

**Trend analysis (`sql/trend_analysis.sql`)** — MoM and QoQ cost per service using `LAG()` window functions over CTEs, written Athena-style so it drops into a real CUR table with no changes.

**Anomaly detection** — 7-day rolling mean/stddev per service → z-score per day, flagged when `|z| > 2.5`. Every flagged day is also checked against its **cost-per-unit-usage** trend: if cost jumps but cost/unit stays flat, that's usage-driven growth (fine). If cost/unit jumps too, that's inefficiency — someone's paying more for the same amount of work.

**Forecast** — linear regression on the last 90 days of daily spend, cross-checked against exponential smoothing (α=0.3). Both landed within ~1.5% of each other (~$82K for the next 30 days), so the forecast holds up under a second method.

## What it found

33 anomaly-days flagged across 14 months. Most are legitimate — a real S3 lifecycle-policy gap where storage grew and cost tracked it, or Lambda usage that spiked because usage spiked. Only one flagged day survived the cost-per-unit check: **AmazonEC2, us-east-1, mid-Feb 2025** — cost jumped 40% above its rolling baseline while usage-per-dollar also jumped 40%, meaning the same workload started costing 40% more per unit of usage.

## Recommendations

1. **Flag AmazonEC2 (us-east-1) for a rightsizing review.** Spend rose ~40% over a two-week window in Feb 2025 with no matching usage increase — this is the one anomaly in the dataset that's cost inefficiency rather than growth, and it's the highest-value fix here.
2. **S3 and Lambda spikes are usage-driven — don't cut them, just alert on them.** The Oct 2024 S3 spike and May 2025 Lambda spike both moved cost and usage together, so the fix isn't reducing spend, it's setting a budget alert so nobody's surprised by the bill next time.
3. **Forecasted spend for the next 30 days is ~$82K, in line with the last actual 30-day period (~$81.4K).** No corrective action needed on the trend itself — the anomaly above is the one line item worth chasing.

## How to run this

```bash
pip install pandas numpy matplotlib scipy
python3 scripts/generate_data.py
python3 scripts/analyze.py
```
