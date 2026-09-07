"""Backfill: purchase_items/wishes — FK контрагента побеждает текст (ПРАВИЛО №6, группа D5, 2026-09-07)

Контекст: contractor_id (FK на contractors) и contractor_inn/contractor_name
(свободный текст, для случая «контрагента ещё нет в справочнике») хранились
и обновлялись НЕЗАВИСИМО в куче писателей (purchases.py PUT/PATCH,
purchase_items_edit split, wish_distribution, purchase_receipts,
purchase_import_parser, backfills 26-CC/26-BB/26-W). Когда FK был задан,
текст рядом мог остаться от старого/другого контрагента — сериализатор и
экспорт читали то текст, то FK, вперемешку.

Решение (план утверждён 2026-09-07, группа D5): FK — источник истины, когда
задан; текстовые колонки в этом случае — только историческая копия, ей не
место в БД. Писатели переведены на app.services.item_contractor
(set_item_contractor/item_contractor) отдельным PR тем же координатором —
эта миграция чистит НАКОПЛЕННЫЕ данные.

Порядок (каждый шаг — отдельный idempotent op.execute):
  1. purchase_items, FK задан, ИНН текста СОВПАДАЕТ с contractors.inn (или
     ИНН текста вовсе пуст, сравнивать не с чем) — текст (inn+name) чистим:
     это ровно дубликат того, что и так читается из FK.
  2. purchase_items, FK задан, ИНН текста ЗАДАН И ОТЛИЧАЕТСЯ от contractors.inn —
     НЕ трогаем (может быть значимое расхождение, не наша забота молча
     переписывать чужой контрагент) — только RAISE NOTICE с id позиции,
     закупки и обоими ИНН, чтобы владелец разобрал вручную.
  3. purchase_items, FK NULL, contractor_inn задан и находится контрагент с
     таким ИНН — линкуем FK, чистим текст (тот самый случай «контрагент был
     заведён с этим ИНН уже после того, как текст сохранили»).
  4. wishes — колонки contractor_id/contractor_name (у Wish НЕТ contractor_inn,
     сравнивать не по чем, кроме имени): FK задан и текст СОВПАДАЕТ с именем
     контрагента (без учёта регистра/пробелов) — чистим. FK задан и текст
     ОТЛИЧАЕТСЯ — оставляем, RAISE NOTICE. Обратного шага (3) для wishes нет:
     без колонки-ИНН достоверно связать текст с контрагентом нельзя (см.
     докстринг item_contractor.py) — сознательно не делаем эвристику по имени.

Идемпотентна целиком — каждый UPDATE отсекает уже приведённые строки своим
WHERE, повторный прогон даёт rowcount=0.

Downgrade: намеренно no-op (см. y7a9c1e3g5i7) — откат означал бы возврат
дублирующего текста рядом с FK, это не откат, а порча инварианта.

Revision ID: b4d6f8h0j2l4
Revises: y7a9c1e3g5i7
Create Date: 2026-09-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "b4d6f8h0j2l4"
down_revision = "y7a9c1e3g5i7"
branch_labels = None
depends_on = None


# Шаг 1: purchase_items, FK задан, текстовый ИНН пуст либо совпадает с
# contractors.inn — текст (inn+name) считается чистым дублем FK, обнуляем.
CLEAR_ITEM_TEXT_WHEN_MATCHES_FK = """
UPDATE purchase_items pi
SET contractor_inn = NULL, contractor_name = NULL
FROM contractors c
WHERE pi.contractor_id = c.id
  AND (pi.contractor_inn IS NOT NULL OR pi.contractor_name IS NOT NULL)
  AND (pi.contractor_inn IS NULL OR TRIM(pi.contractor_inn) = TRIM(c.inn))
"""

# Шаг 2: purchase_items, FK задан, текстовый ИНН задан и ОТЛИЧАЕТСЯ от
# contractors.inn — только отчёт, ничего не пишем.
REPORT_ITEM_INN_MISMATCH = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT pi.id AS item_id, pi.purchase_id AS purchase_id,
           pi.contractor_inn AS item_inn, c.inn AS contractor_inn, c.id AS contractor_id,
           pi.contractor_name AS item_name
    FROM purchase_items pi
    JOIN contractors c ON c.id = pi.contractor_id
    WHERE pi.contractor_inn IS NOT NULL
      AND TRIM(pi.contractor_inn) <> TRIM(c.inn)
  LOOP
    RAISE NOTICE 'b4d6f8h0j2l4 item_inn_mismatch item_id=% purchase_id=% contractor_id=% item_text_inn=% item_text_name=% contractor_inn=%',
      r.item_id, r.purchase_id, r.contractor_id, r.item_inn, r.item_name, r.contractor_inn;
  END LOOP;
END $$;
"""

# Шаг 3: purchase_items, FK NULL, текстовый ИНН задан и находится контрагент
# с таким ИНН — линкуем FK, чистим текст.
LINK_ITEM_FK_FROM_TEXT_INN = """
UPDATE purchase_items pi
SET contractor_id = c.id, contractor_inn = NULL, contractor_name = NULL
FROM contractors c
WHERE pi.contractor_id IS NULL
  AND pi.contractor_inn IS NOT NULL
  AND TRIM(c.inn) = TRIM(pi.contractor_inn)
"""

# Шаг 4a: wishes, FK задан, текст (contractor_name) совпадает с именем
# контрагента без учёта регистра/пробелов — чистим (нет колонки-ИНН у Wish).
CLEAR_WISH_TEXT_WHEN_MATCHES_FK = """
UPDATE wishes w
SET contractor_name = NULL
FROM contractors c
WHERE w.contractor_id = c.id
  AND w.contractor_name IS NOT NULL
  AND LOWER(TRIM(w.contractor_name)) = LOWER(TRIM(c.name))
"""

# Шаг 4b: wishes, FK задан, текст отличается от имени контрагента — только отчёт.
REPORT_WISH_NAME_MISMATCH = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT w.id AS wish_id, w.contractor_id AS contractor_id,
           w.contractor_name AS wish_text, c.name AS contractor_name
    FROM wishes w
    JOIN contractors c ON c.id = w.contractor_id
    WHERE w.contractor_name IS NOT NULL
      AND LOWER(TRIM(w.contractor_name)) <> LOWER(TRIM(c.name))
  LOOP
    RAISE NOTICE 'b4d6f8h0j2l4 wish_name_mismatch wish_id=% contractor_id=% wish_text=% contractor_name=%',
      r.wish_id, r.contractor_id, r.wish_text, r.contractor_name;
  END LOOP;
END $$;
"""


def upgrade() -> None:
    conn = op.get_bind()

    res1 = conn.execute(sa.text(CLEAR_ITEM_TEXT_WHEN_MATCHES_FK))
    print(f"[b4d6f8h0j2l4] purchase_items: текст очищен (совпадал с FK или ИНН не задан): {res1.rowcount}")

    conn.execute(sa.text(REPORT_ITEM_INN_MISMATCH))

    res3 = conn.execute(sa.text(LINK_ITEM_FK_FROM_TEXT_INN))
    print(f"[b4d6f8h0j2l4] purchase_items: FK привязан по текстовому ИНН, текст очищен: {res3.rowcount}")

    res4 = conn.execute(sa.text(CLEAR_WISH_TEXT_WHEN_MATCHES_FK))
    print(f"[b4d6f8h0j2l4] wishes: contractor_name очищен (совпадал с FK): {res4.rowcount}")

    conn.execute(sa.text(REPORT_WISH_NAME_MISMATCH))


def downgrade() -> None:
    # Намеренно no-op — см. докстринг модуля.
    pass
