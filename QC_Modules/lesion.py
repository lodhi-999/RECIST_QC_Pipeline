"""Lesion-level selection, ID, laterality, station, and diameter checks."""

from __future__ import annotations

import pandas as pd

from ..config import NON_NODAL_TARGET_MIN_MM, NODAL_TARGET_SHORT_AXIS_MIN_MM, NODAL_PATHOLOGIC_MIN_MM
from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na, norm, station_is_populated, is_lung_lesion

LEVEL = "04_LESION_SELECTION_RULES"


def run_lesion_qc(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    task = task.drop_duplicates(subset=["PERSON_ID", "Study_date", "Lesion_id_norm"])
    issues.extend(_lesion_id_and_type_consistency(task, baseline_dates))
    issues.extend(_laterality_orientation_station_applicability(task))
    issues.extend(_diameter_and_node_rules(task, baseline_dates))
    return issues


def _lesion_id_and_type_consistency(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []


    task = task.drop_duplicates(subset=["PERSON_ID", "Study_date", "Lesion_id_norm"])
    for _, row in task.iterrows():
        pid, date, lesion_type, lesion_id = row["PERSON_ID"], row["Study_date"], row["Lesion_type_norm"], row["Lesion_id_norm"]
        if is_blank_or_na(lesion_id):
            issues.append(issue(LEVEL, "lesion_id_missing", "ERROR", pid, date, message="Lesion_id is missing", expected="Stable ID like TL1/NTL1/NL1", actual=row.get("Lesion_id")))
            continue
        if lesion_type in {"TL", "NTL", "NL"} and not lesion_id.startswith(lesion_type):
            issues.append(issue(LEVEL, "lesion_id_prefix_mismatch", "WARNING", pid, date, lesion_id=lesion_id, message="Lesion_id prefix does not match Lesion type", expected=f"Lesion_id starts with {lesion_type}", actual={"Lesion type": row.get("Lesion type"), "Lesion_id": row.get("Lesion_id")}))
        if date == baseline_dates.get(pid) and lesion_type == "NL":
            issues.append(issue(LEVEL, "new_lesion_at_baseline", "ERROR", pid, date, lesion_id=lesion_id, message="Baseline lesion is marked as NL", expected="Baseline lesions should be TL or NTL", actual=row.get("Lesion type")))
    return issues


def _laterality_orientation_station_applicability(task: pd.DataFrame) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in task.iterrows():
        pid, date, lesion_id = row["PERSON_ID"], row["Study_date"], row["Lesion_id_norm"]
        lung = is_lung_lesion(row)
        node = row["is_node"]
        if lung and is_blank_or_na(row.get("Laterality")):
            issues.append(issue(LEVEL, "lung_laterality_required", "WARNING", pid, date, lesion_id=lesion_id, message="Lung lesion missing Laterality", expected="RIGHT or LEFT", actual=row.get("Laterality")))
        # if not lung and norm(row.get("Laterality")) in {"RIGHT", "LEFT"}:
        #     issues.append(issue(LEVEL, "laterality_on_non_lung_lesion", "INFO", pid, date, lesion_id=lesion_id, message="Laterality populated for non-lung lesion; review if appropriate", expected="NA unless applicable", actual=row.get("Laterality")))
        if node and not station_is_populated(row.get("Station")):
            issues.append(issue(LEVEL, "node_station_required", "WARNING", pid, date, lesion_id=lesion_id, message="Thoracic lymph-node lesion should have Station populated", expected="Station1 to Station14", actual=row.get("Station")))
        if not node and station_is_populated(row.get("Station")):
            issues.append(issue(LEVEL, "station_on_non_node_lesion", "WARNING", pid, date, lesion_id=lesion_id, message="Station populated but lesion does not appear nodal", expected="Station=NA for non-node lesions", actual=row.get("Station")))
    return issues


def _expected_sod_diameter(row: pd.Series):
    if "Length" in row.index and "Width" in row.index:
        length = pd.to_numeric(row.get("Length"), errors="coerce")
        width = pd.to_numeric(row.get("Width"), errors="coerce")
        if not pd.isna(length) and not pd.isna(width):
            return min(length, width) if row.get("is_node") else max(length, width)
    return row.get("Diameter")


def _diameter_and_node_rules(task: pd.DataFrame, baseline_dates: dict[str, object]) -> list[QCIssue]:
    issues: list[QCIssue] = []
    for _, row in task.iterrows():
        pid, date, lesion_id = row["PERSON_ID"], row["Study_date"], row["Lesion_id_norm"]
        diameter = row["Diameter"]
        
        # --- 1. ADD THIS BLOCK TO SAFELY BYPASS "NE" ---
        if str(diameter).strip().upper() == "NE":
            continue

        # --- 2. Existing logic continues as normal below ---
        if pd.isna(diameter):
            issues.append(issue(LEVEL, "diameter_missing_or_invalid", "ERROR", pid, date, lesion_id=lesion_id, message="Diameter missing or non-numeric", expected="Numeric Diameter", actual=row.get("Diameter")))
            continue
        
        if diameter < 0:
            issues.append(issue(LEVEL, "diameter_negative", "ERROR", pid, date, lesion_id=lesion_id, message="Diameter cannot be negative", expected=">= 0", actual=diameter))
        if "Length" in task.columns and "Width" in task.columns:
            expected = _expected_sod_diameter(row)
            if not pd.isna(expected) and abs(float(diameter) - float(expected)) > 0.1:
                issues.append(issue(LEVEL, "diameter_axis_selection", "ERROR", pid, date, lesion_id=lesion_id, message="Diameter does not match expected Length/Width axis rule", expected=expected, actual=diameter))
        if date != baseline_dates.get(pid):
            continue
        if row["is_node"] and row["is_TL"] and diameter < NODAL_TARGET_SHORT_AXIS_MIN_MM:
            issues.append(issue(LEVEL, "baseline_target_node_size", "ERROR", pid, date, lesion_id=lesion_id, message="Baseline target lymph node below required short-axis threshold", expected=f">= {NODAL_TARGET_SHORT_AXIS_MIN_MM} mm", actual=diameter))
        if row["is_node"] and row["is_NTL"] and diameter < NODAL_PATHOLOGIC_MIN_MM:
            issues.append(issue(LEVEL, "baseline_non_target_node_size", "WARNING", pid, date, lesion_id=lesion_id, message="Baseline non-target lymph node below pathologic-node threshold", expected=f">= {NODAL_PATHOLOGIC_MIN_MM} mm", actual=diameter))
        if not row["is_node"] and row["is_TL"] and diameter < NON_NODAL_TARGET_MIN_MM:
            issues.append(issue(LEVEL, "baseline_non_nodal_target_size", "ERROR", pid, date, lesion_id=lesion_id, message="Baseline non-nodal TL below longest-diameter threshold", expected=f">= {NON_NODAL_TARGET_MIN_MM} mm", actual=diameter))
    return issues
