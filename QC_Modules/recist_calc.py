"""SOD, NADIR, and RECIST response calculation checks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import NODAL_PATHOLOGIC_MIN_MM
from ..issue import issue, QCIssue
from ..normalize import norm, normalize_ntl_response

LEVEL = "06_RECIST_CALCULATION"


def run_recist_qc(task: pd.DataFrame, summary: pd.DataFrame, baseline_dates: dict[str, object]) -> tuple[pd.DataFrame, list[QCIssue]]:
    issues: list[QCIssue] = []
    computed = compute_sod_and_nadir(task, summary, baseline_dates, issues)
    issues.extend(_qc_sod_and_nadir(task, summary, computed))
    computed_tl = compute_tl_response(task, summary, baseline_dates, computed)
    #issues.extend(_qc_tl_response(summary, computed_tl))
    issues.extend(_qc_new_lesion_consistency(task, summary, baseline_dates))
    issues.extend(_qc_ne_reasons(task, summary))
    # issues.extend(_qc_overall_response_consistency(summary))
    return computed, issues


def compute_sod_and_nadir(task: pd.DataFrame, summary: pd.DataFrame, baseline_dates: dict[str, object], issues: list[QCIssue]) -> pd.DataFrame:
    records = []
    for pid, summary_rows in summary.groupby("PERSON_ID"):
        summary_rows = summary_rows.sort_values("Study_date")
        patient_task = task[task["PERSON_ID"] == pid]
        baseline_date = baseline_dates.get(pid)
        baseline_tl_ids = set(patient_task[(patient_task["Study_date"] == baseline_date) & (patient_task["is_TL"])]["Lesion_id_norm"])
        current_nadir = None
        for _, srow in summary_rows.iterrows():
            study_date = srow["Study_date"]
            tl_rows = patient_task[(patient_task["Study_date"] == study_date) & (patient_task["Lesion_id_norm"].isin(baseline_tl_ids))]
            found_ids = set(tl_rows["Lesion_id_norm"])
            missing_ids = sorted(baseline_tl_ids - found_ids)
            if missing_ids:
                issues.append(issue(LEVEL, "sod_missing_baseline_tl", "ERROR", pid, study_date, srow.get("SERIES_TYPE"), message="SOD cannot be fully computed because baseline TL IDs are missing", expected=sorted(baseline_tl_ids), actual=f"Missing: {missing_ids}"))
            numeric_diameters = pd.to_numeric(tl_rows["Diameter"], errors="coerce")
            computed_sod = float(numeric_diameters.sum(skipna=True)) if not tl_rows.empty else 0.0
            current_nadir = computed_sod if current_nadir is None else min(current_nadir, computed_sod)
            records.append({
                "PERSON_ID": pid,
                "Study_date": study_date,
                "SERIES_TYPE": srow.get("SERIES_TYPE"),
                "computed_SOD": computed_sod,
                "computed_NADIR": current_nadir,
                "baseline_TL_ids": ",".join(sorted(baseline_tl_ids)),
                "missing_TL_ids": ",".join(missing_ids),
            })
    return pd.DataFrame(records)


def _qc_sod_and_nadir(task: pd.DataFrame, summary: pd.DataFrame, computed: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    if computed.empty:
        return issues
        
    merged = summary.merge(computed, on=["PERSON_ID", "Study_date"], how="left", suffixes=("", "_calc"))
    for _, row in merged.iterrows():
        pid, date, series = row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE")

        if not pd.isna(row.get("SOD")) and not pd.isna(row.get("computed_SOD")):
            try:
                sod_val = float(row["SOD"])
                comp_sod = float(row["computed_SOD"])
                
                if abs(sod_val - comp_sod) > 0.1:
                    
                    # --- CONDITION 1: CR allows SOD of 0 ---
                    tl_resp = str(row.get("TL_OVERALL_RESPONSE", row.get("TL_RESPONSE_norm", ""))).strip().upper()
                    if tl_resp == "CR" and sod_val == 0.0:
                        continue  
                        
                    # --- CONDITION 2: The 5mm Node Rule ---
                    if sod_val > comp_sod:
                        # Filter task details to see if this patient has ANY target lesions that are nodes on this date
                        patient_tls = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == date) & (task["is_TL"] == True)]
                        has_node = patient_tls["is_node"].any() if "is_node" in patient_tls.columns else False
                        
                        if has_node:
                            issues.append(
                                issue(
                                    LEVEL, 
                                    "sod_mismatch_possible_node", 
                                    "WARNING", 
                                    pid, date, series, 
                                    message="Reported SOD > computed SOD (Target Lesion node present, likely due to <5mm node rule)", 
                                    expected=f"Match, or valid 5mm nodal adjustment", 
                                    actual=f"Reported: {sod_val}, Computed: {comp_sod}"
                                )
                            )
                            continue # Skip the error below since this is a valid warning
                            
                    # Standard error if SOD is too small, OR if SOD is too large but there are NO nodes
                    issues.append(
                        issue(
                            LEVEL, 
                            "sod_mismatch", 
                            "ERROR", 
                            pid, date, series, 
                            message="RECIST_SUMMARY.SOD does not match recomputed SOD", 
                            expected=comp_sod, 
                            actual=sod_val
                        )
                    )

            except (ValueError, TypeError):
                pass
                
    return issues


def compute_tl_response(task: pd.DataFrame, summary: pd.DataFrame, baseline_dates: dict[str, object], computed_sod: pd.DataFrame) -> pd.DataFrame:
    records = []
    for pid, rows in computed_sod.groupby("PERSON_ID"):
        rows = rows.sort_values("Study_date")
        baseline_date = baseline_dates.get(pid)
        baseline_sod_values = rows[rows["Study_date"] == baseline_date]["computed_SOD"]
        if baseline_sod_values.empty:
            continue
        baseline_sod = float(baseline_sod_values.iloc[0])
        for _, row in rows.iterrows():
            date = row["Study_date"]
            current_sod = float(row["computed_SOD"])
            nadir = float(row["computed_NADIR"])
            if date == baseline_date:
                response = "NA"
            elif baseline_sod <= 0 or np.isnan(baseline_sod):
                response = "NE"
            else:
                pct_baseline = ((current_sod - baseline_sod) / baseline_sod) * 100.0
                pct_nadir = np.inf if nadir == 0 and current_sod > 0 else (0 if nadir == 0 else ((current_sod - nadir) / nadir) * 100.0)
                absolute_increase = current_sod - nadir
                baseline_ids = set(str(row.get("baseline_TL_ids", "")).split(",")) - {""}
                current_rows = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == date) & (task["Lesion_id_norm"].isin(baseline_ids))]
                numeric_diams = pd.to_numeric(current_rows["Diameter"], errors="coerce")
                all_zero = not current_rows.empty and numeric_diams.fillna(0).sum() == 0
                node_rows = current_rows[current_rows["is_node"]]
                numeric_node_diams = pd.to_numeric(node_rows["Diameter"], errors="coerce")
                nodes_ok = True if node_rows.empty else (numeric_node_diams < NODAL_PATHOLOGIC_MIN_MM).all()
                if pct_nadir >= 20 and absolute_increase >= 5:
                    response = "PD"
                elif all_zero and nodes_ok:
                    response = "CR"
                elif pct_baseline <= -30:
                    response = "PR"
                else:
                    response = "SD"
            records.append({"PERSON_ID": pid, "Study_date": date, "computed_TL_RESPONSE": response})
    return pd.DataFrame(records)


def _qc_tl_response(summary: pd.DataFrame, computed_tl: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    if computed_tl.empty:
        return issues
    merged = summary.merge(computed_tl, on=["PERSON_ID", "Study_date"], how="left")
    for _, row in merged.iterrows():
        computed = row.get("computed_TL_RESPONSE")
        actual = row.get("TL_RESPONSE_norm")
        if pd.isna(computed) or actual == "NE":
            continue
        if computed != actual:
            issues.append(issue(LEVEL, "tl_response_mismatch", "WARNING", row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE"), message="TL_OVERALL_RESPONSE does not match simplified SOD recomputation", expected=computed, actual=row.get("TL_OVERALL_RESPONSE")))
    return issues


def _qc_new_lesion_consistency(task: pd.DataFrame, summary: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, srow in summary.iterrows():
        pid, date, series = srow["PERSON_ID"], srow["Study_date"], srow.get("SERIES_TYPE")
        rows = task[(task["PERSON_ID"] == pid) & (task["Study_date"] == date)]
        has_nl = rows["is_NL"].any() if not rows.empty else False
        nl_response = srow["NL_RESPONSE_norm"]
        # if date == baseline_dates.get(pid):
            # if nl_response not in {"NA", ""}:
            #     issues.append(issue(LEVEL, "baseline_nl_response_should_be_na", "WARNING", pid, date, series, message="NL_OVERALL_RESPONSE should be NA at baseline", expected="NA", actual=srow.get("NL_OVERALL_RESPONSE")))
            # continue
        if nl_response == "YES" and not has_nl:
            issues.append(issue(LEVEL, "nl_response_yes_without_nl_rows", "ERROR", pid, date, series, message="NL_OVERALL_RESPONSE YES but no task_details NL rows", expected="At least one NL row", actual="No NL rows"))
        if has_nl and nl_response not in {"YES", "NO"}:
            issues.append(issue(LEVEL, "nl_rows_without_nl_response", "WARNING", pid, date, series, message="task_details has NL rows but NL_OVERALL_RESPONSE is not YES/NO", expected="YES or NO", actual=srow.get("NL_OVERALL_RESPONSE")))
    # for _, row in task.iterrows():
    #     if row["is_NL"] and str(row.get("NL_Tumor_state", "")).strip().upper() in {"", "NA"}:
    #         issues.append(issue(LEVEL, "nl_tumor_state_required", "ERROR", row["PERSON_ID"], row["Study_date"], lesion_id=row["Lesion_id_norm"], message="Lesion type NL but NL_Tumor_state missing", expected="Equivocal or Unequivocal", actual=row.get("NL_Tumor_state")))
    return issues


def _qc_ne_reasons(task: pd.DataFrame, summary: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in summary.iterrows():
        pid, date, series = row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE")
        if row["TL_RESPONSE_norm"] == "NE" and norm(row.get("TL_NE_Reason")) in {"", "NA"}:
            issues.append(issue(LEVEL, "tl_ne_reason_required", "ERROR", pid, date, series, message="TL response NE but TL_NE_Reason missing", expected="TL_NE_Reason populated", actual=row.get("TL_NE_Reason")))
        if row["NTL_RESPONSE_norm"] == "NE" and norm(row.get("NTL_NE_Reason")) in {"", "NA"}:
            issues.append(issue(LEVEL, "ntl_ne_reason_required", "ERROR", pid, date, series, message="NTL response NE but NTL_NE_Reason missing", expected="NTL_NE_Reason populated", actual=row.get("NTL_NE_Reason")))
        if row["NL_RESPONSE_norm"] == "NE" and norm(row.get("NL_NE_Reason")) in {"", "NA"}:
            issues.append(issue(LEVEL, "nl_ne_reason_required", "ERROR", pid, date, series, message="NL response NE but NL_NE_Reason missing", expected="NL_NE_Reason populated", actual=row.get("NL_NE_Reason")))
    for _, row in task.iterrows():
        if norm(row.get("NE_Reason")) not in {"", "NA"}:
            issues.append(issue(LEVEL, "task_ne_reason_present", "INFO", row["PERSON_ID"], row["Study_date"], lesion_id=row["Lesion_id_norm"], message="Task_details NE_Reason populated; verify summary NE consistency", expected="Summary response NE where applicable", actual=row.get("NE_Reason")))
    return issues


# def _expected_overall_response(tl, ntl, nl) -> str:
#     tl = norm(tl)
#     ntl = normalize_ntl_response(ntl)
#     nl = norm(nl)
#     if nl == "YES" or tl == "PD" or ntl == "PD":
#         return "PD"
#     if "NE" in {tl, ntl, nl}:
#         return "NE"
#     if tl == "NA" and ntl == "NA" and nl == "NA":
#         return "NA"
#     if tl == "CR" and ntl in {"CR", "NA", ""} and nl in {"NO", "NA", ""}:
#         return "CR"
#     if tl == "CR" and ntl == "NON-CR/NON-PD" and nl in {"NO", "NA", ""}:
#         return "PR"
#     if tl == "PR" and ntl in {"CR", "NON-CR/NON-PD", "NA", ""} and nl in {"NO", "NA", ""}:
#         return "PR"
#     if tl == "SD" and ntl in {"CR", "NON-CR/NON-PD", "SD", "NA", ""} and nl in {"NO", "NA", ""}:
#         return "SD"
#     return "REVIEW"


# def _qc_overall_response_consistency(summary: pd.DataFrame) -> list[QCIssue]:
#     issues: list[QCIssue] = []
#     for _, row in summary.iterrows():
#         expected = _expected_overall_response(row.get("TL_OVERALL_RESPONSE"), row.get("NTL_OVERALL_RESPONSE"), row.get("NL_OVERALL_RESPONSE"))
#         actual = row["OVERALL_RESPONSE_norm"]
#         if expected == "REVIEW":
#             issues.append(issue(LEVEL, "overall_response_logic_review", "WARNING", row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE"), message="Overall response could not be derived with simplified logic; manual SOP review needed", expected="SOP-defined OVERALL_RESPONSE", actual={"TL": row.get("TL_OVERALL_RESPONSE"), "NTL": row.get("NTL_OVERALL_RESPONSE"), "NL": row.get("NL_OVERALL_RESPONSE"), "OVERALL": row.get("OVERALL_RESPONSE")}))
#         elif expected != actual:
#             issues.append(issue(LEVEL, "overall_response_mismatch", "ERROR", row["PERSON_ID"], row["Study_date"], row.get("SERIES_TYPE"), message="OVERALL_RESPONSE does not match TL/NTL/NL-derived response", expected=expected, actual=actual))
#     return issues
