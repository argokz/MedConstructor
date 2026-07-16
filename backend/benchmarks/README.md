# Benchmark artifacts

This directory contains benchmark seeds, reproducible outputs, and
de-identified validation artifacts used by the platform research interface.

**The PostgreSQL database (`validation_ratings`) is the single source of truth.**
The curated files below are the exact, database-consistent exports used in the
manuscript. See `SUPPLEMENTARY_INDEX.md` for the full index and the
database-authoritative headline numbers.

## Human expert validation (two-stage, real blinded cardiologists)

- Pilot calibration — cohort `cardiology_pilot`: 36 variants, 3 experts, 108 ratings.
- Primary validation (main results) — cohort `cardiology_pilot_v2`: 73 variants, 5 experts, 365 ratings.

Public artifacts:

- `cardiology_expert_ratings_anonymized.csv`: raw blinded ratings, one row per
  (variant, expert); experts anonymised `E1`..`E5`; includes the deterministic
  model composite and sub-metrics. Both cohorts.
- `cardiology_agreement_summary.csv`: agreement of the automated composite with
  the mean expert rating, per cohort, plus inter-rater reliability and the
  safety ROC-AUC.
- `cardiology_pattern_level_primary.csv`: automated vs mean expert score by
  controlled error pattern (primary cohort).
- `cardiology_baseline_ablation_primary.csv`: Spearman of the composite vs
  single-metric baselines (primary cohort).
- `cardiology_protocol_grounding.csv`: provenance for the 12 cardiology cases,
  including separate database and source-system identifiers, title, year,
  category, and source URL.

Expert identifiers are cohort-local codes (`E1`, ..., `E5`). No login address,
contact information, signed consent form, or re-identification mapping is
committed.

## Retrieval and graph benchmarks

- `rag_queries*.seed.json`: retrieval test questions and expected sources;
- `rag_research_*`: retrieval outputs and ablation tables;
- `graph_cases*.seed.json`: controlled graph cases and error patterns;
- `graph_research_*`: evaluator outputs (evaluator v4.3, 160 controlled variants);
- `graph_reference_quality_latest.csv`: reference-graph quality audit;
- `benchmark_problems_latest.csv`: per-case reference-audit findings.

Generated `latest` files should be reproducible from the committed seeds and the
versioned scripts in `backend/scripts`. Do not overwrite the primary
human-rating exports with synthetic or demo data.
