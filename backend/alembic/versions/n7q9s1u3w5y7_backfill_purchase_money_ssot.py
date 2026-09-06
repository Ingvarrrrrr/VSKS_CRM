"""Backfill: единая денежная модель закупки (ПРАВИЛО №6, 2026-09-05)

Контекст: до app.services.purchase_money_writer.recalc_purchase_money
контроль над денежными колонками Purchase был у нескольких мест
одновременно (см. докстринг purchase_money_writer.py) — два наблюдаемых
следа этого на данных прода:

  (a) nmck (deprecated-алиас) разошёлся с total_nmck (источник истины) —
      по аудиту владельца на проде 5 строк, где оба поля не NULL и
      различаются, плюс строки, где total_nmck задан, а nmck — NULL.
  (b) «второе перо» (create_purchase/update_purchase писали
      contract_price = Σ purchase_items.total_price В ЛЮБОМ статусе, в т.ч.
      ДО договора) оставило contract_price заполненным у закупок, которые
      ещё не дошли до стадии «Договор» (нет ни contract_id, ни единой
      ContractItem) — по аудиту владельца на проде 371 такая строка (из них
      353 — легаси Excel-импорт без единой позиции вообще, эти удаляются
      ОТДЕЛЬНЫМ скриптом backend/scripts/cleanup_empty_wish_purchases.sql,
      не этой миграцией).

Эта миграция — ТОЛЬКО backfill (UPDATE), без изменения схемы. Идемпотентна:
повторный прогон не меняет уже приведённые строки (WHERE отсекает их).

  UPDATE 1: nmck := total_nmck везде, где total_nmck NOT NULL и
            (nmck IS NULL OR nmck <> total_nmck). Ожидаемо на проде: 5 строк
            с расхождением + сколько-то NULL->значение (точное число
            зависит от прод-данных на момент прогона, см. вывод миграции).

  UPDATE 2: contract_price := NULL для закупок «до договора» (статус НЕ в
            TZ_FROZEN_STATUSES — work_in_progress/contracted/ordered/
            delivered/paid, см. app.routers.purchases.TZ_FROZEN_STATUSES)
            БЕЗ contract_id И без единой ContractItem, у которых
            contract_price сейчас заполнен. Ожидаемо на проде: 371 строка
            (18 из них — не пустые: содержат реальные позиции и вернутся к
            обычному циклу «Договор» с настоящим ContractItem/статусом
            once закупка туда дойдёт; 353 — легаси-импорт без позиций
            вообще, они не пересчитаются здесь заново — contract_price
            просто снимается, planned_total_price/total_nmck этой миграцией
            не трогаются, — и в итоге удаляются отдельным cleanup-скриптом).

Downgrade: намеренно no-op — восстановить исходные (ошибочные) значения
средствами SQL нельзя (не сохраняли снимок «было»), да и не нужно: откат
такого backfill означал бы сознательный возврат к расхождению полей.

Revision ID: n7q9s1u3w5y7
Revises: r4t6v8x0z2b4
Create Date: 2026-09-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "n7q9s1u3w5y7"
down_revision = "r4t6v8x0z2b4"
branch_labels = None
depends_on = None


# Статусы «после договора» — зеркало app.routers.purchases.TZ_FROZEN_STATUSES
# (не импортируется — миграции не должны зависеть от прикладного кода, чтобы
# не сломаться при будущем рефакторинге app/routers/purchases.py).
_TZ_FROZEN_STATUSES = ("work_in_progress", "contracted", "ordered", "delivered", "paid")


def upgrade() -> None:
    conn = op.get_bind()

    # UPDATE 1: nmck (deprecated) := total_nmck (источник истины).
    result_1 = conn.execute(sa.text(
        """
        UPDATE purchases
        SET nmck = total_nmck
        WHERE total_nmck IS NOT NULL
          AND (nmck IS NULL OR nmck <> total_nmck)
        """
    ))
    print(f"[n7q9s1u3w5y7] nmck := total_nmck: {result_1.rowcount} строк обновлено")

    # UPDATE 2: contract_price := NULL для закупок «до договора» без
    # contract_id и без единой ContractItem («второе перо» ранее записало
    # туда Σ purchase_items).
    frozen_list = ", ".join(f"'{s}'" for s in _TZ_FROZEN_STATUSES)
    result_2 = conn.execute(sa.text(
        f"""
        UPDATE purchases p
        SET contract_price = NULL
        WHERE p.status NOT IN ({frozen_list})
          AND p.contract_id IS NULL
          AND p.contract_price IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM contract_items ci WHERE ci.purchase_id = p.id
          )
        """
    ))
    print(f"[n7q9s1u3w5y7] contract_price := NULL (до договора, второе перо): {result_2.rowcount} строк обновлено")


def downgrade() -> None:
    # Намеренно no-op — см. докстринг модуля.
    pass
