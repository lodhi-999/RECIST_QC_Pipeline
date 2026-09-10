"""QC issue model."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import json


def _stringify(value: Any) -> str:
    """Make complex values safe for CSV output."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, default=str, sort_keys=True)
    return str(value)


@dataclass(frozen=True)
class QCIssue:
    qc_level: str
    check_name: str
    severity: str
    PERSON_ID: str | None = None
    Study_date: str | None = None
    SERIES_TYPE: str | None = None
    Lesion_id: str | None = None
    message: str = ""
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> dict[str, str]:
        row = asdict(self)
        for key in ["expected", "actual"]:
            row[key] = _stringify(row.get(key))
        for key, value in row.items():
            if value is None:
                row[key] = ""
        return row


def issue(
    qc_level: str,
    check_name: str,
    severity: str,
    person_id: str | None = None,
    study_date: object | None = None,
    series_type: str | None = None,
    lesion_id: str | None = None,
    message: str = "",
    expected: Any = None,
    actual: Any = None,
) -> QCIssue:
    return QCIssue(
        qc_level=qc_level,
        check_name=check_name,
        severity=severity,
        PERSON_ID=None if person_id is None else str(person_id),
        Study_date="" if study_date is None else str(study_date),
        SERIES_TYPE=series_type,
        Lesion_id=lesion_id,
        message=message,
        expected=expected,
        actual=actual,
    )
