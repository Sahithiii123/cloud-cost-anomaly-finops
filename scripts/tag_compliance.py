"""Calculate tag coverage and cost-weighted tag compliance."""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TAG_COLUMNS = ["Environment", "Owner", "CostCenter", "Application"]
VALID_VALUES = {
    "Environment": {"Production", "Staging", "Development", "Shared"},
    "Owner": {"team-platform", "team-data", "team-commerce", "team-analytics"},
    "CostCenter": {"CC-1001", "CC-2042", "CC-3057", "CC-4108"},
    "Application": {"billing", "catalog", "payments", "analytics"},
}


def add_compliance(frame):
    result = frame.copy()
    result["tags_compliant"] = True
    for column in TAG_COLUMNS:
        result["tags_compliant"] &= result[column].isin(VALID_VALUES[column])
    result["usage_month"] = pd.to_datetime(result["usage_date"]).dt.to_period("M").astype(str)
    result["untagged_cost"] = result["unblended_cost"].where(~result["tags_compliant"], 0.0)
    return result


def summarize(frame, group_columns):
    grouped = frame.groupby(group_columns, as_index=False, dropna=False).agg(
        resource_records=("tags_compliant", "size"),
        compliant_resource_records=("tags_compliant", "sum"),
        total_cost=("unblended_cost", "sum"),
        untagged_cost=("untagged_cost", "sum"),
    )
    grouped["resource_compliance_pct"] = 100 * grouped["compliant_resource_records"] / grouped["resource_records"]
    grouped["spend_compliance_pct"] = 100 * (grouped["total_cost"] - grouped["untagged_cost"]) / grouped["total_cost"]
    return grouped


def main():
    source = pd.read_csv(ROOT / "data" / "cur_sample.csv", parse_dates=["usage_date"])
    tagged = add_compliance(source)
    output = ROOT / "outputs" / "synthetic"
    output.mkdir(parents=True, exist_ok=True)
    by_service_region_month = summarize(tagged, ["service", "region", "usage_month"])
    by_service_region_month.to_csv(output / "tag_compliance_by_service_region_month.csv", index=False)
    by_month = summarize(tagged, ["usage_month"])
    by_month.to_csv(output / "tag_compliance_by_month.csv", index=False)
    by_service_region = summarize(tagged, ["service", "region"])
    by_service_region.to_csv(output / "tag_compliance_by_service_region.csv", index=False)
    top_drivers = (tagged.groupby(["service", "region"], as_index=False)["untagged_cost"].sum()
                   .sort_values("untagged_cost", ascending=False).head(10))
    top_drivers.to_csv(output / "top_untagged_cost_drivers.csv", index=False)

    chart_dir = ROOT / "charts"
    chart_dir.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(by_month["usage_month"], by_month["resource_compliance_pct"], marker="o", label="Resource-record compliance")
    ax.plot(by_month["usage_month"], by_month["spend_compliance_pct"], marker="s", label="Spend compliance")
    ax.set_ylabel("Compliance (%)")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", rotation=60)
    ax.legend()
    ax.set_title("Synthetic Tag Compliance by Month")
    fig.tight_layout()
    fig.savefig(chart_dir / "04_tag_compliance.png", dpi=150)
    plt.close(fig)
    start = by_month.iloc[0]
    end = by_month.iloc[-1]
    print(f"Tag compliance: {start.resource_compliance_pct:.2f}% at start; {end.resource_compliance_pct:.2f}% at end.")


if __name__ == "__main__":
    main()