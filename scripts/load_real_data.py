"""Download and map the complete public FinOps Foundation FOCUS 1.0 sample."""
import json
import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://media.githubusercontent.com/media/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data/main/FOCUS-1.0/focus_data_table.csv.gz"
SAMPLE_URL = "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data/main/FOCUS-1.0/focus_sample.csv"
LICENSE_URL = "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data/main/license.md"


def first_present(row, *names):
    for name in names:
        value = row.get(name)
        if pd.notna(value) and str(value).strip():
            return value
    return None


def clean_tag(value):
    if value is None or pd.isna(value):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def map_focus_frame(source, source_row_start=0):
    required = {"ChargePeriodStart", "BilledCost", "ConsumedQuantity"}
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"FOCUS file is missing required columns: {', '.join(sorted(missing))}")
    mapped = pd.DataFrame()
    mapped["usage_date"] = pd.to_datetime(source["ChargePeriodStart"], errors="coerce", utc=True).dt.tz_convert(None).dt.strftime("%Y-%m-%d")
    mapped["service"] = source.get("ServiceName", source.get("ServiceCategory", "Unknown service")).fillna("Unknown service").astype(str)
    mapped["region"] = source.get("RegionId", source.get("RegionName", "Unknown region")).fillna("Unknown region").astype(str)
    mapped["usage_type"] = source.get("ConsumedUnit", source.get("ChargeCategory", "Unknown unit")).fillna("Unknown unit").astype(str)
    mapped["unblended_cost"] = pd.to_numeric(source["BilledCost"], errors="coerce")
    mapped["usage_quantity"] = pd.to_numeric(source["ConsumedQuantity"], errors="coerce")
    mapped["charge_category"] = source.get("ChargeCategory", pd.Series([None] * len(source), index=source.index)).fillna("").astype(str)
    mapped["line_item_id"] = [f"focus-row-{source_row_start + index:09d}" for index in range(len(source))]
    tags = source["Tags"].map(lambda value: json.loads(value) if isinstance(value, str) and value.strip().startswith("{") else {}) if "Tags" in source else pd.Series([{}] * len(source), index=source.index)
    mapped["Environment"] = tags.map(lambda values: clean_tag(first_present(values, "environment", "Environment")))
    mapped["Owner"] = tags.map(lambda values: clean_tag(first_present(values, "owner", "Owner")))
    mapped["CostCenter"] = tags.map(lambda values: clean_tag(first_present(values, "costcenter", "cost_center", "CostCenter")))
    mapped["Application"] = tags.map(lambda values: clean_tag(first_present(values, "application", "Application")))
    return mapped


