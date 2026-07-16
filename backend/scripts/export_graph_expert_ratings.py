from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Mapping

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.run_benchmark import _student_graph_payload

DEFAULT_BENCHMARK = BACKEND_ROOT / "benchmarks" / "graph_research_latest.json"
DEFAULT_GRAPH_SEED = BACKEND_ROOT / "benchmarks" / "graph_cases.research.seed.json"
DEFAULT_CSV = BACKEND_ROOT / "benchmarks" / "graph_expert_ratings.template.csv"
DEFAULT_ITEMS = BACKEND_ROOT / "benchmarks" / "graph_expert_review_items.jsonl"
DEFAULT_KEY = BACKEND_ROOT / "benchmarks" / "graph_expert_review_key.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = BACKEND_ROOT / resolved
    return resolved


def _review_item_id(case_id: str, variant_id: str) -> str:
    digest = hashlib.sha1(f"{case_id}::{variant_id}".encode("utf-8")).hexdigest()
    return f"gri_{digest[:12]}"


def _graph_results(benchmark: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(benchmark.get("graph", {}).get("results", benchmark.get("results", [])))


def _seed_index(seed_cases: list[Mapping[str, Any]]) -> dict[tuple[str, str], tuple[Mapping[str, Any], Mapping[str, Any]]]:
    index = {}
    for case in seed_cases:
        case_id = str(case.get("case_id"))
        for variant in case.get("variants", []):
            index[(case_id, str(variant.get("variant_id")))] = (case, variant)
    return index


def _build_review_items(
    benchmark: Mapping[str, Any],
    seed_cases: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seed_by_key = _seed_index(seed_cases)
    items = []
    for result in _graph_results(benchmark):
        case_id = str(result.get("case_id"))
        variant_id = str(result.get("variant_id"))
        case, variant = seed_by_key[(case_id, variant_id)]
        reference_graph = case["reference_graph"]
        student_graph = _student_graph_payload(reference_graph, variant)
        review_item_id = _review_item_id(case_id, variant_id)
        items.append(
            {
                "review_item_id": review_item_id,
                "clinical_case_title": case.get("title"),
                "reference_graph": reference_graph,
                "student_graph": student_graph,
                "key": {
                    "review_item_id": review_item_id,
                    "case_id": case_id,
                    "variant_id": variant_id,
                    "expected_pattern": result.get("expected_pattern"),
                    "algorithm_version": result.get("algorithm_version"),
                    "metrics": result.get("metrics", {}),
                },
            }
        )
    return items


def _write_csv_template(path: Path, items: list[dict[str, Any]], delimiter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "review_item_id",
        "clinical_case_title",
        "expert_id",
        "expert_score_0_100",
        "expert_accept",
        "expert_comment",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "review_item_id": item["review_item_id"],
                    "clinical_case_title": item.get("clinical_case_title"),
                    "expert_id": "",
                    "expert_score_0_100": "",
                    "expert_accept": "",
                    "expert_comment": "",
                }
            )


def _write_items_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for item in items:
            expert_item = {
                "review_item_id": item["review_item_id"],
                "clinical_case_title": item.get("clinical_case_title"),
                "reference_graph": item["reference_graph"],
                "student_graph": item["student_graph"],
            }
            file.write(json.dumps(expert_item, ensure_ascii=False) + "\n")


def _write_key(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = [item["key"] for item in items]
    path.write_text(json.dumps({"items": keys}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export blinded graph expert-rating package.")
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK), help="Graph benchmark result JSON.")
    parser.add_argument("--graph-seed", default=str(DEFAULT_GRAPH_SEED), help="Graph seed JSON used by the benchmark.")
    parser.add_argument("--csv-out", default=str(DEFAULT_CSV), help="CSV template for expert scores.")
    parser.add_argument("--items-out", default=str(DEFAULT_ITEMS), help="Blinded JSONL review items with graphs.")
    parser.add_argument("--key-out", default=str(DEFAULT_KEY), help="Researcher-only item key with algorithm metrics.")
    parser.add_argument("--seed", type=int, default=20260617, help="Shuffle seed for blinded item order.")
    parser.add_argument("--no-shuffle", action="store_true", help="Keep benchmark order.")
    parser.add_argument("--delimiter", default=",", help="CSV delimiter.")
    args = parser.parse_args()

    benchmark = _read_json(_resolve(args.benchmark))
    seed_cases = _read_json(_resolve(args.graph_seed))
    items = _build_review_items(benchmark, seed_cases)
    if not args.no_shuffle:
        random.Random(args.seed).shuffle(items)

    _write_csv_template(_resolve(args.csv_out), items, args.delimiter)
    _write_items_jsonl(_resolve(args.items_out), items)
    _write_key(_resolve(args.key_out), items)

    print(
        json.dumps(
            {
                "csv_out": str(_resolve(args.csv_out)),
                "items_out": str(_resolve(args.items_out)),
                "key_out": str(_resolve(args.key_out)),
                "items": len(items),
                "shuffle_seed": None if args.no_shuffle else args.seed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
