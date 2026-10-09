"""
Loads the synthetic CUR data into SQLite, runs Athena-style SQL for
MoM/QoQ trends, detects cost anomalies (z-score on rolling window +
cost-per-unit-usage divergence), builds a simple linear forecast for
next month's spend, and generates charts + written recommendations.
"""
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from data_quality import require_valid_file
from analysis_metrics import forecast_agreement, regional_metrics, score_daily_metrics

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("FINOPS_DATA_PATH", ROOT / "data" / "cur_sample.csv"))
OUTPUT_DIR = Path(os.environ.get("FINOPS_OUTPUT_DIR", ROOT / "outputs" / "synthetic"))
CHARTS = Path(os.environ.get("FINOPS_CHARTS_DIR", ROOT / "charts"))
IS_SYNTHETIC = DATA.resolve() == (ROOT / "data" / "cur_sample.csv").resolve()
CHARTS.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

require_valid_file(DATA, OUTPUT_DIR / "data_quality_report.md",
                   allow_sparse_dates=os.environ.get("FINOPS_ALLOW_SPARSE_DATES") == "1",
                   allow_signed_costs=os.environ.get("FINOPS_ALLOW_SIGNED_COSTS") == "1",
                   allow_non_usage_quantity_nulls=os.environ.get("FINOPS_ALLOW_NON_USAGE_QUANTITY_NULLS") == "1")
df = pd.read_csv(DATA, parse_dates=["usage_date"], low_memory=False,
                 dtype={column: "string" for column in ["Environment", "Owner", "CostCenter", "Application"]})

# ---------------------------------------------------------------
# 1. Load into SQLite and run the trend SQL (MoM / QoQ / rolling)
# ---------------------------------------------------------------
conn = sqlite3.connect(":memory:")
df.to_sql("cur_sample", conn, index=False)

# NOTE: the canonical, documented SQL lives in sql/trend_analysis.sql
# (Athena-style, meant to be read/run as-is against real CUR tables).
# We re-run equivalent queries here directly against SQLite for the
# local demo, since SQLite requires slightly different date functions.

mom_df = pd.read_sql_query("""
    WITH monthly_service_cost AS (
        SELECT strftime('%Y-%m', usage_date) AS usage_month, service,
               SUM(unblended_cost) AS monthly_cost
        FROM cur_sample GROUP BY 1, 2
    )
    SELECT usage_month, service, monthly_cost,
        LAG(monthly_cost) OVER (PARTITION BY service ORDER BY usage_month) AS prev_month_cost,
        ROUND(100.0 * (monthly_cost - LAG(monthly_cost) OVER (PARTITION BY service ORDER BY usage_month))
            / NULLIF(LAG(monthly_cost) OVER (PARTITION BY service ORDER BY usage_month), 0), 2) AS mom_pct_change
    FROM monthly_service_cost ORDER BY service, usage_month
""", conn)

qoq_df = pd.read_sql_query("""
    WITH quarterly_service_cost AS (
        SELECT (strftime('%Y', usage_date) || '-Q' ||
                ((CAST(strftime('%m', usage_date) AS INTEGER) - 1) / 3 + 1)) AS usage_quarter,
               service, SUM(unblended_cost) AS quarterly_cost
        FROM cur_sample GROUP BY 1, 2
    )
    SELECT usage_quarter, service, quarterly_cost,
        LAG(quarterly_cost) OVER (PARTITION BY service ORDER BY usage_quarter) AS prev_quarter_cost,
        ROUND(100.0 * (quarterly_cost - LAG(quarterly_cost) OVER (PARTITION BY service ORDER BY usage_quarter))
            / NULLIF(LAG(quarterly_cost) OVER (PARTITION BY service ORDER BY usage_quarter), 0), 2) AS qoq_pct_change
    FROM quarterly_service_cost ORDER BY service, usage_quarter
""", conn)

print("=== MoM sample ===")
print(mom_df[mom_df.service == "AmazonEC2"].tail(6).to_string(index=False))
print("\n=== QoQ sample ===")
print(qoq_df[qoq_df.service == "AmazonEC2"].to_string(index=False))

# ---------------------------------------------------------------
# 2. Anomaly detection: z-score on daily cost vs rolling 7-day window
#    (computed in pandas since SQLite lacks STDDEV window fn)
# ---------------------------------------------------------------
daily = score_daily_metrics(df, ["service"])

