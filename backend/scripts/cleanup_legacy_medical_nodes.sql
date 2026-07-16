-- Удаление устаревших medical_nodes (open_ru, LOINC, ATC, ICD-11 и др.)
-- Оставляем только данные из MedElement.
--
-- Запуск (из каталога backend, подставьте свои host/port/user/db):
--   psql -h 127.0.0.1 -p 5440 -U postgres -d medical_constructor -f scripts/cleanup_legacy_medical_nodes.sql
--
-- Перед удалением скрипт показывает сводку. Удаление в транзакции — можно откатить (ROLLBACK).

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Просмотр: что будет удалено
-- ---------------------------------------------------------------------------

SELECT COALESCE(source, '(null)') AS source, COUNT(*) AS nodes
FROM medical_nodes
GROUP BY source
ORDER BY nodes DESC;

SELECT COUNT(*) AS legacy_nodes
FROM medical_nodes
WHERE source IN (
    'open_ru',
    'LOINC',
    'ATC',
    'ICD11',
    'ICD-11',
    'SNOMED',
    'Seed'
);

SELECT COUNT(*) AS edges_on_legacy_nodes
FROM medical_edges e
WHERE e.source_id IN (
        SELECT id FROM medical_nodes
        WHERE source IN ('open_ru', 'LOINC', 'ATC', 'ICD11', 'ICD-11', 'SNOMED', 'Seed')
    )
   OR e.target_id IN (
        SELECT id FROM medical_nodes
        WHERE source IN ('open_ru', 'LOINC', 'ATC', 'ICD11', 'ICD-11', 'SNOMED', 'Seed')
    );

-- ---------------------------------------------------------------------------
-- 2. Удаление узлов (рёбра medical_edges удалятся каскадом: ON DELETE CASCADE)
-- ---------------------------------------------------------------------------

DELETE FROM medical_nodes
WHERE source IN (
    'open_ru',
    'LOINC',
    'ATC',
    'ICD11',
    'ICD-11',
    'SNOMED',
    'Seed'
);

-- ---------------------------------------------------------------------------
-- 3. Проверка после удаления
-- ---------------------------------------------------------------------------

SELECT COALESCE(source, '(null)') AS source, COUNT(*) AS nodes
FROM medical_nodes
GROUP BY source
ORDER BY nodes DESC;

SELECT COUNT(*) AS remaining_legacy_nodes
FROM medical_nodes
WHERE source IN (
    'open_ru',
    'LOINC',
    'ATC',
    'ICD11',
    'ICD-11',
    'SNOMED',
    'Seed'
);

-- Подтвердить: COMMIT;
-- Отменить:   ROLLBACK;

COMMIT;
