"""Backfill: acceptance_docs JSONB <-> scalar-кэш (ПРАВИЛО №6, группа D4, 2026-09-07)

Контекст (инвентаризация группы D4): закрывающие документы закупки хранились
ДВАЖДЫ — JSONB-массив `purchases.acceptance_docs` и 4 скалярные колонки
`acceptance_doc_name/date/number/amount`. Решение координатора (2026-09-07):
источник истины — JSONB, но скаляры ОСТАЮТСЯ как производный КЭШ первого
документа — их читает report-builder (field_registry.py/pivot_engine.py),
который умеет только сырые SQL-колонки, а не Python derived_scalars(). Пишет
кэш ТОЛЬКО app.services.acceptance_docs.sync_scalars (вызывается из
add_doc/remove_doc/replace_docs) — единый триггер записи, см. комментарий у
Purchase.acceptance_doc_* в app/models/purchase.py.

Эта миграция — ТОЛЬКО backfill (без изменения схемы), в три шага:

  (a) UPDATE: закупки, у которых acceptance_docs пуст (NULL или '[]'), а хотя
      бы один из 4 скаляров заполнен — собрать ОДИН документ в JSONB из этих
      скаляров (type='legacy'), сохраняя тот же формат полей, что и
      services/purchase_import_parser.py (name/number пустая строка вместо
      NULL, date как ISO-строка).

  (c) UPDATE: закупки, у которых acceptance_docs НЕПУСТ — синхронизировать
      скаляр-кэш из JSONB (первый документ), чтобы report-builder не показывал
      пусто/устаревшее для закупок, чьи закрывающие документы добавлены новым
      кодом (который пишет только JSONB, кэш обновляет sync_scalars — но
      исторические строки, у которых кэш никогда не обновлялся тем же
      триггером, синхронизируются здесь один раз). Та же семантика «первого
      документа», что и derived_scalars()/sync_scalars() — только SQL.

  (b) REPORT (read-only): после (a)+(c) — закупки, где скаляр acceptance_doc_
      amount (кэш = amount ПЕРВОГО документа) расходится с Σ acceptance_docs
      [].amount — это ОЖИДАЕМО для закупок с НЕСКОЛЬКИМИ документами (аванс с
      N чеков) — кэш держит семантику «первый документ», totals считает
      app.services.acceptance_docs.total_amount(); только печать, без
      изменения данных — глазами оценить масштаб.

Идемпотентна: (a)/(c) отсекаются WHERE-условием на несовпадение — повторный
прогон на уже синхронизированных строках ничего не меняет; (b) — чистое чтение.

Downgrade: намеренно no-op — откат означал бы удаление уже рабочих
JSONB-записей/кэша — небезопасно и не нужно.

Revision ID: w6y8a0c2e4g6
Revises: v3w5y7a9c1e3
Create Date: 2026-09-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "w6y8a0c2e4g6"
down_revision = "v3w5y7a9c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # (a) Собрать acceptance_docs из скаляров там, где JSONB пуст, а скаляры
    # заполнены — тот же формат полей, что и purchase_import_parser.py.
    result_a = conn.execute(sa.text(
        """
        UPDATE purchases
        SET acceptance_docs = jsonb_build_array(
            jsonb_build_object(
                'name',   COALESCE(acceptance_doc_name, ''),
                'number', COALESCE(acceptance_doc_number, ''),
                'date',   COALESCE(to_char(acceptance_doc_date, 'YYYY-MM-DD'), ''),
                'amount', acceptance_doc_amount,
                'type',   'legacy'
            )
        )
        WHERE (
              acceptance_docs IS NULL
              OR acceptance_docs = '[]'::jsonb
              -- JSON-null (jsonb_typeof = 'null') — колонка НЕ SQL NULL, но
              -- значения нет; найдено на локальных данных (id 1165-1170).
              OR jsonb_typeof(acceptance_docs) = 'null'
          )
          AND (
              NULLIF(acceptance_doc_name, '') IS NOT NULL
              OR NULLIF(acceptance_doc_number, '') IS NOT NULL
              OR acceptance_doc_date IS NOT NULL
              OR acceptance_doc_amount IS NOT NULL
          )
        """
    ))
    print(f"[w6y8a0c2e4g6] (a) acceptance_docs собран из скаляров: {result_a.rowcount} закупок")

    # (c) Синхронизировать скаляр-кэш из JSONB (первый документ) — та же
    # семантика, что app.services.acceptance_docs.sync_scalars(derived_scalars(p)),
    # выражена в SQL: NULLIF(...,'') повторяет `first.get(...) or None`.
    result_c = conn.execute(sa.text(
        """
        UPDATE purchases
        SET
            acceptance_doc_name   = NULLIF(acceptance_docs->0->>'name', ''),
            acceptance_doc_number = NULLIF(acceptance_docs->0->>'number', ''),
            acceptance_doc_date   = NULLIF(acceptance_docs->0->>'date', '')::date,
            acceptance_doc_amount = NULLIF(acceptance_docs->0->>'amount', '')::numeric
        WHERE acceptance_docs IS NOT NULL
          -- CASE, а не AND jsonb_array_length(...) — Postgres НЕ гарантирует
          -- порядок вычисления операндов AND, jsonb_array_length() на скаляре
          -- (JSON-null/объект) кидает ошибку независимо от предшествующего
          -- jsonb_typeof()-условия слева; CASE — единственная гарантированная
          -- короткая логика (см. предупреждение в доке Postgres по CASE).
          AND (CASE WHEN jsonb_typeof(acceptance_docs) = 'array'
                    THEN jsonb_array_length(acceptance_docs) ELSE 0 END) > 0
          AND (
              acceptance_doc_name IS DISTINCT FROM NULLIF(acceptance_docs->0->>'name', '')
              OR acceptance_doc_number IS DISTINCT FROM NULLIF(acceptance_docs->0->>'number', '')
              OR acceptance_doc_date IS DISTINCT FROM NULLIF(acceptance_docs->0->>'date', '')::date
              OR acceptance_doc_amount IS DISTINCT FROM NULLIF(acceptance_docs->0->>'amount', '')::numeric
          )
        """
    ))
    print(f"[w6y8a0c2e4g6] (c) скаляр-кэш синхронизирован из JSONB: {result_c.rowcount} закупок")

    # (b) Отчёт (read-only), уже ПОСЛЕ (a)+(c): скаляр-кэш (amount первого
    # документа) расходится с Σ acceptance_docs[].amount — ожидаемо для
    # многодокументных закупок (аванс с N чеков), см. докстринг.
    diverging = conn.execute(sa.text(
        """
        SELECT p.id, p.purchase_number, p.acceptance_doc_amount AS cache_amount,
               COALESCE(
                   (SELECT SUM((d->>'amount')::numeric)
                    FROM jsonb_array_elements(p.acceptance_docs) d
                    WHERE d ? 'amount' AND d->>'amount' IS NOT NULL),
                   0
               ) AS jsonb_total
        FROM purchases p
        WHERE p.acceptance_docs IS NOT NULL
          AND (CASE WHEN jsonb_typeof(p.acceptance_docs) = 'array'
                    THEN jsonb_array_length(p.acceptance_docs) ELSE 0 END) > 0
          AND p.acceptance_doc_amount IS NOT NULL
          AND p.acceptance_doc_amount <> COALESCE(
                   (SELECT SUM((d->>'amount')::numeric)
                    FROM jsonb_array_elements(p.acceptance_docs) d
                    WHERE d ? 'amount' AND d->>'amount' IS NOT NULL),
                   0
              )
        ORDER BY p.id
        """
    )).fetchall()
    print(f"[w6y8a0c2e4g6] (b) закупок с расхождением кэш/Σ JSONB (ожидаемо для multi-doc, только отчёт): {len(diverging)}")
    for row in diverging[:20]:
        print(
            f"[w6y8a0c2e4g6]   закупка id={row.id} №{row.purchase_number}: "
            f"acceptance_doc_amount(первый документ)={row.cache_amount}, Σ acceptance_docs[].amount={row.jsonb_total}"
        )
    if len(diverging) > 20:
        print(f"[w6y8a0c2e4g6]   ... и ещё {len(diverging) - 20} строк")


def downgrade() -> None:
    # Намеренно no-op — см. докстринг модуля.
    pass
