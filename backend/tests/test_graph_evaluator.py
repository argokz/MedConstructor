import pytest

from app.schemas import GraphSchema, NodeSchema, EdgeSchema
from app.services.graph_evaluator import GraphEvaluator, EVALUATION_ALGORITHM_VERSION


@pytest.fixture(autouse=True)
def _disable_external_embeddings(monkeypatch):
    monkeypatch.setattr("app.services.graph_evaluator._compute_node_embeddings", lambda *_: {})


def _node(nid: str, label: str, category: str = "DIAGNOSIS") -> dict:
    return {
        "id": nid,
        "position": {"x": 0.0, "y": 0.0},
        "data": {"label": label, "category": category},
    }


def _edge(eid: str, src: str, tgt: str, label: str = "INDICATED_FOR") -> dict:
    return {"id": eid, "source": src, "target": tgt, "label": label}


def test_empty_reference_returns_consistent_keys():
    student = GraphSchema(
        nodes=[
            NodeSchema(**_node("a", "A", "DIAGNOSIS")),
            NodeSchema(**_node("b", "B", "MEDICATION")),
        ],
        edges=[EdgeSchema(**_edge("e1", "a", "b", "INDICATED_FOR"))],
    )
    ref = GraphSchema(nodes=[NodeSchema(**_node("1", "X", "DIAGNOSIS"))], edges=[])
    out = GraphEvaluator.evaluate(student, ref)
    assert out["missing_edges"] == []
    assert out["incorrect_edges"] == []
    assert out["precision"] == 0.0
    assert out["recall"] == 0.0
    assert out["f1_score"] == 0.0
    assert out["algorithm_version"] == EVALUATION_ALGORITHM_VERSION
    assert "composite_score" in out


def test_perfect_match_ignores_node_ids():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("1", "Инфаркт", "DIAGNOSIS")),
            NodeSchema(**_node("2", "Аспирин", "MEDICATION")),
        ],
        edges=[EdgeSchema(**_edge("e", "1", "2", "INDICATED_FOR"))],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("n9", "Инфаркт", "DIAGNOSIS")),
            NodeSchema(**_node("n8", "Аспирин", "MEDICATION")),
        ],
        edges=[EdgeSchema(**_edge("x", "n9", "n8", "INDICATED_FOR"))],
    )
    out = GraphEvaluator.evaluate(st, ref)
    assert out["precision"] == 1.0
    assert out["recall"] == 1.0
    assert out["f1_score"] == 1.0
    assert out["composite_score"] == 1.0
    assert out["missing_edges"] == []
    assert out["incorrect_edges"] == []


def test_wrong_relation_counts_as_error():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("1", "A", "DIAGNOSIS")),
            NodeSchema(**_node("2", "B", "MEDICATION")),
        ],
        edges=[EdgeSchema(**_edge("e", "1", "2", "INDICATED_FOR"))],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("a", "A", "DIAGNOSIS")),
            NodeSchema(**_node("b", "B", "MEDICATION")),
        ],
        edges=[EdgeSchema(**_edge("x", "a", "b", "DETERMINES"))],
    )
    out = GraphEvaluator.evaluate(st, ref)
    assert out["precision"] == 0.0
    assert out["recall"] == 0.0
    assert len(out["missing_edges"]) == 1
    assert out["missing_edges"][0]["relation"] == "indicated_for"
    assert len(out["incorrect_edges"]) == 1
    assert out["incorrect_edges"][0]["relation"] == "determines"


def test_no_edge_submission_is_capped_even_when_nodes_match():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Symptom", "SYMPTOM")),
            NodeSchema(**_node("d", "Diagnosis", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Medication", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "d", "DETERMINES")),
            EdgeSchema(**_edge("e2", "d", "m", "INDICATED_FOR")),
        ],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("x1", "Symptom", "SYMPTOM")),
            NodeSchema(**_node("x2", "Diagnosis", "DIAGNOSIS")),
            NodeSchema(**_node("x3", "Medication", "MEDICATION")),
        ],
        edges=[],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["edge_f1"] == 0.0
    assert out["weighted_edge_f1"] == 0.0
    assert out["student_edge_count"] == 0
    assert out["reference_edge_count"] == 2
    assert out["edge_count_penalty"] == 1.0
    assert len(out["missing_edges"]) == 2
    assert out["composite_score"] <= 0.2


