"""Normalization and derived-field logic.

This module is the first true implementation layer after raw CSV ingestion.
Its job is to standardize column names, parse values, and add derived flags that
QC modules can reuse without duplicating business logic.
"""

from __future__ import annotations

import re
import pandas as pd

from .config import (
    TASK_COLUMN_ALIASES,
    SUMMARY_COLUMN_ALIASES,
    THORAX_LOCATION_KEYWORDS,
    NOT_THORAX_LOCATION_KEYWORDS,
    NODE_KEYWORDS,
)


def txt(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm(value) -> str:
    return txt(value).upper()


def compact(value) -> str:
    return re.sub(r"[\s_\-]+", "", norm(value))


def is_blank_or_na(value) -> bool:
    return norm(value) in {"", "NA", "N/A", "NULL", "NONE", "NAN"}


def is_yes(value) -> bool:
    return norm(value) in {"YES", "Y", "TRUE", "1"}


def is_no(value) -> bool:
    return norm(value) in {"NO", "N", "FALSE", "0"}


def to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date

def to_number(series: pd.Series) -> pd.Series:
    # First, convert to numbers (this turns text into NaN)
    converted = pd.to_numeric(series, errors="coerce")
    
    # Identify exactly where the original value was "NE"
    is_ne = series.astype(str).str.strip().str.upper() == "NE"
    
    # If "NE" exists, change the column to 'object' type so it can hold both numbers and strings
    if is_ne.any():
        converted = converted.astype(object)
        converted[is_ne] = "NE"
        
    return converted



def parse_lesion_list(value) -> list[str]:
    if is_blank_or_na(value):
        return []
    parts = re.split(r"[,;|]+", txt(value))
    return [norm(part) for part in parts if not is_blank_or_na(part)]





def canonicalize_columns(df: pd.DataFrame, aliases: dict[str, list[str]]) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    rename_map = {}
    for canonical, options in aliases.items():
        if canonical in df.columns:
            continue
        for option in options:
            if option in df.columns:
                rename_map[option] = canonical
                break
    return df.rename(columns=rename_map)


def is_valid_station(value) -> bool:
    if is_blank_or_na(value):
        return True
    s = compact(value)
    return bool(
        re.fullmatch(r"STATION(1|2|3|4|5|6|7|8|9|10|11|12|13|14)", s)
        or re.fullmatch(r"(1|2|3|4|5|6|7|8|9|10|11|12|13|14)", s)
    )


def station_is_populated(value) -> bool:
    return not is_blank_or_na(value) and is_valid_station(value)


def normalize_station(value) -> str:
    if is_blank_or_na(value):
        return "NA"
    s = compact(value)
    m = re.fullmatch(r"STATION(1|2|3|4|5|6|7|8|9|10|11|12|13|14)", s)
    if m:
        return f"STATION{m.group(1)}"
    m = re.fullmatch(r"(1|2|3|4|5|6|7|8|9|10|11|12|13|14)", s)
    if m:
        return f"STATION{m.group(1)}"
    return s


def is_node_lesion(row: pd.Series) -> bool:
    # Important: Orientation is directional; Station is lymph-node station.
    location_text = " ".join(
        [norm(row.get("Location", "")), norm(row.get("Other_location", ""))]
    )
    if any(keyword in location_text for keyword in NODE_KEYWORDS):
        return True
    return station_is_populated(row.get("Station", ""))


def classify_thorax_status(row: pd.Series) -> str:
    location_text = " ".join(
        [
            norm(row.get("Location", "")),
            norm(row.get("Other_location", "")),
            norm(row.get("Lobe", "")),
            norm(row.get("Station", "")),
        ]
    )
    region_text = norm(row.get("Anatomical_Region", ""))

    if any(keyword in location_text for keyword in NOT_THORAX_LOCATION_KEYWORDS):
        return "NOT_THORAX"
    if any(keyword in location_text for keyword in THORAX_LOCATION_KEYWORDS):
        return "THORAX"
    if station_is_populated(row.get("Station", "")):
        return "THORAX"
    if "CHEST" in region_text or "THORAX" in region_text:
        return "THORAX"
    if any(keyword in region_text for keyword in NOT_THORAX_LOCATION_KEYWORDS):
        return "NOT_THORAX"
    return "UNKNOWN"


def get_organ_group(row: pd.Series) -> str:
    location_text = " ".join(
        [
            norm(row.get("Location", "")),
            norm(row.get("Other_location", "")),
            norm(row.get("Lobe", "")),
            norm(row.get("Station", "")),
        ]
    )
    if station_is_populated(row.get("Station", "")):
        return "THORACIC_LYMPH_NODES"
    if any(k in location_text for k in ["MEDIASTINAL",  "SUBCARINAL", "SUPRACLAVICULAR", "LYMPH NODE", "NODE", "LN"]):
        return "THORACIC_LYMPH_NODES"
    if any(k in location_text for k in ["RUL", "RML", "RLL", "LUL", "LLL", "LUNG", "LOBE", "RIGHT UPPER", "RIGHT MIDDLE", "RIGHT LOWER", "LEFT UPPER", "LEFT LOWER"]):
        return "LUNG"
    if "PLEURA" in location_text:
        return "PLEURA"
    if "CHEST WALL" in location_text:
        return "CHEST_WALL"
    if "LIVER" in location_text:
        return "LIVER"
    if "ADRENAL" in location_text:
        return "ADRENAL"
    if "BONE" in location_text:
        return "BONE"
    if "BRAIN" in location_text:
        return "BRAIN"
    location = norm(row.get("Location", ""))
    return location if not is_blank_or_na(location) else "UNKNOWN"


def is_lung_lesion(row: pd.Series) -> bool:
    return get_organ_group(row) == "LUNG"


def is_cect_row(row: pd.Series) -> bool:
    
    method = norm(row.get("Imaging_Method", ""))
    
    
    if method == "CHEST W CONTRAST":
        return True
    if method in ["CHEST W/O CONTRAST", "OTHERS", "CT FDG", ""]:
        return False
        
   
    no_contrast = [
        "W/O CONTRAST", "WITHOUT CONTRAST", "WO CONTRAST", 
        "NON-CONTRAST", "NON CONTRAST", "NO CONTRAST"
    ]
    if any(pattern in method for pattern in no_contrast):
        return False
        
    contrast = [
        "W CONTRAST", "WITH CONTRAST", "CONTRAST", "CECT", "ENHANCED"
    ]
    return any(pattern in method for pattern in contrast)


def prepare_task(task: pd.DataFrame) -> pd.DataFrame:
    task = canonicalize_columns(task, TASK_COLUMN_ALIASES)
    task["PERSON_ID"] = task["PERSON_ID"].astype(str).str.strip()
    task["Study_date"] = to_date(task["Study_date"])
    task["Diameter"] = to_number(task["Diameter"])

    task["Lesion_type_norm"] = task["Lesion type"].apply(norm)
    task["Lesion_id_norm"] = task["Lesion_id"].apply(norm)
    task["Laterality_norm"] = task["Laterality"].apply(norm)
    task["Orientation_norm"] = task["Orientation"].apply(norm)
    task["Station_norm"] = task["Station"].apply(normalize_station)
    task["NL_Tumor_state_norm"] = task["NL_Tumor_state"].apply(norm)
    task["is_TL"] = task["Lesion_type_norm"] == "TL"
    task["is_NTL"] = task["Lesion_type_norm"] == "NTL"
    task["is_NL"] = task["Lesion_type_norm"] == "NL"
    task["is_node"] = task.apply(is_node_lesion, axis=1)
    task["thorax_class"] = task.apply(classify_thorax_status, axis=1)
    task["organ_group"] = task.apply(get_organ_group, axis=1)
    task["is_CECT"] = task.apply(is_cect_row, axis=1)
    return task


def normalize_ntl_response(value) -> str:
    value = norm(value)
    no_space = value.replace(" ", "").replace("_", "-")
    if no_space in {"NON-CR/NON-PD", "NONCR/NONPD", "NON-CRNON-PD"}:
        return "NON-CR/NON-PD"
    return value


def prepare_summary(summary: pd.DataFrame) -> pd.DataFrame:
    summary = canonicalize_columns(summary, SUMMARY_COLUMN_ALIASES)
    summary["PERSON_ID"] = summary["PERSON_ID"].astype(str).str.strip()
    summary["Study_date"] = to_date(summary["Study_date"])
    summary["SERIES_TYPE_norm"] = summary["SERIES_TYPE"].apply(compact)
    summary["TL_RESPONSE_norm"] = summary["TL_OVERALL_RESPONSE"].apply(norm)
    summary["NTL_RESPONSE_norm"] = summary["NTL_OVERALL_RESPONSE"].apply(normalize_ntl_response)
    summary["NL_RESPONSE_norm"] = summary["NL_OVERALL_RESPONSE"].apply(norm)
    summary["OVERALL_RESPONSE_norm"] = summary["OVERALL_RESPONSE"].apply(norm)
    summary["LRF_norm"] = summary["LRF"].apply(norm)
    summary["DF_norm"] = summary["DF"].apply(norm)
    summary["SOD"] = to_number(summary["SOD"])
    summary["NADIR"] = to_number(summary["NADIR"])
    return summary


def prepare_metadata(metadata: pd.DataFrame | None) -> pd.DataFrame | None:
    if metadata is None:
        return None
    metadata = metadata.copy()
    metadata.columns = [c.strip() for c in metadata.columns]
    metadata["PERSON_ID"] = metadata["PERSON_ID"].astype(str).str.strip()
    for col in ["BASELINE_REFERENCE_DATE", "CRT_END_DATE", 'CRT_START_DATE']:
        if col in metadata.columns:
            metadata[col] = to_date(metadata[col])
    return metadata


def prepare_image_manifest(image_manifest: pd.DataFrame | None) -> pd.DataFrame | None:
    if image_manifest is None:
        return None
        
    image_manifest = image_manifest.copy()
    
    # 1. Apply the aliases here just like we did for task and summary!
    # (We can reuse SUMMARY_COLUMN_ALIASES since it contains the Study_date mappings)
    image_manifest = canonicalize_columns(image_manifest, SUMMARY_COLUMN_ALIASES)
    
    image_manifest.columns = [c.strip() for c in image_manifest.columns]
    
    if "PERSON_ID" in image_manifest.columns:
        image_manifest["PERSON_ID"] = image_manifest["PERSON_ID"].astype(str).str.strip()
        
    if "Study_date" in image_manifest.columns:
        image_manifest["StudyDate"] = to_date(image_manifest["StudyDate"])
        
    if "image_count" in image_manifest.columns:
        image_manifest["image_count"] = to_number(image_manifest["image_count"])
        
    return image_manifest

def prepare_image_manifest(image_manifest: pd.DataFrame | None) -> pd.DataFrame | None:
    if image_manifest is None:
        return None
    image_manifest = image_manifest.copy()
    image_manifest.columns = [c.strip() for c in image_manifest.columns]
    image_manifest["PERSON_ID"] = image_manifest["PERSON_ID"].astype(str).str.strip()
    image_manifest["StudyDate"] = to_date(image_manifest["StudyDate"])
    image_manifest["image_count"] = to_number(image_manifest["image_count"])
    return image_manifest
