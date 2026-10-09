"""Estimate a simulated cost opportunity for the deliberately injected event."""
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent


def main():
    frame = pd.read_csv(ROOT / "data" / "cur_sample.csv", parse_dates=["usage_date"])
    start = pd.Timestamp("2025-02-10")
    end = pd.Timestamp("2025-02-24")
    target = frame[(frame["service"] == "AmazonEC2") & (frame["region"] == "us-east-1")]
    prior = target[target["usage_date"].between(start - pd.Timedelta(days=14), start - pd.Timedelta(days=1))]
    event = target[target["usage_date"].between(start, end)]
    baseline_daily = float(prior.groupby("usage_date")["unblended_cost"].sum().mean())
    actual_cost = float(event["unblended_cost"].sum())
    baseline_cost = baseline_daily * event["usage_date"].nunique()
    result = {
        "classification": "simulated opportunity; not realized savings",
        "service": "AmazonEC2",
        "region": "us-east-1",
        "period_start": start.date().isoformat(),
        "period_end": end.date().isoformat(),
        "observed_event_cost_usd": actual_cost,
        "counterfactual_baseline_usd": baseline_cost,
        "simulated_opportunity_usd": actual_cost - baseline_cost,
        "assumption": "Per-day cost would have matched the preceding 14-day regional average; no causal proof or remediation is represented.",
    }
    output = ROOT / "outputs" / "synthetic" / "savings_estimate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Simulated opportunity: ${result['simulated_opportunity_usd']:,.2f}; no realized savings claimed.")


if __name__ == "__main__":
    main()