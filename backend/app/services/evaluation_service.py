from __future__ import annotations



import asyncio

import hashlib

import json

import logging
from time import perf_counter

import numpy as np

from datetime import datetime, timezone

from typing import Any, Optional



from fastapi import HTTPException

from sqlalchemy import func, select

from sqlalchemy.exc import IntegrityError

from sqlalchemy.ext.asyncio import AsyncSession



from app.config import Settings

from app.models import EvaluationSnapshot, StudentAssignmentProgress, StudentAttempt

from app.repositories.reference_graph import ReferenceGraphRepository

from app.repositories.student_attempt import StudentAttemptRepository

from app.schemas import GraphEvaluationRequest, GraphEvaluationResponse, GraphSchema

from app.services.concept_matcher import (
    ConceptMatcher,
    build_pairwise_graph_id_maps,
    collect_unique_labels,
)

from app.services.graph_evaluator import GraphEvaluator
from app.services.text_embeddings import encode_texts_sync



logger = logging.getLogger(__name__)





def _stable_hash(payload: Any) -> str:

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scoped_idempotency_key(
    idempotency_key: Optional[str], reference_content_hash: str
) -> Optional[str]:
    if not idempotency_key:
        return None
    return f"{idempotency_key}:{reference_content_hash[:16]}"





