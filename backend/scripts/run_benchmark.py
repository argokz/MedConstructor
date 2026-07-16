from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

import app.services.graph_evaluator as graph_evaluator_module
from app.database import AsyncSessionLocal
from app.schemas import GraphSchema
from app.services.benchmarking import (
    aggregate_graph_quality_results,
    aggregate_graph_results,
    aggregate_rag_results,
    find_rank,
    key_phrase_hit_score,
    section_hit_score,
)
from app.services.graph_evaluator import GraphEvaluator
from app.services.graph_generation_judge import judge_reference_graph
from app.services.rag_service import RAGService, _extract_section_prefix

RAG_MODES = ("dense_only", "dense_rerank", "full")

GRAPH_METRIC_KEYS = (
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


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _section_prefix(text: str) -> str:
    section = _extract_section_prefix(text)
    if section:
        return section
    match = re.match(r"\[Секция:\s*([^\]]+)\]", text or "")
    return match.group(1).strip() if match else ""


def _node_category(node: Mapping[str, Any]) -> str:
    return str(node.get("data", {}).get("category") or node.get("type") or "").upper()


def _node_ids_by_category(graph: Mapping[str, Any], categories: set[str]) -> set[str]:
    return {
        str(node.get("id"))
        for node in graph.get("nodes", [])
        if _node_category(node) in categories
    }


def _remove_category(graph: dict[str, Any], category: str) -> dict[str, Any]:
    blocked = _node_ids_by_category(graph, {category.upper()})
    graph["nodes"] = [node for node in graph.get("nodes", []) if str(node.get("id")) not in blocked]
    graph["edges"] = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("source")) not in blocked and str(edge.get("target")) not in blocked
    ]
    return graph


def _remove_categories(graph: dict[str, Any], categories: list[str]) -> dict[str, Any]:
    blocked = _node_ids_by_category(graph, {category.upper() for category in categories})
    graph["nodes"] = [node for node in graph.get("nodes", []) if str(node.get("id")) not in blocked]
    graph["edges"] = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("source")) not in blocked and str(edge.get("target")) not in blocked
    ]
    return graph


def _remove_edge_id(graph: dict[str, Any], edge_id: str) -> dict[str, Any]:
    graph["edges"] = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("id")) != edge_id
    ]
    return graph


def _change_node_category(graph: dict[str, Any], node_id: str, category: str) -> dict[str, Any]:
    for node in graph.get("nodes", []):
        if str(node.get("id")) == node_id:
            node.setdefault("data", {})["category"] = category
            break
    return graph


def _replace_edge_label(graph: dict[str, Any], edge_id: str, label: str) -> dict[str, Any]:
    for edge in graph.get("edges", []):
        if str(edge.get("id")) == edge_id:
            edge["label"] = label
            break
    return graph


def _add_unsafe_medication(graph: dict[str, Any]) -> dict[str, Any]:
    diagnosis_ids = _node_ids_by_category(graph, {"DIAGNOSIS"})
    source = sorted(diagnosis_ids)[0] if diagnosis_ids else None
    if not source:
        return graph

    unsafe_id = "unsafe_med"
    existing_ids = {str(node.get("id")) for node in graph.get("nodes", [])}
    suffix = 2
    while unsafe_id in existing_ids:
        unsafe_id = f"unsafe_med_{suffix}"
        suffix += 1

    graph.setdefault("nodes", []).append(
        {
            "id": unsafe_id,
            "type": "med",
            "position": {"x": 0.0, "y": 0.0},
            "data": {"label": "Ингибитор АПФ", "category": "MEDICATION"},
        }
    )
    graph.setdefault("edges", []).append(
        {
            "id": f"edge_{unsafe_id}",
            "source": source,
            "target": unsafe_id,
            "label": "INDICATED_FOR",
        }
    )
    return graph


def _remove_edges_from_categories(graph: dict[str, Any], categories: list[str]) -> dict[str, Any]:
    source_ids = _node_ids_by_category(graph, {category.upper() for category in categories})
    graph["edges"] = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("source")) not in source_ids
    ]
    return graph


