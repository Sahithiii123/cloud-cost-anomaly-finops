# Public FOCUS Full Dataset Run

Source: [https://media.githubusercontent.com/media/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data/main/FOCUS-1.0/focus_data_table.csv.gz](https://media.githubusercontent.com/media/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data/main/FOCUS-1.0/focus_data_table.csv.gz)

License: CC BY 4.0 ([license text](https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data/main/license.md)).

The publisher describes this as anonymized real-world FOCUS data. 5488359 source rows were read; 5488359 mapped; 0 rejected for missing date or billed cost; 2 calendar months covered. See `mapping_report.md`. It is not the synthetic dataset and does not substantiate the synthetic resume claims. Sparse dates are reported without imputing rows. Signed BilledCost values are preserved and negative rows are listed in `negative_cost_review.csv`.

Real-data forecast status: **suppressed**. only 0 rolling-origin holdouts; at least 3 required; regression MAPE is unavailable or exceeds 20%; exponential-smoothing MAPE is unavailable or exceeds 20%; method totals disagree by more than 15%
