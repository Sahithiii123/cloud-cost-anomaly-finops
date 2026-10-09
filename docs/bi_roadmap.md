# BI Roadmap

## Short Term: 0-4 Weeks

| Area | Plan |
|---|---|
| Requirements | Confirm finance and engineering definitions for budget, unit cost, anomaly severity, tag policy, and attribution. |
| Stakeholders | FinOps, cloud platform, service owners, finance business partners, data engineering. |
| Deliverables | Validate CUR/FOCUS ingestion; publish daily cost, anomaly, tag compliance, and forecast extracts; prototype a read-only BI report; document discrepancy intake and root-cause workflow. |
| Risks | Inconsistent tags, changing service dimensions, late billing adjustments, sparse resource-level usage, and unapproved budget baselines. |
| Success metrics | Reconciled totals against the source billing export; all KPI definitions approved; data-quality checks visible; report refresh reproducible. Baselines and targets to be agreed, not invented here. |

## Long Term: 1-6 Months

| Area | Plan |
|---|---|
| Requirements | Governed S3/FOCUS or CUR landing zone, catalog and semantic layer, access controls, retention, data contracts, and observability. |
| Stakeholders | FinOps leadership, cloud center of excellence, security, data platform, finance, application owners. |
| Deliverables | Operational ingestion and validation, curated Athena tables, governed KPI model, alert/ticket integrations, role-based BI, and documented lineage. |
| Risks | Provider schema drift, cost allocation disputes, privacy/access controls, noisy alerts, and unowned remediation actions. |
| Success metrics | Reconciliation error, freshness against agreed SLA, tag completeness trend, ticket closure quality, forecast MAPE, and validated realized savings. No targets are asserted until baselines and owners approve them. |

This is a planning document, not evidence that a BI platform or cloud pipeline has been deployed.