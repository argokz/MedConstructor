# Модель оценки клинических графов

Текущая версия алгоритма задается константой `EVALUATION_ALGORITHM_VERSION`
в `app/services/graph_evaluator.py` и сохраняется в каждой записи
`student_attempts.algorithm_version`.

Текущая версия: **4.1.0-clinical-weighted-safety**.

## Цель

Алгоритм оценивает не текстовый ответ студента, а структуру клинического
рассуждения, представленную в виде направленного графа:

```text
профиль пациента / симптом -> обследование -> диагноз -> лечение
```

Это позволяет проверять не только наличие правильных медицинских понятий, но и
качество причинно-диагностических и терапевтических связей между ними.

## Входные данные

На вход подаются:

- граф студента;
- эталонный граф;
- узлы с полями `id`, `data.label`, `data.category`;
- ребра с полями `source`, `target`, `label`.

Допустимые категории узлов:

- `PATIENT_PROFILE`
- `SYMPTOM`
- `EXAM`
- `LAB_TEST`
- `INSTRUMENTAL_TEST`
- `DIAGNOSIS`
- `MEDICATION`
- `SURGERY`
- `MONITORING`

Допустимые типы связей:

- `DETERMINES`
- `REQUIRES_CONFIRMATION`
- `EXCLUDES`
- `INDICATED_FOR`
- `CONTRAINDICATED_DUE_TO`

## 1. Semantic Edge F1

Базовый слой сравнения строится на множестве смысловых троек:

```text
(source_concept, target_concept, relation_type)
```

Идентификаторы узлов не учитываются. Это важно, потому что студент может
создать свои узлы с другими `id`, но с тем же клиническим смыслом.

Для множеств:

```text
S = semantic edges студента
R = semantic edges эталона
```

считаются:

```text
precision = |S ∩ R| / |S|
recall    = |S ∩ R| / |R|
edge_f1   = 2 * precision * recall / (precision + recall)
```

Эти поля сохранены как совместимый baseline: `precision`, `recall`,
`f1_score`, `edge_f1`.

## 2. Weighted Edge F1

В версии v4 связи получают клинический вес. Ошибка в терапевтической или
противопоказательной связи считается более значимой, чем ошибка во
вспомогательной связи.

Вес ребра:

```text
edge_weight =
relation_weight * mean(source_category_weight, target_category_weight)
```

Примеры весов категорий:

```text
DIAGNOSIS  = 1.6
MEDICATION = 1.4
SURGERY    = 1.4
MONITORING = 1.1
LAB_TEST   = 1.2
SYMPTOM    = 1.0
```

Примеры весов отношений:

```text
DETERMINES               = 1.00
REQUIRES_CONFIRMATION    = 1.15
EXCLUDES                 = 1.30
INDICATED_FOR            = 1.45
CONTRAINDICATED_DUE_TO   = 1.80
```

Результат возвращается в полях:

- `weighted_precision`
- `weighted_recall`
- `weighted_edge_f1`
- `structural_correctness`

`structural_correctness` сейчас равен `weighted_edge_f1` и отражает
структурную правильность клинических связей.

## 3. One-to-One Node Coverage

Покрытие узлов показывает, насколько студент включил ключевые медицинские
понятия из эталонного графа.

В v4 используется one-to-one matching: один узел студента может покрыть только
один эталонный узел. Это снижает риск завышения оценки, когда общий узел
студента частично похож сразу на несколько эталонных понятий.

Сходство узлов:

```text
node_similarity = cosine(embedding(reference_label), embedding(student_label))
```

Если названия совпадают после нормализации, сходство равно `1.0`.

Если категории узлов не совпадают, применяется штраф:

```text
adjusted_similarity = similarity * 0.65
```

Метрика:

```text
node_coverage =
sum(reference_node_weight * adjusted_similarity) / sum(reference_node_weight)
```

Дополнительно считается:

```text
category_accuracy =
sum(weight of matched reference nodes with correct category) / sum(reference_node_weight)
```

## 4. Directed Path Completeness

Эта метрика оценивает, восстановил ли студент не только отдельные связи, но и
цельные направленные клинические пути.

Алгоритм строит пары:

```text
start_node -> decision_node
```

где `start_node` обычно относится к `PATIENT_PROFILE` или `SYMPTOM`, а
`decision_node` относится к `DIAGNOSIS`, `MEDICATION`, `SURGERY` или
`MONITORING`.

