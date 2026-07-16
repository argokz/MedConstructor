# Benchmarking

This project now has a small reproducible benchmark harness for two critical
parts of the system:

- RAG retrieval quality and latency.
- Graph evaluation quality across controlled correct and incorrect solutions.

## Files

- `benchmarks/rag_queries.seed.json` contains protocol-search questions with
  expected protocol ids and expected section names.
- `benchmarks/rag_queries.extended.seed.json` contains a broader 14-case RAG
  seed for article-oriented reporting.
- `benchmarks/rag_queries.research.seed.json` contains a draft 50-case RAG
  seed for reproducible article experiments. It combines curated cases with
  auto-generated DB cases that need expert review before publication.
- `benchmarks/graph_cases.seed.json` contains a reference graph plus student
  graph variants: perfect, missing diagnostic data, wrong relation, unsafe extra
  treatment, and broken clinical chain.
- `benchmarks/graph_cases.research.seed.json` contains a deterministic 20-case
  graph grading seed with 160 controlled student variants across the main error
  taxonomy.
- `scripts/build_rag_eval_seed.py` builds the draft research RAG seed from the
  protocol database and enriches cases with expected sections and key phrases.
- `scripts/build_graph_eval_seed.py` builds the deterministic research graph
  grading seed.
- `scripts/export_graph_expert_ratings.py` exports a blinded expert-rating
  package from graph benchmark results.
- `scripts/analyze_graph_expert_ratings.py` computes correlation between
  graph metrics and filled expert grades.
- `scripts/run_benchmark.py` runs both benchmarks and prints JSON.

## Commands

Run the full benchmark with OpenAI as the primary provider:

```powershell
$env:PRIMARY_LLM_PROVIDER='openai'
.\.venv\Scripts\python.exe scripts\run_benchmark.py --out benchmark_results.json
```

Run only the deterministic graph benchmark:

```powershell
.\.venv\Scripts\python.exe scripts\run_benchmark.py --skip-rag
```

Limit the benchmark during development:

```powershell
.\.venv\Scripts\python.exe scripts\run_benchmark.py --limit 1
```

Run RAG ablation modes:

```powershell
$env:PRIMARY_LLM_PROVIDER='openai'
.\.venv\Scripts\python.exe scripts\run_benchmark.py --skip-graph --rag-ablation
```

Build and run the draft research RAG seed:

```powershell
.\.venv\Scripts\python.exe scripts\build_rag_eval_seed.py --target 50 --out benchmarks\rag_queries.research.seed.json
$env:PRIMARY_LLM_PROVIDER='openai'
.\.venv\Scripts\python.exe scripts\run_benchmark.py --skip-graph --rag benchmarks\rag_queries.research.seed.json --out benchmarks\rag_research_latest.json
```

Build and run the deterministic research graph seed:

```powershell
.\.venv\Scripts\python.exe scripts\build_graph_eval_seed.py --target 20 --out benchmarks\graph_cases.research.seed.json
.\.venv\Scripts\python.exe scripts\run_benchmark.py --skip-rag --graph benchmarks\graph_cases.research.seed.json --out benchmarks\graph_research_latest.json
```

Export blinded graph items for teacher scoring:

```powershell
.\.venv\Scripts\python.exe scripts\export_graph_expert_ratings.py --benchmark benchmarks\graph_research_latest.json --graph-seed benchmarks\graph_cases.research.seed.json
```