ANOMALY_Z = 2.5
anomalies = daily[(daily["z_score"].abs() > ANOMALY_Z)].copy()
anomalies = anomalies.sort_values("z_score", ascending=False)
anomalies["likely_waste"] = anomalies["cpu_pct_dev"] > 15  # cost/unit jumped -> inefficiency, not just more usage
anomalies.to_csv(OUTPUT_DIR / "anomalies_detected.csv", index=False)

regional = regional_metrics(df)
regional_anomalies = regional[regional["regional_cost_anomaly"]].copy()
regional_candidates = regional[regional["regional_inefficiency_candidate"]].copy()
regional.to_csv(OUTPUT_DIR / "regional_daily_metrics.csv", index=False)
regional_anomalies.to_csv(OUTPUT_DIR / "regional_anomalies.csv", index=False)
regional_candidates.to_csv(OUTPUT_DIR / "regional_inefficiency_candidates.csv", index=False)

print(f"\n=== {len(anomalies)} anomaly-days flagged (|z| > {ANOMALY_Z}) ===")
print(anomalies[["usage_date", "service", "daily_cost", "z_score", "cpu_pct_dev"]].head(15).to_string(index=False))


# ---------------------------------------------------------------
# 3. Forecast next month's total spend (simple linear regression
#    on daily total cost, + exponential smoothing as a cross-check)
# ---------------------------------------------------------------
total_daily = df.groupby("usage_date", as_index=False)["unblended_cost"].sum()
total_daily = total_daily.sort_values("usage_date").reset_index(drop=True)
total_daily["t"] = np.arange(len(total_daily))

# Linear regression on last 90 days (captures recent trend, not full history)
recent = total_daily.tail(90).copy()
coeffs = np.polyfit(recent["t"], recent["unblended_cost"], 1)
slope, intercept = coeffs

future_t = np.arange(total_daily["t"].max() + 1, total_daily["t"].max() + 31)
linreg_forecast = slope * future_t + intercept
linreg_month_total = linreg_forecast.sum()

# Exponential smoothing (alpha=0.3) cross-check
alpha = 0.3
smoothed = [total_daily["unblended_cost"].iloc[0]]
for val in total_daily["unblended_cost"].iloc[1:]:
    smoothed.append(alpha * val + (1 - alpha) * smoothed[-1])
last_smoothed = smoothed[-1]
exp_smooth_month_total = last_smoothed * 30

def mape(actual, predicted):
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    nonzero = actual_values != 0
    return float(np.mean(np.abs((actual_values[nonzero] - predicted_values[nonzero]) / actual_values[nonzero])) * 100)


def finite_or_none(value):
    numeric = float(value)
    return numeric if np.isfinite(numeric) else None


backtest_rows = []
for origin in range(90, len(total_daily) - 30, 30):
    train = total_daily.iloc[max(0, origin - 90):origin]
    actual = total_daily["unblended_cost"].iloc[origin:origin + 30].to_numpy()
    train_t = train["t"].to_numpy()
    slope_at_origin, intercept_at_origin = np.polyfit(train_t, train["unblended_cost"], 1)
    future_t_at_origin = np.arange(origin, origin + 30)
    regression = slope_at_origin * future_t_at_origin + intercept_at_origin
    smooth_level = float(train["unblended_cost"].iloc[0])
    for value in train["unblended_cost"].iloc[1:]:
        smooth_level = alpha * float(value) + (1 - alpha) * smooth_level
    smoothing = np.full(30, smooth_level)
    backtest_rows.append({
        "origin_date": str(total_daily["usage_date"].iloc[origin - 1].date()),
        "horizon_days": 30,
        "regression_mape_pct": mape(actual, regression),
        "exponential_smoothing_mape_pct": mape(actual, smoothing),
    })

regression_mape = float(np.mean([row["regression_mape_pct"] for row in backtest_rows])) if backtest_rows else None
smoothing_mape = float(np.mean([row["exponential_smoothing_mape_pct"] for row in backtest_rows])) if backtest_rows else None
forecast_agreement_pct = forecast_agreement(linreg_month_total, exp_smooth_month_total)
decision_grade = IS_SYNTHETIC or (
    len(backtest_rows) >= 3
    and regression_mape is not None and regression_mape <= 20
    and smoothing_mape is not None and smoothing_mape <= 20
    and forecast_agreement_pct <= 15
)
suppression_reasons = []
if not IS_SYNTHETIC:
    if len(backtest_rows) < 3:
        suppression_reasons.append(f"only {len(backtest_rows)} rolling-origin holdouts; at least 3 required")
    if regression_mape is None or regression_mape > 20:
        suppression_reasons.append("regression MAPE is unavailable or exceeds 20%")
    if smoothing_mape is None or smoothing_mape > 20:
        suppression_reasons.append("exponential-smoothing MAPE is unavailable or exceeds 20%")
    if forecast_agreement_pct > 15:
        suppression_reasons.append("method totals disagree by more than 15%")