class EvaluationService:

    def __init__(self, session: AsyncSession, settings: Settings) -> None:

        self._session = session

        self._settings = settings

        self._refs = ReferenceGraphRepository(session)

        self._attempts = StudentAttemptRepository(session)



    def _validate_graph_size(self, graph: GraphSchema) -> None:

        if len(graph.nodes) > self._settings.max_graph_nodes:

            raise HTTPException(status_code=422, detail="graph exceeds max_graph_nodes")

        if len(graph.edges) > self._settings.max_graph_edges:

            raise HTTPException(status_code=422, detail="graph exceeds max_graph_edges")

    def _validate_graph_edges(self, graph: GraphSchema) -> None:
        concept_nodes = [node for node in graph.nodes if node.data.category]
        if len(concept_nodes) >= 2 and not graph.edges:
            raise HTTPException(
                status_code=422,
                detail="Добавьте связи между блоками: решение без рёбер не может быть оценено.",
            )



    async def _maybe_replay_idempotent(

        self,
        student_id: int,
        idempotency_key: Optional[str],
        reference_content_hash: Optional[str] = None,

    ) -> Optional[GraphEvaluationResponse]:

        if not idempotency_key:

            return None

        res = await self._session.execute(

            select(StudentAttempt).where(

                StudentAttempt.student_id == student_id,

                StudentAttempt.idempotency_key == idempotency_key,

            )

        )

        existing = res.scalars().first()

        if not existing or not existing.metrics:

            return None

        if (
            reference_content_hash
            and existing.reference_content_hash != reference_content_hash
        ):

            return None

        m = existing.metrics
        snapshot_res = await self._session.execute(
            select(EvaluationSnapshot)
            .where(EvaluationSnapshot.attempt_id == existing.id)
            .order_by(EvaluationSnapshot.created_at.desc(), EvaluationSnapshot.id.desc())
        )
        snapshot = snapshot_res.scalars().first()

        return GraphEvaluationResponse(

            precision=float(m.get("precision", 0.0)),

            recall=float(m.get("recall", 0.0)),

            f1_score=float(m.get("f1_score", 0.0)),

            missing_edges=list(m.get("missing_edges", [])),

            incorrect_edges=list(m.get("incorrect_edges", [])),

            composite_score=m.get("composite_score"),

            edge_f1=m.get("edge_f1"),

            weighted_precision=m.get("weighted_precision"),

            weighted_recall=m.get("weighted_recall"),

            weighted_edge_f1=m.get("weighted_edge_f1"),

            node_coverage=m.get("node_coverage"),

            chain_completeness=m.get("chain_completeness"),

            directed_path_completeness=m.get("directed_path_completeness"),

            category_accuracy=m.get("category_accuracy"),

            structural_correctness=m.get("structural_correctness"),

            safety_penalty=m.get("safety_penalty"),
            edge_count_penalty=m.get("edge_count_penalty"),
            student_edge_count=m.get("student_edge_count"),
            reference_edge_count=m.get("reference_edge_count"),
            unsafe_extra_action=m.get("unsafe_extra_action"),
            missing_critical_action=m.get("missing_critical_action"),
            diagnostic_evidence_gap=m.get("diagnostic_evidence_gap"),
            diagnostic_evidence_findings=m.get("diagnostic_evidence_findings"),
            clinical_connectivity_gap=m.get("clinical_connectivity_gap"),
            clinical_connectivity_findings=m.get("clinical_connectivity_findings"),
            score_caps=m.get("score_caps"),
            safety_findings=m.get("safety_findings"),

            missing_nodes=m.get("missing_nodes"),

            algorithm_version=m.get("algorithm_version"),
            attempt_id=existing.id,
            evaluation_snapshot_id=snapshot.id if snapshot else None,
            graph_version=snapshot.graph_version if snapshot else None,

            message="Идемпотентный повтор: возвращена сохранённая оценка.",

        )



    async def evaluate(self, request: GraphEvaluationRequest) -> GraphEvaluationResponse:

        total_started = perf_counter()
        timing_ms: dict[str, float] = {}

        self._validate_graph_size(request.student_graph)
        self._validate_graph_edges(request.student_graph)



        stage_started = perf_counter()
        ref_row = await self._refs.get_by_id(request.reference_graph_id)
        timing_ms["reference_load"] = round((perf_counter() - stage_started) * 1000, 1)

        if not ref_row:

            raise HTTPException(

                status_code=404,

                detail=f"Reference graph {request.reference_graph_id} not found",

            )



        reference_graph = GraphSchema(**ref_row.graph_data)

        reference_hash = _stable_hash(ref_row.graph_data)
        effective_idempotency_key = _scoped_idempotency_key(
            request.idempotency_key,
            reference_hash,
        )

        replay = await self._maybe_replay_idempotent(
            request.student_id,
            effective_idempotency_key,
            reference_hash,
        )

        if replay:

            return replay



        self._validate_graph_size(reference_graph)



        matcher = ConceptMatcher(
            threshold=self._settings.concept_similarity_threshold,
            embedding_model_name=self._settings.embedding_model_name,
            canonical_names=[],
            matrix=np.zeros((0, self._settings.embedding_vector_dim), dtype=np.float64),
            settings=self._settings,
        )
        labels = collect_unique_labels([request.student_graph, reference_graph])



        concept_matching_mode = "identity"

        if matcher.is_identity:

            label_map = {lbl: lbl.lower().strip() for lbl in labels}

        else:

            concept_matching_mode = "embedding"
            stage_started = perf_counter()

            try:

                vectors = await asyncio.wait_for(
                    asyncio.to_thread(matcher.encode_labels, labels),
                    timeout=max(1.0, float(self._settings.evaluation_embedding_timeout)),
                )

            except ImportError as exc:

                raise HTTPException(

                    status_code=503,

                    detail=(

                        "В БД есть medical_nodes с embedding, но не установлен sentence-transformers. "

                        "Выполните: pip install -r requirements.txt"

                    ),

                ) from exc

            except asyncio.TimeoutError:

                concept_matching_mode = "identity_timeout"
                label_map = {lbl: lbl.lower().strip() for lbl in labels}

            except Exception:

                # Embedding backend unavailable or slow (e.g. OpenAI timeout):
                # degrade gracefully to exact-label matching so the student
                # still receives a score instead of a 5xx / proxy timeout.
                concept_matching_mode = "identity_fallback"
                label_map = {lbl: lbl.lower().strip() for lbl in labels}

            else:

                label_map = matcher.label_to_canonical_batch(labels, vectors)

            timing_ms["label_embedding"] = round((perf_counter() - stage_started) * 1000, 1)



        st_map, ref_map = matcher.build_id_maps(request.student_graph, reference_graph, label_map)

        reference_label_set = {
            node.data.label.lower().strip() for node in reference_graph.nodes
        }
        has_non_exact_student_labels = any(
            node.data.label.lower().strip() not in reference_label_set
            for node in request.student_graph.nodes
        )
        concept_matching_mode = "exact_label"
        embedding_model_version = "exact_label"
        vectors = np.zeros((0, 0), dtype=np.float64)
        timing_ms["label_embedding"] = 0.0

        if has_non_exact_student_labels:
            concept_matching_mode = "embedding_pairwise"
            embedding_model_version = self._settings.embedding_model_name
            stage_started = perf_counter()
            try:
                vector_rows = await asyncio.wait_for(
                    asyncio.to_thread(encode_texts_sync, self._settings, labels),
                    timeout=max(1.0, float(self._settings.evaluation_embedding_timeout)),
                )
                vectors = np.asarray(vector_rows, dtype=np.float64)
            except asyncio.TimeoutError:
                concept_matching_mode = "identity_timeout"
                embedding_model_version = "identity"
            except Exception:
                # Exact matching is conservative; persisting the fallback mode
                # makes these attempts identifiable for later re-scoring.
                concept_matching_mode = "identity_fallback"
                embedding_model_version = "identity"
            timing_ms["label_embedding"] = round(
                (perf_counter() - stage_started) * 1000,
                1,
            )
        st_map, ref_map = build_pairwise_graph_id_maps(
            request.student_graph,
            reference_graph,
            labels,
            vectors,
            self._settings.concept_similarity_threshold,
        )



        stage_started = perf_counter()
        # Canonical maps already encode semantic equivalence, so the evaluator
        # can perform one-to-one matching without a second embedding request.
        evaluation_result = await asyncio.to_thread(

            GraphEvaluator.evaluate,

            request.student_graph,

            reference_graph,

            st_map,

            ref_map,

            {},

        )
        timing_ms["graph_scoring"] = round((perf_counter() - stage_started) * 1000, 1)
        timing_ms["compute_total"] = round((perf_counter() - total_started) * 1000, 1)



        timing_ms["total"] = round((perf_counter() - total_started) * 1000, 1)

        metrics_payload = {

            **evaluation_result,

            "evaluation_context": {

                "concept_similarity_threshold": self._settings.concept_similarity_threshold,

                "embedding_model_name": self._settings.embedding_model_name,

                "concept_matching": concept_matching_mode,

            },
            "evaluation_timing_ms": timing_ms,

        }



        attempt = StudentAttempt(

            assignment_id=request.assignment_id,

            reference_graph_id=request.reference_graph_id,

            student_id=request.student_id,

            submitted_graph=request.student_graph.model_dump(),

            metrics=metrics_payload,

            algorithm_version=evaluation_result.get("algorithm_version"),

            reference_content_hash=reference_hash,

            embedding_model_version=embedding_model_version,

            idempotency_key=effective_idempotency_key,

            review_status="needs_review",

        )

        self._attempts.add(attempt)
        await self._session.flush()
        now = datetime.now(timezone.utc)
        version_query = select(func.count(EvaluationSnapshot.id)).where(
            EvaluationSnapshot.student_id == request.student_id
        )
        if request.assignment_id is not None:
            version_query = version_query.where(EvaluationSnapshot.assignment_id == request.assignment_id)
        else:
            version_query = version_query.where(EvaluationSnapshot.reference_graph_id == request.reference_graph_id)
        version_result = await self._session.execute(version_query)
        graph_version = int(version_result.scalar_one() or 0) + 1
        recommendations_payload = {
            "missing_edges": evaluation_result.get("missing_edges", []),
            "incorrect_edges": evaluation_result.get("incorrect_edges", []),
            "missing_nodes": evaluation_result.get("missing_nodes", []),
            "safety_findings": evaluation_result.get("safety_findings", []),
            "diagnostic_evidence_findings": evaluation_result.get("diagnostic_evidence_findings", []),
            "clinical_connectivity_findings": evaluation_result.get("clinical_connectivity_findings", []),
            "score_caps": evaluation_result.get("score_caps", []),
        }
        snapshot = EvaluationSnapshot(
            attempt_id=attempt.id,
            assignment_id=request.assignment_id,
            reference_graph_id=request.reference_graph_id,
            student_id=request.student_id,
            graph_version=graph_version,
            submitted_graph=request.student_graph.model_dump(),
            metrics=metrics_payload,
            recommendations=recommendations_payload,
            algorithm_version=evaluation_result.get("algorithm_version"),
            reference_content_hash=reference_hash,
            embedding_model_version=embedding_model_version,
            created_at=now,
        )
        self._session.add(snapshot)
        await self._session.flush()
        if request.assignment_id:
            progress_row = await self._session.execute(
                select(StudentAssignmentProgress)
                .where(StudentAssignmentProgress.assignment_id == request.assignment_id)
                .where(StudentAssignmentProgress.student_id == request.student_id)
            )
            progress = progress_row.scalars().first()
            if progress:
                progress.status = "submitted"
                progress.latest_attempt_id = attempt.id
                progress.submitted_at = now
                progress.completed_at = None
                progress.started_at = progress.started_at or now
            else:
                self._session.add(
                    StudentAssignmentProgress(
                        assignment_id=request.assignment_id,
                        student_id=request.student_id,
                        status="submitted",
                        latest_attempt_id=attempt.id,
                        started_at=now,
                        submitted_at=now,
                    )
                )

        try:

            await self._session.commit()

        except IntegrityError:

            await self._session.rollback()

            logger.warning("idempotency conflict, replaying existing attempt")

            replay = await self._maybe_replay_idempotent(
                request.student_id,
                effective_idempotency_key,
                reference_hash,
            )

            if replay:

                return replay

            raise



        composite = evaluation_result.get("composite_score", evaluation_result["f1_score"])
        response_timing = dict(timing_ms)

        return GraphEvaluationResponse(

            precision=evaluation_result["precision"],

            recall=evaluation_result["recall"],

            f1_score=evaluation_result["f1_score"],

            missing_edges=evaluation_result["missing_edges"],

            incorrect_edges=evaluation_result["incorrect_edges"],

            composite_score=composite,

            edge_f1=evaluation_result.get("edge_f1"),

            weighted_precision=evaluation_result.get("weighted_precision"),

            weighted_recall=evaluation_result.get("weighted_recall"),

            weighted_edge_f1=evaluation_result.get("weighted_edge_f1"),

            node_coverage=evaluation_result.get("node_coverage"),

            chain_completeness=evaluation_result.get("chain_completeness"),

            directed_path_completeness=evaluation_result.get("directed_path_completeness"),

            category_accuracy=evaluation_result.get("category_accuracy"),

            structural_correctness=evaluation_result.get("structural_correctness"),

            safety_penalty=evaluation_result.get("safety_penalty"),
            edge_count_penalty=evaluation_result.get("edge_count_penalty"),
            student_edge_count=evaluation_result.get("student_edge_count"),
            reference_edge_count=evaluation_result.get("reference_edge_count"),
            unsafe_extra_action=evaluation_result.get("unsafe_extra_action"),
            missing_critical_action=evaluation_result.get("missing_critical_action"),
            diagnostic_evidence_gap=evaluation_result.get("diagnostic_evidence_gap"),
            diagnostic_evidence_findings=evaluation_result.get("diagnostic_evidence_findings"),
            clinical_connectivity_gap=evaluation_result.get("clinical_connectivity_gap"),
            clinical_connectivity_findings=evaluation_result.get("clinical_connectivity_findings"),
            score_caps=evaluation_result.get("score_caps"),
            safety_findings=evaluation_result.get("safety_findings"),

            missing_nodes=evaluation_result.get("missing_nodes"),

            algorithm_version=evaluation_result.get("algorithm_version"),
            attempt_id=attempt.id,
            evaluation_snapshot_id=snapshot.id,
            graph_version=graph_version,
            evaluation_timing_ms=response_timing,

            message="Граф успешно проверен!",

        )

