import pandas as pd
import pytest

from scripts.data_quality import validate_frame


@pytest.fixture
def valid_frame():
    return pd.DataFrame({
        "usage_date": ["2025-01-01", "2025-01-02"],
        "service": ["AmazonEC2", "AmazonEC2"],
        "region": ["us-east-1", "us-east-1"],
        "usage_type": ["InstanceHours", "InstanceHours"],
        "unblended_cost": [1.0, 2.0],
        "usage_quantity": [1.0, 2.0],
        "Environment": ["Production", None],
        "Owner": ["team-platform", "unknown"],
        "CostCenter": ["CC-1001", "CC-1001"],
        "Application": ["billing", "billing"],
    })


def check(frame, name, allow_sparse_dates=False):
    return next(item for item in validate_frame(frame, allow_sparse_dates=allow_sparse_dates) if item["check"] == name)


def test_valid_frame_passes_and_missing_tags_are_kpi_values(valid_frame):
    assert all(item["passed"] for item in validate_frame(valid_frame))


def test_required_schema_fails_when_column_missing(valid_frame):
    result = check(valid_frame.drop(columns="Application"), "Required schema")
    assert not result["passed"] and result["count"] == 1


def test_dtype_check_fails_for_text_cost(valid_frame):
    valid_frame["unblended_cost"] = ["1", "2"]
    assert not check(valid_frame, "Column dtypes")["passed"]


def test_null_key_check_fails(valid_frame):
    valid_frame.loc[0, "service"] = None
    assert not check(valid_frame, "Null key/measure fields")["passed"]


def test_duplicate_line_item_check_fails(valid_frame):
    valid_frame.loc[1] = valid_frame.loc[0]
    assert not check(valid_frame, "Duplicate line items")["passed"]


def test_negative_cost_check_fails(valid_frame):
    valid_frame.loc[0, "unblended_cost"] = -1
    assert not check(valid_frame, "Negative costs")["passed"]


def test_signed_real_source_costs_are_counted_when_explicitly_allowed(valid_frame):
    valid_frame.loc[0, "unblended_cost"] = -1
    result = next(item for item in validate_frame(valid_frame, allow_signed_costs=True)
                  if item["check"] == "Negative costs")
    assert result["passed"] and result["count"] == 1


def test_missing_non_usage_charge_quantity_is_allowed_when_enabled(valid_frame):
    valid_frame.loc[0, "usage_quantity"] = None
    valid_frame.loc[0, "unblended_cost"] = -1
    valid_frame["charge_category"] = ["Credit", "Usage"]
    result = next(item for item in validate_frame(valid_frame, allow_non_usage_quantity_nulls=True)
                  if item["check"] == "Null key/measure fields")
    assert result["passed"] and result["count"] == 1


def test_missing_usage_charge_quantity_still_fails(valid_frame):
    valid_frame.loc[0, "usage_quantity"] = None
    valid_frame["charge_category"] = ["Usage", "Usage"]
    result = next(item for item in validate_frame(valid_frame, allow_non_usage_quantity_nulls=True)
                  if item["check"] == "Null key/measure fields")
    assert not result["passed"]


def test_date_continuity_check_fails_for_missing_day(valid_frame):
    sparse = valid_frame.drop(index=1)
    sparse.loc[2] = valid_frame.loc[1].copy()
    sparse.loc[2, "usage_date"] = "2025-01-03"
    result = check(sparse, "Date-range continuity")
    assert not result["passed"] and result["count"] == 1


def test_tag_field_validity_fails_for_non_string_value(valid_frame):
    valid_frame["Owner"] = valid_frame["Owner"].astype(object)
    valid_frame.loc[0, "Owner"] = 12
    assert not check(valid_frame, "Tag-field validity")["passed"]


def test_deliberately_bad_fixture_fails_multiple_checks(valid_frame):
    bad = valid_frame.drop(columns="Application")
    bad.loc[0, "unblended_cost"] = -4
    checks = validate_frame(bad)
    assert any(not item["passed"] for item in checks)