from __future__ import annotations

import argparse
import csv
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

from app.services.expert_evaluation import analyze_expert_ratings

DEFAULT_BENCHMARK = BACKEND_ROOT / "benchmarks" / "graph_research_latest.json"
DEFAULT_RATINGS = BACKEND_ROOT / "benchmarks" / "graph_expert_ratings.template.csv"
DEFAULT_KEY = BACKEND_ROOT / "benchmarks" / "graph_expert_review_key.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "benchmarks" / "graph_expert_correlation_latest.json"


def _resolve(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = BACKEND_ROOT / resolved
    return resolved


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ratings_csv(path: Path, delimiter: str) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=delimiter))


def _read_key(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    items = payload.get("items", payload if isinstance(payload, list) else [])
    return {str(item["review_item_id"]): item for item in items}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze correlation between graph metrics and expert scores.")
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK), help="Graph benchmark result JSON.")
    parser.add_argument("--ratings", default=str(DEFAULT_RATINGS), help="Filled expert-rating CSV.")
    parser.add_argument("--key", default=str(DEFAULT_KEY), help="Researcher-only item key JSON.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output JSON report.")
    parser.add_argument("--delimiter", default=",", help="CSV delimiter.")
    args = parser.parse_args()

    benchmark = _read_json(_resolve(args.benchmark))
    ratings = _read_ratings_csv(_resolve(args.ratings), args.delimiter)
    key_by_review_item = _read_key(_resolve(args.key))
    report = analyze_expert_ratings(
        benchmark,
        ratings,
        key_by_review_item=key_by_review_item,
    )

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        out_path = _resolve(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