forecast_status = "published" if decision_grade else "suppressed"
forecast_suppression_reason = "; ".join(suppression_reasons) if suppression_reasons else None
forecast_dates = pd.date_range(total_daily["usage_date"].max() + pd.Timedelta(days=1), periods=30)
if decision_grade:
    forecast_daily = pd.DataFrame({"usage_date": forecast_dates,
                                   "regression_forecast": linreg_forecast,
                                   "exponential_smoothing_forecast": last_smoothed})
else:
    forecast_daily = pd.DataFrame(columns=["usage_date", "regression_forecast", "exponential_smoothing_forecast"])
forecast_daily.to_csv(OUTPUT_DIR / "forecast_daily.csv", index=False)
pd.DataFrame(backtest_rows).to_csv(OUTPUT_DIR / "forecast_backtest.csv", index=False)
(OUTPUT_DIR / "forecast_assessment.json").write_text(json.dumps({
    "status": forecast_status,
    "reason": forecast_suppression_reason,
    "backtest_origins": len(backtest_rows),
    "required_origins": 3 if not IS_SYNTHETIC else 0,
    "regression_mape_pct": regression_mape,
    "exponential_smoothing_mape_pct": smoothing_mape,
    "decision_rule": "For public data, publish only with >=3 rolling-origin 30-observation holdouts, both MAPEs <=20%, and method agreement <=15%. Otherwise forecast values are withheld.",
}, indent=2) + "\n", encoding="utf-8")
efficiencies = anomalies[anomalies["likely_waste"]]
aggregate_alert_keys = anomalies[["usage_date", "service"]].drop_duplicates()
regional_alert_candidates = regional_candidates.merge(aggregate_alert_keys, on=["usage_date", "service"], how="inner")
regional_candidates = regional_candidates.sort_values("unit_cost_z_score", ascending=False)
top_regional_candidate = regional_candidates.iloc[0] if len(regional_candidates) else None
summary = {
    "source": "synthetic" if IS_SYNTHETIC else "public FOCUS full dataset",
    "start_date": str(df["usage_date"].min().date()),
    "end_date": str(df["usage_date"].max().date()),
    "calendar_months": int(df["usage_date"].dt.to_period("M").nunique()),
    "services": int(df["service"].nunique()),
    "regions": int(df["region"].nunique()),
    "anomaly_days": int(len(anomalies)),
    "aggregate_service_day_inefficiencies": int(len(efficiencies)),
    "regional_cost_anomalies": int(len(regional_anomalies)),
    "regional_positive_cost_anomalies": int(regional["positive_regional_cost_anomaly"].sum()),
    "regional_pct_candidates": int(regional["regional_pct_candidate"].sum()),
    "regional_inefficiency_candidates": int(len(regional_candidates)),
    "regional_candidates_within_service_day_alerts": int(len(regional_alert_candidates)),
    "inefficiencies": int(len(regional_candidates)),
    "inefficiency_service": str(top_regional_candidate["service"]) if top_regional_candidate is not None else None,
    "inefficiency_region": str(top_regional_candidate["region"]) if top_regional_candidate is not None else None,
    "cost_per_unit_change_pct": finite_or_none(top_regional_candidate["cpu_pct_dev"]) if top_regional_candidate is not None else None,
    "regional_unit_cost_z_score": finite_or_none(top_regional_candidate["unit_cost_z_score"]) if top_regional_candidate is not None else None,
    "aggregate_service_day_cost_per_unit_change_pct": finite_or_none(efficiencies.iloc[0]["cpu_pct_dev"]) if len(efficiencies) else None,
    "forecast_status": forecast_status,
    "forecast_suppression_reason": forecast_suppression_reason,
    "regression_forecast_30d_usd": float(linreg_month_total) if decision_grade else None,
    "exponential_smoothing_forecast_30d_usd": float(exp_smooth_month_total) if decision_grade else None,
    "forecast_agreement_pct": float(forecast_agreement_pct) if decision_grade else None,
    "forecast_regression_mape_pct": regression_mape,
    "forecast_exponential_smoothing_mape_pct": smoothing_mape,
    "backtest_origins": len(backtest_rows),
    "last_actual_30d_usd": float(total_daily.tail(30)["unblended_cost"].sum()) if IS_SYNTHETIC else None,
}
(OUTPUT_DIR / "analysis_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

if decision_grade:
    print(f"\n=== Forecast: next 30 days ({forecast_status}) ===")
    print(f"Linear regression (last 90d trend): ${linreg_month_total:,.2f}")
    print(f"Exp. smoothing (last-level x30):     ${exp_smooth_month_total:,.2f}")
else:
    print(f"\n=== Forecast suppressed: {forecast_suppression_reason} ===")

if IS_SYNTHETIC:
    last_actual_month = total_daily.tail(30)["unblended_cost"].sum()
    print(f"Last actual 30-day spend:            ${last_actual_month:,.2f}")

# ---------------------------------------------------------------
# 4. Charts
# ---------------------------------------------------------------
plt.style.use("seaborn-v0_8-whitegrid")

# Chart 1: Total cost trend over time
fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(total_daily["usage_date"], total_daily["unblended_cost"], color="#2563eb", linewidth=1)
ax.plot(total_daily["usage_date"], total_daily["unblended_cost"].rolling(7).mean(),
        color="#1e293b", linewidth=2, label="7-day rolling avg")
ax.set_title(f"Total Daily Spend — {summary['calendar_months']} Calendar Months", fontsize=13, fontweight="bold")
ax.set_ylabel("Daily Cost (USD)")
ax.legend()
fig.tight_layout()
fig.savefig(CHARTS / "01_cost_trend.png", dpi=150)
plt.close(fig)

# Chart 2: Anomalies flagged, overlaid on cost trend (per top affected service)
top_anomaly_service = anomalies["service"].value_counts().idxmax() if len(anomalies) else "AmazonEC2"
svc_daily = daily[daily.service == top_anomaly_service]
svc_anomalies = anomalies[anomalies.service == top_anomaly_service]

fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(svc_daily["usage_date"], svc_daily["daily_cost"], color="#2563eb", linewidth=1, label="Daily cost")
ax.plot(svc_daily["usage_date"], svc_daily["roll_mean"], color="#94a3b8", linewidth=1, linestyle="--", label="Rolling avg")
ax.scatter(svc_anomalies["usage_date"], svc_anomalies["daily_cost"], color="#dc2626", s=50, zorder=5, label="Anomaly flagged")
ax.set_title(f"Anomalies Flagged — {top_anomaly_service}", fontsize=13, fontweight="bold")
ax.set_ylabel("Daily Cost (USD)")
ax.legend()
fig.tight_layout()
fig.savefig(CHARTS / "02_anomalies_flagged.png", dpi=150)
plt.close(fig)

# Chart 3: Forecast vs actual (last 60 actual days + next 30 forecast days)
fig, ax = plt.subplots(figsize=(11, 5))
last60 = total_daily.tail(60)
future_dates = pd.date_range(total_daily["usage_date"].max() + pd.Timedelta(days=1), periods=30)
ax.plot(last60["usage_date"], last60["unblended_cost"], color="#2563eb", linewidth=1.3, label="Actual")
if decision_grade:
    ax.plot(future_dates, linreg_forecast, color="#16a34a", linewidth=1.5, linestyle="--", label="Forecast (linear trend)")
else:
    ax.text(0.5, 0.92, "Forecast suppressed: backtest evidence insufficient", transform=ax.transAxes,
            ha="center", va="top", fontsize=10, color="#b91c1c")
ax.axvline(total_daily["usage_date"].max(), color="#94a3b8", linewidth=1, linestyle=":")
ax.set_title("30-Day Spend Forecast vs. Recent Actuals" if decision_grade else "Observed Spend — Forecast Suppressed",
             fontsize=13, fontweight="bold")
ax.set_ylabel("Daily Cost (USD)")
ax.legend()
fig.tight_layout()
fig.savefig(CHARTS / "03_forecast_vs_actual.png", dpi=150)
plt.close(fig)

print(f"\nCharts saved to {CHARTS}")
print("Done.")
