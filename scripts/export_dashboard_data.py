"""Export tidy and wide CSV datasets for a future dashboard."""
from pathlib import Path

import pandas as pd

from tag_compliance import add_compliance, summarize


ROOT = Path(__file__).resolve().parent.parent


def main():
    source = pd.read_csv(ROOT / "data" / "cur_sample.csv", parse_dates=["usage_date"])
    dashboard_dir = ROOT / "dashboard" / "data"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    daily = (source.groupby(["usage_date", "service", "region"], as_index=False)
             .agg(cost_usd=("unblended_cost", "sum"), usage_quantity=("usage_quantity", "sum")))
    daily.to_csv(dashboard_dir / "daily_cost_tidy.csv", index=False)
    wide = daily.pivot_table(index="usage_date", columns=["service", "region"], values="cost_usd", aggfunc="sum", fill_value=0)
    wide.columns = [f"{service}_{region}_cost_usd" for service, region in wide.columns]
    wide.reset_index().to_csv(dashboard_dir / "daily_cost_wide.csv", index=False)

    tagged = add_compliance(source)
    tagged[["usage_date", "service", "region", *["Environment", "Owner", "CostCenter", "Application"],
            "unblended_cost", "tags_compliant", "untagged_cost"]].to_csv(
        dashboard_dir / "tag_compliance_records.csv", index=False)
    summarize(tagged, ["service", "region", "usage_month"]).to_csv(
        dashboard_dir / "tag_compliance_monthly.csv", index=False)
    pd.read_csv(ROOT / "outputs" / "synthetic" / "anomalies_detected.csv").to_csv(
        dashboard_dir / "anomalies.csv", index=False)
    pd.read_csv(ROOT / "outputs" / "synthetic" / "regional_anomalies.csv").to_csv(
        dashboard_dir / "regional_anomalies.csv", index=False)
    pd.read_csv(ROOT / "outputs" / "synthetic" / "regional_inefficiency_candidates.csv").to_csv(
        dashboard_dir / "regional_inefficiency_candidates.csv", index=False)
    pd.read_csv(ROOT / "outputs" / "synthetic" / "forecast_daily.csv").to_csv(
        dashboard_dir / "forecast_daily.csv", index=False)
    print(f"Exported dashboard data to {dashboard_dir.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()