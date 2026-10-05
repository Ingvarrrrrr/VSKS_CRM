"""Phase 22 — пересчёт агрегатов Purchase + авто-переход в paid.

Владелец (2026-08-19): «поставленная человеком галочка, что платёж прошёл, без
подтверждения выпиской из казначейства, не является подтверждением, что платёж
прошёл» — payment_amount («оплачено») считается ТОЛЬКО по
Payment.confirmed_by_statement=True; ручные неподтверждённые платежи
(payment_source='manual', confirmed_by_statement=False) идут в отдельный
агрегат payment_amount_declared («заявлено, ждёт подтверждения») и НЕ
участвуют в авто-переходе закупки в статус paid — иначе закупка «закрывалась
бы» по одному лишь слову человека.
"""
from __future__ import annotations
from datetime import date as _date
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.purchase import Purchase

# План 2026-10-04-fadm-statement (доработка после приёмки 04.10): статусы
# закупки, на которых подтверждённая выпиской сумма ≥ порога заводит запрос
# «Оплачено» (см. recompute_purchase_payments/_request_paid_confirmation ниже).
# Единственное место, где решается этот набор — ПРАВИЛО №6.
PAID_CONFIRMATION_ELIGIBLE_STATUSES = {"contracted", "ordered", "delivered"}


class ServicePeriodConflict(Exception):
    """Платёж помесячной закупки не удалось однозначно отнести к месяцу оказания
    (см. app/services/payment_service_period.py::resolve_service_period) — платёж
    НЕ создан молча, вызывающий роутер превращает это в HTTP 409 (тот же паттерн,
    что PaymentAttachError в app/services/payment_lookup.py).

    purchase_id/occupied_period — структурированные поля для detail 409-ответа
    (см. app/services/payment_service_period.py::service_period_conflict_detail,
    ПРАВИЛО №6 — один хелпер формирования, не копия в каждом роутере); оба
    необязательны — race-backstop (IntegrityError на flush) не привязан к одной
    закупке/месяцу, там известен только текст."""

    def __init__(self, message: str, purchase_id: Optional[int] = None, occupied_period=None):
        super().__init__(message)
        self.purchase_id = purchase_id
        self.occupied_period = occupied_period


async def find_manual_match(
    db: AsyncSession,
    purchase_id: int,
    document_number: Optional[str],
    payment_date,
    amount,
    tolerance: Decimal = Decimal("0.02"),
) -> Optional[Payment]:
    """Ищет уже существующий РУЧНОЙ неподтверждённый платёж (payment_source='manual',
    confirmed_by_statement=False) на этой закупке с совпадающими номером документа
    (нормализованно), датой и суммой (допуск tolerance).

    Используется при разнесении платежа из казначейской выписки (attach() /
    create_payments_from_bank()) — если находится совпадение, вызывающий код
    должен ПОМЕТИТЬ существующую запись подтверждённой, а не создавать вторую
    (иначе сумма закупки после загрузки выписки удвоится, см. владелец 2026-08-19)."""
    from app.services.payment_basis import normalize_doc_number

    if not purchase_id or amount is None:
        return None

    amount_dec = Decimal(str(amount))
    norm_target = normalize_doc_number(str(document_number or ""))

    candidates = (await db.execute(
        select(Payment).where(
            Payment.purchase_id == purchase_id,
            Payment.payment_source == "manual",
            Payment.confirmed_by_statement == False,  # noqa: E712
        )
    )).scalars().all()

    for c in candidates:
        if c.payment_date != payment_date:
            continue
        if c.amount is None:
            continue
        if abs(Decimal(str(c.amount)) - amount_dec) > tolerance:
            continue
        if normalize_doc_number(str(c.document_number or "")) != norm_target:
            continue
        return c

    # Фолбэк на заглушку «Импорта факта» (задача 02.10.2026, план
    # breezy-mixing-lovelace.md часть 3, п.2): импорт заводит платёж «оплачено
    # по отметке» без номера и даты документа (их в исходной таблице просто
    # нет) — точного совпадения номер+дата у такой записи никогда не будет.
    # Подтверждаем её по сумме, чтобы выписка не задвоила оплату второй
    # записью. Частичное совпадение (сумма выписки МЕНЬШЕ заглушки) — тоже
    # матч; вызывающий код (create_payments_from_bank) уменьшает остаток
    # заглушки вместо того чтобы считать её целиком подтверждённой.
    import_candidates = (await db.execute(
        select(Payment).where(
            Payment.purchase_id == purchase_id,
            Payment.payment_source == "manual",
            Payment.confirmed_by_statement == False,  # noqa: E712
            Payment.import_run_id.isnot(None),
            Payment.document_number.is_(None),
            Payment.payment_date.is_(None),
        )
    )).scalars().all()
    for c in import_candidates:
        if c.amount is None:
            continue
        stub_amount = Decimal(str(c.amount))
        if stub_amount <= 0:
            continue
        if amount_dec <= stub_amount + tolerance:
            return c

    return None


