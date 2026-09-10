"""Validation checks for Not Evaluable (NE) responses and SODs."""

from __future__ import annotations

import pandas as pd

from ..issue import issue, QCIssue

# Define a new QC level for this check
LEVEL = "11_NE_VALIDATION"


def run_ne_validation_qc(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    """Main entry point for NE validation QC checks."""
    issues: list[QCIssue] = []
    
    for _, srow in summary.iterrows():
        pid = srow["PERSON_ID"]
        date = srow["Study_date"]
        series = srow.get("SERIES_TYPE")
        
        # Only perform these checks if TL_OVERALL_RESPONSE is "NE"
        if srow.get("TL_RESPONSE_norm") == "NE":
            
            # --- Condition 1: SOD must also be 'NE' ---
            sod_val = str(srow.get("SOD", "")).strip().upper()
            if sod_val != "NE":
                issues.append(
                    issue(
                        LEVEL,
                        "ne_response_requires_ne_sod",
                        "ERROR",
                        person_id=pid,
                        study_date=date,
                        series_type=series,
                        message="TL_OVERALL_RESPONSE is NE, but SOD is not 'NE'",
                        expected="NE",
                        actual=srow.get("SOD")
                    )
                )
            
            # --- Condition 2: At least one TL must have a Diameter of 'NE' ---
            # Filter task details for the same patient, same date, and only Target Lesions (TLs)
            patient_task = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == date) & (task["is_TL"])]
            
            has_ne_diameter = False
            if not patient_task.empty:
                # Convert diameters to string and check if any equal "NE"
                diameters_str = patient_task["Diameter"].astype(str).str.strip().str.upper()
                has_ne_diameter = (diameters_str == "NE").any()
                
            if not has_ne_diameter:
                issues.append(
                    issue(
                        LEVEL,
                        "ne_response_requires_ne_diameter",
                        "ERROR",
                        person_id=pid,
                        study_date=date,
                        series_type=series,
                        message="TL_OVERALL_RESPONSE is NE, but no Target Lesion (TL) has a Diameter of 'NE' at this timepoint",
                        expected="At least one TL with Diameter = 'NE'",
                        actual="No 'NE' diameters found for TLs"
                    )
                )

    return issues