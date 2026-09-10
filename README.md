# RECIST_QC_Pipeline
A modular, config-driven quality-control (QC) pipeline for RECIST-based oncology imaging data. It validates task_details (lesion-level) and RECIST_SUMMARY (timepoint-level) CSV exports against schema, RECIST rules, and longitudinal consistency checks, then produces structured issue logs and pass/fail metrics per patient.
