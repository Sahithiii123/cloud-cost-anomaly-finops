"""Create actionable anomaly tickets and an evidence-backed RCA note."""
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TICKET_COLUMNS = ["ticket_id", "date", "service", "region", "severity", "cost_impact_usd", "baseline_usd",
                  "z_score", "cost_per_unit_change_pct", "classification", "status", "owner",
                  "regional_unit_cost_z_score", "regional_daily_cost", "regional_unit_cost_usd",
                  "regional_unit_cost_baseline_usd", "service_day_cost_per_unit_change_pct",
                  "service_day_cost_z_score"]


def main():
    source = pd.read_csv(ROOT / "data" / "cur_sample.csv", parse_dates=["usage_date"])
    anomalies = pd.read_csv(ROOT / "outputs" / "synthetic" / "anomalies_detected.csv", parse_dates=["usage_date"])
    regional = pd.read_csv(ROOT / "outputs" / "synthetic" / "regional_daily_metrics.csv", parse_dates=["usage_date"])
    tickets_dir = ROOT / "tickets"
    tickets_dir.mkdir(exist_ok=True)
    rows = []
    owner_by_service = {service: "finops-triage" for service in source["service"].unique()}
    for index, anomaly in anomalies.reset_index(drop=True).iterrows():
        regional_rows = regional[(regional["usage_date"] == anomaly["usage_date"])
                                 & (regional["service"] == anomaly["service"])]
        selected = regional_rows.sort_values("z_score", ascending=False, na_position="last").iloc[0]
        classification = ("regional unit-cost anomaly candidate"
                          if bool(selected["regional_inefficiency_candidate"])
                          else "usage-driven / investigate")
        z_value = float(selected["z_score"])
        rows.append({
            "ticket_id": f"FINOPS-{index + 1:04d}",
            "date": anomaly["usage_date"].date().isoformat(),
            "service": anomaly["service"],
            "region": selected["region"],
            "severity": "high" if abs(z_value) >= 3.5 else "medium" if abs(z_value) >= 2.5 else "low",
            "cost_impact_usd": round(float(selected["daily_cost"] - selected["roll_mean"]), 2),
            "baseline_usd": round(float(selected["roll_mean"]), 2),
            "z_score": round(z_value, 4),
            "cost_per_unit_change_pct": round(float(selected["cpu_pct_dev"]), 4),
            "classification": classification,
            "status": "Open",
            "owner": owner_by_service[anomaly["service"]],
            "regional_unit_cost_z_score": round(float(selected["unit_cost_z_score"]), 4),
            "regional_daily_cost": round(float(selected["daily_cost"]), 4),
            "regional_unit_cost_usd": round(float(selected["cost_per_unit"]), 8),
            "regional_unit_cost_baseline_usd": round(float(selected["cpu_roll_mean"]), 8),
            "service_day_cost_per_unit_change_pct": round(float(anomaly["cpu_pct_dev"]), 4),
            "service_day_cost_z_score": round(float(anomaly["z_score"]), 4),
        })
    tickets = pd.DataFrame(rows, columns=TICKET_COLUMNS)
    tickets.to_csv(tickets_dir / "tickets_summary.csv", index=False)
    tickets.to_json(tickets_dir / "anomaly_tickets.json", orient="records", indent=2, date_format="iso")

    detailed = tickets[(tickets["classification"] == "regional unit-cost anomaly candidate")
                       & (tickets["service"] == "AmazonEC2")
                       & (tickets["region"] == "us-east-1")].iloc[0]
    aggregate_row = anomalies[(anomalies["usage_date"] == pd.Timestamp(detailed["date"]))
                              & (anomalies["service"] == detailed["service"])].iloc[0]
    candidate_count = int((tickets["classification"] == "regional unit-cost anomaly candidate").sum())
    rca = f"""# RCA: {detailed['service']} in {detailed['region']} on {detailed['date']}

## What happened
The unchanged service/day detector flagged this modeled event. Regional scoring identifies {candidate_count} high-confidence service-region-day candidates across the 33 original service-day alerts. These are modeled candidates, not claims about production incidents.

## Evidence
- Regional daily cost: ${detailed['regional_daily_cost']:,.2f}; its prior seven-day regional baseline was ${detailed['baseline_usd']:,.2f}.
- Regional cost z-score: {detailed['z_score']:.4f}.
- Regional cost per unit: ${detailed['regional_unit_cost_usd']:.6f}, versus its prior 14-day regional mean of ${detailed['regional_unit_cost_baseline_usd']:.6f}; deviation {detailed['cost_per_unit_change_pct']:+.2f}% and unit-cost z-score {detailed['regional_unit_cost_z_score']:.4f}.
- Secondary service/day aggregate ratio deviation: {detailed['service_day_cost_per_unit_change_pct']:+.2f}% (not a regional measurement); service/day cost z-score {detailed['service_day_cost_z_score']:.4f}.
- Ticket cost impact is the signed regional cost difference from baseline (${detailed['cost_impact_usd']:,.2f}).

## Root-cause hypothesis
The generator explicitly multiplies EC2 cost in `us-east-1` from 2025-02-10 through 2025-02-24 by 1.9 while leaving usage unchanged. On the flagged 2025-02-10 service-region-day, the regional unit-cost measure rises {detailed['cost_per_unit_change_pct']:.2f}% from its rolling mean. This represents a modeled rate/configuration inefficiency; it is not evidence of a production incident.

## Financial impact
Ticket-day impact versus the service-level rolling baseline: ${detailed['cost_impact_usd']:,.2f}. The multi-day simulated counterfactual is in `outputs/synthetic/savings_estimate.json` and is labeled simulated.

## Recommended action
In a real account, validate instance family, purchase option, attached volumes, and resource ownership for the affected region before rightsizing or changing commitments.

## Validation step
Compare normalized cost per instance-hour before and during the modeled period; verify that cost returns to baseline without a workload or availability regression.

## Prevention
Keep resource-level CUR dimensions, enforce required tags, and alert on sustained cost-per-unit deviation only after validating metric coverage.
"""
    (tickets_dir / "ec2_us_east_1_rca.md").write_text(rca, encoding="utf-8")
    regional_candidate_count = int((tickets.classification == "regional unit-cost anomaly candidate").sum())
    print(f"Generated {len(tickets)} tickets; regional unit-cost candidates: {regional_candidate_count}.")


if __name__ == "__main__":
    main()