def test_v4_perfect_match_has_clinical_weighted_metrics():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Chest pain", "SYMPTOM")),
            NodeSchema(**_node("d", "Myocardial infarction", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Aspirin", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "d", "DETERMINES")),
            EdgeSchema(**_edge("e2", "d", "m", "INDICATED_FOR")),
        ],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("x1", "Chest pain", "SYMPTOM")),
            NodeSchema(**_node("x2", "Myocardial infarction", "DIAGNOSIS")),
            NodeSchema(**_node("x3", "Aspirin", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("sx1", "x1", "x2", "DETERMINES")),
            EdgeSchema(**_edge("sx2", "x2", "x3", "INDICATED_FOR")),
        ],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["algorithm_version"] == EVALUATION_ALGORITHM_VERSION
    assert out["weighted_edge_f1"] == 1.0
    assert out["directed_path_completeness"] == 1.0
    assert out["category_accuracy"] == 1.0
    assert out["safety_penalty"] == 0.0
    assert out["composite_score"] == 1.0


def test_v4_category_mismatch_reduces_node_metrics():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("a", "A", "DIAGNOSIS")),
            NodeSchema(**_node("b", "B", "SYMPTOM")),
        ],
        edges=[EdgeSchema(**_edge("e", "a", "b", "DETERMINES"))],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("x", "A", "SYMPTOM")),
            NodeSchema(**_node("y", "B", "SYMPTOM")),
        ],
        edges=[EdgeSchema(**_edge("s", "x", "y", "DETERMINES"))],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["edge_f1"] == 1.0
    assert out["weighted_edge_f1"] == 1.0
    assert out["node_coverage"] < 1.0
    assert out["category_accuracy"] < 1.0
    assert out["composite_score"] < 1.0


def test_monitoring_can_be_indicated_from_diagnosis():
    graph = GraphSchema(
        nodes=[
            NodeSchema(**_node("d", "Gestational hypertension", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Blood pressure monitoring", "MONITORING")),
        ],
        edges=[EdgeSchema(**_edge("e", "d", "m", "INDICATED_FOR"))],
    )

    out = GraphEvaluator.evaluate(graph, graph)

    assert out["composite_score"] == 1.0
    assert out["safety_penalty"] == 0.0


def test_v4_safety_penalty_for_extra_therapy_edge():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("d", "Diagnosis", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Medication A", "MEDICATION")),
        ],
        edges=[EdgeSchema(**_edge("e", "d", "m", "INDICATED_FOR"))],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("d1", "Diagnosis", "DIAGNOSIS")),
            NodeSchema(**_node("m1", "Medication A", "MEDICATION")),
            NodeSchema(**_node("m2", "Medication B", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("s1", "d1", "m1", "INDICATED_FOR")),
            EdgeSchema(**_edge("s2", "d1", "m2", "INDICATED_FOR")),
        ],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["recall"] == 1.0
    assert out["precision"] < 1.0
    assert out["safety_penalty"] > 0.0
    assert out["unsafe_extra_action"] > 0.0
    assert out["missing_critical_action"] == 0.0
    assert out["safety_findings"][0]["kind"] == "unsafe_extra_action"
    assert out["composite_score"] <= 0.5
    assert any(cap["code"] == "unsafe_extra_action" for cap in out["score_caps"])


def test_v43_penalizes_disconnected_clinical_action_chain():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Chest pain", "SYMPTOM")),
            NodeSchema(**_node("d", "Myocardial infarction", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Reperfusion therapy", "SURGERY")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "d", "DETERMINES")),
            EdgeSchema(**_edge("e2", "d", "m", "INDICATED_FOR")),
        ],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("s1", "Chest pain", "SYMPTOM")),
            NodeSchema(**_node("d1", "Myocardial infarction", "DIAGNOSIS")),
            NodeSchema(**_node("m1", "Reperfusion therapy", "SURGERY")),
        ],
        edges=[
            EdgeSchema(**_edge("s1", "s1", "d1", "DETERMINES")),
        ],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["clinical_connectivity_gap"] > 0.0
    assert out["clinical_connectivity_findings"][0]["kind"] in {
        "isolated_clinical_node",
        "action_not_reached_from_diagnosis",
    }
    assert any(cap["code"] == "clinical_connectivity_gap" for cap in out["score_caps"])
    assert out["composite_score"] <= 0.78


