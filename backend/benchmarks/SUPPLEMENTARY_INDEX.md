# Supplementary / research data index

**The PostgreSQL database (`validation_ratings`) is the single source of truth.**
Each cardiologist scored independently and blinded. The files below are the
exact, database-consistent exports used in the manuscript. Earlier ad-hoc
`cardiology_real_*` CSV/JSON exports diverged from the database and have been
removed; regenerate from the database with `backend/scripts/` if needed.

## Expert validation (two-stage, real blinded cardiologists)

- **Pilot calibration** — cohort `cardiology_pilot`: 36 variants, 3 experts, 108 ratings.
- **Primary validation** (main results) — cohort `cardiology_pilot_v2`: 73 variants, 5 experts, 365 ratings.

| File | Content |
|------|---------|
| `cardiology_expert_ratings_anonymized.csv` | Raw blinded ratings, one row per (variant, expert); experts anonymised E1–E5; includes deterministic model composite and sub-metrics. Both cohorts. |
| `cardiology_agreement_summary.csv` | Agreement of the automated composite with the mean expert rating, per cohort, plus inter-rater reliability and the safety ROC-AUC. |
| `cardiology_pattern_level_primary.csv` | Automated vs mean expert score by controlled error pattern (primary cohort). |
| `cardiology_baseline_ablation_primary.csv` | Spearman of composite vs single-metric baselines (primary cohort). |

## Database-authoritative headline numbers

**Primary (5 experts, 73 variants):** Pearson r = 0.7533 (95% CI 0.6244–0.8467);
Spearman ρ = 0.7169 (0.5562–0.8235); Kendall τa = 0.5186; MAE = 0.2483;
RMSE = 0.2744; bias = +0.2413. Inter-rater: mean pairwise Spearman = 0.7560,
ICC(2,1) = 0.683, ICC(2,k) = 0.915, Krippendorff's α = 0.677. Safety ROC-AUC = 0.795.

**Pilot (3 experts, 36 variants):** Pearson 0.8117, Spearman 0.8047, MAE 0.1269,
bias +0.1008, ICC(2,k) 0.612.

## Other benchmark artifacts (unchanged, consistent with the paper)

`rag_research_results_latest.csv`, `rag_research_ablation_results_latest.csv`
(RAG retrieval / ablation, 50 questions); `graph_research_results_latest.csv`
(160 controlled variants, evaluator v4.3, mean composite 0.6471);
`graph_reference_quality_latest.csv` (20 reference graphs);
`cardiology_protocol_grounding.csv` (Table 3 protocol mapping).

Evaluation algorithm version: `4.3.0-reference-quality-calibrated`.
