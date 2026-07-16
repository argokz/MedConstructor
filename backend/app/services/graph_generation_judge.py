from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from typing import Any

from app.schemas import EdgeType, GraphSchema, NodeType

START_CATEGORIES = {NodeType.PATIENT_PROFILE.value, NodeType.SYMPTOM.value}
EVIDENCE_CATEGORIES = {
    NodeType.EXAM.value,
    NodeType.LAB_TEST.value,
    NodeType.INSTRUMENTAL_TEST.value,
    NodeType.MONITORING.value,
}
ACTION_CATEGORIES = {NodeType.MEDICATION.value, NodeType.SURGERY.value}

# Clinical ordering used to pick a detached component's "entry" node and to
# bridge it back to the main reasoning chain during repair.
CLINICAL_RANK = {
    NodeType.PATIENT_PROFILE.value: 0,
    NodeType.SYMPTOM.value: 1,
    NodeType.EXAM.value: 2,
    NodeType.LAB_TEST.value: 2,
    NodeType.INSTRUMENTAL_TEST.value: 2,
    NodeType.DIAGNOSIS.value: 3,
    NodeType.MEDICATION.value: 4,
    NodeType.SURGERY.value: 4,
    NodeType.MONITORING.value: 5,
}

GENERIC_LABELS = {
    "diagnosis",
    "diagnostics",
    "treatment",
    "therapy",
    "management",
    "monitoring",
    "medication",
    "surgery",
    "examination",
    "lab tests",
    "\u0434\u0438\u0430\u0433\u043d\u043e\u0437",
    "\u0434\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430",
    "\u043b\u0435\u0447\u0435\u043d\u0438\u0435",
    "\u0442\u0435\u0440\u0430\u043f\u0438\u044f",
    "\u0432\u0435\u0434\u0435\u043d\u0438\u0435",
    "\u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433",
    "\u043d\u0430\u0431\u043b\u044e\u0434\u0435\u043d\u0438\u0435",
    "\u043e\u0431\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438\u0435",
    "\u0430\u043d\u0430\u043b\u0438\u0437\u044b",
    "\u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044f",
    "\u043f\u0440\u0435\u043f\u0430\u0440\u0430\u0442",
}

GENERIC_TOKENS = {
    "diagnosis",
    "diagnostics",
    "treatment",
    "therapy",
    "management",
    "monitoring",
    "medication",
    "surgery",
    "examination",
    "tests",
    "\u0434\u0438\u0430\u0433\u043d\u043e\u0437",
    "\u0434\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430",
    "\u043b\u0435\u0447\u0435\u043d\u0438\u0435",
    "\u0442\u0435\u0440\u0430\u043f\u0438\u044f",
    "\u0432\u0435\u0434\u0435\u043d\u0438\u0435",
    "\u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433",
    "\u043d\u0430\u0431\u043b\u044e\u0434\u0435\u043d\u0438\u0435",
    "\u043e\u0431\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438\u0435",
    "\u0430\u043d\u0430\u043b\u0438\u0437",
    "\u0430\u043d\u0430\u043b\u0438\u0437\u044b",
    "\u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044f",
    "\u043f\u0440\u0435\u043f\u0430\u0440\u0430\u0442",
}

MONITORING_MARKERS = (
    "monitoring",
    "follow-up",
    "control",
    "observation",
    "\u043a\u043e\u043d\u0442\u0440\u043e\u043b",
    "\u043c\u043e\u043d\u0438\u0442\u043e\u0440",
    "\u043d\u0430\u0431\u043b\u044e\u0434",
    "\u043a\u0442\u0433",
)

THERAPEUTIC_MARKERS = (
    "beta-blocker",
    "anticoag",
    "analges",
    "\u0431\u0435\u0442\u0430-\u0431\u043b\u043e\u043a\u0430\u0442\u043e\u0440",
    "\u0431\u043a\u043a",
    "\u0430\u043d\u0442\u0438\u043a\u043e\u0430\u0433\u0443\u043b",
    "\u0430\u043d\u0442\u0438\u0430\u0433\u0440\u0435\u0433\u0430\u043d\u0442",
    "\u043e\u0431\u0435\u0437\u0431\u043e\u043b",
    "\u0430\u043d\u0430\u043b\u044c\u0433",
    "\u0434\u0438\u0443\u0440\u0435\u0442",
    "\u0438\u043d\u0433\u0438\u0431\u0438\u0442",
    "\u043f\u0440\u0435\u043f\u0430\u0440\u0430\u0442",
    "\u0442\u0435\u0440\u0430\u043f",
)

NON_MEDICATION_ACTION_MARKERS = (
    "hospitalization",
    "hospitalisation",
    "transfer to",
    "referral",
    "emergency service",
    "diet",
    "feeding",
    "physical cooling",
    "госпитализац",
    "перевод в",
    "направление в",
    "обращение в экстр",
    "отделение реанимац",
    "отделение интенсив",
    "диет",
    "вскармливан",
    "физическ",
    "режим полупостель",
)

