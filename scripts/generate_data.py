"""
Generates synthetic AWS Cost & Usage Report (CUR)-style data.
Mimics real CUR structure: line items per service/region/day.
14 months of data, multiple services & regions, with a few
deliberately injected anomalies (spend spikes with no usage growth).
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

SERVICES = {
    "AmazonEC2": {"base_daily": 420, "usage_unit": "InstanceHours"},
    "AmazonS3": {"base_daily": 90, "usage_unit": "GB-Month"},
    "AmazonRDS": {"base_daily": 260, "usage_unit": "InstanceHours"},
    "AWSLambda": {"base_daily": 35, "usage_unit": "Requests(M)"},
    "AmazonCloudFront": {"base_daily": 60, "usage_unit": "GB-Transfer"},
    "AmazonEBS": {"base_daily": 75, "usage_unit": "GB-Month"},
    "AmazonDynamoDB": {"base_daily": 50, "usage_unit": "RCU/WCU"},
}
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]

start = datetime(2024, 6, 1)
end = datetime(2025, 7, 31)
days = pd.date_range(start, end, freq="D")

rows = []
for day in days:
    month_idx = (day.year - start.year) * 12 + (day.month - start.month)
    growth = 1 + 0.015 * month_idx  # mild organic monthly growth ~1.5%
    dow_factor = 0.85 if day.weekday() >= 5 else 1.0  # lower weekend usage

    for svc, cfg in SERVICES.items():
        for region in REGIONS:
            region_weight = {"us-east-1": 1.0, "us-west-2": 0.6, "eu-west-1": 0.5, "ap-south-1": 0.3}[region]
            base = cfg["base_daily"] * region_weight * growth * dow_factor
            noise = np.random.normal(1.0, 0.08)
            cost = max(base * noise, 0)
            usage_qty = cost / np.random.uniform(0.8, 1.2)  # rough usage proxy

            rows.append({
                "usage_date": day.strftime("%Y-%m-%d"),
                "service": svc,
                "region": region,
                "usage_type": cfg["usage_unit"],
                "unblended_cost": round(cost, 4),
                "usage_quantity": round(usage_qty, 2),
            })

df = pd.DataFrame(rows)

# --- Inject deliberate anomalies (for the anomaly detector to catch) ---
# 1) EC2 us-east-1 cost spike in Feb 2025 with NO usage growth (misconfigured instance type / orphaned resources)
mask1 = (df.usage_date >= "2025-02-10") & (df.usage_date <= "2025-02-24") & (df.service == "AmazonEC2") & (df.region == "us-east-1")
df.loc[mask1, "unblended_cost"] *= 1.9
# usage_quantity intentionally NOT scaled up -> cost/usage ratio breaks, this is the FinOps red flag

# 2) S3 cost spike in Oct 2024 (lifecycle policy missing -> storage class not transitioning)
mask2 = (df.usage_date >= "2024-10-05") & (df.usage_date <= "2024-10-20") & (df.service == "AmazonS3")
df.loc[mask2, "unblended_cost"] *= 1.6
df.loc[mask2, "usage_quantity"] *= 1.55  # this one IS usage-driven (legit growth, not anomaly-worthy on its own)

# 3) Lambda cost spike May 2025 - runaway recursive invocation bug
mask3 = (df.usage_date >= "2025-05-14") & (df.usage_date <= "2025-05-18") & (df.service == "AWSLambda")
df.loc[mask3, "unblended_cost"] *= 3.2
df.loc[mask3, "usage_quantity"] *= 3.0  # usage did spike too, but abnormally vs trend

import os
df.to_csv(os.path.join(os.path.dirname(__file__), "..", "data", "cur_sample.csv"), index=False)
print(f"Generated {len(df):,} rows across {df.usage_date.nunique()} days, "
      f"{df.service.nunique()} services, {df.region.nunique()} regions.")
print(f"Total spend: ${df.unblended_cost.sum():,.2f}")
