from app.services.benchmarking import (
    aggregate_graph_quality_results,
    aggregate_graph_results,
    aggregate_rag_results,
    find_rank,
    key_phrase_hit_score,
    reciprocal_rank,
    section_names_match,
    section_hit_score,
)


def test_find_rank_and_reciprocal_rank():
    assert find_rank([3, 9, 11], [11, 12]) == 3
    assert find_rank([3, 9, 11], [1, 2]) is None
    assert reciprocal_rank(4) == 0.25
    assert reciprocal_rank(None) == 0.0


def test_section_hit_score_matches_partial_section_names():
    score = section_hit_score(
        ["Диагностика и обследование", "Лечение"],
        ["Диагностика", "Госпитализация", "Лечение"],
    )
    assert score == 2 / 3


def test_section_names_match_handles_russian_word_forms():
    assert section_names_match("Наблюдение за состоянием плода", "Наблюдение за плодом")
    assert section_names_match("Лечение (стационар)", "Лечение")
    assert section_names_match("Дифференциальный диагноз", "Диагностика")
    assert not section_names_match("Краткое описание", "Госпитализация")


def test_key_phrase_hit_score_matches_substrings():
    score = key_phrase_hit_score(
        [
            "Protocol: anaphylactic shock. Emergency care includes adrenaline."
        ],
        ["anaphylactic shock", "adrenaline", "hospitalization"],
    )

    assert score == 2 / 3


def test_aggregate_rag_results_reports_recall_mrr_latency_and_misses():
    summary = aggregate_rag_results(
        [
            {"id": "a", "hit_rank": 1, "section_hit_score": 1.0, "key_phrase_hit_score": 1.0, "latency_ms": 100},
            {"id": "b", "hit_rank": 4, "section_hit_score": 0.5, "key_phrase_hit_score": 0.5, "latency_ms": 200},
            {"id": "c", "hit_rank": None, "section_hit_score": None, "latency_ms": 300},
        ],
        ks=(1, 3, 5),
    )

    assert summary["n"] == 3
    assert summary["recall"] == {
        "recall_at_1": 0.3333,
        "recall_at_3": 0.3333,
        "recall_at_5": 0.6667,
    }
    assert summary["mrr"] == 0.4167
    assert summary["section_hit_rate"] == 0.75
    assert summary["key_phrase_hit_rate"] == 0.75
    assert summary["latency_ms"]["p50"] == 200.0
    assert summary["misses"] == ["c"]


def test_aggregate_graph_results_averages_core_metrics():
    summary = aggregate_graph_results(
        [
            {
                "case_id": "case",
                "variant_id": "perfect",
                "expected_pattern": "all_metrics_high",
                "pattern_passed": True,
                "metrics": {
                    "edge_f1": 1.0,
                    "weighted_edge_f1": 1.0,
                    "node_coverage": 1.0,
                    "category_accuracy": 1.0,
                    "directed_path_completeness": 1.0,
                    "safety_penalty": 0.0,
                    "unsafe_extra_action": 0.0,
                    "missing_critical_action": 0.0,
                    "composite_score": 1.0,
                },
            },
            {
                "case_id": "case",
                "variant_id": "unsafe",
                "expected_pattern": "unsafe_extra_action_cap",
                "pattern_passed": True,
                "metrics": {
                    "edge_f1": 0.8,
                    "weighted_edge_f1": 0.7,
                    "node_coverage": 1.0,
                    "category_accuracy": 1.0,
                    "directed_path_completeness": 1.0,
                    "safety_penalty": 1.0,
                    "unsafe_extra_action": 1.0,
                    "missing_critical_action": 0.0,
                    "composite_score": 0.52,
                },
            },
        ]
    )

    assert summary["n"] == 2
    assert summary["averages"]["edge_f1"] == 0.9
    assert summary["averages"]["weighted_edge_f1"] == 0.85
    assert summary["averages"]["safety_penalty"] == 0.5
    assert summary["averages"]["composite_score"] == 0.76
    assert summary["pattern_pass_rate"] == 1.0
    assert summary["by_expected_pattern"] == [
        {"expected_pattern": "all_metrics_high", "n": 1, "pass_rate": 1.0},
        {"expected_pattern": "unsafe_extra_action_cap", "n": 1, "pass_rate": 1.0},
    ]
    assert summary["by_case"][1]["variant_id"] == "unsafe"
    assert summary["by_case"][1]["pattern_passed"] is True


def test_aggregate_graph_quality_results_reports_acceptance_and_warning_rates():
    summary = aggregate_graph_quality_results(
        [
            {
                "case_id": "ok",
                "quality": {
                    "schema_valid": True,
                    "accepted": True,
                    "warning_count": 0,
                    "critical_count": 0,
                    "quality_score": 1.0,
                },
            },
            {
                "case_id": "bad",
                "quality": {
                    "schema_valid": True,
                    "accepted": False,
                    "warning_count": 2,
                    "critical_count": 1,
                    "quality_score": 0.6,
                },
            },
        ]
    )

    assert summary["n"] == 2
    assert summary["schema_valid_rate"] == 1.0
    assert summary["accepted_rate"] == 0.5
    assert summary["warning_rate"] == 0.5
    assert summary["critical_rate"] == 0.5
    assert summary["avg_quality_score"] == 0.8