SEVERITY_PENALTY = {
    "info": 0.03,
    "warning": 0.12,
    "critical": 0.28,
}


def _category(raw: Any) -> str:
    return getattr(raw, "value", str(raw or "")).upper().strip()


def _edge_label(raw: Any) -> str:
    return getattr(raw, "value", str(raw or "")).upper().strip()


def _label_tokens(label: str) -> set[str]:
    return set(re.findall(r"[a-z\u0430-\u044f\u04510-9]+", label.lower()))


def _is_generic_label(label: str) -> bool:
    normalized = " ".join(str(label or "").lower().strip().split())
    if not normalized:
        return True
    if normalized in GENERIC_LABELS:
        return True
    tokens = _label_tokens(normalized)
    return bool(tokens) and len(tokens) <= 3 and tokens.issubset(GENERIC_TOKENS)


def _looks_like_monitoring(label: str) -> bool:
    lowered = str(label or "").lower()
    if any(marker in lowered for marker in THERAPEUTIC_MARKERS):
        return False
    return any(marker in lowered for marker in MONITORING_MARKERS)


def _looks_like_non_medication_action(label: str) -> bool:
    lowered = _clinical_text(label)
    if "физическ" in lowered and "охлаж" not in lowered:
        return False
    return any(marker in lowered for marker in NON_MEDICATION_ACTION_MARKERS)


def _clinical_text(label: str) -> str:
    return str(label or "").lower().replace("ё", "е")


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _has_all(text: str, markers: tuple[str, ...]) -> bool:
    return all(marker in text for marker in markers)


def _label(node: Any) -> str:
    return _clinical_text(getattr(getattr(node, "data", None), "label", ""))


def _nodes_matching(
    nodes_by_id: dict[str, Any],
    categories_by_id: dict[str, str],
    *,
    any_markers: tuple[str, ...],
    all_markers: tuple[str, ...] = (),
    categories: set[str] | None = None,
    exclude_markers: tuple[str, ...] = (),
) -> set[str]:
    result: set[str] = set()
    for node_id, node in nodes_by_id.items():
        if categories is not None and categories_by_id.get(node_id) not in categories:
            continue
        text = _label(node)
        if exclude_markers and _has_any(text, exclude_markers):
            continue
        if any_markers and not _has_any(text, any_markers):
            continue
        if all_markers and not _has_all(text, all_markers):
            continue
        result.add(node_id)
    return result


def _edge_ids_between(
    edges: list[Any],
    sources: set[str],
    targets: set[str],
    labels: set[str] | None = None,
) -> list[str]:
    ids: list[str] = []
    for edge in edges:
        if str(edge.source) not in sources or str(edge.target) not in targets:
            continue
        if labels is not None and _edge_label(edge.label) not in labels:
            continue
        ids.append(str(edge.id))
    return ids


