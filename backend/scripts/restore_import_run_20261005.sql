-- Задача 05.10.2026 («Журнал загрузок выписки»): прежнее поведение
-- app/routers/bank_statements.py удаляло успешный ('done') прогон импорта
-- сразу после загрузки (BankStatementImport.id удалён, bank_payments.import_id
-- ушёл в NULL через ON DELETE SET NULL) — владелец не мог найти в журнале
-- свою загрузку от 05.10.2026 06:01:49 UTC (файл
-- 'PrintScroller_21-09-2026 11-22.xlsx'). Поведение исправлено (см.
-- app/routers/bank_statements.py — автоудаление убрано), этот скрипт
-- восстанавливает ОДНУ конкретную уже стёртую запись прогона задним числом.
--
-- НЕ ВЫПОЛНЯТЬ АВТОМАТИЧЕСКИ. Применять на проде вручную по плану деплоя:
--   scp backend/scripts/restore_import_run_20261005.sql root@201.34.139.168:/tmp/x.sql
--   ssh root@201.34.139.168 \
--     'docker exec -i vsks-crm-db-1 psql -U $(docker exec vsks-crm-db-1 printenv POSTGRES_USER) \
--        -d $(docker exec vsks-crm-db-1 printenv POSTGRES_DB) < /tmp/x.sql'
--
-- Идемпотентно: при повторном запуске находит уже восстановленную запись по
-- (file_name, uploaded_at) и ничего не вставляет повторно; UPDATE строк
-- bank_payments безопасен при повторном прогоне (WHERE import_id IS NULL).
--
-- Числа сверены READ-ONLY на проде 05.10.2026:
--   select count(*) from bank_payments
--     where import_id is null and created_at = '2026-10-05 06:01:49.816923+00';
--   → 1824 строки (rows_imported = rows_total, т.к. партия импортировалась
--     одним файлом без строк со skip_reason в этом прогоне).
-- rows_merged_legacy=72 — задано владельцем в задании (легаси-строки без
-- external_doc_id, склеенные этим прогоном, см. app/services/bank_payment_dedup.py).

DO $$
DECLARE
  v_import_id INTEGER;
  v_rows_imported INTEGER;
BEGIN
  SELECT id INTO v_import_id
    FROM bank_statement_imports
    WHERE file_name = 'PrintScroller_21-09-2026 11-22.xlsx'
      AND uploaded_at = '2026-10-05 06:01:49.816923+00'
    LIMIT 1;

  IF v_import_id IS NULL THEN
    SELECT count(*) INTO v_rows_imported
      FROM bank_payments
      WHERE import_id IS NULL
        AND created_at = '2026-10-05 06:01:49.816923+00';

    INSERT INTO bank_statement_imports (
      uploaded_by_id, uploaded_at, file_name, sheet_name,
      rows_total, rows_imported, rows_skipped, rows_matched, rows_unmatched,
      rows_dup, status, error_message, org_id, rows_no_subsidy,
      rows_updated, rows_unchanged, rows_merged_legacy, rows_ambiguous
    ) VALUES (
      NULL, '2026-10-05 06:01:49.816923+00', 'PrintScroller_21-09-2026 11-22.xlsx', NULL,
      v_rows_imported, v_rows_imported, 0, 0, v_rows_imported,
      0, 'done', NULL, NULL, 0,
      0, 0, 72, 0
    )
    RETURNING id INTO v_import_id;

    RAISE NOTICE 'Создан import_run id=% (rows_imported=%)', v_import_id, v_rows_imported;
  ELSE
    RAISE NOTICE 'import_run уже существует (id=%) — повторная вставка пропущена', v_import_id;
  END IF;

  UPDATE bank_payments
    SET import_id = v_import_id
    WHERE import_id IS NULL
      AND created_at = '2026-10-05 06:01:49.816923+00';

  RAISE NOTICE 'bank_payments.import_id проставлен для прогона %', v_import_id;
END $$;
