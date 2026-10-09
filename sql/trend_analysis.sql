-- Athena / Trino SQL over a CUR table named cur_sample.

-- 1) Monthly spend per service, with Month-over-Month % change
WITH monthly_service_cost AS (
    SELECT
        date_format(CAST(usage_date AS timestamp), '%Y-%m') AS usage_month,
        service,
        SUM(unblended_cost) AS monthly_cost
    FROM cur_sample
    GROUP BY 1, 2
),
mom AS (
    SELECT
        usage_month,
        service,
        monthly_cost,
        LAG(monthly_cost) OVER (PARTITION BY service ORDER BY usage_month) AS prev_month_cost,
        ROUND(
            100.0 * (monthly_cost - LAG(monthly_cost) OVER (PARTITION BY service ORDER BY usage_month))
            / NULLIF(LAG(monthly_cost) OVER (PARTITION BY service ORDER BY usage_month), 0)
        , 2) AS mom_pct_change
    FROM monthly_service_cost
)
SELECT * FROM mom
ORDER BY service, usage_month;


-- 2) Quarterly spend per service, with Quarter-over-Quarter % change
WITH quarterly_service_cost AS (
    SELECT
        date_format(date_trunc('quarter', CAST(usage_date AS timestamp)), '%Y') || '-Q' ||
            CAST(quarter(CAST(usage_date AS timestamp)) AS varchar) AS usage_quarter,
        service,
        SUM(unblended_cost) AS quarterly_cost
    FROM cur_sample
    GROUP BY 1, 2
)
SELECT
    usage_quarter,
    service,
    quarterly_cost,
    LAG(quarterly_cost) OVER (PARTITION BY service ORDER BY usage_quarter) AS prev_quarter_cost,
    ROUND(
        100.0 * (quarterly_cost - LAG(quarterly_cost) OVER (PARTITION BY service ORDER BY usage_quarter))
        / NULLIF(LAG(quarterly_cost) OVER (PARTITION BY service ORDER BY usage_quarter), 0)
    , 2) AS qoq_pct_change
FROM quarterly_service_cost
ORDER BY service, usage_quarter;


-- 3) Daily cost with 7-day rolling mean/stddev and z-score.
WITH daily_service_cost AS (
    SELECT
        usage_date,
        service,
        SUM(unblended_cost) AS daily_cost,
        SUM(usage_quantity) AS daily_usage
    FROM cur_sample
    GROUP BY 1, 2
),
rolling AS (
    SELECT
        usage_date,
        service,
        daily_cost,
        daily_usage,
        AVG(daily_cost) OVER (
            PARTITION BY service ORDER BY usage_date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS rolling_avg_cost,
        STDDEV_SAMP(daily_cost) OVER (
            PARTITION BY service ORDER BY usage_date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS rolling_stddev_cost,
        AVG(daily_usage) OVER (
            PARTITION BY service ORDER BY usage_date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS rolling_avg_usage
    FROM daily_service_cost
)
SELECT
    usage_date,
    service,
    daily_cost,
    rolling_avg_cost,
    ROUND((daily_cost - rolling_avg_cost) / NULLIF(rolling_stddev_cost, 0), 4) AS z_score,
    ROUND(100.0 * (daily_cost - rolling_avg_cost) / NULLIF(rolling_avg_cost, 0), 2) AS pct_dev_from_rolling_avg,
    daily_usage,
    rolling_avg_usage
FROM rolling
WHERE rolling_avg_cost IS NOT NULL
ORDER BY service, usage_date;


-- 4) Regional spend anomaly and unit-cost scoring.
-- The primary synthetic detector above remains service/day grain; this query
-- independently scores each service-region-day and does not pool regions.
WITH daily_region AS (
    SELECT
        usage_date,
        service,
        region,
        SUM(unblended_cost) AS daily_cost,
        SUM(usage_quantity) AS daily_usage,
        SUM(unblended_cost) / NULLIF(SUM(usage_quantity), 0) AS cost_per_unit
    FROM cur_sample
    GROUP BY 1, 2, 3
), regional_rolling AS (
    SELECT *,
        AVG(daily_cost) OVER (
            PARTITION BY service, region ORDER BY usage_date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS rolling_avg_cost,
        STDDEV_SAMP(daily_cost) OVER (
            PARTITION BY service, region ORDER BY usage_date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS rolling_stddev_cost,
        AVG(cost_per_unit) OVER (
            PARTITION BY service, region ORDER BY usage_date
            ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
        ) AS rolling_avg_unit_cost,
        STDDEV_SAMP(cost_per_unit) OVER (
            PARTITION BY service, region ORDER BY usage_date
            ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
        ) AS rolling_stddev_unit_cost
    FROM daily_region
), scored AS (
    SELECT *,
        (daily_cost - rolling_avg_cost) / NULLIF(rolling_stddev_cost, 0) AS regional_cost_z_score,
        (cost_per_unit - rolling_avg_unit_cost) / NULLIF(rolling_stddev_unit_cost, 0) AS regional_unit_cost_z_score,
        100.0 * (cost_per_unit - rolling_avg_unit_cost) / NULLIF(rolling_avg_unit_cost, 0) AS regional_unit_cost_change_pct
    FROM regional_rolling
)
SELECT
    usage_date,
    service,
    region,
    daily_cost,
    daily_usage,
    ROUND(cost_per_unit, 4) AS cost_per_unit,
    rolling_avg_cost,
    rolling_stddev_cost,
    ROUND(regional_cost_z_score, 4) AS regional_cost_z_score,
    rolling_avg_unit_cost,
    rolling_stddev_unit_cost,
    ROUND(regional_unit_cost_change_pct, 2) AS regional_unit_cost_change_pct,
    ROUND(regional_unit_cost_z_score, 4) AS regional_unit_cost_z_score,
    regional_cost_z_score > 2.5 AND regional_unit_cost_z_score > 2.5 AS regional_inefficiency_candidate
FROM scored
ORDER BY service, region, usage_date;
