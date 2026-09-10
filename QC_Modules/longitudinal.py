"""Longitudinal consistency checks across timepoints."""

from __future__ import annotations

import pandas as pd

from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na

LEVEL = "05_LONGITUDINAL_CONSISTENCY"


def run_longitudinal_qc(task: pd.DataFrame, summary: pd.DataFrame, metadata: pd.DataFrame | None, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    issues.extend(_followups_after_ccrt_end(summary, metadata))
    issues.extend(_baseline_tl_continue_at_followups(task, summary, baseline_dates))
    issues.extend(_lesion_ids_present_after_first_appearance(task, summary))
    return issues


def _summary_dates_by_patient(summary: pd.DataFrame) -> dict[str, list[object]]:
    return {pid: sorted(rows["Study_date"].dropna().unique()) for pid, rows in summary.groupby("PERSON_ID")}


def _followups_after_ccrt_end(summary: pd.DataFrame, metadata: pd.DataFrame | None) -> list[QCIssue]:
    issues: list[QCIssue] = []
    if metadata is None or "CRT_END_DATE" not in metadata.columns:
        issues.append(issue(LEVEL, "followups_after_ccrt_end", "INFO", message="Cannot verify followups after CCRT end; CRT_END_DATE unavailable", expected="patient_metadata.csv with CRT_END_DATE", actual="Metadata unavailable"))
        return issues
    for _, row in summary.iterrows():
        if row["SERIES_TYPE_norm"] == "BASELINE":
            continue
        pid, date = row["PERSON_ID"], row["Study_date"]
        meta_row = metadata[metadata["PERSON_ID"] == pid]
        if meta_row.empty:
            continue
        ccrt_end = meta_row.iloc[0]["CRT_END_DATE"]
        if pd.isna(ccrt_end):
            issues.append(issue(LEVEL, "followups_after_ccrt_end", "WARNING", pid, date, row.get("SERIES_TYPE"), message="CRT_END_DATE missing", expected="Valid CRT_END_DATE", actual="Missing"))
        elif date < ccrt_end:
            issues.append(issue(LEVEL, "followups_after_ccrt_end", "ERROR", pid, date, row.get("SERIES_TYPE"), message="Follow-up study is not on or after CRT end date", expected=f"Study_date >= {ccrt_end}", actual=date))
    return issues


def _baseline_tl_continue_at_followups(task: pd.DataFrame, summary: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    dates_by_patient = _summary_dates_by_patient(summary)
    for pid, baseline_date in baseline_dates.items():
        patient_task = task[task["PERSON_ID"] == pid]
        baseline_tl_ids = set(patient_task[(patient_task["Study_date"] == baseline_date) & (patient_task["is_TL"])]["Lesion_id_norm"])
        followup_dates = [d for d in dates_by_patient.get(pid, []) if d != baseline_date]
        for lesion_id in baseline_tl_ids:
            for followup_date in followup_dates:
                rows = patient_task[(patient_task["Study_date"] == followup_date) & (patient_task["Lesion_id_norm"] == lesion_id)]
                if rows.empty:
                    issues.append(issue(LEVEL, "baseline_tl_missing_at_followup", "ERROR", pid, followup_date, lesion_id=lesion_id, message="Baseline target lesion missing at follow-up", expected="Same Lesion_id present at each follow-up", actual="Missing"))
                elif rows["Diameter"].isna().all():
                    issues.append(issue(LEVEL, "baseline_tl_measurement_missing_at_followup", "ERROR", pid, followup_date, lesion_id=lesion_id, message="Baseline TL present but Diameter missing at follow-up", expected="Non-null Diameter", actual="Missing"))
                elif not rows["is_TL"].any():
                    issues.append(issue(LEVEL, "baseline_tl_type_changed", "WARNING", pid, followup_date, lesion_id=lesion_id, message="Baseline TL present but Lesion type changed", expected="Lesion type remains TL", actual=rows["Lesion type"].dropna().unique().tolist()))
    return issues


def _lesion_ids_present_after_first_appearance(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    dates_by_patient = _summary_dates_by_patient(summary)
    for pid, patient_task in task.groupby("PERSON_ID"):
        all_dates = dates_by_patient.get(pid, [])
        for lesion_id, lesion_rows in patient_task.groupby("Lesion_id_norm"):
            if is_blank_or_na(lesion_id):
                continue
            first_date = min(lesion_rows["Study_date"].dropna())
            for expected_date in [d for d in all_dates if d >= first_date]:
                exists = ((patient_task["Study_date"] == expected_date) & (patient_task["Lesion_id_norm"] == lesion_id)).any()
                if not exists:
                    issues.append(issue(LEVEL, "lesion_id_missing_after_first_appearance", "ERROR", pid, expected_date, lesion_id=lesion_id, message="Lesion_id missing at a timepoint after first appearance", expected="Lesion_id present from first appearance onward", actual="Missing"))
    return issues
