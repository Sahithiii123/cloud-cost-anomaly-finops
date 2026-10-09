"""Shared daily anomaly, regional efficiency, and forecast metric calculations."""
import numpy as np
import pandas as pd


def score_daily_metrics(frame, group_columns, cost_window=7, unit_cost_window=14):
    daily = frame.groupby(["usage_date", *group_columns], as_index=False, dropna=False).agg(
        daily_cost=("unblended_cost", "sum"),
        daily_usage=("usage_quantity", "sum"),
    )
    daily = daily.sort_values([*group_columns, "usage_date"]).reset_index(drop=True)
    groups = daily.groupby(group_columns, sort=False)
    daily["roll_mean"] = groups["daily_cost"].transform(
        lambda values: values.rolling(cost_window, min_periods=5).mean().shift(1))
    daily["roll_std"] = groups["daily_cost"].transform(
        lambda values: values.rolling(cost_window, min_periods=5).std().shift(1))
    daily["z_score"] = (daily["daily_cost"] - daily["roll_mean"]) / daily["roll_std"].replace(0, np.nan)
    daily["cost_per_unit"] = daily["daily_cost"] / daily["daily_usage"].replace(0, np.nan)
    ratio_groups = daily.groupby(group_columns, sort=False)["cost_per_unit"]
    daily["cpu_roll_mean"] = ratio_groups.transform(
        lambda values: values.rolling(unit_cost_window, min_periods=7).mean().shift(1))
    daily["cpu_roll_std"] = ratio_groups.transform(
        lambda values: values.rolling(unit_cost_window, min_periods=7).std().shift(1))
    daily["cpu_pct_dev"] = (100 * (daily["cost_per_unit"] - daily["cpu_roll_mean"])
                            / daily["cpu_roll_mean"].replace(0, np.nan))
    daily["unit_cost_z_score"] = ((daily["cost_per_unit"] - daily["cpu_roll_mean"])
                                  / daily["cpu_roll_std"].replace(0, np.nan))
    return daily


def regional_metrics(frame):
    metrics = score_daily_metrics(frame, ["service", "region"])
    metrics["regional_cost_anomaly"] = metrics["z_score"].abs() > 2.5
    metrics["positive_regional_cost_anomaly"] = metrics["z_score"] > 2.5
    metrics["regional_pct_candidate"] = metrics["regional_cost_anomaly"] & (metrics["cpu_pct_dev"] > 15)
    metrics["regional_inefficiency_candidate"] = (
        metrics["positive_regional_cost_anomaly"] & (metrics["unit_cost_z_score"] > 2.5)
    )
    return metrics


def forecast_agreement(regression_total, smoothing_total):
    denominator = (float(regression_total) + float(smoothing_total)) / 2
    if denominator == 0:
        return float("nan")
    return abs(float(regression_total) - float(smoothing_total)) / abs(denominator) * 100