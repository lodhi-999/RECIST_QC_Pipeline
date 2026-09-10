# RECIST QC Pipeline

A modular, config-driven quality-control (QC) pipeline for RECIST-based oncology imaging data. It validates `task_details` (lesion-level) and `RECIST_SUMMARY` (timepoint-level) CSV exports against schema, RECIST rules, and longitudinal consistency checks, then produces structured issue logs and pass/fail metrics per patient.

> Built for stage III NSCLC / CCRT-style RECIST review workflows, but the rule set is centralized in `config.py` so it can be adapted to other SOPs.

## Features

- **Schema validation** — required columns, valid label sets, missing core values, duplicate records, date alignment between files, zero-image checks.
- **Normalization layer** — canonicalizes column aliases, parses dates/numbers (including `"NE"` as a valid non-numeric diameter/SOD value), and derives fields like lymph-node status, thorax classification, and organ grouping.
- **RECIST rule checks** — baseline eligibility, target-lesion count/size thresholds, nodal short-axis rules, lesion ID formatting, laterality/station applicability.
- **Longitudinal consistency** — baseline lesions must persist at follow-up, chronological ordering of timepoints, no unexpected new TL/NTL appearing after baseline.
- **Progression & timing checks** — PD requires LRF/DF justification, CRT start/end date windows, NE-response justification and required NE reasons.
- **Structured outputs** — a single tidy issue log plus rollup metrics and a per-patient pass/fail matrix across all QC levels.

## Package Structure

```
.
├── __init__.py              # package version
├── cli.py                   # command-line entry point
├── config.py                # centralized SOP config: columns, aliases, thresholds, QC level order
├── engine.py                # orchestrates the full pipeline (QCContext, run_pipeline)
├── io.py                    # CSV read/write helpers
├── issue.py                 # QCIssue dataclass + issue() factory
├── normalize.py             # column canonicalization, parsing, derived flags
├── metrics.py                # pass/fail metrics and patient status matrix
└── QC_Modules/
    ├── __init__.py
    ├── schema.py             # 01_SCHEMA_AND_INPUTS, 02_NORMALIZATION
    ├── baseline.py           # 03_BASELINE_ELIGIBILITY
    ├── lesion.py             # 04_LESION_SELECTION_RULES
    ├── longitudinal.py       # 05_LONGITUDINAL_CONSISTENCY
    ├── recist_calc.py        # 06_RECIST_CALCULATION (SOD/NADIR, currently disabled — see Known Issues)
    ├── progression.py        # 07_PROGRESSION_DF_LRF
    ├── crt_timing.py         # 08_CRT_TIMING
    ├── chronology.py         # 09_CHRONOLOGY
    ├── timepoint_uniqueness.py  # 10_TIMEPOINT_UNIQUENESS
    ├── ne_validation.py      # 11_NE_VALIDATION
    ├── lesion_format.py      # 12_LESION_FORMAT
    ├── lesion_location.py    # 13_LESION_LOCATION
    └── pixel_coordinates.py  # 14_PIXEL_COORDINATES (not currently wired into engine.py)
```

## Installation

```bash
git clone <this-repo-url>
cd <this-repo>
pip install pandas numpy
```

No other third-party dependencies are required.

## Input Files

Place these in your `--input-dir` (default: `sample_data/`):

| File | Required? | Purpose |
|---|---|---|
| `TASK_DETAILS_V13.csv` | Yes | Lesion-level records (one row per lesion per timepoint) |
| `RECIST_SUMMARY_V13.csv` | Yes | Patient/timepoint-level RECIST summary rows |
| `final_mayo_cohort.csv` | Optional | Patient metadata (`BASELINE_REFERENCE_DATE`, `CRT_START_DATE`, `CRT_END_DATE`) used for timing checks |
| `image_manifest.csv` | Optional | Per-timepoint image counts, used for the zero-images check |

CSVs are read with `keep_default_na=False`, so blank cells are treated as empty strings rather than `NaN` until the normalization layer processes them. Column names can vary slightly — see `TASK_COLUMN_ALIASES` / `SUMMARY_COLUMN_ALIASES` in `config.py` for accepted aliases (e.g. `study_id` → `StudyUID`, `StudyDate` → `Study_date`).

