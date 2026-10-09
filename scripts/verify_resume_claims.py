"""Assert each numeric synthetic resume claim against generated outputs."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent


def main():
    data = pd.read_csv(ROOT / "data" / "cur_sample.csv", parse_dates=["usage_date"])
    summary_path = ROOT / "outputs" / "synthetic" / "analysis_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    anomalies = pd.read_csv(ROOT / "outputs" / "synthetic" / "anomalies_detected.csv")
    tickets = pd.read_csv(ROOT / "tickets" / "tickets_summary.csv")
    regional_anomalies = pd.read_csv(ROOT / "outputs" / "synthetic" / "regional_anomalies.csv")
    regional_candidates = pd.read_csv(ROOT / "outputs" / "synthetic" / "regional_inefficiency_candidates.csv")
    forecast = pd.read_csv(ROOT / "outputs" / "synthetic" / "forecast_daily.csv")
    backtest = pd.read_csv(ROOT / "outputs" / "synthetic" / "forecast_backtest.csv")
    tag_months = pd.read_csv(ROOT / "outputs" / "synthetic" / "tag_compliance_by_month.csv")
    quality_report = (ROOT / "outputs" / "synthetic" / "data_quality_report.md").read_text(encoding="utf-8")
    regression_total = float(forecast["regression_forecast"].sum())
    smoothing_total = float(forecast["exponential_smoothing_forecast"].sum())
    agreement = abs(regression_total - smoothing_total) / ((regression_total + smoothing_total) / 2) * 100
    candidate_tickets = tickets[tickets["classification"] == "regional unit-cost anomaly candidate"]
    ec2_regional_candidate = candidate_tickets[(candidate_tickets["service"] == "AmazonEC2")
                                               & (candidate_tickets["region"] == "us-east-1")]
    aggregate_candidates = anomalies[anomalies["likely_waste"]]
    checks = [
        ("14 months of data", data["usage_date"].dt.to_period("M").nunique() == 14, data["usage_date"].dt.to_period("M").nunique()),
        ("7 services", data["service"].nunique() == 7, data["service"].nunique()),
        ("4 regions", data["region"].nunique() == 4, data["region"].nunique()),
        ("33 anomaly-days", len(anomalies) == 33 and len(tickets) == 33, len(anomalies)),
        ("regional cost-z anomaly rows", len(regional_anomalies) == summary["regional_cost_anomalies"], len(regional_anomalies)),
        ("regional candidates use positive cost z and unit-cost z > 2.5", len(regional_candidates) == 2 and len(candidate_tickets) == 2 and summary["regional_candidates_within_service_day_alerts"] == 2, len(regional_candidates)),
        ("EC2 us-east-1 regional candidate", len(ec2_regional_candidate) == 1, f"{ec2_regional_candidate.iloc[0]['service']} / {ec2_regional_candidate.iloc[0]['region']}" if len(ec2_regional_candidate) else "none"),
        ("regional unit cost deviation matches measured event", len(ec2_regional_candidate) == 1 and 70 <= float(ec2_regional_candidate.iloc[0]["cost_per_unit_change_pct"]) <= 75 and float(ec2_regional_candidate.iloc[0]["regional_unit_cost_z_score"]) > 2.5, f"{ec2_regional_candidate.iloc[0]['cost_per_unit_change_pct']:.2f}% (z={ec2_regional_candidate.iloc[0]['regional_unit_cost_z_score']:.3f})" if len(ec2_regional_candidate) else "none"),
        ("aggregate service-day ratio remains secondary", len(aggregate_candidates) == 1 and 38 <= float(aggregate_candidates.iloc[0]["cpu_pct_dev"]) <= 42 and np.isclose(summary["aggregate_service_day_cost_per_unit_change_pct"], aggregate_candidates.iloc[0]["cpu_pct_dev"]), f"{summary['aggregate_service_day_cost_per_unit_change_pct']:.2f}%"),
        ("30-day forecast approximately $82K", len(forecast) == 30 and 78000 <= regression_total <= 86000, f"${regression_total:,.2f}"),
        ("method agreement within 1.5%", agreement <= 1.5 and np.isclose(agreement, summary["forecast_agreement_pct"]), f"{agreement:.3f}%"),
        ("rolling-origin MAPE has 11 origins", len(backtest) == 11 and len(backtest) == summary["backtest_origins"], len(backtest)),
        ("data quality report passes", "Overall: **PASS**." in quality_report, "PASS" if "Overall: **PASS**." in quality_report else "FAIL"),
        ("tag compliance improves from about 70%", 65 <= tag_months.iloc[0]["resource_compliance_pct"] <= 75 and tag_months.iloc[-1]["resource_compliance_pct"] > tag_months.iloc[0]["resource_compliance_pct"], f"{tag_months.iloc[0]['resource_compliance_pct']:.2f}% to {tag_months.iloc[-1]['resource_compliance_pct']:.2f}%"),
    ]
    for label, passed, value in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {label} ({value})")
    if not all(passed for _, passed, _ in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()