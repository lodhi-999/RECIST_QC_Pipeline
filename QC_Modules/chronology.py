"""Chronological order checks for study dates across timepoints."""

from __future__ import annotations

import re
import pandas as pd

from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na

LEVEL = "09_CHRONOLOGY"


def run_chronology_qc(task: pd.DataFrame, summary: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    """Main entry point for chronological QC checks."""
    issues: list[QCIssue] = []
    
    # 1. Check if dates go backwards or if follow-up numbers are skipped
    issues.extend(_check_timepoint_chronology(summary))
    
    # 2. Check if new unexpected TLs or NTLs appear at follow-ups (NLs are exempt)
    issues.extend(_check_new_tl_ntl_at_followup(task, baseline_dates))
    
    return issues


def _get_timepoint_index(series_type: str) -> int:
    """
    Converts a series type into a numeric index for logical sorting.
    BASELINE -> 0
    FOLLOWUP1 -> 1
    FOLLOWUP2 -> 2
    ERROR / Unknown -> -1 (to be ignored)
    """
    if is_blank_or_na(series_type):
        return -1
        
    s = str(series_type).upper().strip().replace(" ", "").replace("_", "")
    
    if s == "BASELINE":
        return 0
        
    match = re.search(r'FOLLOWUP(\d+)', s)
    if match:
        return int(match.group(1))
        
    return -1


def _check_timepoint_chronology(summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    
    df = summary.copy()
    df = df.dropna(subset=["Study_date", "SERIES_TYPE_norm"])
    df["timepoint_index"] = df["SERIES_TYPE_norm"].apply(_get_timepoint_index)
    df = df[df["timepoint_index"] >= 0]

    for pid, patient_rows in df.groupby("PERSON_ID"):
        
        # --- Check for skipped follow-up numbers (WARNING) ---
        unique_timepoints = sorted(patient_rows["timepoint_index"].unique())
        for i in range(len(unique_timepoints) - 1):
            curr_idx = unique_timepoints[i]
            next_idx = unique_timepoints[i + 1]
            
            if next_idx > curr_idx + 1:
                curr_name = "BASELINE" if curr_idx == 0 else f"FOLLOWUP{curr_idx}"
                issues.append(
                    issue(
                        LEVEL,
                        "skipped_followup_number",
                        "WARNING",
                        person_id=pid,
                        message=f"Skipped follow-up number: sequence jumped from {curr_name} directly to FOLLOWUP{next_idx}",
                        expected=f"FOLLOWUP{curr_idx + 1}",
                        actual=f"FOLLOWUP{next_idx}",
                    )
                )

        # --- Check for chronological date reversals (ERROR) ---
        sorted_rows = patient_rows.sort_values(by=["timepoint_index", "Study_date"]).reset_index(drop=True)
        
        for i in range(len(sorted_rows) - 1):
            curr_row = sorted_rows.iloc[i]
            next_row = sorted_rows.iloc[i + 1]
            
            if curr_row["Study_date"] > next_row["Study_date"]:
                issues.append(
                    issue(
                        LEVEL,
                        "chronology_violation",
                        "ERROR",
                        person_id=pid,
                        study_date=next_row["Study_date"],
                        series_type=next_row["SERIES_TYPE"],
                        message=f"{next_row['SERIES_TYPE']} occurs earlier than previous timepoint ({curr_row['SERIES_TYPE']})",
                        expected=f">= {curr_row['Study_date']} ({curr_row['SERIES_TYPE']})",
                        actual=next_row["Study_date"],
                    )
                )

    return issues


def _check_new_tl_ntl_at_followup(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    """
    Ensures that any Target Lesion (TL) or Non-Target Lesion (NTL) present at a 
    follow-up was also present at baseline. New Lesions (NLs) are exempt.
    """
    issues: list[QCIssue] = []
    
    for pid, baseline_date in baseline_dates.items():
        if pd.isna(baseline_date):
            continue
            
        patient_task = task[task["PERSON_ID"] == pid]
        
        # 1. Gather all TL and NTL IDs present exactly at the baseline date
        baseline_lesions = set(
            patient_task[
                (patient_task["Study_date"] == baseline_date) & 
                (patient_task["is_TL"] | patient_task["is_NTL"])
            ]["Lesion_id_norm"]
        )
        
        # 2. Look at all follow-up dates, strictly filtering for TLs and NTLs
        followup_task = patient_task[
            (patient_task["Study_date"] != baseline_date) & 
            (patient_task["is_TL"] | patient_task["is_NTL"])
        ]
        
        # 3. If a follow-up TL/NTL is not in the baseline set, flag it
        for _, row in followup_task.iterrows():
            lesion_id = row["Lesion_id_norm"]
            lesion_type = row["Lesion_type_norm"]
            
            if not is_blank_or_na(lesion_id) and lesion_id not in baseline_lesions:
                issues.append(
                    issue(
                        LEVEL,
                        "unexpected_lesion_at_followup",
                        "ERROR",
                        person_id=pid,
                        study_date=row["Study_date"],
                        lesion_id=lesion_id,
                        message=f"{lesion_type} '{lesion_id}' appeared in follow-up but was not present at baseline",
                        expected=f"Must be a subset of Baseline TLs/NTLs: {sorted(list(baseline_lesions))}",
                        actual=lesion_id,
                    )
                )
                
    return issues