"""Pipeline engine that wires modules together."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
import pandas as pd

from .io import load_inputs, write_dataframe
from .issue import QCIssue, issue
from .normalize import prepare_task, prepare_summary, prepare_metadata, prepare_image_manifest
from .metrics import build_all_metrics
from .qc_modules import schema, baseline, lesion, longitudinal, recist_calc, progression, crt_timing, chronology, timepoint_uniqueness, ne_validation, lesion_format, lesion_location


@dataclass
class QCContext:
    task_raw: pd.DataFrame
    summary_raw: pd.DataFrame
    metadata_raw: pd.DataFrame | None
    image_manifest_raw: pd.DataFrame | None
    task: pd.DataFrame | None = None
    summary: pd.DataFrame | None = None
    metadata: pd.DataFrame | None = None
    image_manifest: pd.DataFrame | None = None
    baseline_dates: dict[str, object] = field(default_factory=dict)
    computed_sod_nadir: pd.DataFrame = field(default_factory=pd.DataFrame)
    issues: list[QCIssue] = field(default_factory=list)


def get_baseline_dates(summary: pd.DataFrame, task: pd.DataFrame, issues: list[QCIssue]) -> dict[str, object]:
    baseline_dates = {}
    baseline_summary = summary[summary["SERIES_TYPE_norm"] == "BASELINE"]

    for pid, rows in baseline_summary.groupby("PERSON_ID"):
        unique_dates = sorted(rows["Study_date"].dropna().unique())
        if len(unique_dates) > 1:
            issues.append(
                issue(
                    "03_BASELINE_ELIGIBILITY",
                    "baseline_identification",
                    "ERROR",
                    person_id=pid,
                    message="Multiple baseline dates found in RECIST_SUMMARY.csv",
                    expected="Exactly one baseline date per patient",
                    actual=unique_dates,
                )
            )
        if len(unique_dates) >= 1:
            baseline_dates[pid] = unique_dates[0]

    # Fallback for patients with task rows but no summary baseline.
    for pid, rows in task.groupby("PERSON_ID"):
        if pid not in baseline_dates:
            fallback_date = rows["Study_date"].min()
            baseline_dates[pid] = fallback_date
            issues.append(
                issue(
                    "03_BASELINE_ELIGIBILITY",
                    "baseline_identification",
                    "ERROR",
                    person_id=pid,
                    study_date=fallback_date,
                    message="No SERIES_TYPE=BASELINE row found; using earliest task_details date as baseline",
                    expected="RECIST_SUMMARY row with SERIES_TYPE=BASELINE",
                    actual="Fallback to earliest Study_date",
                )
            )
    return baseline_dates


def get_all_patients(task: pd.DataFrame | None, summary: pd.DataFrame | None, image_manifest: pd.DataFrame | None) -> list[str]:
    patients = set()
    if task is not None and "PERSON_ID" in task.columns:
        patients.update(task["PERSON_ID"].dropna().astype(str))
    if summary is not None and "PERSON_ID" in summary.columns:
        patients.update(summary["PERSON_ID"].dropna().astype(str))
    if image_manifest is not None and "PERSON_ID" in image_manifest.columns:
        patients.update(image_manifest["PERSON_ID"].dropna().astype(str))
    return sorted(patients)


def run_pipeline(input_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    loaded = load_inputs(input_dir)
    ctx = QCContext(**loaded)

    missing_task, missing_summary = schema.check_required_columns(ctx.task_raw, ctx.summary_raw)
    ctx.issues.extend(missing_task)
    ctx.issues.extend(missing_summary)

    # If required columns are missing, write whatever can be written and stop cleanly.
    if any(i.severity == "ERROR" for i in ctx.issues):
        issues_df = pd.DataFrame([i.to_dict() for i in ctx.issues])
        outputs = {"qc_issues": write_dataframe(issues_df, output_dir, "qc_issues.csv")}
        return outputs

    ctx.task = prepare_task(ctx.task_raw)
    ctx.summary = prepare_summary(ctx.summary_raw)
    ctx.metadata = prepare_metadata(ctx.metadata_raw)
    ctx.image_manifest = prepare_image_manifest(ctx.image_manifest_raw)
    ctx.baseline_dates = get_baseline_dates(ctx.summary, ctx.task, ctx.issues)

    # Module execution: same sequence as the architecture slide.
    ctx.issues.extend(schema.run_schema_qc(ctx.task, ctx.summary, ctx.image_manifest))
    ctx.issues.extend(baseline.run_baseline_qc(ctx.task, ctx.summary, ctx.metadata, ctx.baseline_dates))
    ctx.issues.extend(lesion.run_lesion_qc(ctx.task, ctx.baseline_dates))
    ctx.issues.extend(longitudinal.run_longitudinal_qc(ctx.task, ctx.summary, ctx.metadata, ctx.baseline_dates))
    ctx.issues.extend(chronology.run_chronology_qc(ctx.task, ctx.summary, ctx.baseline_dates))

    ctx.issues.extend(timepoint_uniqueness.run_timepoint_uniqueness_qc(ctx.task, ctx.summary))
    ctx.issues.extend(ne_validation.run_ne_validation_qc(ctx.task, ctx.summary))
    ctx.issues.extend(lesion_format.run_lesion_format_qc(ctx.task))
    ctx.issues.extend(lesion_location.run_lesion_location_qc(ctx.task, ctx.baseline_dates))

    #computed, recist_issues = recist_calc.run_recist_qc(ctx.task, ctx.summary, ctx.baseline_dates)
    #ctx.computed_sod_nadir = computed
    #ctx.issues.extend(recist_issues)
    ctx.issues.extend(crt_timing.run_crt_timing_qc(ctx.summary, ctx.metadata))
    ctx.issues.extend(progression.run_progression_qc(ctx.task, ctx.summary))

    issues_df = pd.DataFrame([i.to_dict() for i in ctx.issues])
    if issues_df.empty:
        issues_df = pd.DataFrame(columns=[
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

    all_patients = get_all_patients(ctx.task, ctx.summary, ctx.image_manifest)
    metrics = build_all_metrics(issues_df, all_patients)

    output_paths = {
        "qc_issues": write_dataframe(issues_df, output_dir, "qc_issues.csv"),
        "qc_metrics_by_level": write_dataframe(metrics["metrics_by_level"], output_dir, "qc_metrics_by_level.csv"),
        "qc_metrics_by_check": write_dataframe(metrics["metrics_by_check"], output_dir, "qc_metrics_by_check.csv"),
        "qc_patient_status_by_level": write_dataframe(metrics["patient_status_by_level"], output_dir, "qc_patient_status_by_level.csv"),
        "qc_patient_status_by_check": write_dataframe(metrics["patient_status_by_check"], output_dir, "qc_patient_status_by_check.csv"),
        "qc_patient_status_matrix": write_dataframe(metrics["patient_status_matrix"], output_dir, "qc_patient_status_matrix.csv"),
        "passed_patients_final": write_dataframe(metrics["passed_patients_final"], output_dir, "passed_patients_final.csv"),
        "failed_patients_final": write_dataframe(metrics["failed_patients_final"], output_dir, "failed_patients_final.csv"),
        "computed_sod_nadir": write_dataframe(ctx.computed_sod_nadir, output_dir, "computed_sod_nadir.csv"),
    }
    return output_paths
