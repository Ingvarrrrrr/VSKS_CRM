"""Backfill: purchases.contract_number/date/type/contractor_id <- contracts (ПРАВИЛО №6, группа D7, 2026-09-07)

Контекст: до этой волны шапка договора закупки (contract_number/
contract_date/purchase_contract_type/contractor_id) читалась ИЗ КЭША на
purchases, а не из связанного Contract — расхождения чинили четыре фазы
backfill (26-j-1, 26-k-2, 26-lll, 26-mmm), каждый раз одно и то же.

Решение координатора (2026-09-07): читатели (app.services.purchase_
contract_header, сериализатор реестра/карточки) теперь берут значение из
Contract напрямую, когда contract_id задан — расхождение кэша больше не
видно пользователю. Но кэш остаётся (a) единственным источником для закупок
БЕЗ contract_id и (b) fallback'ом, если у самого Contract поле пусто — эта
миграция синхронизирует кэш В ПОСЛЕДНИЙ РАЗ на уже накопленных данных, чтобы
и он не расходился (report-builder/экспорт/документы читают сырые колонки,
не relationship — не переведены в этой волне, см. docstring PLAN).

2026-09-07, ревизия по факту на проде (read-only отчёт координатора): 72
закупки с договором, num/contractor/type расхождений 0, но у 5 закупок
(id 799, 797, 910, 846, 840) contract_date заполнена, а contracts.date =
NULL. Слепой forward-sync (contract → purchase) тут ничего не портит (уже
COALESCE — пустое поле контракта не перетирает непустой кэш), НО и не решает
проблему: Contract так и остаётся без даты, читатель обязан держать fallback
вечно. Правильно — как в волне D1 (t2v4x6z8b0d2, organizations↔contractors):
пустое поле РОДИТЕЛЯ (здесь — Contract) дозаполняется из детей (Purchase),
когда ВСЕ дети, у кого поле непусто, СОГЛАСНЫ (одно и то же значение);
настоящий конфликт (два разных непустых значения у разных закупок одного
договора) — НЕ трогаем, только RAISE NOTICE.

Порядок (каждый шаг — идемпотентен, отдельный op.execute):
  0a. Contract.date дозаполняется из Purchase.contract_date, если у всех
      закупок этого договора, где contract_date задана, одно и то же значение.
  0b. То же для Contract.contractor_id из Purchase.contractor_id.
      (contracts.number/contract_type — NOT NULL колонки, реальной пустоты
      там не бывает — шаг для них не нужен.)
  1.  Forward-sync purchases ← contracts (как раньше) — ТОЛЬКО по непустым
      полям контракта, никогда не затирая непустой кэш NULL'ом:
        - contract_number = TRIM(contracts.number), если contracts.number непусто
        - contract_date = contracts.date, если непусто (после шага 0a у части
          договоров дата уже появилась — эти закупки досинхронизируются)
        - purchase_contract_type = contracts.contract_type, если непусто
        - contractor_id = contracts.contractor_id, ТОЛЬКО если purchases.contractor_id
          сейчас NULL (не перетираем уже установленного контрагента — multi-contractor
          сценарии внутри одного рамочного договора, см. докстринг _sync_purchase_from_contract).

Идемпотентна целиком: и шаг 0 (WHERE date/contractor_id IS NULL), и шаг 1
(WHERE-условие отсекает уже синхронизированные строки) на повторном прогоне
не меняют ничего (rowcount = 0).

Downgrade: намеренно no-op — откат означал бы стирание уже дозаполненных
полей Contract и возврат к рассинхронизированному кэшу, это не откат, а
порча данных.

Revision ID: y7a9c1e3g5i7
Revises: w6y8a0c2e4g6
Create Date: 2026-09-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "y7a9c1e3g5i7"
down_revision = "w6y8a0c2e4g6"
branch_labels = None
depends_on = None


# Шаг 0a: Contract.date дозаполняется из Purchase.contract_date, только когда
# ВСЕ закупки договора с непустой contract_date согласны (одно значение).
# Конфликт (≥2 разных значений) — только RAISE NOTICE, ничего не пишем.
BACKFILL_CONTRACT_DATE_FROM_PURCHASES = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT c.id AS contract_id, c.number AS contract_number,
           array_agg(DISTINCT p.contract_date) AS dates
    FROM contracts c
    JOIN purchases p ON p.contract_id = c.id
    WHERE c.date IS NULL AND p.contract_date IS NOT NULL
    GROUP BY c.id, c.number
  LOOP
    IF array_length(r.dates, 1) = 1 THEN
      UPDATE contracts SET date = r.dates[1] WHERE id = r.contract_id;
      RAISE NOTICE 'y7a9c1e3g5i7 contract_date_backfill contract_id=% number=% date=%',
        r.contract_id, r.contract_number, r.dates[1];
    ELSE
      RAISE NOTICE 'y7a9c1e3g5i7 contract_date_conflict contract_id=% number=% distinct_dates=%',
        r.contract_id, r.contract_number, r.dates;
    END IF;
  END LOOP;
END $$;
"""

