from app.schemas import GraphSchema


def test_graph_schema_preserves_node_metadata_and_edge_handles():
    graph = GraphSchema.model_validate(
        {
            "nodes": [
                {
                    "id": "n1",
                    "type": "med",
                    "position": {"x": 10, "y": 20},
                    "data": {
                        "label": "Chest pain",
                        "category": "SYMPTOM",
                        "description": "Protocol-grounded symptom",
                        "protocol_refs": [{"protocol_id": 489, "section": "Diagnosis"}],
                        "is_critical": True,
                        "source": "ai",
                        "confidence": 0.92,
                    },
                },
                {
                    "id": "n2",
                    "type": "med",
                    "position": {"x": 100, "y": 20},
                    "data": {
                        "label": "ECG",
                        "category": "INSTRUMENTAL_TEST",
                    },
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "type": "custom",
                    "source": "n1",
                    "target": "n2",
                    "label": "DETERMINES",
                    "sourceHandle": "s",
                    "targetHandle": "t",
                }
            ],
        }
    )

    dumped = graph.model_dump()

    node_data = dumped["nodes"][0]["data"]
    assert node_data["description"] == "Protocol-grounded symptom"
    assert node_data["protocol_refs"] == [{"protocol_id": 489, "section": "Diagnosis"}]
    assert node_data["is_critical"] is True
    assert node_data["source"] == "ai"
    assert node_data["confidence"] == 0.92

    edge = dumped["edges"][0]
    assert edge["type"] == "custom"
    assert edge["sourceHandle"] == "s"
    assert edge["targetHandle"] == "t"
