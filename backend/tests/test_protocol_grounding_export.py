from scripts.export_cardiology_protocol_grounding import build_rows, build_task_rows


def test_protocol_grounding_uses_external_source_ids() -> None:
    rows = build_rows()

    assert len(rows) == 12
    assert all(row["database_protocol_id"] for row in rows)
    assert all(row["source_protocol_id"] for row in rows)
    assert all(row["protocol_title"] for row in rows)
    assert all(row["protocol_year"] for row in rows)
    assert all(row["protocol_category"] for row in rows)
    assert all(row["protocol_url"].endswith(row["source_protocol_id"]) for row in rows)


def test_task_export_matches_current_synthetic_result_counts() -> None:
    rows = build_task_rows()
    stemi = next(row for row in rows if row["case_id"] == "cardio_stemi_01")

    assert len(rows) == 12
    assert stemi["database_protocol_id"] == 489
    assert stemi["source_protocol_id"] == "15487"
    assert stemi["reference_node_count"] == 10
    assert stemi["reference_edge_count"] == 13