### Required columns

**`TASK_DETAILS_V13.csv`**: `PERSON_ID`, `StudyUID`, `SeriesUID`, `Study_date`, `Lesion type`, `InstanceUID`, `Diameter`, `Location`, `Lesion_pixel_cooordinate`, `Laterality`, `Imaging_Method`, `Anatomical_Region`, `Lesion_id`, `Other_location`, `Lesion physical coordinate`, `Lobe`, `Orientation`, `Station`, `NL_Tumor_state`, `NE_Reason`, `Comments`

**`RECIST_SUMMARY_V13.csv`**: `PERSON_ID`, `Study_date`, `SERIES_TYPE`, `SOD`, `NADIR`, `TL_OVERALL_RESPONSE`, `TL_NE_Reason`, `NTL_OVERALL_RESPONSE`, `NTL_NE_Reason`, `NL_OVERALL_RESPONSE`, `NL_NE_Reason`, `OVERALL_RESPONSE`, `Remarks`, `LRF`, `LRF_Lesions_List`, `DF`, `DF_Lesions_List`, `Anatomical_location_of_the_PoF`

If any required column is missing, the pipeline stops after writing a `qc_issues.csv` containing only the missing-column errors — no further checks are run.

## Usage

```bash
python -m <package_name>.cli --input-dir sample_data --output-dir qc_outputs
```

Or from Python:

```python
from <package_name>.engine import run_pipeline

outputs = run_pipeline("sample_data", "qc_outputs")
for name, path in outputs.items():
    print(name, path)
```

Replace `<package_name>` with whatever this package is imported as in your project (the `cli.py` entry point uses a relative import, so it must be run as part of an installed/importable package).

## Output Files

Written to `--output-dir` (default: `qc_outputs/`):

| File | Description |
|---|---|
| `qc_issues.csv` | Full flat log of every QC issue: level, check name, severity, patient/date/lesion context, message, expected vs. actual |
| `qc_metrics_by_level.csv` | Pass/fail counts and pass rate per QC level |
| `qc_metrics_by_check.csv` | Issue counts and affected-patient counts per individual check |
| `qc_patient_status_by_level.csv` | Per-patient pass/fail flag for each QC level |
| `qc_patient_status_by_check.csv` | Per-patient pass/fail flag for each individual check |
| `qc_patient_status_matrix.csv` | Wide matrix: one row per patient, one column per QC level, plus `final_pass` and `failed_levels` |
| `passed_patients_final.csv` | Patients that passed every QC level |
| `failed_patients_final.csv` | Patients that failed at least one QC level, with the list of failed levels |
| `computed_sod_nadir.csv` | Recomputed SOD/NADIR per timepoint (empty unless `recist_calc` is re-enabled) |

A patient/level/check is marked **failed** only when it has at least one issue of a severity in `BLOCKING_SEVERITIES` (currently `{"ERROR"}`); `WARNING` and `INFO` issues are informational and don't block pass/fail status. Issues with no `PERSON_ID` (global/file-level issues) are treated as blocking for every patient at that level.

## QC Levels

| Level | Module | Focus |
|---|---|---|
| `01_SCHEMA_AND_INPUTS` | `schema.py` | Required columns, missing core values, duplicates, date alignment, zero images |
| `02_NORMALIZATION` | `schema.py` | Valid label sets for lesion type, laterality, orientation, station, responses |
| `03_BASELINE_ELIGIBILITY` | `baseline.py` | Baseline SOD presence, CECT/thorax relevance, target-lesion count limits |
| `04_LESION_SELECTION_RULES` | `lesion.py` | Lesion ID/type consistency, laterality/station applicability, diameter thresholds |
| `05_LONGITUDINAL_CONSISTENCY` | `longitudinal.py` | Baseline TLs persist at follow-up, follow-ups occur after CRT end |
| `06_RECIST_CALCULATION` | `recist_calc.py` | SOD/NADIR recomputation, NE-reason checks *(disabled by default — see below)* |
| `07_PROGRESSION_DF_LRF` | `progression.py` | PD requires LRF/DF, LRF/DF lesion lists resolve to real lesions |
| `08_CRT_TIMING` | `crt_timing.py` | Baseline within 90 days of CRT start |
| `09_CHRONOLOGY` | `chronology.py` | No skipped/reversed timepoints, no unexpected new TL/NTL at follow-up |
| `10_TIMEPOINT_UNIQUENESS` | `timepoint_uniqueness.py` | One record per patient/timepoint (see module for details) |
| `11_NE_VALIDATION` | `ne_validation.py` | NE responses require NE SOD and at least one NE-diameter TL |
| `12_LESION_FORMAT` | `lesion_format.py` | Lesion IDs end in a number (e.g. `TL1`, `NTL2`) |
| `13_LESION_LOCATION` | `lesion_location.py` | Location or Station required at baseline / first NL mention |
| `14_PIXEL_COORDINATES` | `pixel_coordinates.py` | Pixel coordinate arrays are complete `[x, y, z]` triples *(not wired into `engine.py` yet)* |

