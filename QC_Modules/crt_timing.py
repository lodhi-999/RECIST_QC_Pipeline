"""CCRT timing and baseline relationship checks."""

from __future__ import annotations

import pandas as pd

from ..issue import issue, QCIssue

# We define a new QC level for this specific module
LEVEL = "08_CRT_TIMING"


def run_crt_timing_qc(summary: pd.DataFrame, metadata: pd.DataFrame | None) -> list[QCIssue]:
    """Main entry point for CRT timing QC checks."""
    issues: list[QCIssue] = []
    issues.extend(_baseline_within_90_days_ccrt_start(summary, metadata))
    return issues


def _baseline_within_90_days_ccrt_start(summary: pd.DataFrame, metadata: pd.DataFrame | None) -> list[QCIssue]:
    """
    Checks that the baseline study date is within 90 days of the CRT_START_DATE.
    """
    issues: list[QCIssue] = []

    # 1. Check if metadata even exists and has the column
    if metadata is None or "CRT_START_DATE" not in metadata.columns:
        issues.append(
            issue(
                LEVEL,
                "baseline_within_90_days_ccrt_start",
                "INFO",
                message="Cannot verify baseline timing; CRT_START_DATE unavailable",
                expected="patient_metadata.csv with CRT_START_DATE",
                actual="Metadata unavailable",
            )
        )
        return issues

    # 2. Iterate through summary, only looking at BASELINE rows
    for _, row in summary.iterrows():
        if row["SERIES_TYPE_norm"] != "BASELINE":
            continue

        pid = row["PERSON_ID"]
        study_date = row["Study_date"]

        # 3. Find the matching patient in metadata
        meta_row = metadata[metadata["PERSON_ID"] == pid]

        if meta_row.empty:
            issues.append(
                issue(
                    LEVEL,
                    "baseline_within_90_days_ccrt_start",
                    "WARNING",
                    person_id=pid,
                    study_date=study_date,
                    series_type=row.get("SERIES_TYPE"),
                    message="No metadata row found for patient",
                    expected="Metadata row present",
                    actual="Missing",
                )
            )
            continue

        ccrt_start = meta_row.iloc[0]["CRT_START_DATE"]

        if pd.isna(ccrt_start):
            issues.append(
                issue(
                    LEVEL,
                    "baseline_within_90_days_ccrt_start",
                    "WARNING",
                    person_id=pid,
                    study_date=study_date,
                    series_type=row.get("SERIES_TYPE"),
                    message="CRT_START_DATE is missing",
                    expected="Valid date",
                    actual="Missing",
                )
            )
            continue

        # 4. Calculate the difference in days
        delta_days = abs((study_date - ccrt_start).days)

        if delta_days > 90:
            issues.append(
                issue(
                    LEVEL,
                    "baseline_within_90_days_ccrt_start",
                    "ERROR",
                    person_id=pid,
                    study_date=study_date,
                    series_type=row.get("SERIES_TYPE"),
                    message="Baseline study date is more than 90 days from CCRT start date",
                    expected="<= 90 days difference",
                    actual=f"{delta_days} days difference",
                )
            )

    return issues