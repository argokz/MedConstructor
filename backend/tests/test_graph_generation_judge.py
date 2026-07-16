from app.schemas import GraphSchema
from app.services.graph_generation_judge import (
    judge_reference_graph,
    repair_graph_connectivity,
)


def _node(nid: str, label: str, category: str) -> dict:
    return {
        "id": nid,
        "type": "med",
        "position": {"x": 0.0, "y": 0.0},
        "data": {"label": label, "category": category},
    }


def _edge(eid: str, source: str, target: str, label: str = "DETERMINES") -> dict:
    return {"id": eid, "source": source, "target": target, "label": label}


def _codes(quality: dict) -> set[str]:
    return {warning["code"] for warning in quality["warnings"]}


def test_judge_accepts_connected_diagnosis_and_treatment_graph():
    graph = GraphSchema(
        nodes=[
            _node("p", "Pregnant patient with headache", "PATIENT_PROFILE"),
            _node("s", "Elevated blood pressure and edema", "SYMPTOM"),
            _node("l", "Proteinuria assessment", "LAB_TEST"),
            _node("d", "Gestational hypertension", "DIAGNOSIS"),
            _node("m", "Antihypertensive therapy", "MEDICATION"),
            _node("c", "ACE inhibitor class", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "p", "s"),
            _edge("e2", "s", "l", "REQUIRES_CONFIRMATION"),
            _edge("e3", "l", "d"),
            _edge("e4", "d", "m", "INDICATED_FOR"),
            _edge("e5", "c", "p", "CONTRAINDICATED_DUE_TO"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert quality["accepted"] is True
    assert quality["quality_score"] == 1.0
    assert quality["warnings"] == []


def test_judge_accepts_contraindicated_medication_as_reference_red_flag():
    graph = GraphSchema(
        nodes=[
            _node("p", "Pregnant patient", "PATIENT_PROFILE"),
            _node("s", "Elevated blood pressure", "SYMPTOM"),
            _node("l", "Proteinuria assessment", "LAB_TEST"),
            _node("d", "Gestational hypertension", "DIAGNOSIS"),
            _node("m", "Antihypertensive therapy", "MEDICATION"),
            _node("x", "ACE inhibitor", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "p", "s"),
            _edge("e2", "s", "l", "REQUIRES_CONFIRMATION"),
            _edge("e3", "l", "d"),
            _edge("e4", "d", "m", "INDICATED_FOR"),
            _edge("e5", "x", "p", "CONTRAINDICATED_DUE_TO"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert quality["accepted"] is True
    assert "treatment_without_diagnosis" not in _codes(quality)
    assert "no_path_from_diagnosis_to_action" not in _codes(quality)


def test_judge_does_not_treat_adrenaline_as_monitoring():
    graph = GraphSchema(
        nodes=[
            _node("p", "Patient after allergen exposure", "PATIENT_PROFILE"),
            _node("s", "Bronchospasm and hypotension", "SYMPTOM"),
            _node("e", "Airway and blood pressure assessment", "EXAM"),
            _node("d", "Anaphylactic shock", "DIAGNOSIS"),
            _node("m", "Адреналин внутримышечно", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "p", "s"),
            _edge("e2", "s", "e"),
            _edge("e3", "e", "d"),
            _edge("e4", "d", "m", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert quality["accepted"] is True
    assert "monitoring_misclassified_as_medication" not in _codes(quality)


def test_judge_does_not_treat_rate_control_medication_as_monitoring():
    graph = GraphSchema(
        nodes=[
            _node("s", "Нерегулярный пульс", "SYMPTOM"),
            _node("ecg", "ЭКГ с фибрилляцией предсердий", "INSTRUMENTAL_TEST"),
            _node("d", "Фибрилляция предсердий", "DIAGNOSIS"),
            _node("m", "Бета-блокатор для контроля ЧСС", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "s", "ecg", "REQUIRES_CONFIRMATION"),
            _edge("e2", "ecg", "d"),
            _edge("e3", "d", "m", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert "monitoring_misclassified_as_medication" not in _codes(quality)


def test_judge_flags_treatment_without_diagnosis_as_critical():
    graph = GraphSchema(
        nodes=[
            _node("p", "Patient with fever", "PATIENT_PROFILE"),
            _node("m", "Antibiotic therapy", "MEDICATION"),
        ],
        edges=[],
    )

    quality = judge_reference_graph(graph)

    assert quality["accepted"] is False
    assert quality["critical_count"] >= 1
    assert "missing_diagnosis" in _codes(quality)
    assert "treatment_without_diagnosis" in _codes(quality)


def test_judge_warns_when_diagnosis_has_no_diagnostic_step():
    graph = GraphSchema(
        nodes=[
            _node("s", "Chest pain", "SYMPTOM"),
            _node("d", "Myocardial infarction", "DIAGNOSIS"),
        ],
        edges=[_edge("e1", "s", "d")],
    )

    quality = judge_reference_graph(graph)

    assert quality["critical_count"] == 0
    assert "missing_diagnostic_step" in _codes(quality)


def test_judge_flags_generic_nodes_and_monitoring_category_mismatch():
    graph = GraphSchema(
        nodes=[
            _node("s", "High blood pressure", "SYMPTOM"),
            _node("l", "Proteinuria assessment", "LAB_TEST"),
            _node("d", "Gestational hypertension", "DIAGNOSIS"),
            _node("t", "Treatment", "MEDICATION"),
            _node("bp", "Blood pressure monitoring", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "s", "l"),
            _edge("e2", "l", "d"),
            _edge("e3", "d", "t", "INDICATED_FOR"),
            _edge("e4", "d", "bp", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)
    codes = _codes(quality)

    assert "too_generic_node" in codes
    assert "monitoring_misclassified_as_medication" in codes


def test_judge_blocks_non_drug_actions_categorized_as_medication():
    graph = GraphSchema(
        nodes=[
            _node("s", "Водянистый стул и рвота", "SYMPTOM"),
            _node("e", "Оценка степени обезвоживания", "EXAM"),
            _node("d", "Тяжелое обезвоживание", "DIAGNOSIS"),
            _node("h", "Госпитализация в отделение интенсивной терапии", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "s", "e"),
            _edge("e2", "e", "d"),
            _edge("e3", "d", "h", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert quality["accepted"] is False
    assert "non_medication_action_misclassified_as_medication" in _codes(quality)


def test_judge_blocks_generic_relation_from_diagnosis_to_treatment():
    graph = GraphSchema(
        nodes=[
            _node("s", "Лихорадка и кашель", "SYMPTOM"),
            _node("e", "Рентгенография грудной клетки", "INSTRUMENTAL_TEST"),
            _node("d", "Внебольничная пневмония", "DIAGNOSIS"),
            _node("m", "Антибактериальная терапия", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "s", "e", "REQUIRES_CONFIRMATION"),
            _edge("e2", "e", "d"),
            _edge("e3", "d", "m", "DETERMINES"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert quality["accepted"] is False
    assert "invalid_diagnosis_action_relation" in _codes(quality)


def _detached_graph() -> GraphSchema:
    # Main chain: profile -> diagnosis, evidence -> diagnosis, diagnosis -> med.
    # Detached island: an extra lab feeding a second (differential) diagnosis,
    # with no link to the main chain.
    return GraphSchema(
        nodes=[
            _node("p", "Мужчина 60 лет", "PATIENT_PROFILE"),
            _node("ecg", "ЭКГ", "INSTRUMENTAL_TEST"),
            _node("d", "Инфаркт миокарда с подъемом ST", "DIAGNOSIS"),
            _node("asa", "Ацетилсалициловая кислота", "MEDICATION"),
            _node("dd", "Д-димер", "LAB_TEST"),
            _node("pe", "Тромбоэмболия лёгочной артерии", "DIAGNOSIS"),
        ],
        edges=[
            _edge("e1", "p", "d"),
            _edge("e2", "ecg", "d"),
            _edge("e3", "d", "asa", "INDICATED_FOR"),
            _edge("e4", "dd", "pe"),  # island internal edge
        ],
    )


def test_judge_flags_detached_subgraph_as_critical():
    quality = judge_reference_graph(_detached_graph())

    assert quality["accepted"] is False
    assert quality["critical_count"] >= 1
    assert quality["is_connected"] is False
    assert quality["component_count"] == 2
    assert quality["detached_node_count"] == 2
    assert "detached_subgraph" in _codes(quality)


def test_repair_reconnects_detached_component_and_judge_then_accepts():
    graph = _detached_graph()
    nodes = [node.model_dump() for node in graph.nodes]
    edges = [edge.model_dump() for edge in graph.edges]

    new_nodes, new_edges, actions = repair_graph_connectivity(nodes, edges)

    assert any(a["type"] == "reconnected" for a in actions)
    assert len(new_nodes) == len(nodes)  # nothing pruned; island was reconnectable

    repaired = GraphSchema.model_validate({"nodes": new_nodes, "edges": new_edges})
    quality = judge_reference_graph(repaired)
    assert quality["is_connected"] is True
    assert "detached_subgraph" not in _codes(quality)

    # Idempotent: repairing an already-connected graph is a no-op.
    assert repair_graph_connectivity(new_nodes, new_edges)[2] == []


def test_repair_prunes_island_with_no_valid_bridge():
    # Main chain has no diagnosis; a lone medication island cannot be indicated
    # by anything, so it is pruned rather than wired in with a bogus edge.
    nodes = [
        _node("p", "Пациент", "PATIENT_PROFILE"),
        _node("s", "Боль", "SYMPTOM"),
        _node("m", "Морфин", "MEDICATION"),
    ]
    edges = [_edge("e1", "p", "s")]

    new_nodes, new_edges, actions = repair_graph_connectivity(nodes, edges)

    assert any(a["type"] == "pruned" for a in actions)
    assert {n["id"] for n in new_nodes} == {"p", "s"}


def test_judge_flags_pe_d_dimer_as_confirmatory_in_high_probability_pathway():
    graph = GraphSchema(
        nodes=[
            _node("p", "Послеоперационная пациентка", "PATIENT_PROFILE"),
            _node("s", "Одышка, тахикардия и сатурация 88%", "SYMPTOM"),
            _node("prob", "Высокая клиническая вероятность ТЭЛА", "EXAM"),
            _node("dd", "D-димер повышен", "LAB_TEST"),
            _node("dx", "Тромбоэмболия легочной артерии", "DIAGNOSIS"),
            _node("h", "Терапевтическая антикоагуляция", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "p", "s"),
            _edge("e2", "s", "prob", "REQUIRES_CONFIRMATION"),
            _edge("e3", "prob", "dd", "REQUIRES_CONFIRMATION"),
            _edge("e4", "dd", "dx", "REQUIRES_CONFIRMATION"),
            _edge("e5", "dx", "h", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)
    codes = _codes(quality)

    assert quality["accepted"] is False
    assert "pe_d_dimer_used_as_confirmatory_test" in codes
    assert "pe_high_probability_routed_to_d_dimer" in codes
    assert "pe_missing_imaging_confirmation" in codes


def test_judge_flags_pulmonary_hypertension_echo_without_hemodynamic_confirmation():
    graph = GraphSchema(
        nodes=[
            _node("p", "Patient with unexplained dyspnea", "PATIENT_PROFILE"),
            _node("s", "Dyspnea and right-heart overload", "SYMPTOM"),
            _node("echo", "Echo suggests high probability of pulmonary hypertension", "INSTRUMENTAL_TEST"),
            _node("dx", "Pulmonary hypertension", "DIAGNOSIS"),
            _node("m", "Targeted pulmonary vasodilator therapy", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "p", "s"),
            _edge("e2", "s", "echo", "REQUIRES_CONFIRMATION"),
            _edge("e3", "echo", "dx"),
            _edge("e4", "dx", "m", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)
    codes = _codes(quality)

    assert quality["accepted"] is False
    assert "pulmonary_htn_echo_confirms_final_diagnosis" in codes
    assert "pulmonary_htn_missing_hemodynamic_confirmation" in codes


def test_judge_warns_when_stemi_troponin_can_gate_reperfusion():
    graph = GraphSchema(
        nodes=[
            _node("p", "Мужчина с болью за грудиной", "PATIENT_PROFILE"),
            _node("s", "Давящая боль и холодный пот", "SYMPTOM"),
            _node("ecg", "ЭКГ: подъем ST", "INSTRUMENTAL_TEST"),
            _node("trop", "Тропонин выше 99-го перцентиля", "LAB_TEST"),
            _node("dx", "Инфаркт миокарда с подъемом ST", "DIAGNOSIS"),
            _node("pci", "Первичное ЧКВ как реперфузия", "SURGERY"),
        ],
        edges=[
            _edge("e1", "p", "s"),
            _edge("e2", "s", "ecg", "REQUIRES_CONFIRMATION"),
            _edge("e3", "ecg", "dx"),
            _edge("e4", "trop", "dx", "REQUIRES_CONFIRMATION"),
            _edge("e5", "dx", "pci", "INDICATED_FOR"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert "stemi_troponin_may_delay_reperfusion" in _codes(quality)


def test_judge_does_not_apply_stemi_guardrail_to_nstemi():
    graph = GraphSchema(
        nodes=[
            _node("s", "Боль в грудной клетке", "SYMPTOM"),
            _node("ecg", "ЭКГ без подъема ST", "INSTRUMENTAL_TEST"),
            _node("dx", "NSTEMI высокого риска", "DIAGNOSIS"),
            _node("risk", "Стратификация ишемического риска", "EXAM"),
            _node("angio", "Ранняя коронарография", "SURGERY"),
        ],
        edges=[
            _edge("e1", "s", "ecg", "REQUIRES_CONFIRMATION"),
            _edge("e2", "ecg", "dx", "DETERMINES"),
            _edge("e3", "dx", "risk", "DETERMINES"),
            _edge("e4", "risk", "angio", "DETERMINES"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert "stemi_missing_reperfusion_strategy" not in _codes(quality)
    assert "stemi_missing_ecg_diagnostic_anchor" not in _codes(quality)
    assert quality["critical_count"] == 0


def test_judge_allows_treatment_after_etiology_intermediate_step():
    graph = GraphSchema(
        nodes=[
            _node("s", "Одышка при нагрузке", "SYMPTOM"),
            _node("echo", "ЭхоКГ с высокой вероятностью легочной гипертензии", "INSTRUMENTAL_TEST"),
            _node("suspect", "Подозрение на легочную гипертензию", "DIAGNOSIS"),
            _node("rhc", "Катетеризация правых отделов сердца", "INSTRUMENTAL_TEST"),
            _node("dx", "Подтвержденная легочная гипертензия", "DIAGNOSIS"),
            _node("etiology", "Определение этиологии и клинической группы", "EXAM"),
            _node("therapy", "Терапия после подтверждения диагноза и определения группы", "MEDICATION"),
        ],
        edges=[
            _edge("e1", "s", "echo", "REQUIRES_CONFIRMATION"),
            _edge("e2", "echo", "suspect", "DETERMINES"),
            _edge("e3", "suspect", "rhc", "REQUIRES_CONFIRMATION"),
            _edge("e4", "rhc", "dx", "DETERMINES"),
            _edge("e5", "dx", "etiology", "DETERMINES"),
            _edge("e6", "etiology", "therapy", "DETERMINES"),
        ],
    )

    quality = judge_reference_graph(graph)

    assert "treatment_without_diagnosis" not in _codes(quality)
    assert "pulmonary_htn_missing_hemodynamic_confirmation" not in _codes(quality)
    assert quality["critical_count"] == 0
