"""Validate incoming S3 billing CSVs and copy passing objects to curated storage."""
import json
import os
import sys
from urllib.parse import unquote_plus

import boto3
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from data_quality import validate_frame, write_report

s3 = boto3.client("s3")


def validate_object(source_bucket, source_key, curated_bucket):
    response = s3.get_object(Bucket=source_bucket, Key=source_key)
    frame = pd.read_csv(response["Body"], dtype={column: "string" for column in
                                                 ["Environment", "Owner", "CostCenter", "Application"]})
    checks = validate_frame(frame)
    report_lines = ["# Data Quality Report", "", "| Check | Result | Count | Detail |", "|---|---:|---:|---|"]
    for check in checks:
        report_lines.append(f"| {check['check']} | {'PASS' if check['passed'] else 'FAIL'} | {check['count']} | {check['detail']} |")
    report = ("\n".join(report_lines) + "\n").encode("utf-8")
    report_key = f"quality/{source_key}.md"
    s3.put_object(Bucket=curated_bucket, Key=report_key, Body=report, ContentType="text/markdown")
    failed = [check["check"] for check in checks if not check["passed"]]
    if failed:
        raise ValueError(f"Quality failure for s3://{source_bucket}/{source_key}: {', '.join(failed)}")
    destination_key = f"validated/{os.path.basename(source_key)}"
    s3.copy_object(Bucket=curated_bucket, Key=destination_key,
                   CopySource={"Bucket": source_bucket, "Key": source_key})
    return {"source": f"s3://{source_bucket}/{source_key}", "curated": f"s3://{curated_bucket}/{destination_key}",
            "report": f"s3://{curated_bucket}/{report_key}", "status": "PASS"}


def handler(event, context):
    raw_bucket = os.environ["RAW_BUCKET"]
    curated_bucket = os.environ["CURATED_BUCKET"]
    objects = []
    for record in event.get("Records", []):
        if record.get("eventSource") == "aws:s3":
            objects.append((record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"])))
    detail = event.get("detail", {})
    if detail.get("bucket", {}).get("name") and detail.get("object", {}).get("key"):
        objects.append((detail["bucket"]["name"], unquote_plus(detail["object"]["key"])))
    if not objects:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=raw_bucket, Prefix="incoming/"):
            objects.extend((raw_bucket, item["Key"]) for item in page.get("Contents", []))
    results = [validate_object(bucket, key, curated_bucket) for bucket, key in objects]
    return {"statusCode": 200, "body": json.dumps({"validated": len(results), "results": results})}