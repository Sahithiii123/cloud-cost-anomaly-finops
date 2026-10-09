# Data Quality Report

| Check | Result | Count | Detail |
|---|---:|---:|---|
| Required schema | PASS | 0 | Missing columns: none |
| Column dtypes | PASS | 0 | Unexpected dtypes: none |
| Null key/measure fields | PASS | 18127 | Fields with nulls: usage_quantity; 18127 missing quantities on non-usage charge rows allowed and retained: {'credit': 17334, 'tax': 515, 'purchase': 278} |
| Duplicate line items | PASS | 0 | Fully duplicated rows across mapped line-item fields |
| Negative costs | PASS | 103990 | Negative unblended_cost rows; signed source amounts preserved unchanged and listed for reconciliation |
| Date-range continuity | PASS | 0 | Missing calendar dates: 163; invalid dates: 0; sparse dates are allowed for the public FOCUS sample, no rows were imputed |
| Tag-field validity | PASS | 0 | tag values must be strings or null; missing/inconsistent tags are reported by the KPI |

Overall: **PASS**.