async def find_manual_match_same_period(
    db: AsyncSession,
    purchase_id: int,
    service_period=None,
) -> Optional[Payment]:
    """План 2026-10-06-statement-control, п.2 «выписка замещает отметку»:
    платёжка, привязываемая вручную к закупке (окно «Сверка» —
    app/routers/subsidy_payment_control.py::attach_bank_payment →
    app/services/payment_lookup.py::attach), поглощает НЕподтверждённую
    ручную отметку ТОЙ ЖЕ закупки (для помесячной — ТОГО ЖЕ service_period)
    даже при ДРУГОЙ сумме — в отличие от find_manual_match() выше, который
    требует точного совпадения номера/даты/суммы.

    Вызывающий код (attach()) сам решает, когда применять эту абсорбцию
    (только когда find_manual_match() по точному совпадению ничего не
    нашёл) — ПРАВИЛО №6, здесь только одна точка этой логики, вторая не
    заводится ни в create_payments_from_bank(), ни где-либо ещё."""
    if not purchase_id:
        return None
    candidates = (await db.execute(
        select(Payment).where(
            Payment.purchase_id == purchase_id,
            Payment.payment_source == "manual",
            Payment.confirmed_by_statement == False,  # noqa: E712
        )
    )).scalars().all()
    if service_period is not None:
        candidates = [c for c in candidates if c.service_period == service_period]
    else:
        candidates = [c for c in candidates if c.service_period is None]
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c.payment_date or _date.min, c.id))
    return candidates[0]


async def recompute_purchase_payments(db: AsyncSession, purchase_id: int) -> Purchase:
    """Пересчитать payment_amount (подтверждено казначейством) /
    payment_amount_declared (заявлено, ждёт подтверждения) / doc_number /
    doc_date агрегаты Purchase. Авто-перевод в paid — только если ПОДТВЕРЖДЁННАЯ
    сумма достигла порога."""
    payments = (await db.execute(
        select(Payment).where(Payment.purchase_id == purchase_id)
    )).scalars().all()

    p = await db.get(Purchase, purchase_id)
    if not p:
        return None

    confirmed = [pay for pay in payments if pay.confirmed_by_statement]
    declared = [
        pay for pay in payments
        if pay.payment_source == "manual" and not pay.confirmed_by_statement
    ]

    total_confirmed = sum((Decimal(str(pay.amount)) for pay in confirmed if pay.amount is not None),
                          Decimal(0))
    p.payment_amount = total_confirmed or None

    total_declared = sum((Decimal(str(pay.amount)) for pay in declared if pay.amount is not None),
                         Decimal(0))
    p.payment_amount_declared = total_declared or None

    dates = [pay.payment_date for pay in confirmed if pay.payment_date]
    p.payment_doc_date = max(dates) if dates else None

    numbers = [str(pay.document_number) for pay in confirmed if pay.document_number]
    p.payment_doc_number = "; ".join(numbers) if numbers else None

    # Было: автопереход в paid, молча, только со статуса 'delivered'. Владелец
    # (04.10.2026, план 2026-10-04-fadm-statement): «оплата найдена в выписке →
    # закупка в Оплачено через согласование, НЕЗАВИСИМО от того, отмечена ли
    # поставка» — приёмка 04.10 показала, что из 20 закупок с найденной оплатой
    # запрос создавался только у 3 (гейт был === 'delivered'). Расширено на
    # PAID_CONFIRMATION_ELIGIBLE_STATUSES ниже — ЕДИНСТВЕННОЕ место, где решается,
    # какие статусы годятся (ПРАВИЛО №6): contracted/ordered/delivered (деньги уже
    # обязательство — договор заключён), НЕ wishes/plan_schedule/work_in_progress
    # (обязательства ещё нет), НЕ paid (уже оплачено), НЕ остановленные
    # (stopped_at — см. app/services/purchase_stop.py). Подтверждённая
    # казначейством сумма, достигшая порога, больше НЕ ставит paid сама —
    # заводит запрос согласующим субсидии (см. _request_paid_confirmation ниже);
    # статус меняется только через app/routers/purchase_paid_confirmations.py::
    # confirm, штатным переходом (через delivered, если нужно — см. его докстринг).
    #
    # Владелец (повторно, после QA-находки с «fallback для без-субсидийных»):
    # «молчаливого перевода в Оплачено не должно быть НИГДЕ» — закупка БЕЗ
    # subsidy_id (некого просить подтвердить) НЕ получает никакого особого
    # случая, никакого автоматического paid; статус такой закупки меняет
    # только человек вручную обычным переходом (app/routers/purchase_transitions.py).
    #
    # ПРАВИЛО №6 (2026-09-05): порог = amounts.contract ?? amounts.plan — «сколько
    # должны» (сырые колонки БЕЗ фолбэков на Σ ContractItem/Σ PurchaseItem), это
    # НЕ то же самое, что purchase_amounts().effective (тот для закупки в статусе
    # delivered/paid сам уже приоритетно смотрит на acceptance_doc_amount/payment_
    # amount — здесь конкретно нужны «обязательства», а не «уже случившийся факт»).
    # Раньше — `p.contract_price or p.planned_total_price or Decimal(0)`
    # (Python-truthy: contract_price=0 ошибочно проваливался на planned_total_price).
    from app.services.purchase_amounts import purchase_amounts as _purchase_amounts_fn
    _pa = _purchase_amounts_fn(p)
    threshold = _pa.contract if _pa.contract is not None else (_pa.plan if _pa.plan is not None else Decimal(0))
    if (
        total_confirmed > 0 and total_confirmed >= threshold
        and not getattr(p, "stopped_at", None)
        and p.subsidy_id is not None
        and p.status in PAID_CONFIRMATION_ELIGIBLE_STATUSES
    ):
        await _request_paid_confirmation(db, p)

    await db.flush()
    return p


