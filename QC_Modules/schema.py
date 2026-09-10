"""Schema, label, duplicate, date-alignment, and technical input checks."""

from __future__ import annotations

import pandas as pd

from ..config import (
    TASK_REQUIRED_COLUMNS,
    SUMMARY_REQUIRED_COLUMNS,
    TASK_COLUMN_ALIASES,
    SUMMARY_COLUMN_ALIASES,
    VALID_LESION_TYPES,
    VALID_LATERALITY,
    VALID_ORIENTATION,
    VALID_NL_TUMOR_STATE,
    VALID_TL_RESPONSES,
    VALID_NTL_RESPONSES,
    VALID_NL_RESPONSES,
    VALID_OVERALL_RESPONSES,
    VALID_YES_NO_NA,
)
from ..issue import issue, QCIssue
from ..normalize import canonicalize_columns, is_blank_or_na, is_valid_station

LEVEL = "01_SCHEMA_AND_INPUTS"
NORM_LEVEL = "02_NORMALIZATION"


def check_required_columns(task_raw: pd.DataFrame, summary_raw: pd.DataFrame) -> tuple[list[QCIssue], list[QCIssue]]:
    task_raw = canonicalize_columns(task_raw, TASK_COLUMN_ALIASES)
    summary_raw = canonicalize_columns(summary_raw, SUMMARY_COLUMN_ALIASES)
    missing_task = [c for c in TASK_REQUIRED_COLUMNS if c not in task_raw.columns]
    missing_summary = [c for c in SUMMARY_REQUIRED_COLUMNS if c not in summary_raw.columns]

    task_issues = [
        issue(LEVEL, "required_columns", "ERROR", message=f"Missing required column in task_details.csv: {col}", expected="Column present", actual="Column missing")
        for col in missing_task
    ]
    summary_issues = [
        issue(LEVEL, "required_columns", "ERROR", message=f"Missing required column in RECIST_SUMMARY.csv: {col}", expected="Column present", actual="Column missing")
        for col in missing_summary
    ]
    return task_issues, summary_issues


def run_schema_qc(task: pd.DataFrame, summary: pd.DataFrame, image_manifest: pd.DataFrame | None) -> list[QCIssue]:
    issues: list[QCIssue] = []
    issues.extend(_valid_task_labels(task))
    issues.extend(_valid_summary_labels(summary))
    issues.extend(_missing_core_values(task, summary))
    issues.extend(_duplicate_records(task, summary))
    issues.extend(_study_date_alignment(task, summary))
    issues.extend(_zero_images_uploaded(task, summary, image_manifest))
    return issues