def _append_clinical_guardrail_warnings(
    graph: GraphSchema,
    nodes_by_id: dict[str, Any],
    categories_by_id: dict[str, str],
    adjacency: dict[str, set[str]],
    warnings: list[dict[str, Any]],
) -> None:
    """Protocol-agnostic clinical safety checks distilled from expert review.

    These rules do not replace specialist review. They convert recurring expert
    objections into automatic guardrails so generated reference graphs fail fast
    before they are shown to students.
    """

    diagnosis_category = {NodeType.DIAGNOSIS.value}
    evidence_categories = {
        NodeType.EXAM.value,
        NodeType.LAB_TEST.value,
        NodeType.INSTRUMENTAL_TEST.value,
    }
    action_categories = {NodeType.MEDICATION.value, NodeType.SURGERY.value}

    # Pulmonary embolism: D-dimer is not confirmatory in a high-probability
    # postoperative scenario; CTPA/VQ imaging must support the diagnosis.
    pe_dx = _nodes_matching(
        nodes_by_id,
        categories_by_id,
        any_markers=("тэл", "тромбоэмбол", "pulmonary embol"),
        all_markers=(),
        categories=diagnosis_category,
    )
    if pe_dx:
        d_dimer = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("d-димер", "д-димер", "d-dimer"),
            categories={NodeType.LAB_TEST.value},
        )
        high_probability = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("высокая клиническая вероятность", "high probability"),
            categories=evidence_categories | diagnosis_category,
        )
        ctpa = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("кт-ангио", "кт ангио", "ctpa", "ct angi", "ангиография легоч"),
            categories={NodeType.INSTRUMENTAL_TEST.value},
        )
        dimer_to_dx = _edge_ids_between(graph.edges, d_dimer, pe_dx)
        high_to_dimer = _edge_ids_between(graph.edges, high_probability, d_dimer)
        if dimer_to_dx:
            warnings.append(
                _warning(
                    "pe_d_dimer_used_as_confirmatory_test",
                    "critical",
                    "D-dimer is modeled as confirming pulmonary embolism.",
                    node_ids=sorted(d_dimer.union(pe_dx)),
                    edge_ids=dimer_to_dx,
                    clinical_reason="In a high-probability or postoperative PE scenario, D-dimer must not confirm the diagnosis; imaging such as CTPA should support the diagnosis.",
                )
            )
        if high_to_dimer:
            warnings.append(
                _warning(
                    "pe_high_probability_routed_to_d_dimer",
                    "warning",
                    "High clinical probability of PE is routed to D-dimer testing.",
                    node_ids=sorted(high_probability.union(d_dimer)),
                    edge_ids=high_to_dimer,
                    clinical_reason="When PE probability is high, D-dimer should not drive the pathway; the graph should route to imaging and management decisions.",
                )
            )
        if not _has_path(adjacency, ctpa, pe_dx):
            warnings.append(
                _warning(
                    "pe_missing_imaging_confirmation",
                    "critical",
                    "Pulmonary embolism diagnosis is not supported by CTPA/imaging.",
                    node_ids=sorted(pe_dx),
                    clinical_reason="The PE reference graph should link confirmatory imaging to the diagnosis before anticoagulation/reperfusion decisions.",
                )
            )

    # STEMI: ECG should establish the emergency pathway; troponin can be sampled
    # but should not delay reperfusion.
    stemi_dx = _nodes_matching(
        nodes_by_id,
        categories_by_id,
        any_markers=("stemi", "подъем st", "подъемом st", "подъём st", "подъёмом st"),
        exclude_markers=("nstemi", "без подъема st", "без подъемом st", "без подъём", "без элевац"),
        categories=diagnosis_category,
    )
    if stemi_dx:
        ecg = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("экг", "ecg", "st "),
            categories={NodeType.INSTRUMENTAL_TEST.value},
        )
        troponin = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("тропонин", "troponin"),
            categories={NodeType.LAB_TEST.value},
            exclude_markers=("без задерж", "without delay", "не задерж"),
        )
        reperfusion = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("чкв", "pci", "реперфуз", "фибринолиз", "fibrinolysis"),
            categories=action_categories,
        )
        if not _has_path(adjacency, ecg, stemi_dx):
            warnings.append(
                _warning(
                    "stemi_missing_ecg_diagnostic_anchor",
                    "critical",
                    "STEMI diagnosis is not anchored to ECG/ST-elevation evidence.",
                    node_ids=sorted(stemi_dx),
                    clinical_reason="For STEMI, the emergency pathway should be driven by ECG evidence, not delayed by biomarker confirmation.",
                )
            )
        troponin_to_dx = _edge_ids_between(graph.edges, troponin, stemi_dx)
        if troponin_to_dx and reperfusion:
            warnings.append(
                _warning(
                    "stemi_troponin_may_delay_reperfusion",
                    "warning",
                    "Troponin is modeled as a diagnostic gate before reperfusion.",
                    node_ids=sorted(troponin.union(stemi_dx).union(reperfusion)),
                    edge_ids=troponin_to_dx,
                    clinical_reason="Troponin may be taken, but reperfusion in STEMI should not wait for troponin results when ECG criteria are present.",
                )
            )
        if not reperfusion:
            warnings.append(
                _warning(
                    "stemi_missing_reperfusion_strategy",
                    "critical",
                    "STEMI graph has no PCI/fibrinolysis/reperfusion action.",
                    node_ids=sorted(stemi_dx),
                    clinical_reason="A STEMI reference graph must include an explicit reperfusion strategy.",
                )
            )

    # Pulmonary hypertension: echo suggests probability; right-heart
    # catheterization/hemodynamics confirms the diagnosis.
    ph_dx = _nodes_matching(
        nodes_by_id,
        categories_by_id,
        any_markers=("легочная гипертенз", "легочной гипертенз", "pulmonary hypertension"),
        categories=diagnosis_category,
        exclude_markers=("подозр", "suspicion", "вероятн"),
    )
    if ph_dx:
        echo = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("эхо", "echo"),
            categories={NodeType.INSTRUMENTAL_TEST.value},
        )
        rhc = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("катетеризац", "right-heart", "right heart", "rhc", "гемодинами"),
            categories=evidence_categories,
        )
        echo_to_dx = _edge_ids_between(graph.edges, echo, ph_dx, {EdgeType.DETERMINES.value})
        if echo_to_dx:
            warnings.append(
                _warning(
                    "pulmonary_htn_echo_confirms_final_diagnosis",
                    "warning",
                    "Echo is modeled as directly determining final pulmonary hypertension diagnosis.",
                    node_ids=sorted(echo.union(ph_dx)),
                    edge_ids=echo_to_dx,
                    clinical_reason="Echo should usually establish suspicion/probability; invasive hemodynamic confirmation should support the final diagnosis.",
                )
            )
        if not _has_path(adjacency, rhc, ph_dx):
            warnings.append(
                _warning(
                    "pulmonary_htn_missing_hemodynamic_confirmation",
                    "critical",
                    "Pulmonary hypertension diagnosis lacks catheterization/hemodynamic confirmation.",
                    node_ids=sorted(ph_dx),
                    clinical_reason="The graph should separate suspicion by echo from final confirmation by right-heart catheterization/hemodynamics.",
                )
            )

    # Atrial fibrillation anticoagulation: high stroke risk requires bleeding
    # risk and valvular-status checks before DOAC-style anticoagulation.
    af_dx = _nodes_matching(
        nodes_by_id,
        categories_by_id,
        any_markers=("фибрилляц", "atrial fibrillation"),
        all_markers=(),
        categories=diagnosis_category,
    )
    if af_dx:
        anticoagulants = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("антикоаг", "поак", "doac", "варфар", "warfar", "apix", "rivarox"),
            categories={NodeType.MEDICATION.value},
        )
        bleeding_risk = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("has-bled", "кровотеч", "bleeding"),
            categories=evidence_categories | {NodeType.MONITORING.value},
        )
        valvular_check = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("клапан", "митральн", "mechanical valve", "valvular"),
            categories=evidence_categories | diagnosis_category,
        )
        if anticoagulants and not bleeding_risk:
            warnings.append(
                _warning(
                    "af_anticoagulation_without_bleeding_risk",
                    "warning",
                    "AF anticoagulation is modeled without bleeding-risk assessment.",
                    node_ids=sorted(af_dx.union(anticoagulants)),
                    clinical_reason="A defensible AF graph should show stroke-risk benefit together with bleeding/renal safety assessment.",
                )
            )
        if anticoagulants and not valvular_check:
            warnings.append(
                _warning(
                    "af_anticoagulation_without_valvular_check",
                    "warning",
                    "AF anticoagulation graph does not model valvular-status exclusion/check.",
                    node_ids=sorted(af_dx.union(anticoagulants)),
                    clinical_reason="DOAC-style pathways require checking for mechanical valve/significant mitral stenosis or other valvular constraints.",
                )
            )

    # Aortic dissection: thrombolysis must be explicitly contraindicated and
    # surgery plus hemodynamic control should be present.
    dissection_dx = _nodes_matching(
        nodes_by_id,
        categories_by_id,
        any_markers=("рассло", "dissection"),
        categories=diagnosis_category,
    )
    if dissection_dx:
        thrombolysis = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("тромболиз", "thrombolysis"),
            categories={NodeType.MEDICATION.value},
        )
        ct_angio = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("кт-ангио", "кт ангио", "ct angi", "ангиография"),
            categories={NodeType.INSTRUMENTAL_TEST.value},
        )
        surgery = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("кардиохир", "операц", "surgery", "surgical"),
            categories={NodeType.SURGERY.value},
        )
        bp_hr_control = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("чсс", "ад", "давлен", "bp", "heart rate"),
            categories=evidence_categories | action_categories | {NodeType.MONITORING.value},
        )
        contra_edges = _edge_ids_between(graph.edges, thrombolysis, dissection_dx, {EdgeType.CONTRAINDICATED_DUE_TO.value})
        if thrombolysis and not contra_edges:
            warnings.append(
                _warning(
                    "aortic_dissection_thrombolysis_not_contraindicated",
                    "critical",
                    "Thrombolysis appears in aortic dissection graph without contraindication relation.",
                    node_ids=sorted(thrombolysis.union(dissection_dx)),
                    clinical_reason="Thrombolysis in aortic dissection is life-threatening and must be explicitly contraindicated if present.",
                )
            )
        if not _has_path(adjacency, ct_angio, dissection_dx):
            warnings.append(
                _warning(
                    "aortic_dissection_missing_ct_confirmation",
                    "critical",
                    "Aortic dissection diagnosis lacks CT-angiography confirmation.",
                    node_ids=sorted(dissection_dx),
                    clinical_reason="A defensible dissection graph should link CT angiography/imaging evidence to the diagnosis.",
                )
            )
        if not _has_path(adjacency, dissection_dx, surgery):
            warnings.append(
                _warning(
                    "aortic_dissection_missing_surgical_route",
                    "critical",
                    "Stanford A dissection graph lacks a diagnosis-to-surgery route.",
                    node_ids=sorted(dissection_dx),
                    clinical_reason="Stanford A dissection requires urgent cardiothoracic surgical routing.",
                )
            )
        if not bp_hr_control:
            warnings.append(
                _warning(
                    "aortic_dissection_missing_bp_hr_control",
                    "warning",
                    "Aortic dissection graph lacks explicit BP/heart-rate control targets.",
                    node_ids=sorted(dissection_dx),
                    clinical_reason="Dissection management should model hemodynamic control alongside urgent surgery.",
                )
            )

    # Hypertensive emergency: avoid uncontrolled normalization and make the
    # target-organ/neuro branch explicit when neurological deficit is present.
    hypertensive_emergency = _nodes_matching(
        nodes_by_id,
        categories_by_id,
        any_markers=("гипертоническая экстр", "hypertensive emergency"),
        categories=diagnosis_category,
    )
    if hypertensive_emergency:
        tempo = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("20-25", "20–25", "первый час", "1 час", "титр", "gradual", "titr"),
            categories=evidence_categories | action_categories | {NodeType.MONITORING.value},
        )
        neuro_deficit = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("невролог", "дефицит", "stroke", "neurolog"),
            categories=evidence_categories,
        )
        neuroimaging = _nodes_matching(
            nodes_by_id,
            categories_by_id,
            any_markers=("нейровиз", "кт", "мрт", "ct", "mri"),
            categories={NodeType.INSTRUMENTAL_TEST.value},
        )
        if not tempo:
            warnings.append(
                _warning(
                    "hypertensive_emergency_missing_bp_reduction_tempo",
                    "warning",
                    "Hypertensive emergency graph lacks target tempo of BP reduction.",
                    node_ids=sorted(hypertensive_emergency),
                    clinical_reason="Emergency BP reduction should be titrated; students should not learn abrupt normalization to ordinary values.",
                )
            )
        if neuro_deficit and not neuroimaging:
            warnings.append(
                _warning(
                    "hypertensive_emergency_missing_neuroimaging",
                    "warning",
                    "Neurologic deficit is present without neuroimaging branch.",
                    node_ids=sorted(neuro_deficit.union(hypertensive_emergency)),
                    clinical_reason="Focal neurologic deficit in hypertensive emergency should trigger organ-specific neurologic evaluation.",
                )
            )