Analyze expert-score correlation after the CSV is filled:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_graph_expert_ratings.py --ratings benchmarks\graph_expert_ratings.template.csv --key benchmarks\graph_expert_review_key.json --out benchmarks\graph_expert_correlation_latest.json
```

## Reported Metrics

RAG:

- `recall_at_1`, `recall_at_3`, `recall_at_5`, `recall_at_10`: whether at least
  one expected protocol was retrieved by rank K.
- `mrr`: mean reciprocal rank of the first expected protocol.
- `section_hit_rate`: overlap between retrieved sections and expected sections.
  Section names are matched with light Russian normalization, so clinically
  equivalent names such as `Дифференциальный диагноз` and `Диагностика`, or
  `Наблюдение за состоянием плода` and `Наблюдение за плодом`, count as hits.
- `key_phrase_hit_rate`: overlap between retrieved text and expected clinical
  key phrases. This catches cases where the protocol id is correct but the
  retrieved chunks miss important clinical content.
- `latency_ms`: min, p50, p95, avg, max retrieval time.

Graph evaluation:

- `edge_f1`: legacy exact semantic edge F1.
- `weighted_edge_f1`: clinically weighted edge F1.
- `node_coverage`: one-to-one semantic node coverage.
- `category_accuracy`: whether matched nodes also have the correct clinical type.
- `directed_path_completeness`: recovery of clinically meaningful paths.
- `safety_penalty`, `unsafe_extra_action`, `missing_critical_action`: safety
  oriented penalties.
- `composite_score`: final normalized score used for grading.
- `pattern_pass_rate`: share of controlled student-error variants where the
  expected metric behavior was observed, for example unsafe extra treatment
  capped at `0.75` or a broken reasoning chain producing near-zero directed
  path completeness.

Reference graph generation quality:

- `schema_valid_rate`: share of generated/reference graphs that pass
  `GraphSchema` validation.
- `accepted_rate`: share of graphs accepted by the internal clinical judge.
- `warning_rate`: share of graphs with at least one judge warning.
- `critical_rate`: share of graphs with at least one critical judge finding.
- `avg_quality_score`: heuristic graph quality score after clinical-logic
  penalties.

Expert validation:

- `pearson`, `spearman`, `kendall_tau_a`: agreement between algorithm
  `composite_score` and expert grade.
- `mae`, `rmse`, `bias`: score disagreement after normalizing expert grades to
  the same `0..1` scale.
- `mean_pairwise_pearson`, `mean_pairwise_spearman`: inter-rater agreement when
  at least two experts score overlapping items.

For article/diploma reporting, store the JSON output for each algorithm version
and compare summaries rather than single anecdotal examples.

## Current Seed Results

Latest OpenAI-backed RAG seed run:

- `Recall@1/3/5/10`: `1.0`
- `MRR`: `1.0`
- `section_hit_rate`: `1.0`
- latency: `p50 ~= 855 ms`, `p95 ~= 1874 ms`

The current retrieval path uses title-candidate expansion, low-signal chunk
filtering, section-aware diversification, light medical term expansion
(`гипертензия` -> `гипотензивная терапия`, `лечение` -> `терапия`, etc.), and
fuzzy section-name matching in the benchmark. Title matching ignores generic
words such as `клинический`, `протокол`, `приложение`, `болезнь` and `синдром`,
so specific disease titles are not drowned out by administrative protocol names.

Latest OpenAI-backed extended RAG seed run (`n=14`):

- `Recall@1/3/5/10`: `1.0`
- `MRR`: `1.0`
- `section_hit_rate`: `1.0`
- latency: `p50 ~= 613 ms`, `p95 ~= 1356 ms`

Latest extended RAG ablation (`n=14`):

| Mode | Recall@1 | MRR | Section Hit Rate |
|---|---:|---:|---:|
| `dense_only` | 0.5000 | 0.6690 | 0.7679 |
| `dense_rerank` | 1.0000 | 1.0000 | 0.9107 |
| `full` | 1.0000 | 1.0000 | 1.0000 |

Latest OpenAI-backed research RAG seed run (`n=50`):

- `Recall@1`: `0.94`
- `Recall@3`: `0.98`
- `Recall@5`: `0.98`
- `Recall@10`: `1.00`
- `MRR`: `0.9625`
- `section_hit_rate`: `0.9833`
- `key_phrase_hit_rate`: `0.9910`
- latency: `p50 ~= 635 ms`, `p95 ~= 772 ms`
- full misses: `0`

Latest research RAG ablation (`n=50`):

| Mode | Recall@1 | Recall@3 | Recall@10 | MRR | Section Hit Rate | Key Phrase Hit Rate |
|---|---:|---:|---:|---:|---:|---:|
| `dense_only` | 0.5600 | 0.8200 | 0.8800 | 0.6848 | 0.6767 | 0.9177 |
| `dense_rerank` | 0.8600 | 0.8800 | 0.9000 | 0.8750 | 0.8533 | 0.9353 |
| `full` | 0.9400 | 0.9800 | 1.0000 | 0.9625 | 0.9833 | 0.9910 |

For article reporting, treat latency in ablation as secondary because repeated
modes share the in-process embedding cache. Quality metrics are the primary
comparison here.

Latest deterministic graph benchmark:

- student variants: `n=5`
- average `weighted_edge_f1`: `0.876`
- average `directed_path_completeness`: `0.750`
- average `safety_penalty`: `0.400`
- average `composite_score`: `0.736`

Latest deterministic research graph benchmark:

- reference graph cases: `20`
- student variants: `160`
- `pattern_pass_rate`: `1.0000`
- average `weighted_edge_f1`: `0.8964`
- average `directed_path_completeness`: `0.6675`
- average `safety_penalty`: `0.2425`
- average `composite_score`: `0.7701`

Pattern sensitivity on the research graph seed:

| Expected Pattern | n | Pass Rate |
|---|---:|---:|
| `all_metrics_high` | 20 | 1.0000 |
| `recall_and_node_coverage_drop` | 20 | 1.0000 |
| `category_accuracy_drop` | 20 | 1.0000 |
| `critical_relation_penalty` | 20 | 1.0000 |
| `missing_critical_action_penalty` | 40 | 1.0000 |
| `unsafe_extra_action_cap` | 20 | 1.0000 |
| `directed_path_zero` | 20 | 1.0000 |

Average composite score by student variant:

| Variant | Avg Composite |
|---|---:|
| `perfect` | 1.0000 |
| `wrong_symptom_category` | 0.9800 |
| `missing_contraindication` | 0.7720 |
| `extra_unsafe_treatment` | 0.7500 |
| `missing_critical_action` | 0.7150 |
| `wrong_action_relation` | 0.6950 |
| `broken_chain` | 0.6900 |
| `missing_diagnostic_step` | 0.5585 |

Reference graph quality on the current seed:

- `schema_valid_rate`: `1.0`
- `accepted_rate`: `1.0`
- `warning_rate`: `0.0`
- `critical_rate`: `0.0`
- `avg_quality_score`: `1.0`

Reference graph quality on the research graph seed:

- `schema_valid_rate`: `1.0`
- `accepted_rate`: `1.0`
- `warning_rate`: `0.0`
- `critical_rate`: `0.0`
- `avg_quality_score`: `1.0`

Expert-rating package:

- blinded CSV template: `benchmarks/graph_expert_ratings.template.csv`
- blinded review items: `benchmarks/graph_expert_review_items.jsonl`
- researcher-only key: `benchmarks/graph_expert_review_key.json`
- current correlation report is a smoke-test on the empty template:
  `item_count = 0`, `rating_count = 0`; fill expert scores before reporting
  correlations in an article.

The graph benchmark JSON now includes a `reference_quality` block. This is the
place to report schema validity, warning rate, expert acceptance candidates, and
future correlation with teacher labels.