def main():
    parser = argparse.ArgumentParser(description="Download or map the complete public FOCUS 1.0 dataset.")
    parser.add_argument("--local", type=Path, help="Use a manually downloaded full CSV/CSV.GZ source")
    parser.add_argument("--sample", action="store_true", help="Use only the publisher's 1,000-row sample for a quick smoke test")
    args = parser.parse_args()
    output = ROOT / "outputs" / "real_data"
    output.mkdir(parents=True, exist_ok=True)
    source_url = SAMPLE_URL if args.sample else SOURCE_URL
    raw_path = output / ("focus_sample_source.csv" if args.sample else "focus_data_table_source.csv.gz")
    mapped_path = output / "cur_mapped.csv"
    try:
        if args.local:
            source_path = args.local
            if not source_path.is_file():
                raise OSError(f"Manual source file not found: {source_path}")
        else:
            with requests.get(source_url, timeout=(30, 180), stream=True) as response:
                response.raise_for_status()
                with raw_path.open("wb") as download:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            download.write(block)
            source_path = raw_path
        source_rows = 0
        mapped_rows = 0
        rejected_rows = 0
        negative_cost_rows = 0
        allowed_quantity_null_counts = {}
        covered_months = set()
        write_header = True
        reject_header = True
        negative_header = True
        for chunk in pd.read_csv(source_path, compression="infer", chunksize=100_000, low_memory=False):
            mapped_chunk = map_focus_frame(chunk, source_row_start=source_rows)
            non_usage_nulls = mapped_chunk.loc[
                mapped_chunk["usage_quantity"].isna()
                & mapped_chunk["charge_category"].str.casefold().isin({"credit", "tax", "purchase"}),
                "charge_category",
            ].str.casefold().value_counts()
            for category, count in non_usage_nulls.items():
                allowed_quantity_null_counts[category] = allowed_quantity_null_counts.get(category, 0) + int(count)
            required_missing = mapped_chunk["usage_date"].isna() | mapped_chunk["unblended_cost"].isna()
            rejected = mapped_chunk[required_missing]
            clean = mapped_chunk[~required_missing]
            rejected.to_csv(output / "mapping_rejects.csv", mode="w" if reject_header else "a",
                            header=reject_header, index=False)
            reject_header = False
            clean.to_csv(mapped_path, mode="w" if write_header else "a", header=write_header, index=False)
            write_header = False
            negative = clean[clean["unblended_cost"] < 0]
            negative.to_csv(output / "negative_cost_review.csv", mode="w" if negative_header else "a",
                            header=negative_header, index=False)
            negative_header = False
            negative_cost_rows += len(negative)
            rejected_rows += len(rejected)
            mapped_rows += len(clean)
            covered_months.update(pd.to_datetime(clean["usage_date"]).dt.to_period("M").astype(str).unique())
            source_rows += len(chunk)
        if write_header:
            raise ValueError("The public source contained no parseable data rows.")
        (output / "mapping_report.md").write_text(
            "# FOCUS Mapping Report\n\n"
            f"Source URL: [{source_url}]({source_url})\n\n"
            f"Source rows: {source_rows}. Mapped rows: {mapped_rows}. Rejected rows: {rejected_rows}.\n\n"
            f"Covered calendar months: {len(covered_months)} ({min(covered_months)} to {max(covered_months)}).\n\n"
            f"Negative-cost rows retained for review: {negative_cost_rows}. Missing quantities on non-usage charges retained by category: {allowed_quantity_null_counts}.\n\n"
            "Only rows missing a date or billed cost are excluded. Credit quantities may remain null when the source omits them; those costs remain in spend analysis.\n",
            encoding="utf-8")
    except (requests.RequestException, OSError, ValueError, pd.errors.ParserError) as error:
        instructions = f"""# Real-data download unavailable

Automatic download or mapping failed: `{type(error).__name__}: {error}`.

Manual steps:
1. Download the complete FOCUS 1.0 dataset from [{SOURCE_URL}]({SOURCE_URL}).
2. Save the `.csv.gz` file locally and run `python scripts/load_real_data.py --local <path-to-full-csv-or-csv.gz>`.

License: CC BY 4.0, [{LICENSE_URL}]({LICENSE_URL}). The sample is described by its publisher as anonymized real-world data.
"""
        (output / "download_instructions.md").write_text(instructions, encoding="utf-8")
        print(instructions)
        return

    env = os.environ.copy()
    env["FINOPS_DATA_PATH"] = str(mapped_path)
    env["FINOPS_OUTPUT_DIR"] = str(output)
    env["FINOPS_CHARTS_DIR"] = str(output / "charts")
    env["FINOPS_ALLOW_SPARSE_DATES"] = "1"
    env["FINOPS_ALLOW_SIGNED_COSTS"] = "1"
    env["FINOPS_ALLOW_NON_USAGE_QUANTITY_NULLS"] = "1"
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze.py")], cwd=ROOT, env=env, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    summary = json.loads((output / "analysis_summary.json").read_text(encoding="utf-8"))
    note = "# Public FOCUS Full Dataset Run\n\n"
    note += f"Source: [{source_url}]({source_url})\n\nLicense: CC BY 4.0 ([license text]({LICENSE_URL})).\n\n"
    note += f"The publisher describes this as anonymized real-world FOCUS data. {source_rows} source rows were read; {mapped_rows} mapped; {rejected_rows} rejected for missing date or billed cost; {len(covered_months)} calendar months covered. See `mapping_report.md`. It is not the synthetic dataset and does not substantiate the synthetic resume claims. Sparse dates are reported without imputing rows. Signed BilledCost values are preserved and negative rows are listed in `negative_cost_review.csv`.\n\n"
    note += f"Real-data forecast status: **{summary['forecast_status']}**. {summary['forecast_suppression_reason'] or 'Forecast passed the configured evidence gates.'}\n"
    (output / "README.md").write_text(note, encoding="utf-8")
    print(f"Mapped {mapped_rows:,} of {source_rows:,} public FOCUS rows across {len(covered_months)} months; saved analysis under {output.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()