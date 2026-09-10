"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import run_pipeline


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run modular RECIST QC pipeline")
    parser.add_argument("--input-dir", default="sample_data", help="Directory containing task_details.csv and RECIST_SUMMARY.csv")
    parser.add_argument("--output-dir", default="qc_outputs", help="Directory where QC output CSVs will be written")
    args = parser.parse_args(argv)

    outputs = run_pipeline(args.input_dir, args.output_dir)
    print("QC pipeline complete. Outputs:")
    for name, path in outputs.items():
        print(f"  {name}: {Path(path)}")


if __name__ == "__main__":
    main()
