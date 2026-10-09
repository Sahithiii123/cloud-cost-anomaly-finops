"""Run the complete synthetic FinOps pipeline in a fixed order."""
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STEPS = [
    ["scripts/generate_data.py"],
    ["scripts/data_quality.py"],
    ["scripts/analyze.py"],
    ["scripts/tag_compliance.py"],
    ["scripts/generate_tickets.py"],
    ["scripts/savings_tracker.py"],
    ["scripts/build_excel_report.py"],
    ["scripts/export_dashboard_data.py"],
    ["scripts/build_charts.py"],
    ["scripts/verify_resume_claims.py"],
]


def main():
    for step in STEPS:
        command = [sys.executable, str(ROOT / step[0])]
        print(f"\n>>> {' '.join(step)}", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()