def _apply_variant_operation(reference_graph: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    graph = deepcopy(reference_graph)
    operation = variant.get("operation")
    if not operation:
        return graph

    if operation == "remove_category":
        return _remove_category(graph, str(variant["category"]))
    if operation == "remove_categories":
        return _remove_categories(graph, list(variant.get("categories", [])))
    if operation == "remove_edge_id":
        return _remove_edge_id(graph, str(variant["edge_id"]))
    if operation == "change_node_category":
        return _change_node_category(graph, str(variant["node_id"]), str(variant["category"]))
    if operation == "replace_edge_label":
        return _replace_edge_label(graph, str(variant["edge_id"]), str(variant["label"]))
    if operation == "add_unsafe_medication":
        return _add_unsafe_medication(graph)
    if operation == "remove_edges_from_categories":
        return _remove_edges_from_categories(graph, list(variant.get("source_categories", [])))
    raise ValueError(f"Unknown graph benchmark operation: {operation}")


def _student_graph_payload(reference_graph: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    explicit = variant.get("student_graph")
    if explicit == "__same_as_reference__":
        return deepcopy(reference_graph)
    if isinstance(explicit, dict):
        return deepcopy(explicit)
    return _apply_variant_operation(reference_graph, variant)


def _graph_pattern_check(pattern: str | None, metrics: Mapping[str, Any]) -> dict[str, Any]:
    if not pattern:
        return {"passed": None, "reason": "No expected_pattern provided."}

    composite = float(metrics.get("composite_score") or 0.0)
    weighted_edge_f1 = float(metrics.get("weighted_edge_f1") or 0.0)
    node_coverage = float(metrics.get("node_coverage") or 0.0)
    category_accuracy = float(metrics.get("category_accuracy") or 0.0)
    directed_path = float(metrics.get("directed_path_completeness") or 0.0)
    unsafe_extra = float(metrics.get("unsafe_extra_action") or 0.0)
    missing_critical = float(metrics.get("missing_critical_action") or 0.0)
    safety_penalty = float(metrics.get("safety_penalty") or 0.0)

    checks = {
        "all_metrics_high": (
            composite >= 0.95
            and weighted_edge_f1 >= 0.95
            and node_coverage >= 0.95
            and category_accuracy >= 0.95
            and directed_path >= 0.95
            and safety_penalty == 0.0,
            "Expected a near-perfect graph with no safety penalty.",
        ),
        "recall_and_node_coverage_drop": (
            node_coverage < 0.95 and composite < 0.95,
            "Expected missing clinical content to reduce node coverage and composite score.",
        ),
        "category_accuracy_drop": (
            category_accuracy < 0.95 and composite < 1.0,
            "Expected a wrong node category to reduce category-aware metrics.",
        ),
        "critical_relation_penalty": (
            weighted_edge_f1 < 0.95 and composite < 0.90,
            "Expected an incorrect critical relation to reduce weighted edge F1 and composite score.",
        ),
        "unsafe_extra_action_cap": (
            unsafe_extra > 0.0 and composite <= 0.75,
            "Expected an extra unsafe action to trigger the hard score cap.",
        ),
        "directed_path_zero": (
            directed_path <= 0.05 and composite < 0.85,
            "Expected a broken clinical chain to collapse directed path completeness.",
        ),
        "directed_path_drop": (
            directed_path < 0.95 and composite < 0.95,
            "Expected a broken clinical chain to reduce directed path completeness.",
        ),
        "missing_critical_action_penalty": (
            missing_critical > 0.0 and composite <= 0.85,
            "Expected a missing critical treatment or contraindication edge to be penalized.",
        ),
    }
    passed, reason = checks.get(
        pattern,
        (None, f"No benchmark assertion is defined for expected_pattern={pattern!r}."),
    )
    return {"passed": passed, "reason": reason}


def run_graph_benchmark(path: Path, limit: int | None = None, use_embeddings: bool = False) -> dict[str, Any]:
    if not use_embeddings:
        graph_evaluator_module._compute_node_embeddings = lambda *_: {}

    cases = _read_json(path)
    if limit:
        cases = cases[:limit]

    results: list[dict[str, Any]] = []
    reference_quality_results: list[dict[str, Any]] = []
    for case in cases:
        reference_payload = case["reference_graph"]
        reference_graph = GraphSchema.model_validate(reference_payload)
        reference_quality = judge_reference_graph(reference_graph)
        reference_quality_results.append(
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "quality": reference_quality,
            }
        )

        for variant in case.get("variants", []):
            student_payload = _student_graph_payload(reference_payload, variant)
            student_graph = GraphSchema.model_validate(student_payload)

            t0 = time.perf_counter()
            evaluation = GraphEvaluator.evaluate(student_graph, reference_graph)
            latency_ms = (time.perf_counter() - t0) * 1000
            metrics = {
                key: evaluation.get(key)
                for key in GRAPH_METRIC_KEYS
            }
            pattern_check = _graph_pattern_check(variant.get("expected_pattern"), metrics)

            results.append(
                {
                    "case_id": case.get("case_id"),
                    "variant_id": variant.get("variant_id"),
                    "expected_pattern": variant.get("expected_pattern"),
                    "pattern_passed": pattern_check["passed"],
                    "pattern_reason": pattern_check["reason"],
                    "latency_ms": round(latency_ms, 2),
                    "metrics": metrics,
                    "missing_edges_count": len(evaluation.get("missing_edges") or []),
                    "incorrect_edges_count": len(evaluation.get("incorrect_edges") or []),
                    "missing_nodes_count": len(evaluation.get("missing_nodes") or []),
                    "safety_findings": evaluation.get("safety_findings") or [],
                    "algorithm_version": evaluation.get("algorithm_version"),
                }
            )

    return {
        "summary": aggregate_graph_results(results),
        "reference_quality": {
            "summary": aggregate_graph_quality_results(reference_quality_results),
            "results": reference_quality_results,
        },
        "results": results,
    }


async def run_rag_benchmark(path: Path, limit: int | None = None) -> dict[str, Any]:
    cases = _read_json(path)
    if limit:
        cases = cases[:limit]

    async with AsyncSessionLocal() as session:
        return await _run_rag_cases(session, cases, mode="full")


async def _retrieve_rag_rows(
    service: RAGService,
    query: str,
    retrieve_limit: int,
    mode: str,
    protocol_id: int | None = None,
    protocol_ids: list[int] | None = None,
):
    if mode == "full":
        return await service.retrieve_chunks(
            query=query,
            limit=retrieve_limit,
            protocol_id=protocol_id,
            protocol_ids=protocol_ids,
        )

    query_embedding = await service.get_embedding(query, protocol_id)

    if mode == "dense_only":
        rows = await service._vector_search_with_titles(
            query_embedding,
            limit=retrieve_limit,
            protocol_id=protocol_id,
            protocol_ids=protocol_ids,
        )
        return [(chunk, title) for chunk, title, _ in rows]

    if mode == "dense_rerank":
        retrieve_k = max(retrieve_limit * 5, 32) if protocol_id else max(retrieve_limit * 6, 80)
        final_k = min(retrieve_limit, 10) if protocol_id else retrieve_limit
        candidates = await service._vector_search_with_titles(
            query_embedding,
            limit=retrieve_k,
            protocol_id=protocol_id,
            protocol_ids=protocol_ids,
        )
        ranked = service._dedup_and_rerank(candidates, query, final_k)
        return [(chunk, title) for chunk, title, _ in ranked]

    raise ValueError(f"Unknown RAG benchmark mode: {mode}")


async def _run_rag_cases(
    session,
    cases: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    service = RAGService(session)
    for case in cases:
        query = str(case["query"])
        retrieve_limit = int(case.get("limit", 10))

        t0 = time.perf_counter()
        rows = await _retrieve_rag_rows(
            service=service,
            query=query,
            retrieve_limit=retrieve_limit,
            mode=mode,
            protocol_id=case.get("protocol_id"),
            protocol_ids=case.get("protocol_ids"),
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        protocol_ids = [int(chunk.protocol_id) for chunk, _ in rows]
        sections = [_section_prefix(chunk.text_content) for chunk, _ in rows]
        retrieved_texts = [f"{title}\n{chunk.text_content}" for chunk, title in rows]
        hit_rank = find_rank(protocol_ids, case.get("expected_protocol_ids", []))

        meta = case.get("metadata") or {}
        source_bucket = "auto" if meta.get("requires_expert_review") else "curated"

        results.append(
            {
                "id": case.get("id"),
                "query": query,
                "mode": mode,
                "source": meta.get("source"),
                "source_bucket": source_bucket,
                "latency_ms": round(latency_ms, 2),
                "hit_rank": hit_rank,
                "section_hit_score": section_hit_score(
                    sections,
                    case.get("expected_sections", []),
                ),
                "key_phrase_hit_score": key_phrase_hit_score(
                    retrieved_texts,
                    case.get("expected_key_phrases", []),
                ),
                "expected_protocol_ids": case.get("expected_protocol_ids", []),
                "expected_key_phrases": case.get("expected_key_phrases", []),
                "retrieved_protocol_ids": protocol_ids,
                "retrieved_sections": sections,
                "sources": [
                    {
                        "protocol_id": int(chunk.protocol_id),
                        "protocol_title": title,
                        "section": section,
                        "chunk_index": int(chunk.chunk_index),
                        "preview": " ".join(chunk.text_content.split())[:240],
                    }
                    for (chunk, title), section in zip(rows[:5], sections[:5])
                ],
            }
        )

    curated = [r for r in results if r.get("source_bucket") == "curated"]
    auto = [r for r in results if r.get("source_bucket") == "auto"]
    summary_by_source = {}
    if curated:
        summary_by_source["curated"] = {"n": len(curated), **aggregate_rag_results(curated)}
    if auto:
        summary_by_source["auto"] = {"n": len(auto), **aggregate_rag_results(auto)}

    return {
        "mode": mode,
        "summary": aggregate_rag_results(results),
        "summary_by_source": summary_by_source,
        "results": results,
    }


async def run_rag_ablation(path: Path, limit: int | None = None) -> dict[str, Any]:
    cases = _read_json(path)
    if limit:
        cases = cases[:limit]

    async with AsyncSessionLocal() as session:
        by_mode = {}
        for mode in RAG_MODES:
            by_mode[mode] = await _run_rag_cases(session, cases, mode=mode)
    return {
        "modes": list(RAG_MODES),
        "summary_by_mode": {
            mode: result["summary"]
            for mode, result in by_mode.items()
        },
        # Honest split for the production pipeline: curated (expert-verified) vs
        # auto-generated (expectations derived from the DB, requires_expert_review).
        "summary_by_source_full": by_mode.get("full", {}).get("summary_by_source", {}),
        "by_mode": by_mode,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run RAG and graph-evaluation benchmarks.")
    parser.add_argument("--rag", default="benchmarks/rag_queries.seed.json", help="RAG seed JSON path.")
    parser.add_argument("--graph", default="benchmarks/graph_cases.seed.json", help="Graph seed JSON path.")
    parser.add_argument("--out", default=None, help="Optional output JSON path.")
    parser.add_argument("--skip-rag", action="store_true", help="Skip RAG retrieval benchmark.")
    parser.add_argument("--skip-graph", action="store_true", help="Skip graph-evaluator benchmark.")
    parser.add_argument("--rag-ablation", action="store_true", help="Run dense-only, dense-rerank and full RAG modes.")
    parser.add_argument("--limit", type=int, default=None, help="Limit cases per benchmark.")
    parser.add_argument(
        "--use-embeddings",
        action="store_true",
        help="Allow graph evaluator to call external embeddings for semantic node matching.",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> dict[str, Any]:
    if args.skip_rag and args.skip_graph:
        raise SystemExit("Nothing to run: both --skip-rag and --skip-graph were provided.")

    output: dict[str, Any] = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if not args.skip_graph:
        output["graph"] = run_graph_benchmark(
            path=(BACKEND_ROOT / args.graph).resolve(),
            limit=args.limit,
            use_embeddings=args.use_embeddings,
        )
    if not args.skip_rag:
        if args.rag_ablation:
            output["rag_ablation"] = await run_rag_ablation(
                path=(BACKEND_ROOT / args.rag).resolve(),
                limit=args.limit,
            )
        else:
            output["rag"] = await run_rag_benchmark(
                path=(BACKEND_ROOT / args.rag).resolve(),
                limit=args.limit,
            )
    return output


def main() -> None:
    args = _build_parser().parse_args()
    output = asyncio.run(_main_async(args))
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    print(rendered)

    if args.out:
        out_path = (BACKEND_ROOT / args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