def _weakly_connected_components(
    node_ids: list[str], undirected: dict[str, set[str]]
) -> list[list[str]]:
    """Connected components treating every edge as undirected."""
    seen: set[str] = set()
    components: list[list[str]] = []
    for start in node_ids:
        if start in seen:
            continue
        stack = [start]
        component: list[str] = []
        while stack:
            node_id = stack.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            component.append(node_id)
            stack.extend(undirected.get(node_id, set()) - seen)
        components.append(component)
    return components


def _main_component(
    components: list[list[str]], backbone: set[str]
) -> list[str]:
    """The component that carries the clinical backbone (patient/symptom start +
    diagnosis); ties broken by node count. This is the "main clinical chain";
    everything else is a detached sub-graph."""
    if not components:
        return []
    return max(components, key=lambda component: (len(set(component) & backbone), len(component)))


def _has_path(adjacency: dict[str, set[str]], starts: set[str], targets: set[str]) -> bool:
    if not starts or not targets:
        return False
    queue = deque(starts)
    seen = set(starts)
    while queue:
        node_id = queue.popleft()
        if node_id in targets:
            return True
        for next_id in adjacency.get(node_id, set()):
            if next_id in seen:
                continue
            seen.add(next_id)
            queue.append(next_id)
    return False


def _warning(
    code: str,
    severity: str,
    message: str,
    *,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    clinical_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "node_ids": node_ids or [],
        "edge_ids": edge_ids or [],
        "clinical_reason": clinical_reason or message,
    }


