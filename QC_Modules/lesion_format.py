"""Validates the formatting of Lesion IDs in task details."""

from __future__ import annotations

import re
import pandas as pd

from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na

# Define a new QC level for this check
LEVEL = "12_LESION_FORMAT"


def run_lesion_format_qc(task: pd.DataFrame) -> list[QCIssue]:
    """Main entry point for lesion format QC checks."""
    issues: list[QCIssue] = []
    
    for _, row in task.iterrows():
        pid = row.get("PERSON_ID")
        date = row.get("Study_date")
        lesion_type = str(row.get("Lesion_type_norm", ""))
        lesion_id = str(row.get("Lesion_id", "")).strip()
        
        # Only check TLs, NTLs, and NLs
        if lesion_type in ["TL", "NTL", "NL"]:
            
            # Skip if it's completely blank (schema.py already flags missing IDs)
            if is_blank_or_na(lesion_id):
                continue
                
            # Regex check: Does it end with one or more digits?
            if not re.search(r'\d+$', lesion_id):
                issues.append(
                    issue(
                        LEVEL,
                        "lesion_id_missing_number",
                        "WARNING",
                        person_id=pid,
                        study_date=date,
                        lesion_id=lesion_id,
                        message=f"{lesion_type} ID '{lesion_id}' does not end with a number",
                        expected=f"A number at the end (e.g., {lesion_type}1, {lesion_type}2)",
                        actual=lesion_id,
                    )
                )

    return issues