async def _request_paid_confirmation(db: AsyncSession, p: Purchase) -> None:
    """Завести запрос подтверждения «Оплачено», если его ещё нет (не больше
    одной pending-записи на закупку — частичный уникальный индекс модели) и
    уведомить согласующих субсидии. Статус закупки НЕ меняет — только после
    явного confirm (app/routers/purchase_paid_confirmations.py). Ошибка
    доставки уведомления не должна ронять сохранение платежа — см. try/except
    ниже (тот же паттерн, что app/services/purchase_transition_core.py)."""
    from app.models.purchase_paid_confirmation import PurchasePaidConfirmation

    if not p.subsidy_id:
        return  # нет субсидии — некого спрашивать; закупка остаётся delivered

    existing = (await db.execute(
        select(PurchasePaidConfirmation).where(
            PurchasePaidConfirmation.purchase_id == p.id,
            PurchasePaidConfirmation.status == "pending",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return  # уже ждёт решения — второй запрос не плодим

    confirmation = PurchasePaidConfirmation(
        purchase_id=p.id,
        subsidy_id=p.subsidy_id,
        amount_confirmed=p.payment_amount,
    )
    db.add(confirmation)
    await db.flush()

    try:
        from app.services.sandbox_guard import purchase_is_sandbox
        if await purchase_is_sandbox(db, p):
            return
        from app.models.subsidy_approver import SubsidyApprover
        from app.models.user import User
        from app.notifications import notify_purchase_paid_confirmation_requested
        from app.services.notify_after_commit import queue_after_commit

        approver_ids = (await db.execute(
            select(SubsidyApprover.user_id).where(
                SubsidyApprover.subsidy_id == p.subsidy_id,
                SubsidyApprover.user_id.isnot(None),
            )
        )).scalars().all()
        for uid in {uid for uid in approver_ids if uid}:
            user = await db.get(User, uid)
            if user:
                # QA-находка (05.10.2026): recompute_purchase_payments вызывается
                # ВНУТРИ более широких транзакций, которые коммитят в конце —
                # импорт выписки (app/routers/bank_statements.py, через
                # app/services/bank_payment_dedup.py::recompute_if_now_executed,
                # цикл по строкам) и reject (app/routers/purchase_paid_
                # confirmations.py — recompute ДО финального commit отклонения).
                # Прямой await здесь слал уведомление ДО того, как вызывающий
                # код успевал откатить всё на более поздней ошибке/решении —
                # теперь отправка откладывается до реального after_commit этой
                # же сессии (см. app/services/notify_after_commit.py); при
                # rollback ничего не уходит.
                queue_after_commit(
                    db,
                    lambda u=user: notify_purchase_paid_confirmation_requested(p, u, confirmation),
                )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "paid-confirmation notify failed for purchase %s", p.id, exc_info=True,
        )


async def create_payments_from_bank(
    db: AsyncSession,
    bank_payment_id: int,
    purchase_ids: list[int],
    service_period_overrides: Optional[dict] = None,
) -> list:
    """После того как менеджер подтвердил матч (matched_confirmed=true на BankPayment
    через PATCH /confirm), создать N Payment-записей для указанных закупок.

    Если purchase_ids = [pid_1] → одна запись.
    Если purchase_ids = [pid_1, pid_2, pid_3] → 3 записи с РАВНОЙ долей суммы
    (split по числу закупок). Менеджер может потом скорректировать суммы вручную.

    Для помесячных закупок (Purchase.is_monthly_payment=True) каждой записи
    проставляется service_period — см. app/services/payment_service_period.py.
    При неоднозначности (месяц уже занят / свободных не осталось) платёж НЕ
    создаётся молча — бросается ServicePeriodConflict, если только вызывающий
    код не передал месяц явно в service_period_overrides={purchase_id: date}
    (выбор человека, см. эндпоинт подтверждения)."""
    from app.models.bank_statement import BankPayment
    from app.services.payment_service_period import resolve_service_period
    from app.services.payment_basis import (
        expense_code as _expense_code,
        extract_basis as _extract_basis,
        basis_key as _basis_key,
    )
    bp = await db.get(BankPayment, bank_payment_id)
    if not bp:
        raise ValueError(f"BankPayment {bank_payment_id} not found")

    tolerance_default = Decimal("0.02")
    overrides = service_period_overrides or {}

    n = len(purchase_ids)
    if n == 0:
        return []

    # Равная доля. Если хочется по-другому — менеджер правит руками после.
    share = (Decimal(str(bp.amount)) / n).quantize(Decimal("0.01")) if bp.amount else Decimal(0)

    # Этап 3 плана (payment_basis.py) раньше заполнялся только через
    # app/services/payment_lookup.py::attach — этот путь (create_payments_from_bank)
    # создавал Payment без basis_key вовсе, и уникальный частичный индекс
    # ix_payments_purchase_basis_key_uniq ничего не защищал. Считаем один раз на bp.
    _basis = _extract_basis(bp)
    _code = _expense_code(bp)
    _bk = _basis_key(bp)

    created = []
    for pid in purchase_ids:
        purchase = await db.get(Purchase, pid)

        # Владелец (2026-08-19): если на этой закупке уже есть ручной
        # неподтверждённый платёж с тем же номером/датой/суммой — схлопываем
        # выписку В него (подтверждаем), а не заводим вторую запись, иначе
        # сумма закупки после загрузки выписки удвоится.
        existing_manual = await find_manual_match(db, pid, bp.payment_number, bp.payment_date, share)

        # Задача 04.10.2026 («Помесячные платежи — разные месяцы»): для
        # помесячной закупки определяем месяц оказания ДО записи платежа —
        # см. app/services/payment_service_period.py. Явный выбор человека
        # (overrides) приоритетнее авто-резолва; при конфликте без выбора —
        # не создаём платёж молча (ServicePeriodConflict → 409 в роутере).
        override = overrides.get(pid)
        if override is not None:
            service_period = override
        elif purchase is not None and purchase.is_monthly_payment:
            exclude_id = existing_manual.id if existing_manual is not None else None
            sp_result = await resolve_service_period(db, purchase, bp, exclude_payment_id=exclude_id)
            if sp_result.conflict:
                raise ServicePeriodConflict(
                    f"Закупка №{pid}: не удалось однозначно определить месяц оказания — {sp_result.conflict}",
                    purchase_id=pid,
                    occupied_period=sp_result.occupied_period,
                )
            service_period = sp_result.period
        else:
            service_period = None

        if existing_manual is not None:
            # Заглушка «Импорта факта» (import_run_id задан, номер и дата
            # пустые — см. find_manual_match) с суммой БОЛЬШЕ, чем покрывает
            # эта выписка: подтверждаем только пришедшую часть НОВОЙ записью,
            # а заглушку уменьшаем на неё — остаток ждёт следующей выписки,
            # не задваивается (владелец, план breezy-mixing-lovelace.md
            # часть 3, п.2: «частичное совпадение — уменьшаем заглушку»).
            _is_import_stub = (
                existing_manual.import_run_id is not None
                and existing_manual.document_number is None
            )
            _stub_amount = Decimal(str(existing_manual.amount)) if existing_manual.amount is not None else Decimal(0)
            if _is_import_stub and share < _stub_amount - tolerance_default:
                existing_manual.amount = _stub_amount - share
                pay = Payment(
                    contract_id=bp.matched_contract_id,
                    purchase_id=pid,
                    document_number=bp.payment_number,
                    payment_purpose=(bp.purpose_text or "")[:500],
                    payment_date=bp.payment_date,
                    amount=share,
                    bank_payment_id=bp.id,
                    matched_confirmed=True,
                    payment_source="statement",
                    confirmed_by_statement=True,
                    import_run_id=existing_manual.import_run_id,
                    service_period=service_period,
                    expense_code=_code,
                    basis_kind=_basis.kind,
                    basis_number=_basis.number,
                    basis_date=_basis.date,
                    basis_key=_bk,
                    basis_label=_basis.label,
                )
                db.add(pay)
                created.append(pay)
                continue

            existing_manual.bank_payment_id = bp.id
            existing_manual.payment_source = "statement"
            existing_manual.confirmed_by_statement = True
            existing_manual.matched_confirmed = True
            existing_manual.document_number = bp.payment_number
            existing_manual.payment_date = bp.payment_date
            existing_manual.amount = share
            existing_manual.payment_purpose = (bp.purpose_text or "")[:500]
            existing_manual.contract_id = bp.matched_contract_id
            existing_manual.service_period = service_period
            existing_manual.expense_code = _code
            existing_manual.basis_kind = _basis.kind
            existing_manual.basis_number = _basis.number
            existing_manual.basis_date = _basis.date
            existing_manual.basis_key = _bk
            existing_manual.basis_label = _basis.label
            created.append(existing_manual)
            continue

        pay = Payment(
            contract_id=bp.matched_contract_id,
            purchase_id=pid,
            document_number=bp.payment_number,
            payment_purpose=(bp.purpose_text or "")[:500],
            payment_date=bp.payment_date,
            amount=share,
            bank_payment_id=bp.id,
            matched_confirmed=True,
            payment_source="statement",
            confirmed_by_statement=True,
            service_period=service_period,
            expense_code=_code,
            basis_kind=_basis.kind,
            basis_number=_basis.number,
            basis_date=_basis.date,
            basis_key=_bk,
            basis_label=_basis.label,
        )
        db.add(pay)
        created.append(pay)

    bp.matched_confirmed = True
    try:
        await db.flush()
    except IntegrityError as exc:
        # Частичные уникальные индексы (basis_key / service_period, см. миграции
        # ix_payments_purchase_basis_key_uniq и p2q4r6s8t0v2) — race condition
        # backstop, тот же паттерн, что app/services/payment_lookup.py::attach.
        raise ServicePeriodConflict(
            f"Платёж №{bp.id} конфликтует с уже существующей записью (назначение/месяц уже заняты)"
        ) from exc

    # Этап 0 (попутная гигиена): аванс-отчёт из назначения платежа перезаписывает
    # contract_number/date ТОЛЬКО сейчас, в момент реального подтверждения матча —
    # см. app/services/payment_matcher.py::apply_advance_report_override (раньше
    # это было побочным эффектом auto_match на каждом rematch).
    from app.services.payment_matcher import apply_advance_report_override
    for pid in purchase_ids:
        purchase = await db.get(Purchase, pid)
        apply_advance_report_override(purchase, bp)

    # Recompute aggregates для каждой затронутой закупки
    for pid in purchase_ids:
        await recompute_purchase_payments(db, pid)

    return created


async def unlink_bank_payment(db: AsyncSession, bank_payment_id: int) -> int:
    """Удалить все Payment связанные с этим BankPayment + recompute. Возврат: число удалённых."""
    affected_purchases: set[int] = set()
    payments = (await db.execute(
        select(Payment).where(Payment.bank_payment_id == bank_payment_id)
    )).scalars().all()
    for p in payments:
        if p.purchase_id:
            affected_purchases.add(p.purchase_id)
        await db.delete(p)
    await db.flush()
    for pid in affected_purchases:
        await recompute_purchase_payments(db, pid)
    return len(payments)
