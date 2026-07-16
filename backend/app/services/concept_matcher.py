from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import MedicalNode
from app.schemas import GraphSchema
from app.services.text_embeddings import encode_texts_sync


_CORPUS_CACHE: dict[str, tuple[float, tuple[str, ...], np.ndarray]] = {}


def _normalize_fallback(label: str) -> str:
    return label.lower().strip()


@dataclass
class ConceptMatcher:
    """Maps free-text labels to canonical `MedicalNode.name` using cosine similarity."""

    threshold: float
    embedding_model_name: str
    canonical_names: List[str]
    matrix: np.ndarray  # L2-normalized rows (n, d), or shape (0, d)
    settings: Settings

    @property
    def is_identity(self) -> bool:
        return self.matrix.shape[0] == 0

    @property
    def embedding_model_version(self) -> str:
        return "identity" if self.is_identity else self.embedding_model_name

    @classmethod
    async def from_session(cls, session: AsyncSession, settings: Settings) -> ConceptMatcher:
        cache_key = f"{settings.embedding_model_name}|{settings.embedding_vector_dim}"
        ttl = max(0.0, float(settings.concept_matcher_cache_ttl_seconds))
        cached = _CORPUS_CACHE.get(cache_key)
        if cached and monotonic() - cached[0] <= ttl:
            names = list(cached[1])
            mat = cached[2]
        else:
            result = await session.execute(
                select(MedicalNode.name, MedicalNode.embedding)
                .where(MedicalNode.embedding.is_not(None))
            )
            rows = list(result.all())
            names = [str(row[0]) for row in rows]
            if rows:
                mat = np.asarray([list(row[1]) for row in rows], dtype=np.float64)
                norms = np.linalg.norm(mat, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                mat = mat / norms
                mat.setflags(write=False)
            else:
                mat = np.zeros((0, settings.embedding_vector_dim), dtype=np.float64)
            _CORPUS_CACHE[cache_key] = (monotonic(), tuple(names), mat)

        if not names:
            return cls(
                threshold=settings.concept_similarity_threshold,
                embedding_model_name=settings.embedding_model_name,
                canonical_names=[],
                matrix=np.zeros((0, settings.embedding_vector_dim), dtype=np.float64),
                settings=settings,
            )
        return cls(
            threshold=settings.concept_similarity_threshold,
            embedding_model_name=settings.embedding_model_name,
            canonical_names=names,
            matrix=mat,
            settings=settings,
        )

    def encode_labels(self, labels: Sequence[str]) -> np.ndarray:
        """Sync CPU/GPU-heavy call — run via asyncio.to_thread from the service layer."""
        if self.is_identity:
            return np.zeros((0, 0), dtype=np.float64)
        rows = encode_texts_sync(self.settings, list(labels))
        return np.asarray(rows, dtype=np.float64)

    def label_to_canonical_batch(
        self, labels: Sequence[str], vectors: np.ndarray
    ) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if self.is_identity or vectors.size == 0:
            for lbl in labels:
                out[lbl] = _normalize_fallback(lbl)
            return out

        sims = vectors @ self.matrix.T
        for i, lbl in enumerate(labels):
            row = sims[i]
            j = int(np.argmax(row))
            score = float(row[j])
            if score >= self.threshold:
                out[lbl] = self.canonical_names[j]
            else:
                out[lbl] = _normalize_fallback(lbl)
        return out

    def build_id_maps(
        self,
        student: GraphSchema,
        reference: GraphSchema,
        label_to_canonical: Dict[str, str],
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        st = {
            n.id: label_to_canonical.get(n.data.label, _normalize_fallback(n.data.label))
            for n in student.nodes
        }
        ref = {
            n.id: label_to_canonical.get(n.data.label, _normalize_fallback(n.data.label))
            for n in reference.nodes
        }
        return st, ref


def collect_unique_labels(graphs: Iterable[GraphSchema]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for g in graphs:
        for n in g.nodes:
            if n.data.label not in seen:
                seen.add(n.data.label)
                ordered.append(n.data.label)
    return ordered


def build_pairwise_graph_id_maps(
    student: GraphSchema,
    reference: GraphSchema,
    labels: Sequence[str],
    vectors: np.ndarray,
    threshold: float,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Map student concepts directly to concepts in the current reference graph."""
    label_indices = {
        _normalize_fallback(label): index for index, label in enumerate(labels)
    }
    reference_canonical = {
        node.id: _normalize_fallback(node.data.label) for node in reference.nodes
    }
    student_canonical: Dict[str, str] = {}

    if vectors.size == 0 or vectors.shape[0] != len(labels):
        return (
            {node.id: _normalize_fallback(node.data.label) for node in student.nodes},
            reference_canonical,
        )

    matrix = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms
    reference_indices = [
        label_indices[_normalize_fallback(node.data.label)]
        for node in reference.nodes
    ]
    reference_matrix = matrix[reference_indices]
    reference_values = set(reference_canonical.values())

    for node in student.nodes:
        normalized = _normalize_fallback(node.data.label)
        if normalized in reference_values:
            student_canonical[node.id] = normalized
            continue

        student_index = label_indices.get(normalized)
        if student_index is None or reference_matrix.size == 0:
            student_canonical[node.id] = normalized
            continue
        similarities = reference_matrix @ matrix[student_index]
        best_index = int(np.argmax(similarities))
        if float(similarities[best_index]) >= threshold:
            reference_node = reference.nodes[best_index]
            student_canonical[node.id] = reference_canonical[reference_node.id]
        else:
            student_canonical[node.id] = normalized

    return student_canonical, reference_canonical
