from __future__ import annotations

import math
import random
from collections import defaultdict
from itertools import combinations
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping, Sequence


def normalize_expert_score(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    score = float(value)
    if score < 0:
        raise ValueError("Expert score must be non-negative.")
    if score > 1.0:
        score = score / 100.0
    if score > 1.0:
        raise ValueError("Expert score must be in 0..1 or 0..100 scale.")
    return score


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys):
        raise ValueError("Correlation inputs must have equal length.")
    if len(xs) < 2:
        return None

    mean_x = mean(xs)
    mean_y = mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denominator_x == 0 or denominator_y == 0:
        return None
    return numerator / (denominator_x * denominator_y)


def rank_average(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        for original_index, _value in ordered[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def spearman_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys):
        raise ValueError("Correlation inputs must have equal length.")
    if len(xs) < 2:
        return None
    return pearson_correlation(rank_average(xs), rank_average(ys))


def kendall_tau_a(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys):
        raise ValueError("Correlation inputs must have equal length.")
    if len(xs) < 2:
        return None

    concordant = 0
    discordant = 0
    total_pairs = 0
    for i, j in combinations(range(len(xs)), 2):
        dx = xs[i] - xs[j]
        dy = ys[i] - ys[j]
        if dx == 0 or dy == 0:
            total_pairs += 1
            continue
        total_pairs += 1
        if dx * dy > 0:
            concordant += 1
        else:
            discordant += 1
    if total_pairs == 0:
        return None
    return (concordant - discordant) / total_pairs


def regression_error_summary(model_scores: Sequence[float], expert_scores: Sequence[float]) -> dict[str, float | None]:
    if len(model_scores) != len(expert_scores):
        raise ValueError("Score inputs must have equal length.")
    if not model_scores:
        return {"mae": None, "rmse": None, "bias": None}

    errors = [model - expert for model, expert in zip(model_scores, expert_scores)]
    return {
        "mae": round(sum(abs(error) for error in errors) / len(errors), 4),
        "rmse": round(math.sqrt(sum(error**2 for error in errors) / len(errors)), 4),
        "bias": round(mean(errors), 4),
    }


def _quantile(values: Sequence[float], probability: float) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    index = (len(clean) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return clean[int(index)]
    weight = index - lower
    return clean[lower] * (1.0 - weight) + clean[upper] * weight


def _bootstrap_statistic(
    model_scores: Sequence[float],
    expert_scores: Sequence[float],
    statistic: str,
    *,
    iterations: int = 2000,
    seed: int = 20260618,
) -> tuple[float | None, float | None]:
    if len(model_scores) != len(expert_scores):
        raise ValueError("Score inputs must have equal length.")
    if len(model_scores) < 3:
        return (None, None)

    rng = random.Random(seed)
    n = len(model_scores)
    sampled_values: list[float] = []

    def compute(xs: list[float], ys: list[float]) -> float | None:
        if statistic == "pearson":
            return pearson_correlation(xs, ys)
        if statistic == "spearman":
            return spearman_correlation(xs, ys)
        if statistic == "kendall_tau_a":
            return kendall_tau_a(xs, ys)
        errors = [x - y for x, y in zip(xs, ys)]
        if statistic == "mae":
            return sum(abs(error) for error in errors) / len(errors)
        if statistic == "rmse":
            return math.sqrt(sum(error**2 for error in errors) / len(errors))
        if statistic == "bias":
            return mean(errors)
        raise ValueError(f"Unsupported bootstrap statistic: {statistic}")

    for _ in range(iterations):
        indices = [rng.randrange(n) for _ in range(n)]
        xs = [float(model_scores[index]) for index in indices]
        ys = [float(expert_scores[index]) for index in indices]
        value = compute(xs, ys)
        if value is not None and math.isfinite(value):
            sampled_values.append(value)

    if len(sampled_values) < max(20, iterations // 20):
        return (None, None)
    return (
        _round_or_none(_quantile(sampled_values, 0.025)),
        _round_or_none(_quantile(sampled_values, 0.975)),
    )


def bootstrap_confidence_intervals(
    model_scores: Sequence[float],
    expert_scores: Sequence[float],
    *,
    iterations: int = 2000,
    seed: int = 20260618,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for offset, statistic in enumerate(("pearson", "spearman", "kendall_tau_a", "mae", "rmse", "bias")):
        low, high = _bootstrap_statistic(
            model_scores,
            expert_scores,
            statistic,
            iterations=iterations,
            seed=seed + offset * 997,
        )
        result[f"{statistic}_ci_low"] = low
        result[f"{statistic}_ci_high"] = high
    return result


def correlation_summary(
    model_scores: Sequence[float],
    expert_scores: Sequence[float],
    *,
    include_ci: bool = False,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "n": len(model_scores),
        "pearson": _round_or_none(pearson_correlation(model_scores, expert_scores)),
        "spearman": _round_or_none(spearman_correlation(model_scores, expert_scores)),
        "kendall_tau_a": _round_or_none(kendall_tau_a(model_scores, expert_scores)),
        "mean_model_score": round(mean(model_scores), 4) if model_scores else None,
        "mean_expert_score": round(mean(expert_scores), 4) if expert_scores else None,
    }
    summary.update(regression_error_summary(model_scores, expert_scores))
    if include_ci:
        summary.update(bootstrap_confidence_intervals(model_scores, expert_scores))
    return summary


def _graph_results(benchmark: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if "graph" in benchmark:
        return list(benchmark.get("graph", {}).get("results", []))
    return list(benchmark.get("results", []))


def _result_key(case_id: Any, variant_id: Any) -> str:
    return f"{case_id}::{variant_id}"


def graph_result_index(benchmark: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _result_key(result.get("case_id"), result.get("variant_id")): result
        for result in _graph_results(benchmark)
    }


def _rating_score(row: Mapping[str, Any]) -> float | None:
    for field in ("expert_score_0_100", "expert_score", "score", "rating"):
        if field in row:
            return normalize_expert_score(row.get(field))
    return None


def _rating_key(row: Mapping[str, Any], key_by_review_item: Mapping[str, Mapping[str, Any]]) -> str | None:
    case_id = row.get("case_id")
    variant_id = row.get("variant_id")
    if case_id and variant_id:
        return _result_key(case_id, variant_id)

    review_item_id = str(row.get("review_item_id") or "").strip()
    if not review_item_id:
        return None
    mapped = key_by_review_item.get(review_item_id)
    if not mapped:
        return None
    return _result_key(mapped.get("case_id"), mapped.get("variant_id"))


def _scores_from_items(items: Iterable[Mapping[str, Any]]) -> tuple[list[float], list[float]]:
    model_scores = []
    expert_scores = []
    for item in items:
        model_scores.append(float(item["model_score"]))
        expert_scores.append(float(item["expert_mean_score"]))
    return model_scores, expert_scores


def _baseline_score(metrics: Mapping[str, Any], name: str) -> float | None:
    if name == "safety_adjusted_weighted_edge_f1":
        weighted = metrics.get("weighted_edge_f1")
        safety = metrics.get("safety_penalty") or 0.0
        if weighted is None:
            return None
        return max(0.0, float(weighted) - 0.35 * float(safety))
    value = metrics.get(name)
    return float(value) if value is not None else None


def baseline_comparison_rows(
    benchmark: Mapping[str, Any],
    item_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    benchmark_by_key = graph_result_index(benchmark)
    score_defs = [
        ("composite_v4_3", "composite_score", "Reference-quality calibrated clinical composite score v4.3."),
        ("edge_f1_baseline", "edge_f1", "Unweighted directed edge overlap."),
        ("weighted_edge_f1_only", "weighted_edge_f1", "Edge overlap with clinical node and relation weights only."),
        ("node_coverage_only", "node_coverage", "Coverage of reference clinical concepts only."),
        ("category_accuracy_only", "category_accuracy", "Matched node category correctness only."),
        ("directed_path_only", "directed_path_completeness", "Continuity of directed reasoning paths only."),
        (
            "safety_adjusted_weighted_edge_f1",
            "safety_adjusted_weighted_edge_f1",
            "Weighted edge F1 minus safety penalty without full composite weighting.",
        ),
    ]
    expert_scores_by_key = {
        _result_key(item.get("case_id"), item.get("variant_id")): float(item["expert_mean_score"])
        for item in item_rows
        if item.get("expert_mean_score") is not None
    }

    rows: list[dict[str, Any]] = []
    composite_summary: dict[str, Any] | None = None
    for model_name, metric_key, description in score_defs:
        model_scores: list[float] = []
        expert_scores: list[float] = []
        for key, expert_score in expert_scores_by_key.items():
            result = benchmark_by_key.get(key)
            if not result:
                continue
            metrics = result.get("metrics") or result
            score = _baseline_score(metrics, metric_key)
            if score is None:
                continue
            model_scores.append(float(score))
            expert_scores.append(expert_score)
        summary = correlation_summary(model_scores, expert_scores, include_ci=True)
        if model_name == "composite_v4_3":
            composite_summary = summary
        rows.append(
            {
                "model": model_name,
                "metric_source": metric_key,
                "description": description,
                **summary,
                "delta_spearman_vs_composite": None,
                "delta_mae_vs_composite": None,
            }
        )

    if composite_summary:
        composite_spearman = composite_summary.get("spearman")
        composite_mae = composite_summary.get("mae")
        for row in rows:
            if row["model"] == "composite_v4_3":
                row["delta_spearman_vs_composite"] = 0.0
                row["delta_mae_vs_composite"] = 0.0
                continue
            if composite_spearman is not None and row.get("spearman") is not None:
                row["delta_spearman_vs_composite"] = round(float(row["spearman"]) - float(composite_spearman), 4)
            if composite_mae is not None and row.get("mae") is not None:
                row["delta_mae_vs_composite"] = round(float(row["mae"]) - float(composite_mae), 4)
    return rows


def analyze_expert_ratings(
    benchmark: Mapping[str, Any],
    rating_rows: Sequence[Mapping[str, Any]],
    *,
    key_by_review_item: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    key_by_review_item = key_by_review_item or {}
    benchmark_by_key = graph_result_index(benchmark)

    item_ratings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped_rows: list[dict[str, Any]] = []
    expert_ids = set()

    for index, row in enumerate(rating_rows, start=1):
        try:
            score = _rating_score(row)
        except ValueError as exc:
            skipped_rows.append({"row": index, "reason": str(exc)})
            continue
        if score is None:
            skipped_rows.append({"row": index, "reason": "Empty expert score."})
            continue

        key = _rating_key(row, key_by_review_item)
        if not key or key not in benchmark_by_key:
            skipped_rows.append({"row": index, "reason": "Cannot map rating row to benchmark result."})
            continue

        expert_id = str(row.get("expert_id") or "expert").strip() or "expert"
        expert_ids.add(expert_id)
        item_ratings[key].append(
            {
                "expert_id": expert_id,
                "score": score,
                "comment": row.get("expert_comment") or row.get("comment"),
            }
        )

    item_rows: list[dict[str, Any]] = []
    for key, ratings in sorted(item_ratings.items()):
        result = benchmark_by_key[key]
        expert_scores = [float(rating["score"]) for rating in ratings]
        metrics = result.get("metrics", {})
        item_rows.append(
            {
                "case_id": result.get("case_id"),
                "variant_id": result.get("variant_id"),
                "expected_pattern": result.get("expected_pattern"),
                "model_score": float(metrics.get("composite_score") or 0.0),
                "expert_mean_score": mean(expert_scores),
                "expert_score_std": pstdev(expert_scores) if len(expert_scores) > 1 else 0.0,
                "expert_rating_count": len(expert_scores),
            }
        )

    model_scores, expert_scores = _scores_from_items(item_rows)
    baseline_comparison = baseline_comparison_rows(benchmark, item_rows)
    by_expert = []
    for expert_id in sorted(expert_ids):
        expert_items = []
        for key, ratings in item_ratings.items():
            result = benchmark_by_key[key]
            scores = [float(rating["score"]) for rating in ratings if rating["expert_id"] == expert_id]
            if not scores:
                continue
            expert_items.append(
                {
                    "model_score": float(result.get("metrics", {}).get("composite_score") or 0.0),
                    "expert_mean_score": mean(scores),
                }
            )
        expert_model_scores, expert_scores_for_id = _scores_from_items(expert_items)
        by_expert.append(
            {
                "expert_id": expert_id,
                **correlation_summary(expert_model_scores, expert_scores_for_id),
            }
        )

    by_pattern = []
    for pattern in sorted({str(item.get("expected_pattern")) for item in item_rows if item.get("expected_pattern")}):
        subset = [item for item in item_rows if item.get("expected_pattern") == pattern]
        pattern_model_scores, pattern_expert_scores = _scores_from_items(subset)
        by_pattern.append(
            {
                "expected_pattern": pattern,
                **correlation_summary(pattern_model_scores, pattern_expert_scores),
            }
        )

    inter_rater = pairwise_inter_rater_summary(item_ratings)

    return {
        "item_count": len(item_rows),
        "rating_count": sum(len(ratings) for ratings in item_ratings.values()),
        "expert_count": len(expert_ids),
        "skipped_row_count": len(skipped_rows),
        "skipped_rows": skipped_rows[:20],
        "correlation_with_mean_expert": correlation_summary(model_scores, expert_scores, include_ci=True),
        "baseline_comparison": baseline_comparison,
        "by_expert": by_expert,
        "by_expected_pattern": by_pattern,
        "inter_rater": inter_rater,
        "items": [
            {
                **item,
                "expert_mean_score": round(float(item["expert_mean_score"]), 4),
                "expert_score_std": round(float(item["expert_score_std"]), 4),
            }
            for item in item_rows
        ],
    }


def pairwise_inter_rater_summary(item_ratings: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    by_expert: dict[str, dict[str, float]] = defaultdict(dict)
    for item_key, ratings in item_ratings.items():
        for rating in ratings:
            by_expert[str(rating["expert_id"])][item_key] = float(rating["score"])

    pairwise = []
    for expert_a, expert_b in combinations(sorted(by_expert), 2):
        common_items = sorted(set(by_expert[expert_a]).intersection(by_expert[expert_b]))
        scores_a = [by_expert[expert_a][item] for item in common_items]
        scores_b = [by_expert[expert_b][item] for item in common_items]
        metrics = correlation_summary(scores_a, scores_b)
        pairwise.append(
            {
                "expert_a": expert_a,
                "expert_b": expert_b,
                **metrics,
            }
        )

    usable = [pair for pair in pairwise if pair["n"] >= 2]
    return {
        "pair_count": len(pairwise),
        "mean_pairwise_pearson": (
            round(mean(pair["pearson"] for pair in usable if pair["pearson"] is not None), 4)
            if any(pair["pearson"] is not None for pair in usable)
            else None
        ),
        "mean_pairwise_spearman": (
            round(mean(pair["spearman"] for pair in usable if pair["spearman"] is not None), 4)
            if any(pair["spearman"] is not None for pair in usable)
            else None
        ),
        "pairs": pairwise,
    }