## Configuration

All SOP-specific values live in `config.py` so the QC modules themselves stay generic:

- `TASK_REQUIRED_COLUMNS` / `SUMMARY_REQUIRED_COLUMNS` — required schema
- `TASK_COLUMN_ALIASES` / `SUMMARY_COLUMN_ALIASES` — accepted column name variants
- `MAX_TOTAL_TARGET_LESIONS`, `MAX_TARGET_LESIONS_PER_ORGAN` — target lesion selection caps (default 5 total / 2 per organ)
- `NON_NODAL_TARGET_MIN_MM`, `NODAL_TARGET_SHORT_AXIS_MIN_MM`, `NODAL_PATHOLOGIC_MIN_MM` — RECIST size thresholds (10mm / 15mm / 10mm)
- `BASELINE_CECT_WINDOW_DAYS` — baseline imaging window (28 days)
- `VALID_*` sets — allowed values for lesion type, laterality, orientation, responses, etc.
- `THORAX_LOCATION_KEYWORDS`, `NOT_THORAX_LOCATION_KEYWORDS`, `NODE_KEYWORDS` — keyword lists used to classify anatomy
- `QC_LEVEL_ORDER` — the level sequence used for reporting and the pass/fail matrix
- `BLOCKING_SEVERITIES` — which severities count as a failure (default `{"ERROR"}`)

## Known Issues / In-Progress Items

- **`06_RECIST_CALCULATION` is disabled.** `recist_calc.run_recist_qc` is imported in `engine.py` but its call is commented out, and the level is commented out of `QC_LEVEL_ORDER` in `config.py`. `ctx.computed_sod_nadir` is therefore always an empty DataFrame, and `computed_sod_nadir.csv` will be empty until this is re-enabled.
- **`14_PIXEL_COORDINATES` is not called from `engine.py`.** `pixel_coordinates.py` exists and is fully implemented but isn't imported/invoked in the pipeline — pixel coordinate completeness is currently unchecked.
- **Several checks are commented out** in `baseline.py` (CECT/chest-region enforcement), `recist_calc.py` (TL response mismatch, overall response consistency), reflecting rules that were relaxed during development — review before re-enabling.
- `io.py` silently synthesizes `InstanceUID = "SYNTHETIC_UID"` and a null `Lesion physical coordinate` column when they're absent from the input file, which can mask genuinely missing data — check `qc_issues.csv` for `zero_images_uploaded` if this matters for your dataset.
- `timepoint_uniqueness.py` is referenced throughout `engine.py` and this README but wasn't included in the reviewed source — confirm its behavior separately.

## Extending the Pipeline

To add a new QC module:

1. Create `qc_modules/your_check.py` with a `run_your_check_qc(...)` function that returns `list[QCIssue]`, using `issue()` from `issue.py`.
2. Add a new level string to `QC_LEVEL_ORDER` in `config.py`.
3. Import and call your module from `run_pipeline()` in `engine.py`, extending `ctx.issues`.

Because `metrics.py` derives all rollups from the `qc_issues` DataFrame and `QC_LEVEL_ORDER`, no changes to the metrics layer are needed as long as your issues carry the correct `qc_level`.

