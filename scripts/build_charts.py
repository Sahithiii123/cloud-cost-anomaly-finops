"""Fail if the pipeline did not produce all expected chart assets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = ["01_cost_trend.png", "02_anomalies_flagged.png", "03_forecast_vs_actual.png", "04_tag_compliance.png"]


def main():
    missing = [name for name in EXPECTED if not (ROOT / "charts" / name).is_file() or (ROOT / "charts" / name).stat().st_size == 0]
    if missing:
        raise SystemExit("Missing chart outputs: " + ", ".join(missing))
    print(f"Chart outputs verified: {len(EXPECTED)} PNG files.")


if __name__ == "__main__":
    main()