def _valid_task_labels(task: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in task.iterrows():
        pid, date, lesion_id = row["PERSON_ID"], row["Study_date"], row["Lesion_id_norm"]
        if row["Lesion_type_norm"] not in VALID_LESION_TYPES:
            issues.append(issue(NORM_LEVEL, "valid_lesion_type", "ERROR", pid, date, lesion_id=lesion_id, message="Invalid Lesion type", expected=sorted(VALID_LESION_TYPES), actual=row.get("Lesion type")))
        if row["Laterality_norm"] not in VALID_LATERALITY:
            issues.append(issue(NORM_LEVEL, "valid_laterality", "WARNING", pid, date, lesion_id=lesion_id, message="Invalid Laterality", expected=sorted(VALID_LATERALITY), actual=row.get("Laterality")))
        if row["Orientation_norm"] not in VALID_ORIENTATION:
            issues.append(issue(NORM_LEVEL, "valid_orientation", "WARNING", pid, date, lesion_id=lesion_id, message="Invalid Orientation", expected=sorted(VALID_ORIENTATION), actual=row.get("Orientation")))
        if not is_valid_station(row.get("Station")):
            issues.append(issue(NORM_LEVEL, "valid_station", "WARNING", pid, date, lesion_id=lesion_id, message="Invalid Station; expected Station1-Station14, numeric 1-14, or NA", expected="Station1..Station14 or NA", actual=row.get("Station")))
        if row["NL_Tumor_state_norm"] not in VALID_NL_TUMOR_STATE:
            issues.append(issue(NORM_LEVEL, "valid_nl_tumor_state", "WARNING", pid, date, lesion_id=lesion_id, message="Invalid NL_Tumor_state", expected=sorted(VALID_NL_TUMOR_STATE), actual=row.get("NL_Tumor_state")))
    return issues


def _valid_summary_labels(summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in summary.iterrows():
        pid, date, series = row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE")
        checks = [
            ("valid_tl_overall_response", row["TL_RESPONSE_norm"], VALID_TL_RESPONSES, "TL_OVERALL_RESPONSE"),
            ("valid_ntl_overall_response", row["NTL_RESPONSE_norm"], VALID_NTL_RESPONSES, "NTL_OVERALL_RESPONSE"),
            ("valid_nl_overall_response", row["NL_RESPONSE_norm"], VALID_NL_RESPONSES, "NL_OVERALL_RESPONSE"),
            ("valid_overall_response", row["OVERALL_RESPONSE_norm"], VALID_OVERALL_RESPONSES, "OVERALL_RESPONSE"),
            ("valid_lrf", row["LRF_norm"], VALID_YES_NO_NA, "LRF"),
            ("valid_df", row["DF_norm"], VALID_YES_NO_NA, "DF"),
        ]
        for check_name, normalized_value, allowed, source_col in checks:
            if normalized_value not in allowed:
                issues.append(issue(NORM_LEVEL, check_name, "ERROR", pid, date, series_type=series, message=f"Invalid {source_col}", expected=sorted(allowed), actual=row.get(source_col)))
    return issues


def _missing_core_values(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    task_core = ["PERSON_ID", "Study_date", "StudyUID", "SeriesUID", "InstanceUID", "Lesion type", "Diameter",  "Lesion_id" ]
    for _, row in task.iterrows():
        for col in task_core:
            if is_blank_or_na(row.get(col)):
                issues.append(issue(LEVEL, "missing_core_task_value", "ERROR", row.get("PERSON_ID"), row.get("Study_date"), lesion_id=row.get("Lesion_id_norm"), message=f"Missing core task_details value: {col}", expected="Non-empty value", actual=row.get(col)))
    summary_core = ["PERSON_ID", "Study_date", "SERIES_TYPE"]
    for _, row in summary.iterrows():
        for col in summary_core:
            if is_blank_or_na(row.get(col)):
                issues.append(issue(LEVEL, "missing_core_summary_value", "ERROR", row.get("PERSON_ID"), row.get("Study_date"), series_type=row.get("SERIES_TYPE"), message=f"Missing core RECIST_SUMMARY value: {col}", expected="Non-empty value", actual=row.get(col)))
    return issues


def _duplicate_records(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    
    # ---------------------------------------------------------
    # 1. TASK CHECK
    # Criteria: Flag if the exact same Lesion ID is recorded 
    # more than once on the exact same Study_date.
    # ---------------------------------------------------------
    if not task.empty:
        # Create a boolean mask that flags True for any row where 
        # Patient, Date, and Lesion ID are identical to another row.
        task_dupe_mask = task.duplicated(subset=["PERSON_ID", "Study_date", "Lesion_id_norm"], keep=False)
        
        # Extract only the rows that triggered the mask
        task_dupes = task[task_dupe_mask]
        
        if not task_dupes.empty:
            # Isolate the unique combinations so we don't spam 50 errors for one lesion
            unique_task_dupes = task_dupes.drop_duplicates(subset=["PERSON_ID", "Study_date", "Lesion_id_norm"])
            
            for _, row in unique_task_dupes.iterrows():
                # Manually count how many times this specific combination exists
                duplicate_count = len(task[
                    (task["PERSON_ID"] == row["PERSON_ID"]) & 
                    (task["Study_date"] == row["Study_date"]) & 
                    (task["Lesion_id_norm"] == row["Lesion_id_norm"])
                ])
                
                issues.append(
                    issue(
                        LEVEL, 
                        "duplicate_task_lesion_record", 
                        "WARNING", 
                        person_id=row["PERSON_ID"], 
                        study_date=row["Study_date"], 
                        lesion_id=row["Lesion_id_norm"], 
                        message="Multiple entries found for this Lesion ID on this specific date", 
                        expected="Exactly one row per Lesion ID per date", 
                        actual=f"Found {duplicate_count} rows"
                    )
                )

    # ---------------------------------------------------------
    # 2. SUMMARY CHECK
    # Criteria: Flag if the exact same Patient has more than 
    # one summary row on the exact same Study_date.
    # ---------------------------------------------------------
    if not summary.empty:
        summary_dupe_mask = summary.duplicated(subset=["PERSON_ID", "Study_date"], keep=False)
        summary_dupes = summary[summary_dupe_mask]
        
        if not summary_dupes.empty:
            unique_summary_dupes = summary_dupes.drop_duplicates(subset=["PERSON_ID", "Study_date"])
            
            for _, row in unique_summary_dupes.iterrows():
                duplicate_count = len(summary[
                    (summary["PERSON_ID"] == row["PERSON_ID"]) & 
                    (summary["Study_date"] == row["Study_date"])
                ])
                
                issues.append(
                    issue(
                        LEVEL, 
                        "duplicate_summary_record", 
                        "WARNING", 
                        person_id=row["PERSON_ID"], 
                        study_date=row["Study_date"], 
                        message="Duplicate RECIST_SUMMARY rows for same patient and date", 
                        expected="Exactly one row per date", 
                        actual=f"Found {duplicate_count} rows"
                    )
                )
                
    return issues


def _study_date_alignment(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    task_keys = set(task[["PERSON_ID", "Study_date"]].drop_duplicates().itertuples(index=False, name=None))
    summary_keys = set(summary[["PERSON_ID", "Study_date"]].drop_duplicates().itertuples(index=False, name=None))
    for pid, study_date in sorted(task_keys - summary_keys):
        issues.append(issue(LEVEL, "study_date_alignment", "ERROR", pid, study_date, message="Date exists in task_details.csv but not RECIST_SUMMARY.csv", expected="Matching summary row", actual="Missing"))
    for pid, study_date in sorted(summary_keys - task_keys):
        issues.append(issue(LEVEL, "study_date_alignment", "ERROR", pid, study_date, message="Date exists in RECIST_SUMMARY.csv but not task_details.csv", expected="Matching task rows", actual="Missing"))
    return issues


def _zero_images_uploaded(task: pd.DataFrame, summary: pd.DataFrame, image_manifest: pd.DataFrame | None) -> list[QCIssue]:
    issues: list[QCIssue] = []
    if image_manifest is not None:
        for _, row in image_manifest.iterrows():
            if row["image_count"] == 0:
                issues.append(issue(LEVEL, "zero_images_uploaded", "ERROR", row["PERSON_ID"], row["Study_date"], message="Zero images uploaded for patient/study", expected="image_count > 0", actual=0))
        return issues

    for _, srow in summary.iterrows():
        rows = task[(task["PERSON_ID"] == srow["PERSON_ID"]) & (task["Study_date"] == srow["Study_date"])]
        if rows.empty:
            issues.append(issue(LEVEL, "zero_or_missing_task_rows", "ERROR", srow["PERSON_ID"], srow["Study_date"], series_type=srow.get("SERIES_TYPE"), message="No task_details rows for summary timepoint", expected="At least one task row", actual="No rows"))
        elif rows["InstanceUID"].dropna().nunique() == 0:
            issues.append(issue(LEVEL, "zero_images_uploaded", "ERROR", srow["PERSON_ID"], srow["Study_date"], series_type=srow.get("SERIES_TYPE"), message="No valid InstanceUID found", expected="At least one InstanceUID", actual=0))
    return issues
