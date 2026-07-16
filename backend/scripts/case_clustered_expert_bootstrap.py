"""Reproduce case-clustered confidence intervals reported in the article."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.expert_evaluation import pearson_correlation, spearman_correlation


DEFAULT_INPUT = BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_validation_v2_latest.json"
DEFAULT_OUTPUT = (
    BACKEND_ROOT / "benchmarks" / "cardiology_real_case_cluster_bootstrap_v2_latest.json"
)


def quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(value for value in values if math.isfinite(value))
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def interval(values: Sequence[float]) -> dict[str, float]:
    return {
        "low": round(quantile(values, 0.025), 4),
        "high": round(quantile(values, 0.975), 4),
    }


def load_rows(payload: dict[str, Any]) -> list[dict[str, float | str]]:
    metrics_by_item = {
        (str(row["case_id"]), str(row["variant_id"])): row["metrics"]
        for row in payload["results"]
    }
    rows: list[dict[str, float | str]] = []
    for item in payload["expert_items"]:
        key = (str(item["case_id"]), str(item["variant_id"]))
        metrics = metrics_by_item[key]
        baseline = max(
            0.0,
            float(metrics["weighted_edge_f1"]) - 0.35 * float(metrics["safety_penalty"]),
        )
        rows.append(
            {
                "case_id": key[0],
                "composite": float(item["model_score"]),
                "expert": float(item["expert_mean_score"]),
                "baseline": baseline,
            }
        )
    return rows


def correlation(rows: Sequence[dict[str, float | str]], field: str, fn: Callable) -> float:
    model = [float(row[field]) for row in rows]
    expert = [float(row["expert"]) for row in rows]
    value = fn(model, expert)
    if value is None:
        raise RuntimeError(f"Could not compute {field} correlation")
    return float(value)


def run(payload: dict[str, Any], iterations: int, seed: int) -> dict[str, Any]:
    rows = load_rows(payload)
    grouped: dict[str, list[dict[str, float | str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["case_id"])].append(row)
    case_ids = sorted(grouped)

    rng = random.Random(seed)
    pearson_samples: list[float] = []
    spearman_samples: list[float] = []
    delta_samples: list[float] = []
    for _ in range(iterations):
        sampled_cases = [case_ids[rng.randrange(len(case_ids))] for _ in case_ids]
        sample = [row for case_id in sampled_cases for row in grouped[case_id]]
        pearson = correlation(sample, "composite", pearson_correlation)
        spearman = correlation(sample, "composite", spearman_correlation)
        baseline_spearman = correlation(sample, "baseline", spearman_correlation)
        pearson_samples.append(pearson)
        spearman_samples.append(spearman)
        delta_samples.append(spearman - baseline_spearman)

    return {
        "method": "Non-parametric case-clustered percentile bootstrap",
        "resampling_unit": "clinical_case",
        "case_order": case_ids,
        "case_count": len(case_ids),
        "variant_count": len(rows),
        "iterations": iterations,
        "seed": seed,
        "baseline": "max(0, weighted_edge_f1 - 0.35 * safety_penalty)",
        "point_estimates": {
            "pearson_composite": round(correlation(rows, "composite", pearson_correlation), 4),
            "spearman_composite": round(correlation(rows, "composite", spearman_correlation), 4),
            "spearman_baseline": round(correlation(rows, "baseline", spearman_correlation), 4),
        },
        "confidence_intervals_95": {
            "pearson_composite": interval(pearson_samples),
            "spearman_composite": interval(spearman_samples),
            "spearman_delta_composite_minus_baseline": interval(delta_samples),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260618)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = run(payload, args.iterations, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
