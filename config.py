"""Configuration for the RECIST QC pipeline.

The values here are intentionally centralized so SOP-specific changes do not
require editing the QC modules themselves.
"""

TASK_REQUIRED_COLUMNS = [
    "PERSON_ID",
    "StudyUID",
    "SeriesUID",
    "Study_date",
    "Lesion type",
    "InstanceUID",
    "Diameter",
    "Location",
    "Lesion_pixel_cooordinate",
    "Laterality",
    "Imaging_Method",
    "Anatomical_Region",
    "Lesion_id",
    "Other_location",
    "Lesion physical coordinate",
    "Lobe",
    "Orientation",
    "Station",
    "NL_Tumor_state",
    "NE_Reason",
    "Comments",
]

SUMMARY_REQUIRED_COLUMNS = [
    "PERSON_ID",
    "Study_date",
    "SERIES_TYPE",
    "SOD",
    "NADIR",
    "TL_OVERALL_RESPONSE",
    "TL_NE_Reason",
    "NTL_OVERALL_RESPONSE",
    "NTL_NE_Reason",
    "NL_OVERALL_RESPONSE",
    "NL_NE_Reason",
    "OVERALL_RESPONSE",
    "Remarks",
    "LRF",
    "LRF_Lesions_List",
    "DF",
    "DF_Lesions_List",
    "Anatomical_location_of_the_PoF",
]



TASK_COLUMN_ALIASES = {
    "StudyUID": ["study_id", "StudyUID"],
    "SeriesUID": ["series_id", "SeriesUID"],
    "Study_date": ["StudyDate", "Study_date,", "Study Date", "STUDY_DATE"],
    "Lesion type": ["lesion_type", "Lesion_type"],
    "Lesion_pixel_cooordinate": [
        "Lesion_pixel_coordinate",
        "Lesion pixel coordinate",
        "Lesion_pixel_cooordinate",
    ],
    "Lesion physical coordinate": [
        "Lesion_physical_coordinate",
        "Lesoin physical coordinate",
        "Lesion physical coordinate",
    ],
    "Other_location": ["LOCATION-OTHER", "Other Location", "Other_location"],
}



SUMMARY_COLUMN_ALIASES = {
    "Study_date": ["Study_date,", "Study Date", "STUDY_DATE"],
    "OVERALL_RESPONSE": ["Overall Response", "Overall_Response", "OVERALL_RESPONSE"],
}

QC_LEVEL_ORDER = [
    "01_SCHEMA_AND_INPUTS",
    "02_NORMALIZATION",
    "03_BASELINE_ELIGIBILITY",
    "04_LESION_SELECTION_RULES",
    "05_LONGITUDINAL_CONSISTENCY",
   # "06_RECIST_CALCULATION",
    "07_PROGRESSION_DF_LRF",
    "08_CRT_TIMING",
    "09_CHRONOLOGY",
    "10_TIMEPOINT_UNIQUENESS",
    "11_NE_VALIDATION",
    "12_LESION_FORMAT",
    "13_LESION_LOCATION"
]

BLOCKING_SEVERITIES = {"ERROR"}

MAX_TOTAL_TARGET_LESIONS = 5
MAX_TARGET_LESIONS_PER_ORGAN = 2

# RECIST-like thresholds. Adjust here if the SOP uses strict > rather than >=.
NON_NODAL_TARGET_MIN_MM = 10.0
NODAL_TARGET_SHORT_AXIS_MIN_MM = 15.0
NODAL_PATHOLOGIC_MIN_MM = 10.0
BASELINE_CECT_WINDOW_DAYS = 28

VALID_LESION_TYPES = {"TL", "NTL", "NL"}
VALID_LATERALITY = {"RIGHT", "LEFT", "BILATERAL", "NA", ""}
VALID_ORIENTATION = {
    "SUPERIOR",
    "INFERIOR",
    "ANTERIOR",
    "POSTERIOR",
    "MEDIAL",
    "LATERAL",
    "NA",
    "",
}
VALID_NL_TUMOR_STATE = {"EQUIVOCAL", "UNEQUIVOCAL", "NA", ""}
VALID_YES_NO_NA = {"YES", "NO", "NA", ""}
VALID_TL_RESPONSES = {"CR", "PR", "SD", "PD", "NE", "NA", "BASELINE" ,""}
VALID_NTL_RESPONSES = {
    "CR",
    "PR",   # allowed leniently because the shared table included it
    "SD",   # allowed leniently because the shared table included it
    "PD",
    "NE",
    "NON-CR/NON-PD",
    "NON CR/NON PD",
    "NON-CR NON-PD",
    "NON CR NON PD",
    "NA",
    'NN',
    "",
}
# Column description says new lesion response should be Yes/No/NE/NA.
VALID_NL_RESPONSES = {"YES", "NO", "NE", "NA", ""}
VALID_OVERALL_RESPONSES = {"CR", "PR", "SD", "PD", "NE", "NA", ""}

THORAX_LOCATION_KEYWORDS = {
    "CHEST",
    "THORAX",
    "LUNG",
    "RUL",
    "RML",
    "RLL",
    "LUL",
    "LLL",
    "RIGHT UPPER LOBE",
    "RIGHT MIDDLE LOBE",
    "RIGHT LOWER LOBE",
    "LEFT UPPER LOBE",
    "LEFT LOWER LOBE",
    "MEDIASTINUM",
    "MEDIASTINAL",
    "HILAR",
    "RIGHT HILAR",
    "LEFT HILAR",
    "SUBCARINAL",
    "SUPRACLAVICULAR",
    "PLEURA",
    "CHEST WALL",
}

NOT_THORAX_LOCATION_KEYWORDS = {
    "BRAIN",
    "LIVER",
    "ADRENAL",
    "BONE",
    "KIDNEY",
    "SPLEEN",
    "ABDOMEN",
    "PELVIS",
    "PERITONEUM",
    "RETROPERITONEAL",
    "DISTANT",
}

NODE_KEYWORDS = {
    "NODE",
    "LYMPH NODE",
    "LN",
    "MEDIASTINAL",
    
    "SUBCARINAL",
    "SUPRACLAVICULAR",
}
