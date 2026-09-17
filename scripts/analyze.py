"""
Loads the synthetic CUR data into SQLite, runs Athena-style SQL for
MoM/QoQ trends, detects cost anomalies (z-score on rolling window +
cost-per-unit-usage divergence), builds a simple linear forecast for
next month's spend, and generates charts + written recommendations.
"""
import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "cur_sample.csv"
CHARTS = ROOT / "charts"
CHARTS.mkdir(exist_ok=True)

df = pd.read_csv(DATA, parse_dates=["usage_date"])

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
daily = df.groupby(["usage_date", "service"], as_index=False).agg(
    daily_cost=("unblended_cost", "sum"),
    daily_usage=("usage_quantity", "sum"),
)
daily = daily.sort_values(["service", "usage_date"])

daily["roll_mean"] = daily.groupby("service")["daily_cost"].transform(
    lambda s: s.rolling(7, min_periods=5).mean().shift(1)
)
daily["roll_std"] = daily.groupby("service")["daily_cost"].transform(
    lambda s: s.rolling(7, min_periods=5).std().shift(1)
)
daily["z_score"] = (daily["daily_cost"] - daily["roll_mean"]) / daily["roll_std"]

# cost-per-unit-usage (efficiency signal)
daily["cost_per_unit"] = daily["daily_cost"] / daily["daily_usage"]
daily["cpu_roll_mean"] = daily.groupby("service")["cost_per_unit"].transform(
    lambda s: s.rolling(14, min_periods=7).mean().shift(1)
)
daily["cpu_pct_dev"] = 100 * (daily["cost_per_unit"] - daily["cpu_roll_mean"]) / daily["cpu_roll_mean"]

ANOMALY_Z = 2.5
anomalies = daily[(daily["z_score"].abs() > ANOMALY_Z)].copy()
anomalies = anomalies.sort_values("z_score", ascending=False)
anomalies["likely_waste"] = anomalies["cpu_pct_dev"] > 15  # cost/unit jumped -> inefficiency, not just more usage
anomalies.to_csv(ROOT / "data" / "anomalies_detected.csv", index=False)

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

print(f"\n=== Forecast: next 30 days ===")
print(f"Linear regression (last 90d trend): ${linreg_month_total:,.2f}")
print(f"Exp. smoothing (last-level x30):     ${exp_smooth_month_total:,.2f}")

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
ax.set_title("Total Daily AWS Spend — 14 Month Trend", fontsize=13, fontweight="bold")
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
ax.plot(future_dates, linreg_forecast, color="#16a34a", linewidth=1.5, linestyle="--", label="Forecast (linear trend)")
ax.axvline(total_daily["usage_date"].max(), color="#94a3b8", linewidth=1, linestyle=":")
ax.set_title("30-Day Spend Forecast vs. Recent Actuals", fontsize=13, fontweight="bold")
ax.set_ylabel("Daily Cost (USD)")
ax.legend()
fig.tight_layout()
fig.savefig(CHARTS / "03_forecast_vs_actual.png", dpi=150)
plt.close(fig)

print("\nCharts saved to /charts")
print("Done.")
