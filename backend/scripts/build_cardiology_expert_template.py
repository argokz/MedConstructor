"""Build a blinded, fillable expert-rating template for the REAL cardiologist panel.

This replaces the synthetic-proxy path for the cardiology expert validation.
It reads the cardiology benchmark (which already contains the deterministic
v4.1 model metrics in ``graph.results``) and emits two files:

1. ``cardiology_expert_ratings_REAL.template.csv`` -- one row per (variant x expert),
   pre-populated with a blinded ``review_item_id`` and the human-readable graph the
   cardiologist actually evaluated. The expert (or the person entering their paper
   scores) only fills ``expert_score_0_100`` (0-100) and optional accept/comment.

2. ``cardiology_expert_review_key.json`` -- researcher-only mapping from
   ``review_item_id`` to case/variant/expected_pattern and the model metrics. This
   file must NOT be given to raters; it is used only by the analyzer afterwards.

After the CSV is filled, run::

    python scripts/analyze_graph_expert_ratings.py \
        --benchmark benchmarks/cardiology_graph_benchmark_for_expert_eval.json \
        --ratings   benchmarks/cardiology_expert_ratings_REAL.filled.csv \
        --key       benchmarks/cardiology_expert_review_key.json \
        --out       benchmarks/cardiology_real_expert_validation_latest.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_BENCHMARK = BACKEND_ROOT / "benchmarks" / "cardiology_synthetic_latest.json"
DEFAULT_TEMPLATE = BACKEND_ROOT / "benchmarks" / "cardiology_expert_ratings_REAL.template.csv"
DEFAULT_KEY = BACKEND_ROOT / "benchmarks" / "cardiology_expert_review_key.json"
# Unwrapped benchmark (``graph.results`` at top level) so analyze_graph_expert_ratings.py
# can index the model metrics directly.
DEFAULT_EVAL_BENCHMARK = BACKEND_ROOT / "benchmarks" / "cardiology_graph_benchmark_for_expert_eval.json"

# Default raters. Use neutral, stable ids; real names stay out of the dataset.
DEFAULT_EXPERTS = ["expert_01", "expert_02", "expert_03"]


def _review_item_id(case_id: str, variant_id: str) -> str:
    digest = hashlib.sha1(f"{case_id}::{variant_id}".encode("utf-8")).hexdigest()[:12]
    return f"cre_{digest}"


def _cardiology_block(benchmark: dict[str, Any]) -> dict[str, Any]:
    # The artifact may be wrapped (``{"cardiology": {...}}``) or already unwrapped.
    return benchmark.get("cardiology", benchmark)


def _variant_descriptions(block: dict[str, Any]) -> dict[tuple[str, str], str]:
    descriptions: dict[tuple[str, str], str] = {}
    for case in block.get("cases", []):
        case_id = case.get("case_id")
        for variant in case.get("variants", []):
            descriptions[(case_id, variant.get("variant_id"))] = (
                variant.get("description") or ""
            )
    return descriptions


def _case_titles(block: dict[str, Any]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for case in block.get("cases", []):
        titles[case.get("case_id")] = case.get("title") or case.get("case_id")
    return titles


def build(
    benchmark_path: Path,
    template_path: Path,
    key_path: Path,
    experts: list[str],
    eval_benchmark_path: Path = DEFAULT_EVAL_BENCHMARK,
) -> dict[str, Any]:
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    block = _cardiology_block(benchmark)
    results = block.get("graph", {}).get("results", [])
    if not results:
        raise SystemExit(f"No graph.results found in {benchmark_path}")

    # Emit an unwrapped benchmark so the shared analyzer finds ``graph.results``.
    eval_benchmark_path.write_text(
        json.dumps({"graph": block.get("graph", {})}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    descriptions = _variant_descriptions(block)
    titles = _case_titles(block)

    template_rows: list[dict[str, Any]] = []
    key_items: list[dict[str, Any]] = []

    for result in results:
        case_id = result.get("case_id")
        variant_id = result.get("variant_id")
        review_item_id = _review_item_id(case_id, variant_id)
        case_title = titles.get(case_id, case_id)
        description = descriptions.get((case_id, variant_id), "")
        metrics = result.get("metrics", {})

        key_items.append(
            {
                "review_item_id": review_item_id,
                "case_id": case_id,
                "variant_id": variant_id,
                "expected_pattern": result.get("expected_pattern"),
                "algorithm_version": result.get("algorithm_version"),
                "metrics": metrics,
            }
        )

        for expert_id in experts:
            template_rows.append(
                {
                    "review_item_id": review_item_id,
                    "clinical_case_title": case_title,
                    "graph_under_review": description,
                    "expert_id": expert_id,
                    "expert_score_0_100": "",
                    "expert_accept": "",
                    "expert_comment": "",
                }
            )

    fieldnames = [
        "review_item_id",
        "clinical_case_title",
        "graph_under_review",
        "expert_id",
        "expert_score_0_100",
        "expert_accept",
        "expert_comment",
    ]
    with template_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(template_rows)

    key_payload = {
        "source_benchmark": benchmark_path.name,
        "algorithm_version": block.get("algorithm_version"),
        "note": "Researcher-only key. Do NOT share with raters: it contains the expected error pattern and model metrics.",
        "items": key_items,
    }
    key_path.write_text(
        json.dumps(key_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "template": str(template_path),
        "key": str(key_path),
        "eval_benchmark": str(eval_benchmark_path),
        "variants": len(results),
        "experts": experts,
        "expected_rows_to_fill": len(template_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the blinded real-cardiologist rating template.")
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK))
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--key", default=str(DEFAULT_KEY))
    parser.add_argument(
        "--experts",
        default=",".join(DEFAULT_EXPERTS),
        help="Comma-separated neutral rater ids (one block of rows per rater).",
    )
    args = parser.parse_args()

    experts = [e.strip() for e in args.experts.split(",") if e.strip()]
    info = build(Path(args.benchmark), Path(args.template), Path(args.key), experts)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
