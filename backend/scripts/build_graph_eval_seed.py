from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_OUTPUT = BACKEND_ROOT / "benchmarks" / "graph_cases.research.seed.json"

POSITION = {"x": 0.0, "y": 0.0}


def _node(node_id: str, label: str, category: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "med",
        "position": dict(POSITION),
        "data": {"label": label, "category": category},
    }


def _edge(edge_id: str, source: str, target: str, label: str) -> dict[str, str]:
    return {"id": edge_id, "source": source, "target": target, "label": label}


CASE_SPECS: list[dict[str, Any]] = [
    {
        "case_id": "gestational_hypertension",
        "title": "Гестационная гипертензия",
        "profile": "Пациентка 28 лет, беременность 30 недель",
        "symptom": "АД 145/95 мм рт.ст., головная боль и отеки",
        "evidence": [
            ("exam", "Повторное измерение артериального давления", "EXAM"),
            ("lab", "Оценка протеинурии и тромбоцитов", "LAB_TEST"),
        ],
        "diagnosis": "Гестационная гипертензия легкой степени",
        "action": ("Лабеталол или метилдопа при показаниях", "MEDICATION"),
        "followup": "Мониторинг артериального давления и состояния плода",
        "contraindication": ("Ингибитор АПФ при беременности", "MEDICATION", "profile"),
    },
    {
        "case_id": "severe_preeclampsia",
        "title": "Тяжелая преэклампсия",
        "profile": "Пациентка 32 лет, беременность 35 недель",
        "symptom": "АД 170/110 мм рт.ст., головная боль и нарушение зрения",
        "evidence": [
            ("lab", "Протеинурия, креатинин и тромбоциты", "LAB_TEST"),
            ("exam", "Оценка неврологических симптомов", "EXAM"),
        ],
        "diagnosis": "Тяжелая преэклампсия",
        "action": ("Сульфат магния для профилактики судорог", "MEDICATION"),
        "followup": "Мониторинг АД, диуреза и сердцебиения плода",
        "contraindication": ("Ингибитор АПФ при беременности", "MEDICATION", "profile"),
    },
    {
        "case_id": "ectopic_pregnancy",
        "title": "Внематочная беременность",
        "profile": "Пациентка репродуктивного возраста с задержкой менструации",
        "symptom": "Боль внизу живота, кровянистые выделения и слабость",
        "evidence": [
            ("lab", "Положительный бета-ХГЧ", "LAB_TEST"),
            ("instrumental", "Трансвагинальное УЗИ без плодного яйца в матке", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Внематочная беременность",
        "action": ("Лапароскопическое лечение при нестабильности", "SURGERY"),
        "followup": "Мониторинг гемодинамики и уровня ХГЧ",
        "contraindication": ("Ожидательная тактика при гемодинамической нестабильности", "SURGERY", "symptom"),
    },
    {
        "case_id": "obstetric_sepsis",
        "title": "Акушерский сепсис",
        "profile": "Роженица в раннем послеродовом периоде",
        "symptom": "Лихорадка, тахикардия и гипотензия",
        "evidence": [
            ("lab", "Лейкоцитоз, С-реактивный белок и посев крови", "LAB_TEST"),
            ("exam", "Оценка источника инфекции", "EXAM"),
        ],
        "diagnosis": "Акушерский сепсис",
        "action": ("Немедленная широкоспектральная антибактериальная терапия", "MEDICATION"),
        "followup": "Мониторинг лактата, диуреза и гемодинамики",
        "contraindication": ("Задержка введения антибиотика при сепсисе", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "pulmonary_embolism_pregnancy",
        "title": "Тромбоэмболия легочной артерии при беременности",
        "profile": "Беременная пациентка с внезапной одышкой",
        "symptom": "Одышка, боль в груди и тахикардия",
        "evidence": [
            ("instrumental", "Компрессионное УЗИ вен или КТ-ангиография по показаниям", "INSTRUMENTAL_TEST"),
            ("exam", "Оценка сатурации и гемодинамики", "EXAM"),
        ],
        "diagnosis": "Тромбоэмболия легочной артерии",
        "action": ("Низкомолекулярный гепарин", "MEDICATION"),
        "followup": "Мониторинг сатурации, кровотечения и состояния плода",
        "contraindication": ("Варфарин в первом триместре беременности", "MEDICATION", "profile"),
    },
    {
        "case_id": "anaphylactic_shock",
        "title": "Анафилактический шок",
        "profile": "Пациент после введения лекарственного препарата",
        "symptom": "Крапивница, бронхоспазм и падение артериального давления",
        "evidence": [
            ("exam", "Оценка дыхательных путей, сатурации и давления", "EXAM"),
            ("lab", "Сывороточная триптаза при возможности", "LAB_TEST"),
        ],
        "diagnosis": "Анафилактический шок",
        "action": ("Адреналин внутримышечно", "MEDICATION"),
        "followup": "Мониторинг дыхательных путей и гемодинамики",
        "contraindication": ("Бета-блокатор как лечение анафилаксии", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "pediatric_asthma_exacerbation",
        "title": "Обострение бронхиальной астмы у ребенка",
        "profile": "Ребенок 9 лет с известной бронхиальной астмой",
        "symptom": "Свистящее дыхание, одышка и кашель",
        "evidence": [
            ("exam", "Аускультация легких и оценка степени одышки", "EXAM"),
            ("instrumental", "Пикфлоуметрия или спирометрия при возможности", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Обострение бронхиальной астмы",
        "action": ("Ингаляционный сальбутамол через спейсер", "MEDICATION"),
        "followup": "Мониторинг сатурации и частоты дыхания",
        "contraindication": ("Неселективный бета-блокатор при бронхоспазме", "MEDICATION", "symptom"),
    },
    {
        "case_id": "ulcerative_colitis_child",
        "title": "Язвенный колит у детей",
        "profile": "Подросток с длительной диареей",
        "symptom": "Кровь в стуле, боль в животе и потеря массы тела",
        "evidence": [
            ("lab", "Фекальный кальпротектин и общий анализ крови", "LAB_TEST"),
            ("instrumental", "Колоноскопия с биопсией", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Язвенный колит",
        "action": ("Месалазин или кортикостероиды по тяжести", "MEDICATION"),
        "followup": "Мониторинг роста, питания и активности воспаления",
        "contraindication": ("НПВС при активном язвенном колите", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "renovascular_hypertension",
        "title": "Реноваскулярная гипертензия",
        "profile": "Пациент с резистентной артериальной гипертензией",
        "symptom": "Высокое АД несмотря на комбинированную терапию",
        "evidence": [
            ("instrumental", "Дуплексное сканирование почечных артерий", "INSTRUMENTAL_TEST"),
            ("lab", "Креатинин и скорость клубочковой фильтрации", "LAB_TEST"),
        ],
        "diagnosis": "Реноваскулярная гипертензия",
        "action": ("Реваскуляризация почечной артерии при показаниях", "SURGERY"),
        "followup": "Мониторинг АД и функции почек",
        "contraindication": ("Ингибитор АПФ при двустороннем стенозе почечных артерий", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "von_willebrand_disease",
        "title": "Болезнь Виллебранда",
        "profile": "Пациент с повторными носовыми кровотечениями",
        "symptom": "Кровоточивость слизистых и синяки после травм",
        "evidence": [
            ("lab", "Активность фактора Виллебранда и фактор VIII", "LAB_TEST"),
            ("lab2", "АЧТВ и агрегация тромбоцитов", "LAB_TEST"),
        ],
        "diagnosis": "Болезнь Виллебранда",
        "action": ("Десмопрессин или концентрат фактора Виллебранда", "MEDICATION"),
        "followup": "Мониторинг кровотечения и гемостаза",
        "contraindication": ("Аспирин при болезни Виллебранда", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "diabetic_ketoacidosis_child",
        "title": "Диабетический кетоацидоз у ребенка",
        "profile": "Ребенок с сахарным диабетом 1 типа",
        "symptom": "Рвота, боли в животе, запах ацетона и сонливость",
        "evidence": [
            ("lab", "Глюкоза, кетоны и метаболический ацидоз", "LAB_TEST"),
            ("lab2", "Калий, натрий и осмолярность крови", "LAB_TEST"),
        ],
        "diagnosis": "Диабетический кетоацидоз",
        "action": ("Инфузионная терапия и внутривенный инсулин", "MEDICATION"),
        "followup": "Мониторинг гликемии, калия и неврологического статуса",
        "contraindication": ("Рутинное введение бикарбоната без тяжелого ацидоза", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "acute_appendicitis_child",
        "title": "Острый аппендицит у ребенка",
        "profile": "Ребенок с острой болью в животе",
        "symptom": "Боль в правой подвздошной области, тошнота и лихорадка",
        "evidence": [
            ("exam", "Симптомы раздражения брюшины", "EXAM"),
            ("instrumental", "УЗИ органов брюшной полости", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Острый аппендицит",
        "action": ("Аппендэктомия", "SURGERY"),
        "followup": "Мониторинг температуры и послеоперационной раны",
        "contraindication": ("Слабительные средства при подозрении на аппендицит", "MEDICATION", "symptom"),
    },
    {
        "case_id": "community_pneumonia_child",
        "title": "Внебольничная пневмония у ребенка",
        "profile": "Ребенок с кашлем и лихорадкой",
        "symptom": "Лихорадка, тахипноэ и влажные хрипы",
        "evidence": [
            ("instrumental", "Рентгенография органов грудной клетки", "INSTRUMENTAL_TEST"),
            ("lab", "Общий анализ крови и С-реактивный белок", "LAB_TEST"),
        ],
        "diagnosis": "Внебольничная пневмония",
        "action": ("Антибактериальная терапия по возрасту и тяжести", "MEDICATION"),
        "followup": "Мониторинг сатурации и дыхательной недостаточности",
        "contraindication": ("Опиоидное противокашлевое средство у ребенка", "MEDICATION", "profile"),
    },
    {
        "case_id": "meningococcal_infection",
        "title": "Менингококковая инфекция",
        "profile": "Пациент с внезапной лихорадкой",
        "symptom": "Петехиальная сыпь, ригидность затылочных мышц и слабость",
        "evidence": [
            ("exam", "Осмотр кожи и менингеальные симптомы", "EXAM"),
            ("lab", "Посев крови или ПЦР на менингококк", "LAB_TEST"),
        ],
        "diagnosis": "Менингококковая инфекция",
        "action": ("Немедленное введение цефтриаксона", "MEDICATION"),
        "followup": "Мониторинг гемодинамики и сознания",
        "contraindication": ("Отсрочка антибиотика до лабораторного подтверждения", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "acute_coronary_syndrome",
        "title": "Острый коронарный синдром",
        "profile": "Пациент 58 лет с факторами сердечно-сосудистого риска",
        "symptom": "Загрудинная боль с иррадиацией и холодный пот",
        "evidence": [
            ("instrumental", "ЭКГ в 12 отведениях", "INSTRUMENTAL_TEST"),
            ("lab", "Серийное определение тропонина", "LAB_TEST"),
        ],
        "diagnosis": "Острый коронарный синдром",
        "action": ("Антитромботическая терапия и реперфузия по показаниям", "MEDICATION"),
        "followup": "Мониторинг ЭКГ, боли и гемодинамики",
        "contraindication": ("Тромболизис при активном кровотечении", "MEDICATION", "symptom"),
    },
    {
        "case_id": "ischemic_stroke",
        "title": "Ишемический инсульт",
        "profile": "Пациент с внезапной очаговой неврологической симптоматикой",
        "symptom": "Слабость в руке, асимметрия лица и нарушение речи",
        "evidence": [
            ("exam", "Оценка неврологического дефицита по шкале NIHSS", "EXAM"),
            ("instrumental", "КТ или МРТ головного мозга", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Ишемический инсульт",
        "action": ("Тромболитическая терапия в терапевтическом окне", "MEDICATION"),
        "followup": "Неврологический мониторинг и контроль давления",
        "contraindication": ("Тромболизис при внутричерепном кровоизлиянии", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "neonatal_sepsis",
        "title": "Неонатальный сепсис",
        "profile": "Новорожденный первых суток жизни",
        "symptom": "Вялость, нестабильная температура и плохое сосание",
        "evidence": [
            ("lab", "Посев крови, С-реактивный белок и прокальцитонин", "LAB_TEST"),
            ("exam", "Оценка дыхания, перфузии и тонуса", "EXAM"),
        ],
        "diagnosis": "Неонатальный сепсис",
        "action": ("Ампициллин и гентамицин эмпирически", "MEDICATION"),
        "followup": "Мониторинг температуры, дыхания и гемодинамики",
        "contraindication": ("Задержка антибиотиков при подозрении на сепсис", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "iron_deficiency_anemia_pregnancy",
        "title": "Железодефицитная анемия при беременности",
        "profile": "Беременная пациентка во втором триместре",
        "symptom": "Слабость, бледность и одышка при нагрузке",
        "evidence": [
            ("lab", "Гемоглобин, ферритин и средний объем эритроцита", "LAB_TEST"),
            ("exam", "Оценка симптомов анемии и питания", "EXAM"),
        ],
        "diagnosis": "Железодефицитная анемия при беременности",
        "action": ("Пероральные препараты железа", "MEDICATION"),
        "followup": "Контроль гемоглобина и ферритина",
        "contraindication": ("Высокие дозы железа без лабораторного контроля", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "pulmonary_tuberculosis",
        "title": "Туберкулез легких",
        "profile": "Пациент с длительным кашлем",
        "symptom": "Кашель более двух недель, ночная потливость и похудание",
        "evidence": [
            ("lab", "Микроскопия, ПЦР или посев мокроты", "LAB_TEST"),
            ("instrumental", "Рентгенография органов грудной клетки", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Туберкулез легких",
        "action": ("Комбинированная противотуберкулезная терапия", "MEDICATION"),
        "followup": "Контроль мокроты, переносимости и приверженности",
        "contraindication": ("Монотерапия одним противотуберкулезным препаратом", "MEDICATION", "diagnosis"),
    },
    {
        "case_id": "chronic_kidney_disease",
        "title": "Хроническая болезнь почек",
        "profile": "Пациент с сахарным диабетом и гипертензией",
        "symptom": "Отеки, повышенное АД и снижение толерантности к нагрузке",
        "evidence": [
            ("lab", "СКФ и альбуминурия", "LAB_TEST"),
            ("instrumental", "УЗИ почек", "INSTRUMENTAL_TEST"),
        ],
        "diagnosis": "Хроническая болезнь почек",
        "action": ("Нефропротективная медикаментозная терапия", "MEDICATION"),
        "followup": "Мониторинг СКФ, калия и альбуминурии",
        "contraindication": ("Регулярный прием НПВС при хронической болезни почек", "MEDICATION", "diagnosis"),
    },
]


BASE_VARIANTS: list[dict[str, Any]] = [
    {
        "variant_id": "perfect",
        "expected_pattern": "all_metrics_high",
        "student_graph": "__same_as_reference__",
    },
    {
        "variant_id": "missing_diagnostic_step",
        "expected_pattern": "recall_and_node_coverage_drop",
        "operation": "remove_categories",
        "categories": ["EXAM", "LAB_TEST", "INSTRUMENTAL_TEST"],
    },
    {
        "variant_id": "wrong_symptom_category",
        "expected_pattern": "category_accuracy_drop",
        "operation": "change_node_category",
        "node_id": "symptom",
        "category": "DIAGNOSIS",
    },
    {
        "variant_id": "wrong_action_relation",
        "expected_pattern": "critical_relation_penalty",
        "operation": "replace_edge_label",
        "edge_id": "e_diagnosis_action",
        "label": "DETERMINES",
    },
    {
        "variant_id": "missing_critical_action",
        "expected_pattern": "missing_critical_action_penalty",
        "operation": "remove_edge_id",
        "edge_id": "e_diagnosis_action",
    },
    {
        "variant_id": "extra_unsafe_treatment",
        "expected_pattern": "unsafe_extra_action_cap",
        "operation": "add_unsafe_medication",
    },
    {
        "variant_id": "broken_chain",
        "expected_pattern": "directed_path_zero",
        "operation": "remove_edges_from_categories",
        "source_categories": ["PATIENT_PROFILE", "SYMPTOM"],
    },
]


def build_reference_graph(spec: dict[str, Any]) -> dict[str, Any]:
    nodes = [
        _node("profile", spec["profile"], "PATIENT_PROFILE"),
        _node("symptom", spec["symptom"], "SYMPTOM"),
    ]
    for evidence_id, label, category in spec["evidence"]:
        nodes.append(_node(evidence_id, label, category))
    nodes.extend(
        [
            _node("diagnosis", spec["diagnosis"], "DIAGNOSIS"),
            _node("action", spec["action"][0], spec["action"][1]),
            _node("followup", spec["followup"], "MONITORING"),
        ]
    )
    if spec.get("contraindication"):
        label, category, _target = spec["contraindication"]
        nodes.append(_node("contraindication", label, category))

    edges = [
        _edge("e_profile_symptom", "profile", "symptom", "DETERMINES"),
    ]
    for evidence_id, _label, category in spec["evidence"]:
        relation = "REQUIRES_CONFIRMATION" if category in {"LAB_TEST", "INSTRUMENTAL_TEST"} else "DETERMINES"
        edges.append(_edge(f"e_symptom_{evidence_id}", "symptom", evidence_id, relation))
        edges.append(_edge(f"e_{evidence_id}_diagnosis", evidence_id, "diagnosis", "REQUIRES_CONFIRMATION"))
    edges.extend(
        [
            _edge("e_diagnosis_action", "diagnosis", "action", "INDICATED_FOR"),
            _edge("e_diagnosis_followup", "diagnosis", "followup", "INDICATED_FOR"),
        ]
    )
    if spec.get("contraindication"):
        _label, _category, target = spec["contraindication"]
        edges.append(_edge("e_contraindication", "contraindication", target, "CONTRAINDICATED_DUE_TO"))

    return {"nodes": nodes, "edges": edges}


def build_variants(has_contraindication: bool) -> list[dict[str, Any]]:
    variants = [dict(variant) for variant in BASE_VARIANTS]
    if has_contraindication:
        variants.append(
            {
                "variant_id": "missing_contraindication",
                "expected_pattern": "missing_critical_action_penalty",
                "operation": "remove_edge_id",
                "edge_id": "e_contraindication",
            }
        )
    return variants


def build_seed(target: int) -> list[dict[str, Any]]:
    if target < 1:
        raise ValueError("--target must be positive")
    if target > len(CASE_SPECS):
        raise ValueError(f"--target can be at most {len(CASE_SPECS)} for this deterministic seed")

    cases = []
    for spec in CASE_SPECS[:target]:
        cases.append(
            {
                "case_id": spec["case_id"],
                "title": spec["title"],
                "metadata": {
                    "source": "deterministic_research_seed",
                    "requires_expert_review": True,
                    "error_taxonomy": [
                        "missing_diagnostic_step",
                        "wrong_category",
                        "wrong_relation",
                        "missing_critical_action",
                        "extra_unsafe_action",
                        "broken_chain",
                        "missing_contraindication",
                    ],
                },
                "reference_graph": build_reference_graph(spec),
                "variants": build_variants(bool(spec.get("contraindication"))),
            }
        )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic graph grading eval seed.")
    parser.add_argument("--target", type=int, default=20, help="Number of reference graph cases to generate.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output seed JSON path.")
    args = parser.parse_args()

    seed = build_seed(args.target)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = BACKEND_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "out": str(out_path),
                "reference_cases": len(seed),
                "student_variants": sum(len(case["variants"]) for case in seed),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
