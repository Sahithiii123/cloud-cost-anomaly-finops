import pandas as pd

from scripts.analysis_metrics import forecast_agreement, regional_metrics, score_daily_metrics
from scripts.tag_compliance import add_compliance, summarize


def test_planted_cost_spike_is_detected():
    costs = [9, 10, 11, 10, 9, 10, 11, 10, 30]
    frame = pd.DataFrame({
        "usage_date": pd.date_range("2025-01-01", periods=len(costs)),
        "service": "AmazonEC2",
        "region": "us-east-1",
        "unblended_cost": costs,
        "usage_quantity": [10] * len(costs),
    })
    scored = score_daily_metrics(frame, ["service"])
    assert scored.iloc[-1]["z_score"] > 2.5
    assert scored.iloc[-1]["cpu_pct_dev"] > 15


def test_regional_unit_cost_uses_independent_region_baselines():
    days = pd.date_range("2025-01-01", periods=16)
    rows = []
    for index, day in enumerate(days):
        for region, base_cost, base_usage in [("us-east-1", 100 + index % 3, 100), ("us-west-2", 200 + index % 3, 50)]:
            cost = base_cost
            usage = base_usage
            if index == 15 and region == "us-east-1":
                cost *= 1.8
            rows.append({"usage_date": day, "service": "AmazonEC2", "region": region,
                         "unblended_cost": cost, "usage_quantity": usage})
    metrics = regional_metrics(pd.DataFrame(rows))
    event = metrics[(metrics.usage_date == days[-1]) & (metrics.region == "us-east-1")].iloc[0]
    unaffected = metrics[(metrics.usage_date == days[-1]) & (metrics.region == "us-west-2")].iloc[0]
    assert event["cpu_pct_dev"] > 70
    assert event["unit_cost_z_score"] > 2.5
    assert unaffected["cpu_pct_dev"] < 2
    assert not unaffected["regional_inefficiency_candidate"]


def test_tag_compliance_calculation_counts_invalid_and_missing_tags():
    frame = pd.DataFrame({
        "usage_date": ["2025-01-01", "2025-01-01"],
        "service": ["AmazonEC2", "AmazonEC2"],
        "region": ["us-east-1", "us-east-1"],
        "unblended_cost": [100.0, 50.0],
        "Environment": ["Production", "unknown"],
        "Owner": ["team-platform", "team-platform"],
        "CostCenter": ["CC-1001", "CC-1001"],
        "Application": ["billing", "billing"],
    })
    result = summarize(add_compliance(frame), ["service"])
    assert result.iloc[0]["resource_compliance_pct"] == 50
    assert result.iloc[0]["spend_compliance_pct"] == 100 * 100 / 150


def test_forecast_agreement_matches_pipeline_metric():
    agreement = forecast_agreement(82164.36913316786, 82631.24428252476)
    assert round(agreement, 3) == 0.567
    assert agreement < 1.5