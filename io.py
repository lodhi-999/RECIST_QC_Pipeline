"""File I/O layer for the modular RECIST QC package."""

from __future__ import annotations

from pathlib import Path
import pandas as pd


def read_csv_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(path, keep_default_na=False)


def read_csv_optional(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, keep_default_na=False)


def load_inputs(input_dir: str | Path) -> dict:
    input_dir = Path(input_dir)

    task_raw = read_csv_required(input_dir / "TASK_DETAILS_V13.csv")
    
    # Patch the truly missing columns so the pipeline doesn't crash
    if "InstanceUID" not in task_raw.columns:
        task_raw["InstanceUID"] = "SYNTHETIC_UID"
    if "Lesion physical coordinate" not in task_raw.columns:
        task_raw["Lesion physical coordinate"] = pd.NA


        
    return {
        "task_raw": task_raw ,
        "summary_raw": read_csv_required(input_dir / "RECIST_SUMMARY_V13.csv"),
        "metadata_raw": read_csv_optional(input_dir / "final_mayo_cohort.csv"),
        "image_manifest_raw": read_csv_optional(input_dir / "image_manifest.csv"),
    }


def write_dataframe(df: pd.DataFrame, output_dir: str | Path, filename: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    df.to_csv(path, index=False)
    return path