def format_quality_warning(warning: dict[str, Any]) -> str:
    severity = str(warning.get("severity") or "warning").upper()
    code = str(warning.get("code") or "graph_quality")
    message = str(warning.get("message") or "")
    return f"{severity} {code}: {message}"


def judge_reference_graph(graph: GraphSchema) -> dict[str, Any]:
    nodes_by_id = {str(node.id): node for node in graph.nodes}
    categories_by_id = {node_id: _category(node.data.category) for node_id, node in nodes_by_id.items()}

    adjacency: dict[str, set[str]] = defaultdict(set)
    undirected: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, list[Any]] = defaultdict(list)
    outgoing: dict[str, list[Any]] = defaultdict(list)
    for edge in graph.edges:
        source = str(edge.source)
        target = str(edge.target)
        adjacency[source].add(target)
        undirected[source].add(target)
        undirected[target].add(source)
        incoming[target].append(edge)
        outgoing[source].append(edge)

    starts = {node_id for node_id, category in categories_by_id.items() if category in START_CATEGORIES}
    evidence = {node_id for node_id, category in categories_by_id.items() if category in EVIDENCE_CATEGORIES}
    diagnoses = {node_id for node_id, category in categories_by_id.items() if category == NodeType.DIAGNOSIS.value}
    actions = {node_id for node_id, category in categories_by_id.items() if category in ACTION_CATEGORIES}
    contraindicated_actions = {
        node_id
        for node_id in actions
        if any(
            _edge_label(edge.label) == EdgeType.CONTRAINDICATED_DUE_TO.value
            for edge in outgoing.get(node_id, [])
        )
    }
    indicated_actions = actions - contraindicated_actions

    # Differential diagnoses that the graph explicitly rules out (target of an
    # EXCLUDES edge) are not the working diagnosis, so they do not need a full
    # diagnostic-evidence workup of their own.
    excluded_diagnoses = {
        str(edge.target)
        for edge in graph.edges
        if _edge_label(edge.label) == EdgeType.EXCLUDES.value
        and categories_by_id.get(str(edge.target)) == NodeType.DIAGNOSIS.value
    }

    warnings: list[dict[str, Any]] = []

    if not nodes_by_id:
        warnings.append(
            _warning(
                "empty_graph",
                "critical",
                "Reference graph has no nodes.",
                clinical_reason="A task cannot be graded against an empty clinical reasoning graph.",
            )
        )

    if not diagnoses:
        warnings.append(
            _warning(
                "missing_diagnosis",
                "critical",
                "Reference graph has no DIAGNOSIS node.",
                clinical_reason="The expected clinical decision is absent, so treatment and grading become ambiguous.",
            )
        )

    if not starts:
        warnings.append(
            _warning(
                "missing_clinical_start",
                "warning",
                "Reference graph has no PATIENT_PROFILE or SYMPTOM starting node.",
                clinical_reason="Students should be able to reason from patient data toward decisions.",
            )
        )

    if diagnoses and not evidence:
        warnings.append(
            _warning(
                "missing_diagnostic_step",
                "warning",
                "Reference graph has a diagnosis but no exam, lab, instrumental test, or monitoring evidence.",
                clinical_reason="A defensible diagnosis usually needs an explicit evidence step.",
            )
        )

    if starts and diagnoses and not _has_path(adjacency, starts, diagnoses):
        warnings.append(
            _warning(
                "no_path_to_diagnosis",
                "critical",
                "No directed path connects patient data or symptoms to diagnosis.",
                node_ids=sorted(starts.union(diagnoses)),
                clinical_reason="The graph does not express clinical reasoning from presentation to diagnosis.",
            )
        )

    # Detached sub-graph detection (undirected connectivity). Any node not in the
    # component that carries the clinical backbone is an island — internally it may
    # have edges, but it is not part of the main reasoning chain. This is a
    # CRITICAL defect: it blocks acceptance so such graphs can never be
    # auto-published, at every write path that keys status off critical_count.
    all_node_ids = list(nodes_by_id.keys())
    components = _weakly_connected_components(all_node_ids, undirected)
    backbone = starts | diagnoses
    main_component = set(_main_component(components, backbone))
    detached_ids = [node_id for node_id in all_node_ids if node_id not in main_component]
    if detached_ids and len(components) > 1:
        detached_labels = [str(nodes_by_id[node_id].data.label or "") for node_id in detached_ids]
        preview = ", ".join(f"'{label}'" for label in detached_labels[:6])
        warnings.append(
            _warning(
                "detached_subgraph",
                "critical",
                f"{len(detached_ids)} node(s) in {len(components) - 1} detached sub-graph(s) "
                f"are not connected to the main clinical chain: {preview}.",
                node_ids=sorted(detached_ids),
                clinical_reason="Blocks that are not linked to the main patient→diagnosis→treatment "
                "chain do not participate in clinical reasoning or grading; every block must connect "
                "to the main chain.",
            )
        )

    for diagnosis_id in sorted(diagnoses):
        if diagnosis_id in excluded_diagnoses:
            continue
        incoming_sources = {str(edge.source) for edge in incoming.get(diagnosis_id, [])}
        if evidence and not incoming_sources.intersection(evidence):
            warnings.append(
                _warning(
                    "diagnosis_without_diagnostic_evidence",
                    "warning",
                    "Diagnosis has no direct incoming edge from a diagnostic/evidence node.",
                    node_ids=[diagnosis_id],
                    clinical_reason="The diagnosis should usually be supported by exam, lab, instrumental, or monitoring evidence.",
                )
            )

    for action_id in sorted(actions):
        has_indication = False
        has_contraindication = action_id in contraindicated_actions
        for edge in incoming.get(action_id, []):
            if str(edge.source) in diagnoses and _edge_label(edge.label) == EdgeType.INDICATED_FOR.value:
                has_indication = True
                break
        if not has_indication:
            has_indication = _has_path(adjacency, diagnoses, {action_id})
        if not has_indication and not has_contraindication:
            warnings.append(
                _warning(
                    "treatment_without_diagnosis",
                    "critical",
                    "Medication or surgery is not indicated by a diagnosis.",
                    node_ids=[action_id],
                    clinical_reason="Therapeutic actions should follow an established or working diagnosis.",
                )
            )

    if diagnoses and indicated_actions and not _has_path(adjacency, diagnoses, indicated_actions):
        warnings.append(
            _warning(
                "no_path_from_diagnosis_to_action",
                "warning",
                "No directed path connects diagnosis to treatment action.",
                node_ids=sorted(diagnoses.union(indicated_actions)),
                clinical_reason="The reference answer should explain why treatment follows from diagnosis.",
            )
        )

    for edge in graph.edges:
        source_id = str(edge.source)
        target_id = str(edge.target)
        source_category = categories_by_id.get(source_id)
        target_category = categories_by_id.get(target_id)
        relation = _edge_label(edge.label)
        if (
            source_category == NodeType.DIAGNOSIS.value
            and target_category in ACTION_CATEGORIES | {NodeType.MONITORING.value}
            and relation != EdgeType.INDICATED_FOR.value
        ):
            warnings.append(
                _warning(
                    "invalid_diagnosis_action_relation",
                    "critical",
                    "Diagnosis-to-action edge does not use INDICATED_FOR.",
                    node_ids=[source_id, target_id],
                    edge_ids=[str(edge.id)],
                    clinical_reason="Treatment and monitoring decisions must be explicitly modeled as indicated by a diagnosis; a generic DETERMINES relation is not sufficient.",
                )
            )

    # Safety coverage: the platform's core differentiator is safety-aware grading,
    # but contraindication structure is easy to omit. Surface (advisory) when a
    # graph prescribes therapy yet models no contraindication at all, so the teacher
    # can add a safety constraint where the protocol supports one.
    if actions and not contraindicated_actions:
        warnings.append(
            _warning(
                "no_contraindication_modeled",
                "info",
                "Reference graph prescribes treatment but models no contraindication (CONTRAINDICATED_DUE_TO).",
                node_ids=sorted(actions),
                clinical_reason="Safety-aware reasoning is the platform's core; where the protocol lists a contraindication or red flag, model it so students are assessed on safety.",
            )
        )

    for node_id, node in sorted(nodes_by_id.items()):
        label = str(node.data.label or "")
        category = categories_by_id[node_id]
        if _is_generic_label(label):
            warnings.append(
                _warning(
                    "too_generic_node",
                    "warning",
                    f"Node '{label}' is too generic.",
                    node_ids=[node_id],
                    clinical_reason="Generic nodes are hard to compare against student answers and reduce pedagogical precision.",
                )
            )
        if (
            category == NodeType.MEDICATION.value
            and node_id not in contraindicated_actions
            and _looks_like_monitoring(label)
        ):
            warnings.append(
                _warning(
                    "monitoring_misclassified_as_medication",
                    "warning",
                    f"Monitoring-like node '{label}' is categorized as MEDICATION.",
                    node_ids=[node_id],
                    clinical_reason="Monitoring/control actions should not be graded as drug therapy.",
                )
            )
        if category == NodeType.MEDICATION.value and _looks_like_non_medication_action(label):
            warnings.append(
                _warning(
                    "non_medication_action_misclassified_as_medication",
                    "critical",
                    f"Non-drug action '{label}' is categorized as MEDICATION.",
                    node_ids=[node_id],
                    clinical_reason="Hospitalization, referral, diet, feeding, and physical measures are not medicines. Misclassification makes category scoring and safety checks clinically misleading.",
                )
            )

    labels = [str(node.data.label or "").lower().strip() for node in graph.nodes]
    duplicate_labels = [label for label, count in Counter(labels).items() if label and count > 1]
    for label in duplicate_labels:
        duplicate_ids = [
            str(node.id)
            for node in graph.nodes
            if str(node.data.label or "").lower().strip() == label
        ]
        warnings.append(
            _warning(
                "duplicate_node_label",
                "info",
                f"Duplicate node label '{label}'.",
                node_ids=duplicate_ids,
                clinical_reason="Duplicate labels can make graph matching less stable.",
            )
        )

    _append_clinical_guardrail_warnings(
        graph,
        nodes_by_id,
        categories_by_id,
        adjacency,
        warnings,
    )

    if len(graph.nodes) > 24 or len(graph.edges) > max(36, round(len(graph.nodes) * 1.5)):
        warnings.append(
            _warning(
                "reference_graph_too_dense",
                "warning",
                f"Reference graph is dense ({len(graph.nodes)} nodes, {len(graph.edges)} edges).",
                clinical_reason="A single educational task should focus on assessable decisions. Dense graphs can penalize concise but clinically valid student answers and should be simplified or split into subtasks.",
            )
        )

    penalty = sum(SEVERITY_PENALTY.get(str(w["severity"]), 0.12) for w in warnings)
    quality_score = max(0.0, min(1.0, round(1.0 - penalty, 2)))
    critical_count = sum(1 for warning in warnings if warning["severity"] == "critical")
    warning_count = len(warnings)

    return {
        "schema_valid": True,
        "accepted": critical_count == 0 and quality_score >= 0.75,
        "quality_score": quality_score,
        "warning_count": warning_count,
        "critical_count": critical_count,
        "component_count": len(components),
        "detached_node_count": len(detached_ids),
        "is_connected": not detached_ids,
        "has_diagnosis": bool(diagnoses),
        "has_diagnostic_step": bool(evidence),
        "has_start_to_diagnosis_path": (not starts or not diagnoses) or _has_path(adjacency, starts, diagnoses),
        "has_diagnosis_to_action_path": (
            (not diagnoses or not indicated_actions)
            or _has_path(adjacency, diagnoses, indicated_actions)
        ),
        "warnings": warnings,
    }


