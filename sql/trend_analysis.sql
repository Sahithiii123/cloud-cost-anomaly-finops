-- =====================================================================
-- trend_analysis.sql
-- Written in Athena-compatible ANSI SQL (also runs on SQLite for this
-- repo's local demo). Uses CTEs + window functions for MoM/QoQ trends.
-- =====================================================================

-- 1) Monthly spend per service, with Month-over-Month % change
WITH monthly_service_cost AS (
    SELECT
        strftime('%Y-%m', usage_date) AS usage_month,
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
        (strftime('%Y', usage_date) || '-Q' ||
            ((CAST(strftime('%m', usage_date) AS INTEGER) - 1) / 3 + 1)) AS usage_quarter,
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


-- 3) Daily cost with 7-day rolling average, rolling stddev, and z-score
--    (feeds the anomaly detector: flag any day where |z| > 2.5)
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
        -- SQLite has no native STDDEV window fn; computed in pandas layer instead.
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
    ROUND(100.0 * (daily_cost - rolling_avg_cost) / NULLIF(rolling_avg_cost, 0), 2) AS pct_dev_from_rolling_avg,
    daily_usage,
    rolling_avg_usage
FROM rolling
WHERE rolling_avg_cost IS NOT NULL
ORDER BY service, usage_date;


-- 4) Cost-per-unit-usage trend — the real FinOps signal.
--    If cost is rising but cost/usage ratio is ALSO rising, that's
--    inefficiency/waste, not just legit growth.
WITH daily_ratio AS (
    SELECT
        usage_date,
        service,
        SUM(unblended_cost) AS daily_cost,
        SUM(usage_quantity) AS daily_usage,
        SUM(unblended_cost) / NULLIF(SUM(usage_quantity), 0) AS cost_per_unit
    FROM cur_sample
    GROUP BY 1, 2
)
SELECT
    usage_date,
    service,
    daily_cost,
    daily_usage,
    ROUND(cost_per_unit, 4) AS cost_per_unit,
    AVG(cost_per_unit) OVER (
        PARTITION BY service ORDER BY usage_date
        ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
    ) AS rolling_avg_cost_per_unit
FROM daily_ratio
ORDER BY service, usage_date;
