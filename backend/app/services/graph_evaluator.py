"""
Clinical graph evaluation.

The evaluator keeps the legacy exact semantic Edge F1 for compatibility, and
adds a v4 clinical-weighted layer for research reporting:
- weighted Edge F1
- one-to-one semantic node coverage
- category-aware matching
- directed clinical path completeness
- safety penalty for critical wrong or missing therapeutic/exclusion links
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Set, Tuple

import networkx as nx

from app.schemas import GraphSchema
from app.services.graph_validator import _compute_node_embeddings

EVALUATION_ALGORITHM_VERSION = "4.3.0-reference-quality-calibrated"

WEIGHT_EDGE_F1 = 0.45
WEIGHT_NODE_COVERAGE = 0.20
WEIGHT_CHAIN_COMPLETENESS = 0.20
WEIGHT_CATEGORY_ACCURACY = 0.15
WEIGHT_UNSAFE_EXTRA_ACTION = 0.50
WEIGHT_MISSING_CRITICAL_ACTION = 0.28
WEIGHT_DIAGNOSTIC_EVIDENCE_GAP = 0.25
WEIGHT_CLINICAL_CONNECTIVITY_GAP = 0.25
NO_EDGE_SUBMISSION_CAP = 0.20
UNSAFE_EXTRA_ACTION_CAP = 0.50
CRITICAL_SAFETY_CONFLICT_CAP = 0.40
MISSING_CRITICAL_ACTION_CAP = 0.74
PARTIAL_MISSING_CRITICAL_ACTION_CAP = 0.82
DIAGNOSTIC_EVIDENCE_GAP_CAP = 0.78
CATEGORY_ACCURACY_GAP_CAP = 0.88
CLINICAL_CONNECTIVITY_GAP_CAP = 0.78
SEVERE_CLINICAL_CONNECTIVITY_GAP_CAP = 0.62

ENTITY_MATCH_THRESHOLD = 0.75
CATEGORY_MISMATCH_FACTOR = 0.65

NODE_CATEGORY_WEIGHTS = {
    "PATIENT_PROFILE": 1.0,
    "SYMPTOM": 1.0,
    "EXAM": 1.1,
    "LAB_TEST": 1.2,
    "INSTRUMENTAL_TEST": 1.2,
    "DIAGNOSIS": 1.6,
    "MEDICATION": 1.4,
    "SURGERY": 1.4,
    "MONITORING": 1.1,
}

EDGE_RELATION_WEIGHTS = {
    "determines": 1.0,
    "requires_confirmation": 1.15,
    "confirms": 1.15,
    "excludes": 1.3,
    "indicated_for": 1.45,
    "contraindicated_due_to": 1.8,
    "contraindicated_for": 1.8,
    "monitors": 1.15,
    "leads_to": 1.2,
    "treats": 1.45,
    "risk_for": 1.25,
}

CLINICAL_START_CATEGORIES = {"PATIENT_PROFILE", "SYMPTOM"}
CLINICAL_DECISION_CATEGORIES = {"DIAGNOSIS", "MEDICATION", "SURGERY", "MONITORING"}
CLINICAL_ACTION_CATEGORIES = {"MEDICATION", "SURGERY", "MONITORING"}
CLINICAL_CONNECTIVITY_CATEGORIES = {
    "PATIENT_PROFILE",
    "SYMPTOM",
    "EXAM",
    "LAB_TEST",
    "INSTRUMENTAL_TEST",
    "DIAGNOSIS",
    "MEDICATION",
    "SURGERY",
    "MONITORING",
}
DIAGNOSTIC_EVIDENCE_CATEGORIES = {
    "PATIENT_PROFILE",
    "SYMPTOM",
    "EXAM",
    "LAB_TEST",
    "INSTRUMENTAL_TEST",
}
DIAGNOSTIC_EVIDENCE_RELATIONS = {
    "determines",
    "requires_confirmation",
    "confirms",
    "leads_to",
    "excludes",
}
SAFETY_CRITICAL_RELATIONS = {"contraindicated_due_to", "contraindicated_for", "excludes"}
SAFETY_CRITICAL_CATEGORIES = {"MEDICATION", "SURGERY"}


class GraphEvaluator:
    @staticmethod
    def _normalize_relation(raw: Any) -> str:
        return getattr(raw, "value", str(raw or "unknown")).lower().strip()

    @staticmethod
    def _category_key(raw: Any) -> str:
        return getattr(raw, "value", str(raw or "")).upper().strip()

    @staticmethod
    def _canonical_label(
        node_id: str,
        label: str,
        id_to_canonical: Optional[Mapping[str, str]],
    ) -> str:
        if id_to_canonical and node_id in id_to_canonical:
            return id_to_canonical[node_id].lower().strip()
        return label.lower().strip()

    @staticmethod
    def _node_weight(category: Any) -> float:
        return NODE_CATEGORY_WEIGHTS.get(GraphEvaluator._category_key(category), 1.0)

    @staticmethod
    def _edge_weight(source_category: Any, target_category: Any, relation: str) -> float:
        source_weight = GraphEvaluator._node_weight(source_category)
        target_weight = GraphEvaluator._node_weight(target_category)
        relation_weight = EDGE_RELATION_WEIGHTS.get(relation, 1.0)
        return relation_weight * ((source_weight + target_weight) / 2)

    @staticmethod
    def construct_nx_graph(
        graph_schema: GraphSchema,
        id_to_canonical: Optional[Mapping[str, str]] = None,
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        for node in graph_schema.nodes:
            label = GraphEvaluator._canonical_label(node.id, node.data.label, id_to_canonical)
            graph.add_node(node.id, label=label, category=node.data.category)

        for edge in graph_schema.edges:
            relation = GraphEvaluator._normalize_relation(edge.label)
            graph.add_edge(edge.source, edge.target, label=relation)
        return graph

    @staticmethod
    def get_semantic_edges(graph: nx.DiGraph) -> Set[Tuple[str, str, str]]:
        semantic_edges: Set[Tuple[str, str, str]] = set()
        for source, target, data in graph.edges(data=True):
            source_label = graph.nodes[source].get("label", "")
            target_label = graph.nodes[target].get("label", "")
            relation = GraphEvaluator._normalize_relation(data.get("label"))
            semantic_edges.add((source_label, target_label, relation))
        return semantic_edges

    @staticmethod
    def _apply_canonical_labels(
        graph: GraphSchema,
        id_to_canonical: Optional[Mapping[str, str]],
    ) -> GraphSchema:
        if not id_to_canonical:
            return graph

        nodes = []
        for node in graph.nodes:
            label = node.data.label
            if node.id in id_to_canonical:
                label = id_to_canonical[node.id]
            data = node.data.model_dump()
            data["label"] = label
            nodes.append(
                {
                    "id": node.id,
                    "type": node.type,
                    "position": node.position,
                    "data": data,
                }
            )
        return GraphSchema(nodes=nodes, edges=[edge.model_dump() for edge in graph.edges])

    @classmethod
    def _semantic_edge_details(
        cls,
        graph: GraphSchema,
        id_to_canonical: Optional[Mapping[str, str]] = None,
    ) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
        nodes = {node.id: node for node in graph.nodes}
        details: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        for edge in graph.edges:
            source = nodes.get(edge.source)
            target = nodes.get(edge.target)
            if not source or not target:
                continue

            source_label = cls._canonical_label(source.id, source.data.label, id_to_canonical)
            target_label = cls._canonical_label(target.id, target.data.label, id_to_canonical)
            relation = cls._normalize_relation(edge.label)
            source_category = cls._category_key(source.data.category)
            target_category = cls._category_key(target.data.category)
            triple = (source_label, target_label, relation)
            weight = cls._edge_weight(source_category, target_category, relation)

            if triple not in details:
                details[triple] = {
                    "weight": 0.0,
                    "source_label": source_label,
                    "target_label": target_label,
                    "source_category": source_category,
                    "target_category": target_category,
                    "relation": relation,
                }
            details[triple]["weight"] += weight

        return details

    @staticmethod
    def _weighted_prf(
        student_edges: Mapping[Tuple[str, str, str], Mapping[str, Any]],
        reference_edges: Mapping[Tuple[str, str, str], Mapping[str, Any]],
    ) -> Dict[str, float]:
        matched = set(student_edges).intersection(reference_edges)
        student_total = sum(float(value["weight"]) for value in student_edges.values())
        reference_total = sum(float(value["weight"]) for value in reference_edges.values())
        matched_student = sum(float(student_edges[key]["weight"]) for key in matched)
        matched_reference = sum(float(reference_edges[key]["weight"]) for key in matched)

        precision = matched_student / student_total if student_total else 0.0
        recall = matched_reference / reference_total if reference_total else 0.0
        f1 = 0.0
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        return {"precision": precision, "recall": recall, "f1": f1}

    @classmethod
    def _node_records(
        cls,
        graph: GraphSchema,
        id_to_canonical: Optional[Mapping[str, str]] = None,
    ) -> list[Dict[str, Any]]:
        return [
            {
                "id": node.id,
                "label": cls._canonical_label(node.id, node.data.label, id_to_canonical),
                "display_label": node.data.label,
                "category": cls._category_key(node.data.category),
                "weight": cls._node_weight(node.data.category),
            }
            for node in graph.nodes
        ]

    @staticmethod
    def _label_similarity(label_a: str, label_b: str, embeddings: Mapping[str, Any]) -> float:
        if label_a.lower().strip() == label_b.lower().strip():
            return 1.0
        vec_a = embeddings.get(label_a)
        vec_b = embeddings.get(label_b)
        if vec_a is None or vec_b is None:
            return 0.0
        try:
            return max(0.0, min(1.0, float(vec_a.dot(vec_b))))
        except AttributeError:
            return 0.0

    @classmethod
    def _one_to_one_node_metrics(
        cls,
        student_graph: GraphSchema,
        reference_graph: GraphSchema,
        student_id_to_canonical: Optional[Mapping[str, str]],
        reference_id_to_canonical: Optional[Mapping[str, str]],
        embeddings: Mapping[str, Any],
    ) -> Dict[str, Any]:
        student_nodes = cls._node_records(student_graph, student_id_to_canonical)
        reference_nodes = cls._node_records(reference_graph, reference_id_to_canonical)
        total_weight = sum(float(node["weight"]) for node in reference_nodes)

        if not reference_nodes or total_weight <= 0:
            return {"node_coverage": 1.0, "category_accuracy": 1.0, "missing_nodes": []}
        if not student_nodes:
            return {
                "node_coverage": 0.0,
                "category_accuracy": 0.0,
                "missing_nodes": [node["display_label"] for node in reference_nodes],
            }

        candidates: list[tuple[float, float, int, int, bool]] = []
        for ref_i, ref_node in enumerate(reference_nodes):
            for st_i, st_node in enumerate(student_nodes):
                raw_similarity = cls._label_similarity(ref_node["label"], st_node["label"], embeddings)
                if raw_similarity < ENTITY_MATCH_THRESHOLD:
                    continue
                category_match = ref_node["category"] == st_node["category"]
                adjusted_similarity = (
                    raw_similarity if category_match else raw_similarity * CATEGORY_MISMATCH_FACTOR
                )
                weighted_score = adjusted_similarity * float(ref_node["weight"])
                candidates.append((weighted_score, adjusted_similarity, ref_i, st_i, category_match))

        candidates.sort(key=lambda item: item[0], reverse=True)
        used_reference: set[int] = set()
        used_student: set[int] = set()
        matched: list[tuple[int, int, float, bool]] = []

        for _, adjusted_similarity, ref_i, st_i, category_match in candidates:
            if ref_i in used_reference or st_i in used_student:
                continue
            used_reference.add(ref_i)
            used_student.add(st_i)
            matched.append((ref_i, st_i, adjusted_similarity, category_match))

        coverage_numerator = 0.0
        category_numerator = 0.0
        for ref_i, _, adjusted_similarity, category_match in matched:
            ref_weight = float(reference_nodes[ref_i]["weight"])
            coverage_numerator += ref_weight * adjusted_similarity
            if category_match:
                category_numerator += ref_weight

        missing_nodes = [
            node["display_label"]
            for index, node in enumerate(reference_nodes)
            if index not in used_reference
        ]
        return {
            "node_coverage": coverage_numerator / total_weight,
            "category_accuracy": category_numerator / total_weight,
            "missing_nodes": missing_nodes,
        }

    @classmethod
    def _directed_path_completeness(
        cls,
        reference_graph: GraphSchema,
        reference_id_to_canonical: Optional[Mapping[str, str]],
        matched_edges: Set[Tuple[str, str, str]],
    ) -> float:
        records = cls._node_records(reference_graph, reference_id_to_canonical)
        by_id = {record["id"]: record for record in records}
        category_by_label = {record["label"]: record["category"] for record in records}

        reference = nx.DiGraph()
        matched = nx.DiGraph()
        for record in records:
            reference.add_node(record["label"], category=record["category"])

        for edge in reference_graph.edges:
            source = by_id.get(edge.source)
            target = by_id.get(edge.target)
            if source and target:
                reference.add_edge(source["label"], target["label"])

        for source, target, _ in matched_edges:
            matched.add_edge(source, target)

        if reference.number_of_edges() == 0:
            return 1.0

        start_nodes = [
            node
            for node, category in category_by_label.items()
            if category in CLINICAL_START_CATEGORIES
        ]
        if not start_nodes:
            start_nodes = [node for node in reference.nodes if reference.out_degree(node) > 0]

        target_nodes = [
            node
            for node, category in category_by_label.items()
            if category in CLINICAL_DECISION_CATEGORIES
        ]
        if not target_nodes:
            target_nodes = [node for node in reference.nodes if reference.out_degree(node) == 0]

        required_pairs: set[tuple[str, str]] = set()
        for source in start_nodes:
            for target in target_nodes:
                if source != target and nx.has_path(reference, source, target):
                    required_pairs.add((source, target))

        if not required_pairs:
            return 1.0

        recovered = sum(
            1
            for source, target in required_pairs
            if matched.has_node(source)
            and matched.has_node(target)
            and nx.has_path(matched, source, target)
        )
        return recovered / len(required_pairs)

    @staticmethod
    def _is_safety_critical(edge_detail: Mapping[str, Any]) -> bool:
        if edge_detail.get("relation") == "indicated_for":
            return (
                edge_detail.get("source_category") in SAFETY_CRITICAL_CATEGORIES
                or edge_detail.get("target_category") in SAFETY_CRITICAL_CATEGORIES
            )
        return (
            edge_detail.get("relation") in SAFETY_CRITICAL_RELATIONS
            or edge_detail.get("source_category") in SAFETY_CRITICAL_CATEGORIES
            or edge_detail.get("target_category") in SAFETY_CRITICAL_CATEGORIES
        )

    @classmethod
    def _safety_penalty_details(
        cls,
        false_positive_edges: Set[Tuple[str, str, str]],
        false_negative_edges: Set[Tuple[str, str, str]],
        student_edge_details: Mapping[Tuple[str, str, str], Mapping[str, Any]],
        reference_edge_details: Mapping[Tuple[str, str, str], Mapping[str, Any]],
    ) -> Dict[str, Any]:
        reference_critical_total = 0.0
        unsafe_extra_weight = 0.0
        missing_critical_weight = 0.0
        findings: list[Dict[str, str]] = []

        for detail in reference_edge_details.values():
            if cls._is_safety_critical(detail):
                reference_critical_total += float(detail["weight"])

        for edge in false_positive_edges:
            detail = student_edge_details.get(edge)
            if detail and cls._is_safety_critical(detail):
                unsafe_extra_weight += float(detail["weight"])
                findings.append(
                    {
                        "kind": "unsafe_extra_action",
                        "source": edge[0],
                        "target": edge[1],
                        "relation": edge[2],
                    }
                )
        for edge in false_negative_edges:
            detail = reference_edge_details.get(edge)
            if detail and cls._is_safety_critical(detail):
                missing_critical_weight += float(detail["weight"])
                findings.append(
                    {
                        "kind": "missing_critical_action",
                        "source": edge[0],
                        "target": edge[1],
                        "relation": edge[2],
                    }
                )

        unsafe_denominator = max(reference_critical_total, unsafe_extra_weight)
        unsafe_extra_action = (
            min(1.0, unsafe_extra_weight / unsafe_denominator)
            if unsafe_denominator > 0
            else 0.0
        )
        missing_critical_action = (
            min(1.0, missing_critical_weight / reference_critical_total)
            if reference_critical_total > 0
            else 0.0
        )
        safety_penalty = max(
            unsafe_extra_action,
            missing_critical_action,
            0.6 * unsafe_extra_action + 0.4 * missing_critical_action,
        )
        return {
            "safety_penalty": min(1.0, safety_penalty),
            "unsafe_extra_action": unsafe_extra_action,
            "missing_critical_action": missing_critical_action,
            "safety_findings": findings,
        }

    @staticmethod
    def _is_diagnostic_evidence(edge_detail: Mapping[str, Any]) -> bool:
        return (
            edge_detail.get("target_category") == "DIAGNOSIS"
            and edge_detail.get("source_category") in DIAGNOSTIC_EVIDENCE_CATEGORIES
            and edge_detail.get("relation") in DIAGNOSTIC_EVIDENCE_RELATIONS
        )

    @classmethod
    def _diagnostic_evidence_gap_details(
        cls,
        false_negative_edges: Set[Tuple[str, str, str]],
        reference_edge_details: Mapping[Tuple[str, str, str], Mapping[str, Any]],
    ) -> Dict[str, Any]:
        reference_evidence_total = 0.0
        missing_evidence_weight = 0.0
        findings: list[Dict[str, str]] = []

        for detail in reference_edge_details.values():
            if cls._is_diagnostic_evidence(detail):
                reference_evidence_total += float(detail["weight"])

        for edge in false_negative_edges:
            detail = reference_edge_details.get(edge)
            if not detail or not cls._is_diagnostic_evidence(detail):
                continue
            missing_evidence_weight += float(detail["weight"])
            findings.append(
                {
                    "kind": "missing_diagnostic_evidence",
                    "source": str(detail.get("source_label") or edge[0]),
                    "target": str(detail.get("target_label") or edge[1]),
                    "relation": edge[2],
                }
            )

        diagnostic_evidence_gap = (
            min(1.0, missing_evidence_weight / reference_evidence_total)
            if reference_evidence_total > 0
            else 0.0
        )
        return {
            "diagnostic_evidence_gap": diagnostic_evidence_gap,
            "diagnostic_evidence_findings": findings,
        }

    @classmethod
    def _clinical_connectivity_gap_details(
        cls,
        graph: GraphSchema,
        id_to_canonical: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        records = cls._node_records(graph, id_to_canonical)
        if len(records) <= 1:
            return {"clinical_connectivity_gap": 0.0, "clinical_connectivity_findings": []}

        by_id = {record["id"]: record for record in records}
        clinical_nodes = [
            record
            for record in records
            if record["category"] in CLINICAL_CONNECTIVITY_CATEGORIES
        ]
        total_weight = sum(float(record["weight"]) for record in clinical_nodes)
        if total_weight <= 0:
            return {"clinical_connectivity_gap": 0.0, "clinical_connectivity_findings": []}

        directed = nx.DiGraph()
        for record in records:
            directed.add_node(record["id"], **record)
        for edge in graph.edges:
            if edge.source in by_id and edge.target in by_id:
                directed.add_edge(edge.source, edge.target)

        start_ids = [
            record["id"]
            for record in records
            if record["category"] in CLINICAL_START_CATEGORIES
        ]
        diagnosis_ids = [
            record["id"]
            for record in records
            if record["category"] == "DIAGNOSIS"
        ]
        action_ids = [
            record["id"]
            for record in records
            if record["category"] in CLINICAL_ACTION_CATEGORIES
        ]
        contraindicated_action_ids = {
            edge.source
            for edge in graph.edges
            if edge.source in action_ids
            and cls._normalize_relation(edge.label) in {"contraindicated_due_to", "contraindicated_for"}
        }
        diagnostic_ids = [
            record["id"]
            for record in records
            if record["category"] in {"EXAM", "LAB_TEST", "INSTRUMENTAL_TEST"}
        ]

        penalties: dict[str, dict[str, Any]] = {}

        def add_penalty(node_id: str, kind: str, multiplier: float = 1.0) -> None:
            record = by_id.get(node_id)
            if not record:
                return
            weight = float(record["weight"]) * multiplier
            existing = penalties.get(node_id)
            if existing and float(existing["weight"]) >= weight:
                return
            penalties[node_id] = {
                "kind": kind,
                "node": str(record["display_label"]),
                "category": str(record["category"]),
                "weight": weight,
            }

        for record in clinical_nodes:
            node_id = record["id"]
            if directed.degree(node_id) == 0:
                add_penalty(node_id, "isolated_clinical_node", 1.25)

        if start_ids and diagnosis_ids:
            for diagnosis_id in diagnosis_ids:
                if directed.degree(diagnosis_id) == 0:
                    continue
                if not any(nx.has_path(directed, start_id, diagnosis_id) for start_id in start_ids):
                    add_penalty(diagnosis_id, "diagnosis_not_reached_from_start", 1.15)

        if diagnosis_ids:
            for action_id in action_ids:
                if directed.degree(action_id) == 0:
                    continue
                if action_id in contraindicated_action_ids:
                    continue
                if not any(nx.has_path(directed, diagnosis_id, action_id) for diagnosis_id in diagnosis_ids):
                    add_penalty(action_id, "action_not_reached_from_diagnosis", 1.25)

            for diagnostic_id in diagnostic_ids:
                if directed.degree(diagnostic_id) == 0:
                    continue
                supports_diagnosis = any(
                    nx.has_path(directed, diagnostic_id, diagnosis_id)
                    for diagnosis_id in diagnosis_ids
                )
                guides_post_diagnosis_action = any(
                    nx.has_path(directed, diagnosis_id, diagnostic_id)
                    for diagnosis_id in diagnosis_ids
                ) and (
                    not action_ids
                    or any(nx.has_path(directed, diagnostic_id, action_id) for action_id in action_ids)
                )
                if not supports_diagnosis and not guides_post_diagnosis_action:
                    add_penalty(diagnostic_id, "diagnostic_evidence_not_linked_to_diagnosis", 1.10)
        elif action_ids:
            for action_id in action_ids:
                add_penalty(action_id, "action_without_diagnosis", 1.35)

        penalty_weight = sum(float(item["weight"]) for item in penalties.values())
        gap = min(1.0, penalty_weight / total_weight)
        findings = [
            {
                "kind": str(item["kind"]),
                "node": str(item["node"]),
                "category": str(item["category"]),
            }
            for item in sorted(
                penalties.values(),
                key=lambda item: (str(item["kind"]), str(item["node"])),
            )
        ]
        return {
            "clinical_connectivity_gap": gap,
            "clinical_connectivity_findings": findings,
        }

    @staticmethod
    def _apply_clinical_score_caps(
        score: float,
        *,
        unsafe_extra_action: float,
        missing_critical_action: float,
        diagnostic_evidence_gap: float,
        clinical_connectivity_gap: float,
        category_accuracy: float,
        has_edges: bool,
        has_reference_edges: bool,
    ) -> tuple[float, list[Dict[str, Any]], float]:
        caps: list[Dict[str, Any]] = []
        edge_count_penalty = 0.0

        def apply_cap(code: str, cap: float, reason: str) -> None:
            nonlocal score
            applied = score > cap
            if applied:
                score = cap
            caps.append(
                {
                    "code": code,
                    "cap": round(cap, 2),
                    "applied": applied,
                    "reason": reason,
                }
            )

        if unsafe_extra_action > 0 and missing_critical_action > 0:
            apply_cap(
                "critical_safety_conflict",
                CRITICAL_SAFETY_CONFLICT_CAP,
                "Unsafe extra action is combined with a missing critical safety relation.",
            )
        elif unsafe_extra_action > 0:
            apply_cap(
                "unsafe_extra_action",
                UNSAFE_EXTRA_ACTION_CAP,
                "Potentially unsafe extra treatment or procedure was detected.",
            )

        if missing_critical_action >= 1.0:
            apply_cap(
                "missing_critical_action",
                MISSING_CRITICAL_ACTION_CAP,
                "All critical treatment or safety relations of this type are missing.",
            )
        elif missing_critical_action >= 0.35:
            apply_cap(
                "partial_missing_critical_action",
                PARTIAL_MISSING_CRITICAL_ACTION_CAP,
                "A clinically important treatment or safety relation is missing.",
            )

        if diagnostic_evidence_gap >= 0.30:
            apply_cap(
                "diagnostic_evidence_gap",
                DIAGNOSTIC_EVIDENCE_GAP_CAP,
                "A clinically meaningful share of diagnostic evidence is missing.",
            )

        if clinical_connectivity_gap >= 0.60:
            apply_cap(
                "severe_clinical_connectivity_gap",
                SEVERE_CLINICAL_CONNECTIVITY_GAP_CAP,
                "Major clinical nodes are disconnected from the diagnostic or treatment chain.",
            )
        elif clinical_connectivity_gap >= 0.20:
            apply_cap(
                "clinical_connectivity_gap",
                CLINICAL_CONNECTIVITY_GAP_CAP,
                "Some clinical nodes are isolated or not reachable through the reasoning chain.",
            )

        if category_accuracy < 0.95:
            apply_cap(
                "category_accuracy_gap",
                CATEGORY_ACCURACY_GAP_CAP,
                "At least one matched clinical concept has an incorrect category.",
            )

        if has_reference_edges and not has_edges:
            apply_cap(
                "no_edges",
                NO_EDGE_SUBMISSION_CAP,
                "A graph without relations does not represent clinical reasoning.",
            )
            edge_count_penalty = 1.0

        return score, caps, edge_count_penalty

    @classmethod
    def evaluate(
        cls,
        student_graph: GraphSchema,
        reference_graph: GraphSchema,
        student_id_to_canonical: Optional[Mapping[str, str]] = None,
        reference_id_to_canonical: Optional[Mapping[str, str]] = None,
        node_embeddings: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        graph_student = cls.construct_nx_graph(student_graph, student_id_to_canonical)
        graph_reference = cls.construct_nx_graph(reference_graph, reference_id_to_canonical)

        student_edges = cls.get_semantic_edges(graph_student)
        reference_edges = cls.get_semantic_edges(graph_reference)

        if not reference_edges:
            return {
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
                "edge_f1": 0.0,
                "weighted_precision": 0.0,
                "weighted_recall": 0.0,
                "weighted_edge_f1": 0.0,
                "node_coverage": 0.0,
                "chain_completeness": 0.0,
                "directed_path_completeness": 0.0,
                "category_accuracy": 0.0,
                "structural_correctness": 0.0,
                "safety_penalty": 0.0,
                "edge_count_penalty": 0.0,
                "student_edge_count": len(student_edges),
                "reference_edge_count": 0,
                "unsafe_extra_action": 0.0,
                "missing_critical_action": 0.0,
                "diagnostic_evidence_gap": 0.0,
                "diagnostic_evidence_findings": [],
                "clinical_connectivity_gap": 0.0,
                "clinical_connectivity_findings": [],
                "score_caps": [],
                "safety_findings": [],
                "composite_score": 0.0,
                "missing_edges": [],
                "incorrect_edges": [],
                "missing_nodes": [],
                "algorithm_version": EVALUATION_ALGORITHM_VERSION,
            }

        true_positives = student_edges.intersection(reference_edges)
        false_positives = student_edges - reference_edges
        false_negatives = reference_edges - student_edges

        precision = len(true_positives) / len(student_edges) if student_edges else 0.0
        recall = len(true_positives) / len(reference_edges)

        f1_score = 0.0
        if precision + recall > 0:
            f1_score = 2 * (precision * recall) / (precision + recall)

        missing = [
            {"source": source, "target": target, "relation": relation}
            for source, target, relation in sorted(false_negatives)
        ]

        incorrect = []
        for edge in student_graph.edges:
            source_node = next((node for node in student_graph.nodes if node.id == edge.source), None)
            target_node = next((node for node in student_graph.nodes if node.id == edge.target), None)
            if not source_node or not target_node:
                continue

            source_label = cls._canonical_label(
                source_node.id,
                source_node.data.label,
                student_id_to_canonical,
            )
            target_label = cls._canonical_label(
                target_node.id,
                target_node.data.label,
                student_id_to_canonical,
            )
            relation = cls._normalize_relation(edge.label)

            if (source_label, target_label, relation) in false_positives:
                incorrect.append(
                    {
                        "id": str(edge.id),
                        "source": str(source_node.data.label),
                        "target": str(target_node.data.label),
                        "relation": relation,
                    }
                )

        student_edge_details = cls._semantic_edge_details(student_graph, student_id_to_canonical)
        reference_edge_details = cls._semantic_edge_details(reference_graph, reference_id_to_canonical)
        weighted = cls._weighted_prf(student_edge_details, reference_edge_details)

        node_coverage = recall
        category_accuracy = recall
        missing_nodes: list[str] = []
        try:
            student_records = cls._node_records(student_graph, student_id_to_canonical)
            reference_records = cls._node_records(reference_graph, reference_id_to_canonical)
            student_labels = [record["label"] for record in student_records]
            reference_labels = [record["label"] for record in reference_records]
            embeddings = (
                _compute_node_embeddings(student_labels, reference_labels)
                if node_embeddings is None
                else node_embeddings
            )
            node_metrics = cls._one_to_one_node_metrics(
                student_graph,
                reference_graph,
                student_id_to_canonical,
                reference_id_to_canonical,
                embeddings,
            )
            node_coverage = node_metrics["node_coverage"]
            category_accuracy = node_metrics["category_accuracy"]
            missing_nodes = node_metrics["missing_nodes"]
        except Exception:
            node_coverage = recall
            category_accuracy = recall

        directed_path_completeness = cls._directed_path_completeness(
            reference_graph,
            reference_id_to_canonical,
            true_positives,
        )
        safety_details = cls._safety_penalty_details(
            false_positives,
            false_negatives,
            student_edge_details,
            reference_edge_details,
        )
        diagnostic_details = cls._diagnostic_evidence_gap_details(
            false_negatives,
            reference_edge_details,
        )
        connectivity_details = cls._clinical_connectivity_gap_details(
            student_graph,
            student_id_to_canonical,
        )
        safety_penalty = float(safety_details["safety_penalty"])
        unsafe_extra_action = float(safety_details["unsafe_extra_action"])
        missing_critical_action = float(safety_details["missing_critical_action"])
        diagnostic_evidence_gap = float(diagnostic_details["diagnostic_evidence_gap"])
        clinical_connectivity_gap = float(connectivity_details["clinical_connectivity_gap"])
        structural_correctness = weighted["f1"]

        composite_score = (
            WEIGHT_EDGE_F1 * weighted["f1"]
            + WEIGHT_NODE_COVERAGE * node_coverage
            + WEIGHT_CHAIN_COMPLETENESS * directed_path_completeness
            + WEIGHT_CATEGORY_ACCURACY * category_accuracy
            - WEIGHT_UNSAFE_EXTRA_ACTION * unsafe_extra_action
            - WEIGHT_MISSING_CRITICAL_ACTION * missing_critical_action
            - WEIGHT_DIAGNOSTIC_EVIDENCE_GAP * diagnostic_evidence_gap
            - WEIGHT_CLINICAL_CONNECTIVITY_GAP * clinical_connectivity_gap
        )
        composite_score, score_caps, edge_count_penalty = cls._apply_clinical_score_caps(
            composite_score,
            unsafe_extra_action=unsafe_extra_action,
            missing_critical_action=missing_critical_action,
            diagnostic_evidence_gap=diagnostic_evidence_gap,
            clinical_connectivity_gap=clinical_connectivity_gap,
            category_accuracy=category_accuracy,
            has_edges=bool(student_edges),
            has_reference_edges=bool(reference_edges),
        )
        composite_score = max(0.0, min(1.0, round(composite_score, 2)))

        return {
            "precision": round(precision, 2),
            "recall": round(recall, 2),
            "f1_score": round(f1_score, 2),
            "edge_f1": round(f1_score, 2),
            "weighted_precision": round(weighted["precision"], 2),
            "weighted_recall": round(weighted["recall"], 2),
            "weighted_edge_f1": round(weighted["f1"], 2),
            "node_coverage": round(node_coverage, 2),
            "chain_completeness": round(directed_path_completeness, 2),
            "directed_path_completeness": round(directed_path_completeness, 2),
            "category_accuracy": round(category_accuracy, 2),
            "structural_correctness": round(structural_correctness, 2),
            "safety_penalty": round(safety_penalty, 2),
            "edge_count_penalty": round(edge_count_penalty, 2),
            "student_edge_count": len(student_edges),
            "reference_edge_count": len(reference_edges),
            "unsafe_extra_action": round(unsafe_extra_action, 2),
            "missing_critical_action": round(missing_critical_action, 2),
            "diagnostic_evidence_gap": round(diagnostic_evidence_gap, 2),
            "diagnostic_evidence_findings": diagnostic_details["diagnostic_evidence_findings"],
            "clinical_connectivity_gap": round(clinical_connectivity_gap, 2),
            "clinical_connectivity_findings": connectivity_details["clinical_connectivity_findings"],
            "score_caps": score_caps,
            "safety_findings": safety_details["safety_findings"],
            "composite_score": composite_score,
            "missing_edges": missing,
            "incorrect_edges": incorrect,
            "missing_nodes": missing_nodes,
            "algorithm_version": EVALUATION_ALGORITHM_VERSION,
        }
