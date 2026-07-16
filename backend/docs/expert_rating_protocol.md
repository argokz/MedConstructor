# Expert Rating Protocol

This protocol is used to validate whether graph-evaluation metrics correlate
with teacher judgement.

## Files

- `benchmarks/graph_expert_ratings.template.csv`: table filled by experts.
- `benchmarks/graph_expert_review_items.jsonl`: blinded review items with the
  reference graph and the student graph.
- `benchmarks/graph_expert_review_key.json`: researcher-only mapping from
  blinded item ids to benchmark cases, expected error patterns, and algorithm
  metrics.
- `benchmarks/graph_expert_correlation_latest.json`: generated correlation
  report after expert scores are filled.

## Blinding

Experts should receive only:

- `graph_expert_ratings.template.csv`;
- `graph_expert_review_items.jsonl`.

They should not receive `graph_expert_review_key.json`, because it contains the
expected error pattern and algorithm score.

## Expert Score

Fill `expert_score_0_100` on a 0-100 scale:

| Score Range | Meaning |
|---:|---|
| 90-100 | Clinically complete, safe, and logically connected solution. |
| 75-89 | Mostly correct solution with minor omissions or ontology errors. |
| 60-74 | Partially correct solution with important but non-catastrophic gaps. |
| 40-59 | Major reasoning defect, missing diagnostic logic, or wrong therapeutic relation. |
| 0-39 | Unsafe action, missing critical action, or clinically unacceptable solution. |

Optional fields:

- `expert_accept`: `yes`/`no` clinical acceptability judgement.
- `expert_comment`: short reason for the grade.

Use at least two independent experts if possible. The analyzer reports
correlation against the mean expert score and pairwise inter-rater agreement.

## Commands

Export the blinded package:

```powershell
.\.venv\Scripts\python.exe scripts\export_graph_expert_ratings.py --benchmark benchmarks\graph_research_latest.json --graph-seed benchmarks\graph_cases.research.seed.json
```

After experts fill the CSV:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_graph_expert_ratings.py --ratings benchmarks\graph_expert_ratings.template.csv --key benchmarks\graph_expert_review_key.json --out benchmarks\graph_expert_correlation_latest.json
```

## Reported Statistics

- Pearson correlation: linear agreement between `composite_score` and expert score.
- Spearman correlation: rank-order agreement.
- Kendall tau-a: pairwise rank agreement.
- MAE/RMSE: absolute score disagreement after normalizing expert scores to 0-1.
- Bias: average `model_score - expert_score`.
- Pairwise inter-rater Pearson/Spearman when two or more experts grade the same items.