# Шаг 0b: то же для Contract.contractor_id.
BACKFILL_CONTRACT_CONTRACTOR_FROM_PURCHASES = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT c.id AS contract_id, c.number AS contract_number,
           array_agg(DISTINCT p.contractor_id) AS contractor_ids
    FROM contracts c
    JOIN purchases p ON p.contract_id = c.id
    WHERE c.contractor_id IS NULL AND p.contractor_id IS NOT NULL
    GROUP BY c.id, c.number
  LOOP
    IF array_length(r.contractor_ids, 1) = 1 THEN
      UPDATE contracts SET contractor_id = r.contractor_ids[1] WHERE id = r.contract_id;
      RAISE NOTICE 'y7a9c1e3g5i7 contract_contractor_backfill contract_id=% number=% contractor_id=%',
        r.contract_id, r.contract_number, r.contractor_ids[1];
    ELSE
      RAISE NOTICE 'y7a9c1e3g5i7 contract_contractor_conflict contract_id=% number=% distinct_contractor_ids=%',
        r.contract_id, r.contract_number, r.contractor_ids;
    END IF;
  END LOOP;
END $$;
"""

# Шаг 1: forward-sync purchases ← contracts, ТОЛЬКО по непустым полям
# контракта — точное зеркало app.routers.purchases._sync_purchase_from_contract.
# Никогда не пишет NULL/'' поверх непустого кэша закупки (COALESCE / CASE-guard
# на каждое поле отдельно).
SYNC_PURCHASES_FROM_CONTRACT = """
UPDATE purchases p
SET
    contract_number = CASE
        WHEN c.number IS NOT NULL AND TRIM(c.number) <> '' THEN TRIM(c.number)
        ELSE p.contract_number
    END,
    contract_date = COALESCE(c.date, p.contract_date),
    purchase_contract_type = COALESCE(c.contract_type, p.purchase_contract_type),
    contractor_id = CASE
        WHEN p.contractor_id IS NULL AND c.contractor_id IS NOT NULL THEN c.contractor_id
        ELSE p.contractor_id
    END
FROM contracts c
WHERE p.contract_id = c.id
  AND (
      (c.number IS NOT NULL AND TRIM(c.number) <> '' AND p.contract_number IS DISTINCT FROM TRIM(c.number))
      OR (c.date IS NOT NULL AND p.contract_date IS DISTINCT FROM c.date)
      OR (c.contract_type IS NOT NULL AND p.purchase_contract_type IS DISTINCT FROM c.contract_type)
      OR (c.contractor_id IS NOT NULL AND p.contractor_id IS NULL)
  )
"""


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text(BACKFILL_CONTRACT_DATE_FROM_PURCHASES))
    conn.execute(sa.text(BACKFILL_CONTRACT_CONTRACTOR_FROM_PURCHASES))

    result = conn.execute(sa.text(SYNC_PURCHASES_FROM_CONTRACT))
    print(f"[y7a9c1e3g5i7] purchases синхронизированы из contracts (шапка договора): {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — см. докстринг модуля.
    pass
