# Research validation and reproducibility

## Scope

MedConstructor is evaluated as an educational technology and scoring
system. The current evidence supports technical feasibility and scoring
validity on controlled graph variants. It does not establish improved learning
outcomes or clinical effectiveness.

## Protocol grounding

Clinical tasks and candidate reference graphs are grounded in protocol records
stored in the platform knowledge base. Public research artifacts retain source
protocol identifiers, titles, years, categories, and relevant sections where
available. Protocol texts are not redistributed when source licensing does not
permit redistribution.

For the cardiology benchmark, `cardiology_protocol_grounding.csv` separates the
internal database primary key from the source record identifier. Scientific
tables must use the latter when reporting a protocol ID.

## Model boundaries

- GPT-5.1: schema-constrained generation and validation assistance.
- `text-embedding-3-small`: retrieval and semantic concept matching.
- Evaluation algorithm v4.3: deterministic metric aggregation, penalties, and
  safety caps.
- Teacher/clinical expert: final reference-graph approval and publication.

The language model does not directly assign the reported automated graph score.

## Benchmark layers

1. RAG retrieval benchmark: 50 protocol-grounded questions.
2. Controlled graph benchmark: 20 reference graphs and 160 predefined
   student-like variants covering expected error patterns.
3. Cardiology pilot calibration: 3 experts, 36 variants, 108 ratings.
4. Primary cardiology validation: 5 experts, 73 variants, 365 blinded ratings
   across 12 protocol-grounded clinical tasks.

In the primary validation, all five experts rated the same 73 variants on a
0-100 scale without seeing the automated score, expected error pattern, or
system recommendation. Public exports contain pseudonymous cohort-local expert
codes only.

## Reported primary indicators

- Pearson correlation with mean expert rating: 0.7533 (95% CI 0.6244-0.8467).
- Spearman rank correlation: 0.7169 (95% CI 0.5562-0.8235).
- Mean absolute error on the normalized 0-1 scale: 0.2483.
- Mean model-minus-expert bias: +0.2413.
- Mean pairwise inter-rater Spearman correlation: 0.7560; ICC(2,k) = 0.915;
  Krippendorff's alpha = 0.677.
- Safety ROC-AUC (composite vs unsafe-flagged variants): 0.795.

All values are computed directly from the platform database
(`validation_ratings`), the single source of truth.

The positive bias means the evaluator was more lenient than the expert panel on
average. Results should be read together with pattern-level discrepancies,
especially unsafe extra actions, missing critical actions, and incomplete
diagnostic reasoning chains.

## Artifact classes

- `cardiology_expert_ratings_anonymized.csv`: de-identified long-format human
  expert ratings (both cohorts; experts `E1`..`E5`).
- `cardiology_agreement_summary.csv`: automated-vs-expert agreement, inter-rater
  reliability, and the safety ROC-AUC, per cohort.
- `cardiology_pattern_level_primary.csv`: automated vs mean expert score by
  controlled error pattern (primary cohort).
- `cardiology_baseline_ablation_primary.csv`: composite vs single-metric
  baseline comparison (primary cohort).
- `rag_research_*` and `graph_research_*`: retrieval and graph benchmark outputs.

See [backend/benchmarks/README.md](../backend/benchmarks/README.md) for the
public artifact index.

## Ethics and privacy

The validation used educational graph variants and did not involve patients,
patient-level records, students, learner assessment, or clinical intervention.
Written informed consent was collected from participating cardiology experts.
No signed forms or re-identification mapping belong in this repository.

No formal ethics committee review or exemption determination was obtained
before data collection. This limitation must remain explicit in publications;
an institutional determination should be obtained before submission whenever
required by the target journal or institution.

## Limitations

- controlled student-like variants are not real classroom submissions;
- the primary expert panel contains five cardiologists in one discipline;
- reference graphs require clinical review even after automated validation;
- protocol coverage and currency constrain retrieval and generation quality;
- prospective student and teacher studies remain necessary.
