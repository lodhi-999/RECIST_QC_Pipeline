"""QC checks for lesion pixel coordinates."""

from __future__ import annotations

import pandas as pd
import ast  # <-- ADD THIS IMPORT

from ..issue import issue, QCIssue
from ..normalize import is_blank_or_na

# Define a new QC level for this check
LEVEL = "14_PIXEL_COORDINATES"


def run_pixel_coordinate_qc(task: pd.DataFrame) -> list[QCIssue]:
    """Ensures lesion pixel coordinates have x, y, and z if populated."""
    issues: list[QCIssue] = []
    
    # Check for the column name, accounting for the typo in the raw data (3 'o's)
    coord_col = None
    for col in ["Lesion_pixel_coordinate", "Lesion_pixel_cooordinate"]:
        if col in task.columns:
            coord_col = col
            break
            
    # If neither column exists in the file, exit the check safely
    if not coord_col:
        return issues

    for _, row in task.iterrows():
        pid = row.get("PERSON_ID")
        date = row.get("Study_date")
        lesion_id = row.get("Lesion_id_norm", row.get("Lesion_id"))
        
        coord_val = row.get(coord_col)
        
        # 1. If the value is completely blank or "NA", IGNORE it and move to the next row
        if is_blank_or_na(coord_val):
            continue
            
        # 2. If it is NOT blank, check if it's missing x, y, or z
        incomplete = False
        try:
            # Safely evaluate the string into a real Python list (e.g., "[[1,2,3]]" -> [[1,2,3]])
            parsed_coords = ast.literal_eval(coord_val) if isinstance(coord_val, str) else coord_val
            
            if not isinstance(parsed_coords, list) or len(parsed_coords) == 0:
                incomplete = True
            else:
                for point in parsed_coords:
                    # Check if each point is a list and has exactly 3 elements (x, y, z)
                    if not isinstance(point, list) or len(point) != 3:
                        incomplete = True
                        break
                    
                    # Ensure none of the individual x, y, z values inside are empty or None
                    if any(val is None or str(val).strip() == "" for val in point):
                        incomplete = True
                        break
                        
        except (ValueError, SyntaxError):
            # If it fails to parse (e.g., malformed brackets like "[[179, 287,]"), flag it
            incomplete = True
            
        if incomplete:
            issues.append(
                issue(
                    LEVEL,
                    "incomplete_pixel_coordinates",
                    "WARNING",
                    person_id=pid,
                    study_date=date,
                    lesion_id=lesion_id,
                    message="Lesion pixel coordinates are partially missing (x, y, or z is absent or malformed)",
                    expected="Complete coordinate array with 3 values per point (e.g., [[x, y, z], [x, y, z]])",
                    actual=str(coord_val)
                )
            )
            
    return issues