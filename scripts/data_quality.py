"""Schema and integrity checks shared by local analysis and Lambda."""
from pathlib import Path
import argparse

import pandas as pd
from pandas.api.types import is_numeric_dtype


REQUIRED_COLUMNS = {
    "usage_date", "service", "region", "usage_type", "unblended_cost",
    "usage_quantity", "Environment", "Owner", "CostCenter", "Application",
}
STRING_COLUMNS = {
    "usage_date", "service", "region", "usage_type", "Environment", "Owner",
    "CostCenter", "Application", "charge_category", "line_item_id",
}
NUMERIC_COLUMNS = {"unblended_cost", "usage_quantity"}
KEY_COLUMNS = ["usage_date", "service", "region", "usage_type"]
TAG_COLUMNS = ["Environment", "Owner", "CostCenter", "Application"]


def _check(name, count, detail, passed=None):
    return {"check": name, "passed": count == 0 if passed is None else bool(passed),
            "count": int(count), "detail": detail}


def validate_frame(frame, allow_sparse_dates=False, allow_signed_costs=False,
                   allow_non_usage_quantity_nulls=False):
    """Return named checks; tag completeness is a KPI, not a file-integrity failure."""
    missing_columns = REQUIRED_COLUMNS - set(frame.columns)
    schema = _check("Required schema", len(missing_columns),
                    "Missing columns: " + (", ".join(sorted(missing_columns)) or "none"))

    dtype_errors = []
    for column in STRING_COLUMNS & set(frame.columns):
        if not frame[column].isna().all() and not (pd.api.types.is_string_dtype(frame[column]) or frame[column].dtype == object
                or pd.api.types.is_datetime64_any_dtype(frame[column])):
            dtype_errors.append(column)
    for column in NUMERIC_COLUMNS & set(frame.columns):
        if not is_numeric_dtype(frame[column]):
            dtype_errors.append(column)
    dtypes = _check("Column dtypes", len(dtype_errors),
                    "Unexpected dtypes: " + (", ".join(sorted(dtype_errors)) or "none"))

    null_fields = [column for column in KEY_COLUMNS + ["unblended_cost", "usage_quantity"]
                   if column in frame and frame[column].isna().any()]
    null_count = sum(int(frame[column].isna().sum()) for column in null_fields)
    allowed_non_usage_nulls = 0
    allowed_charge_counts = {}
    if allow_non_usage_quantity_nulls and {"usage_quantity", "charge_category"}.issubset(frame.columns):
        charge_categories = frame["charge_category"].astype("string").str.casefold()
        missing_quantity = frame["usage_quantity"].isna()
        allowed_rows = missing_quantity & charge_categories.isin({"credit", "tax", "purchase"})
        allowed_non_usage_nulls = int(allowed_rows.sum())
        allowed_charge_counts = charge_categories[allowed_rows].value_counts().to_dict()
    invalid_null_count = null_count - allowed_non_usage_nulls
    nulls = _check("Null key/measure fields", null_count,
                   "Fields with nulls: " + (", ".join(null_fields) or "none")
                   + (f"; {allowed_non_usage_nulls} missing quantities on non-usage charge rows allowed and retained: {allowed_charge_counts}"
                      if allowed_non_usage_nulls else ""), passed=invalid_null_count == 0)

    duplicate_count = int(frame.duplicated(keep=False).sum()) if not missing_columns else 1
    duplicates = _check("Duplicate line items", duplicate_count,
                         "Fully duplicated rows across mapped line-item fields")

    negative_count = (int((frame["unblended_cost"] < 0).sum())
                      if "unblended_cost" in frame and is_numeric_dtype(frame["unblended_cost"])
                      else int("unblended_cost" in REQUIRED_COLUMNS))
    negative_detail = "Negative unblended_cost rows"
    if allow_signed_costs and negative_count:
        negative_detail += "; signed source amounts preserved unchanged and listed for reconciliation"
    negative_costs = _check("Negative costs", negative_count, negative_detail,
                            passed=negative_count == 0 or allow_signed_costs)

    continuity_count = 1
    continuity_detail = "Cannot evaluate without valid usage_date values"
    if "usage_date" in frame:
        parsed_dates = pd.to_datetime(frame["usage_date"], errors="coerce")
        invalid_dates = int(parsed_dates.isna().sum())
        dates = parsed_dates.dropna().dt.normalize().drop_duplicates().sort_values()
        if not dates.empty:
            expected = pd.date_range(dates.iloc[0], dates.iloc[-1], freq="D")
            gaps = expected.difference(dates)
            continuity_count = len(gaps) + invalid_dates
            continuity_detail = f"Missing calendar dates: {len(gaps)}; invalid dates: {invalid_dates}"
            if allow_sparse_dates:
                continuity_detail += "; sparse dates are allowed for the public FOCUS sample, no rows were imputed"
    continuity = _check("Date-range continuity", continuity_count if not allow_sparse_dates else invalid_dates,
                        continuity_detail)

    tag_error_count = 0
    tag_detail = []
    if missing_columns.intersection(TAG_COLUMNS):
        tag_error_count += len(missing_columns.intersection(TAG_COLUMNS))
        tag_detail.append("missing tag columns: " + ", ".join(sorted(missing_columns.intersection(TAG_COLUMNS))))
    else:
        for column in TAG_COLUMNS:
            values = frame[column]
            invalid = values.notna() & (~values.map(lambda value: isinstance(value, str) and bool(value.strip())))
            tag_error_count += int(invalid.sum())
        tag_detail.append("tag values must be strings or null; missing/inconsistent tags are reported by the KPI")
    tag_validity = _check("Tag-field validity", tag_error_count, "; ".join(tag_detail))

    return [schema, dtypes, nulls, duplicates, negative_costs, continuity, tag_validity]


