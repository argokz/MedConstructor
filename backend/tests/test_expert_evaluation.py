import pytest

from app.services.expert_evaluation import (
    analyze_expert_ratings,
    normalize_expert_score,
    pearson_correlation,
    spearman_correlation,
)


def _benchmark():
    return {
        "graph": {
            "results": [
                {
                    "case_id": "case_a",
                    "variant_id": "perfect",
                    "expected_pattern": "all_metrics_high",
                    "metrics": {"composite_score": 1.0},
                },
                {
                    "case_id": "case_a",
                    "variant_id": "minor",
                    "expected_pattern": "category_accuracy_drop",
                    "metrics": {"composite_score": 0.8},
                },
                {
                    "case_id": "case_a",
                    "variant_id": "major",
                    "expected_pattern": "directed_path_zero",
                    "metrics": {"composite_score": 0.6},
                },
            ]
        }
    }


def test_normalize_expert_score_accepts_0_100_and_0_1_scales():
    assert normalize_expert_score("95") == 0.95
    assert normalize_expert_score("0.75") == 0.75
    assert normalize_expert_score("") is None


def test_correlations_are_one_for_identical_order():
    xs = [1.0, 0.8, 0.6]
    ys = [100.0, 80.0, 60.0]
    normalized = [normalize_expert_score(value) for value in ys]

    assert pearson_correlation(xs, normalized) == pytest.approx(1.0)
    assert spearman_correlation(xs, normalized) == pytest.approx(1.0)


def test_analyze_expert_ratings_correlates_model_with_mean_expert_score():
    ratings = [
        {"case_id": "case_a", "variant_id": "perfect", "expert_id": "e1", "expert_score_0_100": "100"},
        {"case_id": "case_a", "variant_id": "minor", "expert_id": "e1", "expert_score_0_100": "80"},
        {"case_id": "case_a", "variant_id": "major", "expert_id": "e1", "expert_score_0_100": "60"},
        {"case_id": "case_a", "variant_id": "perfect", "expert_id": "e2", "expert_score_0_100": "90"},
        {"case_id": "case_a", "variant_id": "minor", "expert_id": "e2", "expert_score_0_100": "70"},
        {"case_id": "case_a", "variant_id": "major", "expert_id": "e2", "expert_score_0_100": "50"},
        {"case_id": "case_a", "variant_id": "major", "expert_id": "e2", "expert_score_0_100": ""},
    ]

    report = analyze_expert_ratings(_benchmark(), ratings)

    assert report["item_count"] == 3
    assert report["rating_count"] == 6
    assert report["expert_count"] == 2
    assert report["skipped_row_count"] == 1
    assert report["correlation_with_mean_expert"]["pearson"] == 1.0
    assert report["correlation_with_mean_expert"]["spearman"] == 1.0
    assert report["inter_rater"]["mean_pairwise_pearson"] == 1.0


def test_analyze_expert_ratings_can_use_blinded_review_item_key():
    key = {
        "blind_a": {"case_id": "case_a", "variant_id": "perfect"},
        "blind_b": {"case_id": "case_a", "variant_id": "minor"},
        "blind_c": {"case_id": "case_a", "variant_id": "major"},
    }
    ratings = [
        {"review_item_id": "blind_a", "expert_id": "e1", "expert_score_0_100": "100"},
        {"review_item_id": "blind_b", "expert_id": "e1", "expert_score_0_100": "80"},
        {"review_item_id": "blind_c", "expert_id": "e1", "expert_score_0_100": "60"},
    ]

    report = analyze_expert_ratings(_benchmark(), ratings, key_by_review_item=key)

    assert report["item_count"] == 3
    assert report["correlation_with_mean_expert"]["pearson"] == 1.0
