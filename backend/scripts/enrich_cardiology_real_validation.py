from __future__ import annotations

import argparse
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

from app.services.expert_evaluation import baseline_comparison_rows, correlation_summary


DEFAULT_INPUT = BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_validation_latest.json"


def _metric_keys() -> tuple[str, ...]:
    return (
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
    )


def _normalize_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in results:
        if row.get("metrics"):
            normalized.append(row)
            continue
        metrics = {key: row.get(key) for key in _metric_keys() if key in row}
        normalized.append({**row, "metrics": metrics})
    return normalized


def enrich_payload(payload: dict[str, Any]) -> dict[str, Any]:
    item_rows = payload.get("expert_items") or payload.get("items") or []
    results = payload.get("results") or payload.get("graph", {}).get("results") or []
    if not isinstance(item_rows, list) or not isinstance(results, list):
        raise ValueError("Artifact must contain list fields `expert_items` and `results`.")

    paired = [
        item
        for item in item_rows
        if item.get("model_score") is not None and item.get("expert_mean_score") is not None
    ]
    model_scores = [float(item["model_score"]) for item in paired]
    expert_scores = [float(item["expert_mean_score"]) for item in paired]
    correlation = correlation_summary(model_scores, expert_scores, include_ci=True)
    baselines = baseline_comparison_rows(
        {"graph": {"results": _normalize_results(results)}},
        paired,
    )

    summary = dict(payload.get("summary") or {})
    summary.update(
        {
            "expert_pearson": correlation.get("pearson"),
            "expert_pearson_ci_low": correlation.get("pearson_ci_low"),
            "expert_pearson_ci_high": correlation.get("pearson_ci_high"),
            "expert_spearman": correlation.get("spearman"),
            "expert_spearman_ci_low": correlation.get("spearman_ci_low"),
            "expert_spearman_ci_high": correlation.get("spearman_ci_high"),
            "expert_kendall_tau_a": correlation.get("kendall_tau_a"),
            "expert_kendall_tau_a_ci_low": correlation.get("kendall_tau_a_ci_low"),
            "expert_kendall_tau_a_ci_high": correlation.get("kendall_tau_a_ci_high"),
            "expert_mae": correlation.get("mae"),
            "expert_mae_ci_low": correlation.get("mae_ci_low"),
            "expert_mae_ci_high": correlation.get("mae_ci_high"),
            "expert_rmse": correlation.get("rmse"),
            "expert_rmse_ci_low": correlation.get("rmse_ci_low"),
            "expert_rmse_ci_high": correlation.get("rmse_ci_high"),
            "expert_bias": correlation.get("bias"),
            "expert_bias_ci_low": correlation.get("bias_ci_low"),
            "expert_bias_ci_high": correlation.get("bias_ci_high"),
        }
    )
    correct_reference_items = [
        item
        for item in paired
        if item.get("variant_id") == "correct_reference_solution"
    ]
    non_reference_items = [
        item
        for item in paired
        if item.get("variant_id") != "correct_reference_solution"
    ]
    reference_audit_cases = [
        {
            "case_id": item.get("case_id"),
            "expert_mean_score": item.get("expert_mean_score"),
            "model_score": item.get("model_score"),
            "rating_count": item.get("expert_rating_count"),
            "audit_required": True,
            "recommended_action": (
                "Teacher or clinical expert should revise the reference graph before "
                "using this case as publication-grade validation evidence."
            ),
        }
        for item in correct_reference_items
        if float(item.get("expert_mean_score") or 0.0) < 0.85
    ]
    if correct_reference_items:
        summary.update(
            {
                "reference_correct_count": len(correct_reference_items),
                "reference_correct_mean_expert": round(
                    sum(float(item.get("expert_mean_score") or 0.0) for item in correct_reference_items)
                    / len(correct_reference_items),
                    4,
                ),
                "reference_correct_audit_required_count": len(reference_audit_cases),
                "reference_correct_audit_required_rate": round(
                    len(reference_audit_cases) / len(correct_reference_items),
                    4,
                ),
            }
        )
    if non_reference_items:
        non_reference_correlation = correlation_summary(
            [float(item["model_score"]) for item in non_reference_items],
            [float(item["expert_mean_score"]) for item in non_reference_items],
            include_ci=True,
        )
        summary.update(
            {
                "student_variant_expert_spearman": non_reference_correlation.get("spearman"),
                "student_variant_expert_spearman_ci_low": non_reference_correlation.get("spearman_ci_low"),
                "student_variant_expert_spearman_ci_high": non_reference_correlation.get("spearman_ci_high"),
                "student_variant_expert_mae": non_reference_correlation.get("mae"),
                "student_variant_expert_bias": non_reference_correlation.get("bias"),
            }
        )
    non_composite = [row for row in baselines if row.get("model") != "composite_v4_3"]
    best_baseline = max(non_composite, key=lambda row: float(row.get("spearman") or -1.0), default={})
    if best_baseline:
        summary.update(
            {
                "baseline_best_non_composite_model": best_baseline.get("model"),
                "baseline_best_non_composite_spearman": best_baseline.get("spearman"),
                "baseline_composite_delta_spearman_vs_best_baseline": (
                    round(float(correlation["spearman"]) - float(best_baseline["spearman"]), 4)
                    if correlation.get("spearman") is not None and best_baseline.get("spearman") is not None
                    else None
                ),
                "baseline_composite_delta_mae_vs_best_baseline": (
                    round(float(correlation["mae"]) - float(best_baseline["mae"]), 4)
                    if correlation.get("mae") is not None and best_baseline.get("mae") is not None
                    else None
                ),
            }
        )

    payload["summary"] = summary
    payload["reference_audit"] = {
        "criterion": "correct_reference_solution expert_mean_score < 0.85",
        "interpretation": (
            "A correct/reference graph below this threshold should be reviewed by a teacher or "
            "clinical expert before the case is used as validation evidence or assigned to students."
        ),
        "cases": reference_audit_cases,
        "reference_quality_items": [
            {
                "case_id": item.get("case_id"),
                "expert_mean_score": item.get("expert_mean_score"),
                "model_score": item.get("model_score"),
                "rating_count": item.get("expert_rating_count"),
                "audit_required": float(item.get("expert_mean_score") or 0.0) < 0.85,
            }
            for item in correct_reference_items
        ],
    }
    payload["correlation_with_mean_expert"] = correlation
    payload["baseline_comparison"] = baselines
    payload["statistical_methodology"] = {
        "confidence_intervals": "95% non-parametric bootstrap over evaluated graph variants; deterministic seed 20260618.",
        "baseline_models": [
            "edge_f1_baseline",
            "weighted_edge_f1_only",
            "node_coverage_only",
            "category_accuracy_only",
            "directed_path_only",
            "safety_adjusted_weighted_edge_f1",
        ],
        "primary_model": "composite_v4_3",
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Add CI and baseline-comparison tables to the real cardiology validation artifact.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="JSON artifact to enrich.")
    parser.add_argument("--output", default=None, help="Output path. Defaults to overwriting --input.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else input_path
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    enriched = enrich_payload(payload)
    output_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output_path),
                "baseline_rows": len(enriched.get("baseline_comparison") or []),
                "spearman": enriched.get("summary", {}).get("expert_spearman"),
                "spearman_ci": [
                    enriched.get("summary", {}).get("expert_spearman_ci_low"),
                    enriched.get("summary", {}).get("expert_spearman_ci_high"),
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
