from __future__ import annotations

import math
import re
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def section_tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-zа-яё0-9]{4,}", normalize_text(value)):
        for ending in (
            "иями",
            "ями",
            "ами",
            "ого",
            "ему",
            "ыми",
            "ими",
            "ией",
            "ия",
            "ие",
            "ии",
            "ый",
            "ий",
            "ой",
            "ая",
            "ое",
            "ые",
            "ом",
            "ем",
            "ах",
            "ях",
            "а",
            "я",
            "ы",
            "и",
            "у",
            "е",
            "о",
        ):
            if len(token) - len(ending) >= 4 and token.endswith(ending):
                token = token[: -len(ending)]
                break
        if token.startswith(("диагност", "диагноз")):
            token = "диагност"
        elif token.startswith(("лечен", "терап")):
            token = "лечен"
        elif token.startswith(("наблюден", "мониторинг", "контроль")):
            token = "мониторинг"
        elif token.startswith(("госпитал", "стационар")):
            token = "госпитал"
        tokens.add(token)
    return tokens


def section_names_match(retrieved: str, expected: str) -> bool:
    normalized_retrieved = normalize_text(retrieved)
    normalized_expected = normalize_text(expected)
    if not normalized_retrieved or not normalized_expected:
        return False
    if normalized_expected in normalized_retrieved or normalized_retrieved in normalized_expected:
        return True

    expected_tokens = section_tokens(expected)
    retrieved_tokens = section_tokens(retrieved)
    if not expected_tokens or not retrieved_tokens:
        return False
    overlap = len(expected_tokens.intersection(retrieved_tokens)) / len(expected_tokens)
    return overlap >= 0.6


def find_rank(retrieved_ids: Sequence[int], expected_ids: Iterable[int]) -> int | None:
    expected = {int(item) for item in expected_ids}
    for index, protocol_id in enumerate(retrieved_ids, start=1):
        if int(protocol_id) in expected:
            return index
    return None


def recall_at(rank: int | None, k: int) -> float:
    return 1.0 if rank is not None and rank <= k else 0.0


def reciprocal_rank(rank: int | None) -> float:
    return 1.0 / rank if rank else 0.0


def section_hit_score(retrieved_sections: Sequence[str], expected_sections: Sequence[str]) -> float | None:
    if not expected_sections:
        return None

    normalized_retrieved = [normalize_text(section) for section in retrieved_sections if section]
    if not normalized_retrieved:
        return 0.0

    hits = 0
    for expected in expected_sections:
        if any(section_names_match(section, expected) for section in normalized_retrieved):
            hits += 1
    return hits / len(expected_sections)


def key_phrase_hit_score(retrieved_texts: Sequence[str], expected_key_phrases: Sequence[str]) -> float | None:
    if not expected_key_phrases:
        return None

    corpus = normalize_text(" ".join(text for text in retrieved_texts if text))
    if not corpus:
        return 0.0

    hits = 0
    for phrase in expected_key_phrases:
        normalized_phrase = normalize_text(phrase)
        if not normalized_phrase:
            continue
        if normalized_phrase in corpus:
            hits += 1
            continue

        phrase_tokens = section_tokens(normalized_phrase)
        corpus_tokens = section_tokens(corpus)
        if phrase_tokens and len(phrase_tokens.intersection(corpus_tokens)) / len(phrase_tokens) >= 0.75:
            hits += 1

    total = len([phrase for phrase in expected_key_phrases if normalize_text(phrase)])
    if total == 0:
        return None
    return hits / total


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - pos) + ordered[high] * (pos - low)


def latency_summary(latencies_ms: Sequence[float]) -> dict[str, float]:
    if not latencies_ms:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "avg": 0.0, "max": 0.0}
    values = [float(value) for value in latencies_ms]
    return {
        "min": round(min(values), 2),
        "p50": round(median(values), 2),
        "p95": round(percentile(values, 0.95), 2),
        "avg": round(mean(values), 2),
        "max": round(max(values), 2),
    }


