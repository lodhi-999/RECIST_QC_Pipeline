"""Validates lesion locations conditionally based on series type and lesion type."""

from __future__ import annotations

import pandas as pd

from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na

# Define a new QC level for this check
LEVEL = "13_LESION_LOCATION"


def run_lesion_location_qc(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    """Main entry point for lesion location QC checks."""
    issues: list[QCIssue] = []
    
    # Sort task by date to ensure we easily find the true "first mention" of any lesion
    task_sorted = task.dropna(subset=["Study_date"]).sort_values("Study_date")
    
    for pid, patient_task in task_sorted.groupby("PERSON_ID"):
        baseline_date = baseline_dates.get(pid)
        
        # --- 1. Check TLs and NTLs at Baseline ---
        if pd.notna(baseline_date):
            baseline_lesions = patient_task[
                (patient_task["Study_date"] == baseline_date) & 
                (patient_task["is_TL"] | patient_task["is_NTL"])
            ]
            
            for _, row in baseline_lesions.iterrows():
                lesion_id = row.get("Lesion_id_norm")
                has_loc = not is_blank_or_na(row.get("Location"))
                has_station = not is_blank_or_na(row.get("Station"))
                
                # If neither Location nor Station is present, it's an error
                if not (has_loc or has_station):
                    issues.append(
                        issue(
                            LEVEL,
                            "missing_baseline_location",
                            "ERROR",
                            person_id=pid,
                            study_date=baseline_date,
                            lesion_id=lesion_id,
                            message=f"{row.get('Lesion_type')} '{lesion_id}' is missing Location (and Station) at Baseline",
                            expected="Location or Station provided",
                            actual="Both missing"
                        )
                    )

        # --- 2. Check NLs at their First Mention ---
        nl_lesions = patient_task[patient_task["is_NL"]]
        
        # Because we sorted by date earlier, drop_duplicates on the ID isolates the very first time it appears
        first_nls = nl_lesions.drop_duplicates(subset=["Lesion_id_norm"])
        
        for _, row in first_nls.iterrows():
            lesion_id = row.get("Lesion_id_norm")
            has_loc = not is_blank_or_na(row.get("Location"))
            has_station = not is_blank_or_na(row.get("Station"))
            
            if not (has_loc or has_station):
                issues.append(
                    issue(
                        LEVEL,
                        "missing_nl_first_mention_location",
                        "ERROR",
                        person_id=pid,
                        study_date=row["Study_date"],
                        lesion_id=lesion_id,
                        message=f"New Lesion '{lesion_id}' is missing Location (and Station) at its first mention",
                        expected="Location or Station provided",
                        actual="Both missing"
                    )
                )

    return issues