def _bridge_edge(
    entry_id: str,
    entry_category: str,
    main_diagnosis: str | None,
    main_start: str | None,
) -> dict[str, Any] | None:
    """A clinically-valid directed edge that attaches a detached component's entry
    node to the main chain, or None if no defensible bridge exists (then the
    component is pruned). Edge directions/labels obey the same category rules the
    generator's normalizer enforces, so the result stays schema-valid."""
    edge_id = f"edge_repair_{entry_id}"
    if entry_category in EVIDENCE_CATEGORIES and main_diagnosis:
        # evidence supports the working diagnosis
        return {"id": edge_id, "source": entry_id, "target": main_diagnosis, "label": EdgeType.DETERMINES.value}
    if entry_category in {NodeType.SYMPTOM.value, NodeType.PATIENT_PROFILE.value} and main_diagnosis:
        # presentation leads to the working diagnosis
        return {"id": edge_id, "source": entry_id, "target": main_diagnosis, "label": EdgeType.DETERMINES.value}
    if entry_category in ACTION_CATEGORIES and main_diagnosis:
        # treatment is indicated by the diagnosis
        return {"id": edge_id, "source": main_diagnosis, "target": entry_id, "label": EdgeType.INDICATED_FOR.value}
    if entry_category == NodeType.MONITORING.value and main_diagnosis:
        return {"id": edge_id, "source": main_diagnosis, "target": entry_id, "label": EdgeType.INDICATED_FOR.value}
    if entry_category == NodeType.DIAGNOSIS.value and main_start:
        # a secondary diagnosis reasoned from the presentation
        return {"id": edge_id, "source": main_start, "target": entry_id, "label": EdgeType.DETERMINES.value}
    return None


