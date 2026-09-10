"""Progression checks involving PD, LRF, and DF."""

from __future__ import annotations

import pandas as pd

from ..issue import issue, QCIssue
from ..normalize import is_yes, parse_lesion_list, is_blank_or_na

LEVEL = "07_PROGRESSION_DF_LRF"


def run_progression_qc(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    issues.extend(_pd_requires_df_or_lrf(summary))
    issues.extend(_lrf_df_lists_and_locations(task, summary))
    
    return issues


def _pd_requires_df_or_lrf(summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in summary.iterrows():
        if row["OVERALL_RESPONSE_norm"] != "PD":
            continue
        if not is_yes(row.get("LRF")) and not is_yes(row.get("DF")):
            issues.append(issue(LEVEL, "pd_requires_df_or_lrf", "ERROR", row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE"), message="OVERALL_RESPONSE is PD but neither LRF nor DF is YES", expected="LRF=YES or DF=YES", actual={"OVERALL_RESPONSE": row.get("OVERALL_RESPONSE"), "LRF": row.get("LRF"), "DF": row.get("DF")}))
    return issues


def _lrf_df_lists_and_locations(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in summary.iterrows():
        pid, date, series = row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE")
        lrf_yes = is_yes(row.get("LRF"))
        df_yes = is_yes(row.get("DF"))
        lrf_ids = parse_lesion_list(row.get("LRF_Lesions_List"))
        df_ids = parse_lesion_list(row.get("DF_Lesions_List"))

        if lrf_yes and not lrf_ids:
            issues.append(issue(LEVEL, "lrf_lesions_list_required", "ERROR", pid, date, series, message="LRF is YES but LRF_Lesions_List is empty", expected="One or more Lesion_id values", actual=row.get("LRF_Lesions_List")))
        if df_yes and not df_ids:
            issues.append(issue(LEVEL, "df_lesions_list_required", "ERROR", pid, date, series, message="DF is YES but DF_Lesions_List is empty", expected="One or more Lesion_id values", actual=row.get("DF_Lesions_List")))
        if not lrf_yes and lrf_ids:
            issues.append(issue(LEVEL, "lrf_list_without_lrf_yes", "WARNING", pid, date, series, message="LRF_Lesions_List populated but LRF is not YES", expected="LRF=YES", actual={"LRF": row.get("LRF"), "LRF_Lesions_List": row.get("LRF_Lesions_List")}))
        if not df_yes and df_ids:
            issues.append(issue(LEVEL, "df_list_without_df_yes", "WARNING", pid, date, series, message="DF_Lesions_List populated but DF is not YES", expected="DF=YES", actual={"DF": row.get("DF"), "DF_Lesions_List": row.get("DF_Lesions_List")}))
        if (lrf_yes or df_yes) and is_blank_or_na(row.get("Anatomical_location_of_the_PoF")):
            issues.append(issue(LEVEL, "pof_location_required", "ERROR", pid, date, series, message="LRF or DF is YES but Anatomical_location_of_the_PoF is empty", expected="Progression location populated", actual=row.get("Anatomical_location_of_the_PoF")))

        same_timepoint = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == date)]
        for lesion_id in lrf_ids:
            rows = same_timepoint[same_timepoint["Lesion_id_norm"] == lesion_id]
            if rows.empty:
                issues.append(issue(LEVEL, "lrf_lesion_id_not_found", "ERROR", pid, date, series, lesion_id=lesion_id, message="LRF lesion ID not found in task_details for same patient/study date", expected="Listed Lesion_id exists", actual="Missing"))
            elif not (rows["thorax_class"] == "THORAX").any():
                issues.append(issue(LEVEL, "lrf_location_definition", "WARNING", pid, date, series, lesion_id=lesion_id, message="LRF lesion does not appear thoracic/locoregional", expected="Thoracic/locoregional", actual=rows[["Location", "Other_location"]].drop_duplicates().to_dict("records")))

        for lesion_id in df_ids:
            rows = same_timepoint[same_timepoint["Lesion_id_norm"] == lesion_id]
            if rows.empty:
                issues.append(issue(LEVEL, "df_lesion_id_not_found", "ERROR", pid, date, series, lesion_id=lesion_id, message="DF lesion ID not found in task_details for same patient/study date", expected="Listed Lesion_id exists", actual="Missing"))
            elif (rows["thorax_class"] == "THORAX").any():
                issues.append(issue(LEVEL, "df_location_definition", "WARNING", pid, date, series, lesion_id=lesion_id, message="DF lesion appears thoracic; verify against SOP", expected="Distant/non-thoracic", actual=rows[["Location", "Other_location"]].drop_duplicates().to_dict("records")))
    return issues


