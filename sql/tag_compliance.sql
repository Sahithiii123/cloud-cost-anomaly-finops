-- Athena-style spend and resource-record tag compliance over normalized CUR tags.
WITH tagged AS (
    SELECT
        date_trunc('month', CAST(usage_date AS timestamp)) AS usage_month,
        service,
        region,
        unblended_cost,
        CASE WHEN Environment IN ('Production', 'Staging', 'Development', 'Shared')
                   AND Owner IN ('team-platform', 'team-data', 'team-commerce', 'team-analytics')
                   AND CostCenter IN ('CC-1001', 'CC-2042', 'CC-3057', 'CC-4108')
                   AND Application IN ('billing', 'catalog', 'payments', 'analytics')
             THEN 1 ELSE 0 END AS compliant_record
    FROM cur_sample
)
SELECT
    usage_month,
    service,
    region,
    COUNT(*) AS resource_records,
    SUM(compliant_record) AS compliant_resource_records,
    100.0 * SUM(compliant_record) / NULLIF(COUNT(*), 0) AS resource_compliance_pct,
    SUM(unblended_cost) AS total_cost,
    SUM(CASE WHEN compliant_record = 0 THEN unblended_cost ELSE 0 END) AS untagged_cost,
    100.0 * SUM(CASE WHEN compliant_record = 1 THEN unblended_cost ELSE 0 END)
        / NULLIF(SUM(unblended_cost), 0) AS spend_compliance_pct
FROM tagged
GROUP BY 1, 2, 3;