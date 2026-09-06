-- cleanup_empty_wish_purchases.sql — владелец (сессия 2026-09-05): удалить
-- «пустые» закупки-заготовки — легаси Excel-импорт, который завёл строку
-- purchases без единой позиции. Критерий (задан владельцем):
--   status = 'wishes' AND subsidy_id IS NULL
--   AND NOT EXISTS (SELECT 1 FROM purchase_items WHERE purchase_id = purchases.id)
-- Ожидаемо на проде — 353 строки (см. app/services/purchase_amounts_audit.py
-- и docstring миграции n7q9s1u3w5y7_backfill_purchase_money_ssot.py: это те
-- же 353 из 371 «до-договорных закупок со старым contract_price», у которых,
-- в отличие от остальных 18, вообще нет ни единой строки purchase_items —
-- некуда даже вернуться, когда закупка дойдёт до реального «Договора»).
--
-- ИДЕМПОТЕНТНОСТЬ (правка QA, 2026-09-06): раньше здесь был DROP TABLE IF
-- EXISTS + CREATE TABLE AS SELECT — при повторном запуске (например, скрипт
-- по ошибке вызвали дважды, или прогнали снова спустя время «на всякий
-- случай») это ЗАТИРАЛО уже собранный бэкап пустой таблицей, если на момент
-- второго прогона подходящих под критерий строк в purchases больше не
-- нашлось (потому что первый прогон их уже удалил) — резервная копия
-- терялась молча. Теперь: CREATE TABLE IF NOT EXISTS (бэкап переживает
-- повторные прогоны) + INSERT ... WHERE NOT EXISTS (не дублирует уже
-- сохранённые строки). Повторный запуск на уже вычищенной базе — 0 строк
-- добавлено в бэкап, 0 удалено из purchases, бэкап цел (проверено локально
-- дважды подряд, см. отчёт).
--
-- Резервная копия: purchases_deleted_20260905 (LIKE purchases INCLUDING ALL —
-- та же структура/индексы/PK, БЕЗ внешних FK на другие таблицы — так и
-- было раньше при CREATE TABLE AS SELECT, LIKE их тоже не копирует).
-- Восстановление при необходимости:
--   INSERT INTO purchases SELECT * FROM purchases_deleted_20260905;
--
-- Проверка перед удалением: скрипт ДИНАМИЧЕСКИ находит ВСЕ FOREIGN KEY
-- constraint'ы, ссылающиеся на purchases(id) (через information_schema — не
-- жёстко прописанный список таблиц, чтобы не разойтись с реальной схемой),
-- и для каждого считает, есть ли хоть одна строка, ссылающаяся на строки
-- бэкапа, которые ВСЁ ЕЩЁ живы в purchases (обычно — только что вставленные
-- этим прогоном; но так же самовосстановится, если предыдущий прогон упал
-- между INSERT и DELETE). Если находит — RAISE EXCEPTION, удаление НЕ
-- происходит (вся транзакция откатится, включая уже сделанный INSERT).
--
-- Запуск (один stdin-файл, без интерактивного psql):
--   docker exec -i <контейнер БД> psql -U vsks -d vsks_crm -f - < backend/scripts/cleanup_empty_wish_purchases.sql
-- Локально: docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm -f - < ...
-- (см. ПРАВИЛО №4 в CLAUDE.md — соединение только внутри docker-сети).

BEGIN;

CREATE TABLE IF NOT EXISTS purchases_deleted_20260905 (LIKE purchases INCLUDING ALL);

DO $$
DECLARE
    inserted_count INT;
    deleted_count INT;
    fk RECORD;
    dep_count BIGINT;
    fk_checked INT := 0;
BEGIN
    INSERT INTO purchases_deleted_20260905
    SELECT p.*
    FROM purchases p
    WHERE p.status = 'wishes'
      AND p.subsidy_id IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM purchase_items pi WHERE pi.purchase_id = p.id
      )
      AND NOT EXISTS (
          SELECT 1 FROM purchases_deleted_20260905 b WHERE b.id = p.id
      );
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RAISE NOTICE 'cleanup_empty_wish_purchases: % новых строк добавлено в бэкап purchases_deleted_20260905', inserted_count;

    -- FK-проверка по строкам бэкапа, которые ВСЁ ЕЩЁ живы в purchases
    -- (обычно = только что вставленные выше).
    FOR fk IN
        SELECT DISTINCT
            tc.table_name AS referencing_table,
            kcu.column_name AS referencing_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
           AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND ccu.table_name = 'purchases'
          AND ccu.column_name = 'id'
    LOOP
        fk_checked := fk_checked + 1;
        EXECUTE format(
            'SELECT COUNT(*) FROM %I t JOIN purchases_deleted_20260905 b ON t.%I = b.id JOIN purchases p ON p.id = b.id',
            fk.referencing_table, fk.referencing_column
        ) INTO dep_count;
        IF dep_count > 0 THEN
            RAISE EXCEPTION
                'cleanup_empty_wish_purchases: % зависимых строк найдено в %.% — удаление ОТМЕНЕНО (транзакция откатится)',
                dep_count, fk.referencing_table, fk.referencing_column;
        END IF;
    END LOOP;
    RAISE NOTICE 'cleanup_empty_wish_purchases: проверено % FK-constraint(ов) на purchases(id), зависимых строк не найдено — удаление разрешено', fk_checked;

    DELETE FROM purchases p
    USING purchases_deleted_20260905 b
    WHERE p.id = b.id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'cleanup_empty_wish_purchases: % строк удалено из purchases', deleted_count;
END $$;

-- Итоговые счётчики (видно в выводе psql -f -).
SELECT
    (SELECT COUNT(*) FROM purchases_deleted_20260905) AS backup_total_rows,
    (SELECT COUNT(*) FROM purchases
        WHERE status = 'wishes' AND subsidy_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM purchase_items pi WHERE pi.purchase_id = purchases.id)
    ) AS remaining_candidates_not_yet_backed_up;

COMMIT;