def aggregate_rag_results(results: Sequence[Mapping[str, Any]], ks: Sequence[int] = (1, 3, 5, 10)) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "n": 0,
            "recall": {f"recall_at_{k}": 0.0 for k in ks},
            "mrr": 0.0,
            "section_hit_rate": None,
            "latency_ms": latency_summary([]),
        }

    ranks = [result.get("hit_rank") for result in results]
    recall = {
        f"recall_at_{k}": round(sum(recall_at(rank, k) for rank in ranks) / total, 4)
        for k in ks
    }
    section_scores = [
        float(result["section_hit_score"])
        for result in results
        if result.get("section_hit_score") is not None
    ]
    key_phrase_scores = [
        float(result["key_phrase_hit_score"])
        for result in results
        if result.get("key_phrase_hit_score") is not None
    ]
    return {
        "n": total,
        "recall": recall,
        "mrr": round(sum(reciprocal_rank(rank) for rank in ranks) / total, 4),
        "section_hit_rate": (
            round(sum(section_scores) / len(section_scores), 4)
            if section_scores
            else None
        ),
        "key_phrase_hit_rate": (
            round(sum(key_phrase_scores) / len(key_phrase_scores), 4)
            if key_phrase_scores
            else None
        ),
        "latency_ms": latency_summary([float(result.get("latency_ms", 0.0)) for result in results]),
        "misses": [result.get("id") for result in results if result.get("hit_rank") is None],
    }


def aggregate_graph_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "n": 0,
            "averages": {},
            "pattern_pass_rate": None,
            "by_expected_pattern": [],
            "by_case": [],
        }

    metric_names = [
        "edge_f1",
        "weighted_edge_f1",
        "node_coverage",
        "category_accuracy",
        "directed_path_completeness",
        "safety_penalty",
        "unsafe_extra_action",
        "missing_critical_action",
        "diagnostic_evidence_gap",
        "clinical_connectivity_gap",
        "composite_score",
    ]
    averages = {}
    for metric in metric_names:
        values = [
            float(result["metrics"][metric])
            for result in results
            if result.get("metrics", {}).get(metric) is not None
        ]
        averages[metric] = round(sum(values) / len(values), 4) if values else None

    pattern_results = [
        result for result in results
        if result.get("pattern_passed") is not None
    ]
    by_expected_pattern = []
    expected_patterns = sorted(
        {
            str(result.get("expected_pattern"))
            for result in pattern_results
            if result.get("expected_pattern")
        }
    )
    for pattern in expected_patterns:
        subset = [
            result for result in pattern_results
            if result.get("expected_pattern") == pattern
        ]
        passed = sum(1 for result in subset if result.get("pattern_passed") is True)
        by_expected_pattern.append(
            {
                "expected_pattern": pattern,
                "n": len(subset),
                "pass_rate": round(passed / len(subset), 4) if subset else None,
            }
        )

    return {
        "n": len(results),
        "averages": averages,
        "pattern_pass_rate": (
            round(
                sum(1 for result in pattern_results if result.get("pattern_passed") is True)
                / len(pattern_results),
                4,
            )
            if pattern_results
            else None
        ),
        "by_expected_pattern": by_expected_pattern,
        "by_case": [
            {
                "case_id": result.get("case_id"),
                "variant_id": result.get("variant_id"),
                "expected_pattern": result.get("expected_pattern"),
                "pattern_passed": result.get("pattern_passed"),
                "metrics": result.get("metrics", {}),
            }
            for result in results
        ],
    }


def aggregate_graph_quality_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "n": 0,
            "schema_valid_rate": None,
            "accepted_rate": None,
            "warning_rate": None,
            "critical_rate": None,
            "avg_quality_score": None,
        }

    total = len(results)
    qualities = [result.get("quality", {}) for result in results]
    return {
        "n": total,
        "schema_valid_rate": round(
            sum(1 for quality in qualities if quality.get("schema_valid")) / total,
            4,
        ),
        "accepted_rate": round(
            sum(1 for quality in qualities if quality.get("accepted")) / total,
            4,
        ),
        "warning_rate": round(
            sum(1 for quality in qualities if int(quality.get("warning_count") or 0) > 0) / total,
            4,
        ),
        "critical_rate": round(
            sum(1 for quality in qualities if int(quality.get("critical_count") or 0) > 0) / total,
            4,
        ),
        "avg_quality_score": round(
            sum(float(quality.get("quality_score") or 0.0) for quality in qualities) / total,
            4,
        ),
    }