def test_v43_allows_post_diagnosis_stratification_before_action():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Irregular pulse", "SYMPTOM")),
            NodeSchema(**_node("ecg", "ECG confirms atrial fibrillation", "INSTRUMENTAL_TEST")),
            NodeSchema(**_node("d", "Atrial fibrillation", "DIAGNOSIS")),
            NodeSchema(**_node("risk", "Bleeding risk assessment", "EXAM")),
            NodeSchema(**_node("m", "Anticoagulation after risk assessment", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "ecg", "REQUIRES_CONFIRMATION")),
            EdgeSchema(**_edge("e2", "ecg", "d", "DETERMINES")),
            EdgeSchema(**_edge("e3", "d", "risk", "DETERMINES")),
            EdgeSchema(**_edge("e4", "risk", "m", "DETERMINES")),
        ],
    )

    out = GraphEvaluator.evaluate(ref, ref)

    assert out["clinical_connectivity_gap"] == 0.0
    assert out["clinical_connectivity_findings"] == []


def test_v43_does_not_require_diagnosis_path_to_contraindicated_action():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Chest pain", "SYMPTOM")),
            NodeSchema(**_node("ct", "CT angiography", "INSTRUMENTAL_TEST")),
            NodeSchema(**_node("d", "Aortic dissection", "DIAGNOSIS")),
            NodeSchema(**_node("bad", "Thrombolysis", "MEDICATION")),
            NodeSchema(**_node("sx", "Urgent surgery", "SURGERY")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "ct", "REQUIRES_CONFIRMATION")),
            EdgeSchema(**_edge("e2", "ct", "d", "DETERMINES")),
            EdgeSchema(**_edge("e3", "d", "sx", "INDICATED_FOR")),
            EdgeSchema(**_edge("e4", "bad", "d", "CONTRAINDICATED_DUE_TO")),
        ],
    )

    out = GraphEvaluator.evaluate(ref, ref)

    assert "action_not_reached_from_diagnosis" not in {
        item["kind"] for item in out["clinical_connectivity_findings"]
    }


def test_v42_missing_diagnostic_evidence_is_explicitly_penalized():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Progressive dyspnea", "SYMPTOM")),
            NodeSchema(**_node("t", "Echocardiography", "INSTRUMENTAL_TEST")),
            NodeSchema(**_node("d", "Heart failure", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Guideline therapy", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "t", "DETERMINES")),
            EdgeSchema(**_edge("e2", "t", "d", "DETERMINES")),
            EdgeSchema(**_edge("e3", "d", "m", "INDICATED_FOR")),
        ],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("s1", "Progressive dyspnea", "SYMPTOM")),
            NodeSchema(**_node("t1", "Echocardiography", "INSTRUMENTAL_TEST")),
            NodeSchema(**_node("d1", "Heart failure", "DIAGNOSIS")),
            NodeSchema(**_node("m1", "Guideline therapy", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("s1", "s1", "t1", "DETERMINES")),
            EdgeSchema(**_edge("s3", "d1", "m1", "INDICATED_FOR")),
        ],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["diagnostic_evidence_gap"] == 1.0
    assert out["diagnostic_evidence_findings"][0]["kind"] == "missing_diagnostic_evidence"
    assert any(cap["code"] == "diagnostic_evidence_gap" for cap in out["score_caps"])
    assert out["composite_score"] <= 0.82


def test_v4_directed_path_completeness_penalizes_broken_chain():
    ref = GraphSchema(
        nodes=[
            NodeSchema(**_node("s", "Symptom", "SYMPTOM")),
            NodeSchema(**_node("l", "Lab test", "LAB_TEST")),
            NodeSchema(**_node("d", "Diagnosis", "DIAGNOSIS")),
            NodeSchema(**_node("m", "Medication", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("e1", "s", "l", "DETERMINES")),
            EdgeSchema(**_edge("e2", "l", "d", "DETERMINES")),
            EdgeSchema(**_edge("e3", "d", "m", "INDICATED_FOR")),
        ],
    )
    st = GraphSchema(
        nodes=[
            NodeSchema(**_node("s1", "Symptom", "SYMPTOM")),
            NodeSchema(**_node("l1", "Lab test", "LAB_TEST")),
            NodeSchema(**_node("d1", "Diagnosis", "DIAGNOSIS")),
            NodeSchema(**_node("m1", "Medication", "MEDICATION")),
        ],
        edges=[
            EdgeSchema(**_edge("s1", "s1", "l1", "DETERMINES")),
            EdgeSchema(**_edge("s3", "d1", "m1", "INDICATED_FOR")),
        ],
    )

    out = GraphEvaluator.evaluate(st, ref)

    assert out["edge_f1"] > 0.0
    assert out["directed_path_completeness"] == 0.0
    assert out["composite_score"] < out["edge_f1"]
