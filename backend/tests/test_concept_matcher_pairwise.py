import numpy as np

from app.schemas import GraphSchema
from app.services.concept_matcher import build_pairwise_graph_id_maps


def _graph(nodes: list[tuple[str, str]]) -> GraphSchema:
    return GraphSchema.model_validate(
        {
            "nodes": [
                {
                    "id": node_id,
                    "position": {"x": 0, "y": 0},
                    "data": {"label": label, "category": "DIAGNOSIS"},
                }
                for node_id, label in nodes
            ],
            "edges": [],
        }
    )


def test_pairwise_match_maps_semantic_student_label_to_reference_label():
    student = _graph([("s1", "acute myocardial infarction")])
    reference = _graph([("r1", "myocardial infarction"), ("r2", "pneumonia")])
    labels = [
        "acute myocardial infarction",
        "myocardial infarction",
        "pneumonia",
    ]
    vectors = np.asarray(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.0, 1.0],
        ]
    )

    student_map, reference_map = build_pairwise_graph_id_maps(
        student, reference, labels, vectors, threshold=0.8
    )

    assert student_map["s1"] == reference_map["r1"]
    assert student_map["s1"] != reference_map["r2"]


def test_pairwise_match_keeps_unrelated_label_distinct():
    student = _graph([("s1", "unrelated finding")])
    reference = _graph([("r1", "myocardial infarction")])
    labels = ["unrelated finding", "myocardial infarction"]
    vectors = np.asarray([[1.0, 0.0], [0.0, 1.0]])

    student_map, reference_map = build_pairwise_graph_id_maps(
        student, reference, labels, vectors, threshold=0.8
    )

    assert student_map["s1"] != reference_map["r1"]


def test_pairwise_match_falls_back_to_exact_normalized_labels():
    student = _graph([("s1", "  Diagnosis A ")])
    reference = _graph([("r1", "diagnosis a")])
    labels = ["  Diagnosis A ", "diagnosis a"]

    student_map, reference_map = build_pairwise_graph_id_maps(
        student,
        reference,
        labels,
        np.zeros((0, 0)),
        threshold=0.8,
    )

    assert student_map["s1"] == reference_map["r1"]
