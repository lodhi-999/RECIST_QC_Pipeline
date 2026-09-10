"""Metric and patient pass/fail output layer."""

from __future__ import annotations

import pandas as pd

from .config import QC_LEVEL_ORDER, BLOCKING_SEVERITIES


def _empty_issues_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "qc_level",
        "check_name",
        "severity",
        "PERSON_ID",
        "Study_date",
        "SERIES_TYPE",
        "Lesion_id",
        "message",
        "expected",
        "actual",
    ])


def _issue_counts(df: pd.DataFrame) -> dict[str, int]:
    return {
        "error_issues": int((df["severity"] == "ERROR").sum()) if not df.empty else 0,
        "warning_issues": int((df["severity"] == "WARNING").sum()) if not df.empty else 0,
        "info_issues": int((df["severity"] == "INFO").sum()) if not df.empty else 0,
    }


def build_patient_status_by_level(issues_df: pd.DataFrame, all_patients: list[str]) -> pd.DataFrame:
    rows = []
    if issues_df.empty:
        issues_df = _empty_issues_df()

    for level in QC_LEVEL_ORDER:
        level_issues = issues_df[issues_df["qc_level"] == level]
        global_blocking = level_issues[
            (level_issues["PERSON_ID"].astype(str).str.len() == 0)
            & (level_issues["severity"].isin(BLOCKING_SEVERITIES))
        ]
        for pid in all_patients:
            patient_issues = level_issues[level_issues["PERSON_ID"].astype(str) == str(pid)]
            counts = _issue_counts(patient_issues)
            error_count = counts["error_issues"] + len(global_blocking)
            rows.append({
                "PERSON_ID": pid,
                "qc_level": level,
                "passed": error_count == 0,
                "error_issues": error_count,
                "warning_issues": counts["warning_issues"],
                "info_issues": counts["info_issues"],
            })
    return pd.DataFrame(rows)


def build_metrics_by_level(status_by_level: pd.DataFrame, issues_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total_patients = status_by_level["PERSON_ID"].nunique() if not status_by_level.empty else 0
    for level in QC_LEVEL_ORDER:
        level_status = status_by_level[status_by_level["qc_level"] == level]
        level_issues = issues_df[issues_df["qc_level"] == level] if not issues_df.empty else _empty_issues_df()
        counts = _issue_counts(level_issues)
        passed = int(level_status["passed"].sum()) if not level_status.empty else 0
        failed = int((~level_status["passed"]).sum()) if not level_status.empty else 0
        pass_rate = round(passed / total_patients, 4) if total_patients else 0
        rows.append({
            "qc_level": level,
            "total_patients": total_patients,
            "passed_patients": passed,
            "failed_patients": failed,
            "pass_rate": pass_rate,
            **counts,
        })
    return pd.DataFrame(rows)


def build_metrics_by_check(issues_df: pd.DataFrame) -> pd.DataFrame:
    if issues_df.empty:
        return pd.DataFrame(columns=[
            "qc_level",
            "check_name",
            "error_issues",
            "warning_issues",
            "info_issues",
            "affected_patients",
        ])

    rows = []
    for (level, check), g in issues_df.groupby(["qc_level", "check_name"], dropna=False):
        counts = _issue_counts(g)
        affected = g[g["PERSON_ID"].astype(str).str.len() > 0]["PERSON_ID"].nunique()
        rows.append({
            "qc_level": level,
            "check_name": check,
            **counts,
            "affected_patients": int(affected),
        })
    return pd.DataFrame(rows).sort_values(["qc_level", "error_issues", "warning_issues"], ascending=[True, False, False])


def build_patient_status_by_check(issues_df: pd.DataFrame, all_patients: list[str]) -> pd.DataFrame:
    if issues_df.empty:
        return pd.DataFrame(columns=[
            "PERSON_ID",
            "qc_level",
            "check_name",
            "passed",
            "error_issues",
            "warning_issues",
            "info_issues",
        ])

    rows = []
    checks = issues_df[["qc_level", "check_name"]].drop_duplicates().sort_values(["qc_level", "check_name"])
    for _, chk in checks.iterrows():
        level = chk["qc_level"]
        check = chk["check_name"]
        check_issues = issues_df[(issues_df["qc_level"] == level) & (issues_df["check_name"] == check)]
        global_blocking = check_issues[
            (check_issues["PERSON_ID"].astype(str).str.len() == 0)
            & (check_issues["severity"].isin(BLOCKING_SEVERITIES))
        ]
        for pid in all_patients:
            patient_issues = check_issues[check_issues["PERSON_ID"].astype(str) == str(pid)]
            counts = _issue_counts(patient_issues)
            errors = counts["error_issues"] + len(global_blocking)
            rows.append({
                "PERSON_ID": pid,
                "qc_level": level,
                "check_name": check,
                "passed": errors == 0,
                "error_issues": errors,
                "warning_issues": counts["warning_issues"],
                "info_issues": counts["info_issues"],
            })
    return pd.DataFrame(rows)


def build_patient_status_matrix(status_by_level: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if status_by_level.empty:
        empty = pd.DataFrame(columns=["PERSON_ID"])
        return empty, empty, empty

    matrix = status_by_level.pivot(index="PERSON_ID", columns="qc_level", values="passed").reset_index()
    for level in QC_LEVEL_ORDER:
        if level not in matrix.columns:
            matrix[level] = True
    matrix["final_pass"] = matrix[QC_LEVEL_ORDER].all(axis=1)
    failed_levels = []
    for _, row in matrix.iterrows():
        failed = [level for level in QC_LEVEL_ORDER if not bool(row[level])]
        failed_levels.append(",".join(failed))
    matrix["failed_levels"] = failed_levels

    passed = matrix[matrix["final_pass"]][["PERSON_ID"]].copy()
    failed = matrix[~matrix["final_pass"]][["PERSON_ID", "failed_levels"]].copy()
    return matrix, passed, failed


def build_all_metrics(issues_df: pd.DataFrame, all_patients: list[str]) -> dict[str, pd.DataFrame]:
    if issues_df.empty:
        issues_df = _empty_issues_df()
    status_by_level = build_patient_status_by_level(issues_df, all_patients)
    metrics_by_level = build_metrics_by_level(status_by_level, issues_df)
    metrics_by_check = build_metrics_by_check(issues_df)
    status_by_check = build_patient_status_by_check(issues_df, all_patients)
    matrix, passed, failed = build_patient_status_matrix(status_by_level)
    return {
        "patient_status_by_level": status_by_level,
        "metrics_by_level": metrics_by_level,
        "metrics_by_check": metrics_by_check,
        "patient_status_by_check": status_by_check,
        "patient_status_matrix": matrix,
        "passed_patients_final": passed,
        "failed_patients_final": failed,
    }
