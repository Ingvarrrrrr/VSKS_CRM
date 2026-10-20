"""Гвард удаления договора (Правило №5 — вынесен из routers/contracts.py).

Повод: DELETE /api/contracts/{cid} делал просто db.delete(c) + commit — упало
IntegrityError-ом на FK bank_payments.matched_contract_id (NO ACTION, см.
app/models/bank_statement.py:125) на договоре id=1137 «ВРЕМ-635» (17 строк
bank_payments, все matched_confirmed=false). Остальные FK на contracts.id
(проверено на проде):
  - purchases.contract_id          NO ACTION  -> бизнес-документ, БЛОКИРУЕТ
  - payments.contract_id           NO ACTION  -> бизнес-документ, БЛОКИРУЕТ
  - bank_payments.matched_contract_id NO ACTION
        -> подтверждённая строка (matched_confirmed=True) — реальное
           разнесение платежа, БЛОКИРУЕТ; неподтверждённая — это только
           автосопоставление выписки, безопасно снять самим.
  - contract_items.contract_id SET NULL, wishes.contract_id SET NULL,
    contract_subsidies CASCADE — уже обрабатываются БД корректно, не трогаем.

По образцу app/services/subsidy_delete_impact.py и
app/services/product_delete_impact.py (Правило №6: тот же "посчитать
зависимости -> 409, если блокируют" паттерн), но объединять их в одну
функцию нецелесообразно — разные сущности и разный набор зависимых таблиц;
второй такой проверки для contracts в проекте не было.
"""
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.bank_statement import BankPayment
from app.models.payment import Payment
from app.models.purchase import Purchase

MAX_LISTED_PURCHASES = 5


async def assert_contract_deletable_and_unlink(db: AsyncSession, contract_id: int) -> None:
    """Проверяет, можно ли удалить договор `contract_id`.

    Бросает HTTPException(409) с одним сообщением, объединяющим ВСЕ сработавшие
    причины, если на договоре есть закупки, платежи или подтверждённые строки
    банковской выписки. Иначе — обнуляет (одним UPDATE) matched_contract_id у
    НЕподтверждённых строк bank_payments, ссылающихся на этот договор (и
    matched_purchase_id, если та закупка принадлежала этому же договору —
    после прохождения проверки выше таких закупок уже нет, условие оставлено
    корректным на случай будущих изменений порядка проверок).
    """
    reasons: list[str] = []

    purchase_rows = (await db.execute(
        select(Purchase.id, Purchase.registry_number)
        .where(Purchase.contract_id == contract_id)
        .order_by(Purchase.id)
    )).all()
    if purchase_rows:
        numbers = [row.registry_number or f"id={row.id}" for row in purchase_rows]
        shown = ", ".join(numbers[:MAX_LISTED_PURCHASES])
        extra = len(numbers) - MAX_LISTED_PURCHASES
        if extra > 0:
            shown += f" и ещё {extra}"
        reasons.append(f"к нему привязаны закупки {shown} — сначала отвяжите договор в закупках")

    payments_count = (await db.execute(
        select(func.count()).select_from(Payment).where(Payment.contract_id == contract_id)
    )).scalar() or 0
    if payments_count:
        reasons.append(f"к договору привязаны платежи ({payments_count} шт.) — сначала отвяжите платежи от договора")

    confirmed_count = (await db.execute(
        select(func.count()).select_from(BankPayment).where(
            BankPayment.matched_contract_id == contract_id,
            BankPayment.matched_confirmed.is_(True),
        )
    )).scalar() or 0
    if confirmed_count:
        reasons.append(
            f"{confirmed_count} строк(и) выписки разнесены на этот договор и подтверждены — "
            "сначала отмените разнесение в реестре платежей"
        )

    if reasons:
        raise HTTPException(409, "Договор нельзя удалить: " + "; ".join(reasons) + ".")

    contract_purchase_ids = select(Purchase.id).where(Purchase.contract_id == contract_id).scalar_subquery()
    await db.execute(
        update(BankPayment)
        .where(
            BankPayment.matched_contract_id == contract_id,
            BankPayment.matched_confirmed.is_(False),
        )
        .values(
            matched_contract_id=None,
            matched_purchase_id=case(
                (BankPayment.matched_purchase_id.in_(contract_purchase_ids), None),
                else_=BankPayment.matched_purchase_id,
            ),
        )
    )