def repair_graph_connectivity(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Guarantee a single connected clinical graph.

    Detached components (islands) are reconnected to the main clinical chain via a
    single clinically-valid bridge edge on the component's lowest-rank "entry"
    node; if no defensible bridge exists the component is pruned. Returns
    (nodes, edges, actions) where every action records what was changed so the
    caller can surface it for teacher review. Idempotent: a fully-connected graph
    is returned unchanged with no actions.
    """
    actions: list[dict[str, Any]] = []
    id_to_node = {str(node.get("id")): node for node in nodes}

    def category(node_id: str) -> str:
        return _category((id_to_node[node_id].get("data") or {}).get("category"))

    def label(node_id: str) -> str:
        return str((id_to_node[node_id].get("data") or {}).get("label") or "")

    undirected: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in id_to_node and target in id_to_node:
            undirected[source].add(target)
            undirected[target].add(source)

    node_ids = list(id_to_node.keys())
    components = _weakly_connected_components(node_ids, undirected)
    if len(components) <= 1:
        return nodes, edges, actions

    starts = {nid for nid in node_ids if category(nid) in START_CATEGORIES}
    diagnoses = {nid for nid in node_ids if category(nid) == NodeType.DIAGNOSIS.value}
    main_set = set(_main_component(components, starts | diagnoses))
    main_diagnosis = next((nid for nid in main_set if category(nid) == NodeType.DIAGNOSIS.value), None)
    main_start = next((nid for nid in main_set if category(nid) in START_CATEGORIES), None)

    result_edges = list(edges)
    pruned_ids: set[str] = set()

    for component in components:
        if set(component) <= main_set:
            continue
        entry = min(component, key=lambda nid: CLINICAL_RANK.get(category(nid), 9))
        bridge = _bridge_edge(entry, category(entry), main_diagnosis, main_start)
        if bridge:
            result_edges.append(bridge)
            actions.append({
                "type": "reconnected",
                "entry_id": entry,
                "entry_label": label(entry),
                "edge": bridge,
                "component_labels": [label(nid) for nid in component],
            })
        else:
            pruned_ids.update(component)
            actions.append({
                "type": "pruned",
                "node_ids": list(component),
                "labels": [label(nid) for nid in component],
            })

    if pruned_ids:
        nodes = [node for node in nodes if str(node.get("id")) not in pruned_ids]
        result_edges = [
            edge for edge in result_edges
            if str(edge.get("source")) not in pruned_ids and str(edge.get("target")) not in pruned_ids
        ]

    return nodes, result_edges, actions
