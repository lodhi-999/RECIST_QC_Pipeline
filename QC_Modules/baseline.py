"""Baseline eligibility and baseline-only QC checks."""

from __future__ import annotations

import pandas as pd

from ..config import BASELINE_CECT_WINDOW_DAYS, MAX_TOTAL_TARGET_LESIONS, MAX_TARGET_LESIONS_PER_ORGAN
from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na

LEVEL = "03_BASELINE_ELIGIBILITY"


def run_baseline_qc(task: pd.DataFrame, summary: pd.DataFrame, metadata: pd.DataFrame | None, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    issues.extend(_baseline_summary_values(summary, baseline_dates))
    issues.extend(_baseline_cect_and_chest(task, metadata, baseline_dates))
    issues.extend(_baseline_stage_iii_relevance_and_thorax(task, baseline_dates))
    issues.extend(_baseline_tl_count_per_organ(task, baseline_dates))
    return issues


def _baseline_summary_values(summary: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in summary.iterrows():
        pid, study_date = row["PERSON_ID"], row["Study_date"]
        if study_date != baseline_dates.get(pid):
            continue
        if row["SERIES_TYPE_norm"] != "BASELINE":
            issues.append(issue(LEVEL, "baseline_series_type", "WARNING", pid, study_date, row.get("SERIES_TYPE"), message="Study date identified as baseline but SERIES_TYPE is not BASELINE", expected="BASELINE", actual=row.get("SERIES_TYPE")))
        for col in ["TL_OVERALL_RESPONSE", "NTL_OVERALL_RESPONSE", "NL_OVERALL_RESPONSE"]:
            if str(row.get(col, "")).strip().upper() not in { 'NO' , "NA", 'BASELINE', ""}:
                issues.append(issue(LEVEL, "baseline_response_should_be_na_no_baseline", "WARNING", pid, study_date, row.get("SERIES_TYPE"), message=f"{col} should usually be NA or NO or BASELINE at baseline", expected="NA or NO or BASELINE", actual=row.get(col)))
        if pd.isna(row.get("SOD")):
            issues.append(issue(LEVEL, "baseline_sod_missing", "ERROR", pid, study_date, row.get("SERIES_TYPE"), message="Baseline SOD is missing", expected="Numeric SOD", actual=row.get("SOD")))
    return issues


def _baseline_cect_and_chest(task: pd.DataFrame, metadata: pd.DataFrame | None, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for pid, baseline_date in baseline_dates.items():
        rows = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == baseline_date)]
        if rows.empty:
            issues.append(issue(LEVEL, "baseline_task_rows_missing", "ERROR", pid, baseline_date, message="No task_details rows found for baseline", expected="Baseline task rows present", actual="Missing"))
            continue
        # if not rows["is_CECT"].any():
        #     issues.append(issue(LEVEL, "baseline_cect_selected", "ERROR", pid, baseline_date, message="Baseline does not appear contrast-enhanced from Imaging_Method", expected="Chest w Contrast / CECT", actual=sorted(rows["Imaging_Method"].dropna().unique())))
        has_chest = rows["Anatomical_Region"].apply(lambda x: "CHEST" in str(x).upper() or "THORAX" in str(x).upper()).any()
        # if not has_chest:
        #     issues.append(issue(LEVEL, "baseline_anatomical_region", "ERROR", pid, baseline_date, message="Baseline Anatomical_Region is not CHEST/THORAX", expected="CHEST or THORAX", actual=sorted(rows["Anatomical_Region"].dropna().unique())))

        if metadata is None or "BASELINE_REFERENCE_DATE" not in metadata.columns:
            issues.append(issue(LEVEL, "baseline_cect_within_4_weeks", "INFO", pid, baseline_date, message="Cannot verify CECT within 4 weeks; BASELINE_REFERENCE_DATE unavailable", expected="patient_metadata.csv with BASELINE_REFERENCE_DATE", actual="Metadata unavailable"))
            continue
        meta_row = metadata[metadata["PERSON_ID"] == pid]
        if meta_row.empty:
            issues.append(issue(LEVEL, "baseline_cect_within_4_weeks", "WARNING", pid, baseline_date, message="No metadata row found", expected="Metadata row", actual="Missing"))
            continue
        reference_date = meta_row.iloc[0]["BASELINE_REFERENCE_DATE"]
        if pd.isna(reference_date):
            issues.append(issue(LEVEL, "baseline_cect_within_4_weeks", "WARNING", pid, baseline_date, message="BASELINE_REFERENCE_DATE missing", expected="Valid date", actual="Missing"))
            continue
        delta = abs((baseline_date - reference_date).days)
        if delta > BASELINE_CECT_WINDOW_DAYS:
            issues.append(issue(LEVEL, "baseline_cect_within_4_weeks", "WARNING", pid, baseline_date, message="Baseline CECT outside 4-week window", expected=f"<= {BASELINE_CECT_WINDOW_DAYS} days", actual=f"{delta} days"))
    return issues


def _baseline_stage_iii_relevance_and_thorax(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for pid, baseline_date in baseline_dates.items():
        rows = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == baseline_date)]
        for _, row in rows.iterrows():
            if row["thorax_class"] == "NOT_THORAX":
                issues.append(issue(LEVEL, "baseline_stage_iii_nsclc_relevance", "WARNING", pid, baseline_date, lesion_id=row["Lesion_id_norm"], message="Baseline lesion appears outside thorax / not relevant to stage III NSCLC", expected="Thoracic or locoregional baseline lesion", actual={"Location": row.get("Location"), "Other_location": row.get("Other_location"), "Anatomical_Region": row.get("Anatomical_Region")}))
            # elif row["thorax_class"] == "UNKNOWN":
            #     issues.append(issue(LEVEL, "baseline_thorax_not_thorax_categorization", "WARNING", pid, baseline_date, lesion_id=row["Lesion_id_norm"], message="Could not classify baseline lesion as Thorax or Not-Thorax", expected="Clear thoracic/non-thoracic location", actual={"Location": row.get("Location"), "Other_location": row.get("Other_location"), "Anatomical_Region": row.get("Anatomical_Region")}))
    return issues


def _baseline_tl_count_per_organ(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for pid, baseline_date in baseline_dates.items():
        baseline_tl = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == baseline_date) & (task["is_TL"])]
        total = baseline_tl["Lesion_id_norm"].nunique()
        if total > MAX_TOTAL_TARGET_LESIONS:
            issues.append(issue(LEVEL, "baseline_total_tl_count", "ERROR", pid, baseline_date, message="Too many total target lesions selected at baseline", expected=f"<= {MAX_TOTAL_TARGET_LESIONS}", actual=total))
        counts = baseline_tl.groupby("organ_group")["Lesion_id_norm"].nunique().reset_index(name="tl_count")
        for _, row in counts.iterrows():
            if row["tl_count"] > MAX_TARGET_LESIONS_PER_ORGAN:
                issues.append(issue(LEVEL, "baseline_tl_count_per_organ", "ERROR", pid, baseline_date, message="Too many target lesions selected for one organ/anatomical group", expected=f"<= {MAX_TARGET_LESIONS_PER_ORGAN} TL per organ", actual=f"{row['organ_group']}: {row['tl_count']}"))
    return issues