def write_report(checks, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Data Quality Report", "", "| Check | Result | Count | Detail |", "|---|---:|---:|---|"]
    for check in checks:
        result = "PASS" if check["passed"] else "FAIL"
        detail = check["detail"].replace("|", "\\|")
        lines.append(f"| {check['check']} | {result} | {check['count']} | {detail} |")
    lines.extend(["", f"Overall: **{'PASS' if all(check['passed'] for check in checks) else 'FAIL'}**."])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_file(input_path, report_path=None, allow_sparse_dates=False, allow_signed_costs=False,
                  allow_non_usage_quantity_nulls=False):
    frame = pd.read_csv(input_path, dtype={column: "string" for column in TAG_COLUMNS})
    checks = validate_frame(frame, allow_sparse_dates=allow_sparse_dates, allow_signed_costs=allow_signed_costs,
                            allow_non_usage_quantity_nulls=allow_non_usage_quantity_nulls)
    if report_path is not None:
        write_report(checks, report_path)
    return checks


def require_valid_file(input_path, report_path, allow_sparse_dates=False, allow_signed_costs=False,
                       allow_non_usage_quantity_nulls=False):
    checks = validate_file(input_path, report_path, allow_sparse_dates=allow_sparse_dates,
                           allow_signed_costs=allow_signed_costs,
                           allow_non_usage_quantity_nulls=allow_non_usage_quantity_nulls)
    failed = [check for check in checks if not check["passed"]]
    if failed:
        failed_names = ", ".join(check["check"] for check in failed)
        raise SystemExit(f"Data quality failed: {failed_names}. See {report_path}")
    return checks


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Validate a CUR-style CSV and write a quality report.")
    parser.add_argument("--input", type=Path, default=root / "data" / "cur_sample.csv")
    parser.add_argument("--report", type=Path, default=root / "outputs" / "synthetic" / "data_quality_report.md")
    args = parser.parse_args()
    require_valid_file(args.input, args.report)
    print(f"Data quality passed. Report: {args.report}")