Для каждой такой пары проверяется:

1. существует ли направленный путь в эталоне;
2. существует ли тот же направленный путь среди правильно восстановленных
   студентом ребер.

Метрика:

```text
directed_path_completeness =
recovered_required_paths / all_required_paths
```

Поле `chain_completeness` сохранено как совместимое имя и сейчас равно
`directed_path_completeness`.

## 5. Safety Penalty

`safety_penalty` снижает итоговую оценку за клинически опасные ошибки.

В версии 4.1 safety-ошибки разделены на два объяснимых подтипа:

- `unsafe_extra_action` — лишнее потенциально опасное действие студента;
- `missing_critical_action` — пропущенное критическое действие из эталона.

Критическими считаются:

- лишние или неверные связи с `MEDICATION` / `SURGERY`;
- пропущенные или неверные терапевтические связи `INDICATED_FOR`;
- ошибки в `CONTRAINDICATED_DUE_TO`;
- ошибки в `EXCLUDES`.

Метрика:

```text
unsafe_extra_action =
unsafe_extra_weight / max(reference_critical_weight, unsafe_extra_weight)

missing_critical_action =
missing_critical_weight / reference_critical_weight

safety_penalty =
max(unsafe_extra_action, missing_critical_action)
```

Значение находится в диапазоне `[0, 1]` и вычитается из итоговой оценки с
коэффициентом `0.35`.

Если найдено лишнее опасное действие, итоговая оценка дополнительно
ограничивается сверху значением `0.75`. Если пропущены все критические
терапевтические действия, оценка ограничивается сверху значением `0.85`.

## Итоговая оценка

Итоговая клинически взвешенная оценка:

```text
composite_score =
0.40 * weighted_edge_f1 +
0.25 * node_coverage +
0.25 * directed_path_completeness +
0.10 * category_accuracy -
0.35 * safety_penalty
```

После расчета значение ограничивается диапазоном `[0, 1]`.

## Интерпретация

- `weighted_edge_f1` показывает точность структуры связей.
- `node_coverage` показывает полноту набора ключевых понятий.
- `directed_path_completeness` показывает цельность клинического рассуждения.
- `category_accuracy` показывает корректность онтологической классификации.
- `safety_penalty` отражает потенциально опасные клинические ошибки.
- `unsafe_extra_action` показывает лишние опасные назначения.
- `missing_critical_action` показывает пропущенные критические действия.

## Значение для статьи

Алгоритм можно описать как гибридную модель автоматизированной оценки
клинического мышления студентов на основе семантического сравнения графов
знаний.

Научная новизна:

- оценка проводится по структуре рассуждения, а не только по текстовому ответу;
- сравнение выполняется на уровне медицинских понятий и типизированных связей;
- используется клиническое взвешивание ошибок;
- отдельно оценивается полнота направленной диагностико-терапевтической цепочки;
- вводится штраф за потенциально опасные терапевтические ошибки.
- воспроизводимый benchmark дополнительно считает `pattern_pass_rate` на
  контролируемых типах студенческих ошибок.

Текущий research benchmark для статьи:

- `benchmarks/graph_cases.research.seed.json`: 20 эталонных графов;
- 160 вариантов студенческих решений;
- типы ошибок: пропуск диагностики, неверная категория, неверная связь,
  пропуск критического действия, пропуск противопоказания, лишнее опасное
  действие, разрыв клинической цепочки;
- последний прогон: `pattern_pass_rate = 1.0`, `accepted_rate = 1.0`,
  `warning_rate = 0.0`.

Экспертная валидация:

- `scripts/export_graph_expert_ratings.py` формирует слепой пакет для
  преподавателей;
- `scripts/analyze_graph_expert_ratings.py` считает корреляцию между
  `composite_score` и экспертной оценкой;
- основной отчёт: Pearson, Spearman, Kendall tau-a, MAE, RMSE, bias,
  межэкспертное согласие;
- протокол заполнения описан в `docs/expert_rating_protocol.md`.

## Воспроизводимость

В `student_attempts.metrics` сохраняются:

- все итоговые метрики;
- `algorithm_version`;
- `reference_content_hash`;
- `embedding_model_version`;
- `evaluation_context`;
- `concept_similarity_threshold`;
- `embedding_model_name`;
- режим сопоставления понятий: `identity` или `embedding`.
