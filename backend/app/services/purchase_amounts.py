"""purchase_amounts.py — единый расчёт «эффективной суммы закупки» по стадии
жизненного цикла (Purchase.status).

Контекст (инвентаризация 2026-09-05): у Purchase НЕТ одного поля «сумма».
Денежные колонки: planned_total_price, total_nmck, nmck, contract_price,
acceptance_doc_amount, final_total_amount, payment_amount,
payment_amount_declared. Девять читателей по коду считают «сумму закупки» по
РАЗНЫМ формулам — полный список с точными файл:строка приведён в
app/services/purchase_amounts_audit.py (там же — фактический замер расхождений
на текущих данных). Этот модуль НЕ заменяет ни одного из них (задача этого шага
— только измерить расхождение, поведение существующих эндпоинтов не меняется)
— он вводит единственный НОВЫЙ источник истины, на который можно будет
постепенно переводить читателей отдельными шагами.

Решение владельца (сессия 2026-09-05, уточнено тем же днём — вторая волна) —
«сумма закупки» = по стадии, при пустом поле стадии спускаться на предыдущую:
    paid            → payment_amount ?? payment_amount_declared ??
                       acceptance_doc_amount ?? contract_price ??
                       Σ contract_items.total ?? planned_total_price ??
                       Σ purchase_items.total_price
    delivered       → acceptance_doc_amount ?? contract_price ??
                       Σ contract_items.total ?? planned_total_price ??
                       Σ purchase_items.total_price
    contracted / ordered / work_in_progress
    (и любой другой статус «после договора», см. ниже)
                    → contract_price ?? Σ contract_items.total ??
                       planned_total_price ?? Σ purchase_items.total_price
    до договора (wishes / plan_schedule / …)
                    → planned_total_price ?? Σ purchase_items.total_price

(Первая волна — короче: paid не заглядывал в payment_amount_declared/
acceptance_doc_amount/contract_price, delivered/contract-стадия не заглядывали
за одну ступень фолбэка. Второй заход владельца — цепочка длиннее: КАЖДАЯ
стадия обязана в итоге долистать до planned_total_price/Σ purchase_items,
если все более «поздние» поля пусты, а не остановиться на None раньше срока.)

Рамочная голова (is_framework_head — тот же критерий, что и
app.routers.purchases.is_framework_head: purchase_contract_type в
{framework_cumulative, framework_with_amount} И parent_purchase_id IS NULL) —
отдельный случай ПОВЕРХ формулы по стадии: effective = Contract.max_amount,
если задан; если NULL — падает в обычную формулу по стадии ниже (та же логика,
что и во всех 9 читателях: голова без явно введённой предельной суммы
продолжает считаться по contract_price/этапу, как обычная закупка).

Статусы, НЕ укладывающиеся явно в четыре группы владельца (перечислено явно,
как и было указано в задании):
  - 'cancelled' — отменённая закупка. Все 9 существующих читателей либо явно
    исключают cancelled (`.notin_(["cancelled"])` — dashboard.py, purchase_
    payments.py порог не привязан к статусу вовсе), либо просто не включают
    его в свой `status.in_(...)` (documents.py, feo_categories.py, feo_plan.py,
    subsidies.py._calculate_spent — единственный, кто явно ЗАХВАТЫВАЕТ
    cancelled в `notin_(_EXCLUDED_FROM_SPENT)`, т.е. у него cancelled как раз
    исключён). Ни один читатель не относит cancelled ни к «после договора», ни
    к «поставлено/оплачено» — договорные поля отменённой закупки не более
    актуальны, чем плановые. Отнесена к группе «до договора» (ближайшая по
    смыслу — «было запланировано, не реализовано»); локально на 458 закупках
    ни одной cancelled нет, так что это решение не наблюдаемо на текущих данных
    (см. audit).
  - 'planned' — легаси-статус: фигурирует в STATUS_LABELS
    (app/routers/purchase_transitions.py:41-51) и как default тестовой фабрики
    make_purchase (backend/tests/conftest.py:315), но ОТСУТСТВУЕТ в
    STATUS_ORDER (app/routers/purchases.py:584) и в реальных данных (0 закупок
    локально). Отнесён туда же, к «до договора».
  - любой прочий/будущий статус, не входящий в PAID_STATUSES /
    DELIVERED_STATUSES / CONTRACT_STAGE_STATUSES — по построению функции ниже
    (if/elif с явным else) молча попадает в группу «до договора». Осознанный
    выбор: «до договора» — самая безопасная группа по умолчанию (не пытается
    читать договорные/приёмочные суммы для строки, которая до них не дошла).

Ноль (Decimal("0")) — ЗНАЧЕНИЕ, отличное от «пусто» (None). Проверки везде —
`is not None`, никогда `or`/truthiness (тот баг уже разбирался в задаче:
`float(p.planned_total_price or 0)` в нескольких читателях путает
законный 0 с отсутствием числа только в контексте деления/приведения к float
для ответа — здесь, где 0 и None различаются по смыслу «эффективной суммы»,
разница обязана сохраняться).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.acceptance_docs import total_amount as _acceptance_total_amount

# Критерий рамочной головы — ЗЕРКАЛО app.routers.purchases.is_framework_head
# (не импортируется напрямую, чтобы не тянуть весь роутер как зависимость
# сервисного модуля; оба места обязаны определять его ОДИНАКОВО — см. FRAMEWORK_TYPES
# в app/routers/purchase_budget.py, откуда оно там берётся).
FRAMEWORK_TYPES: frozenset[str] = frozenset({"framework_cumulative", "framework_with_amount"})

# «После договора» — цена ИЗ ДОГОВОРА уже приоритетнее плана (совпадает с
# FACT_PRICED_STATUSES в app/services/feo_plan.py:50, но НЕ импортируется
# оттуда напрямую: feo_plan.py считает «факт позиции» с пропорциональным
# распределением, разными приоритетами источников и ContractItem.total per-item;
# здесь — заведомо более простая формула «сумма закупки целиком», прямого
# переиспользования нет, только совпадение набора статусов на этой стадии).
CONTRACT_STAGE_STATUSES: frozenset[str] = frozenset({"work_in_progress", "contracted", "ordered"})
DELIVERED_STATUSES: frozenset[str] = frozenset({"delivered"})
PAID_STATUSES: frozenset[str] = frozenset({"paid"})
# Всё остальное (wishes, plan_schedule, cancelled, легаси 'planned', любой
# незнакомый статус) — «до договора», см. докстринг модуля выше.


def _dec(v) -> Optional[Decimal]:
    """None остаётся None; всё прочее (Decimal/float/int/str-число) → Decimal.
    Не путать с `or 0` — 0 здесь тоже проходит как Decimal("0"), не как None."""
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


@dataclass(frozen=True)
class PurchaseAmounts:
    """Снимок денежных сумм закупки + вычисленная эффективная сумма.

    plan/contract/fact/paid — сырые колонки Purchase (planned_total_price/
    contract_price/acceptance_doc_amount/payment_amount) как есть, без
    фолбэков — на случай, если вызывающему коду нужно показать именно их, а не
    только итог.
    effective — сумма по формуле владельца (см. докстринг модуля).
    effective_source — имя колонки/формулы, откуда взято effective (для
    отладки/аудита; см. purchase_amounts_audit.py).
    """
    plan: Optional[Decimal]
    contract: Optional[Decimal]
    fact: Optional[Decimal]
    paid: Optional[Decimal]
    effective: Optional[Decimal]
    effective_source: str


def contract_amount(
    p: Purchase,
    *,
    contract_items_total: Optional[Decimal] = None,
    framework_max_amount: Optional[Decimal] = None,
) -> Optional[Decimal]:
    """«Цена договора» — contract_price ?? Σ contract_items.total, рамочная
    голова с Contract.max_amount — поверх (иначе манула contract_price, БЕЗ
    отката на Σ contract_items — голова не считается автоматически, см.
    app.services.purchase_money_writer).

    НЕ то же самое, что purchase_amounts(p).effective — это сознательно
    ДРУГОЙ показатель («сколько по договору», без отката на план/НМЦК/
    Σ purchase_items, который делает effective для закупок «до договора» или
    без единой ContractItem). Единственные, кто ДОЛЖЕН считать «цену
    договора» — эта функция: договорные документы (CONTRACT_FAMILY_DOC_TYPES
    в app/routers/documents.py::_resolve_doc_amount) и писатель
    app.services.purchase_money_writer.recalc_purchase_money (его часть,
    отвечающая за contract_price, — та же формула, не вторая копия).
    """
    contract = _dec(getattr(p, "contract_price", None))
    contract_items_total = _dec(contract_items_total)
    framework_max_amount = _dec(framework_max_amount)
    is_head = (
        getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
        and getattr(p, "parent_purchase_id", None) is None
    )
    if is_head:
        return framework_max_amount if framework_max_amount is not None else contract
    if contract is not None:
        return contract
    return contract_items_total


def purchase_amounts(
    p: Purchase,
    *,
    contract_items_total: Optional[Decimal] = None,
    items_total: Optional[Decimal] = None,
    framework_max_amount: Optional[Decimal] = None,
) -> PurchaseAmounts:
    """Чистая функция — БЕЗ обращений к БД. Суммы позиций (Σ contract_items.total
    / Σ purchase_items.total_price) и Contract.max_amount передаются уже
    посчитанными вызывающим кодом (см. load_purchase_amounts — bulk-версия для
    списка закупок).

    contract_items_total/items_total/framework_max_amount = None означает
    «нет ни одной строки» (а не «сумма строк равна 0» — тот случай приходит уже
    как Decimal("0")).

    Атрибуты читаются через getattr(..., None), не прямым обращением — вызывающий
    код (см. documents.py::_resolve_doc_amount, тесты test_contract_documents_
    use_contract_items.py) местами подставляет SimpleNamespace вместо реального
    Purchase; отсутствующее поле должно читаться как None, а не падать AttributeError.
    """
    plan = _dec(getattr(p, "planned_total_price", None))
    contract = _dec(getattr(p, "contract_price", None))
    # ПРАВИЛО №6 (2026-09-07, группа D4): "фактическая сумма" больше не читается
    # из скаляра acceptance_doc_amount напрямую — источник истины JSONB
    # acceptance_docs (см. app.services.acceptance_docs.total_amount, которая
    # сама фолбэчится на этот же скаляр для немигрированных закупок).
    fact = _acceptance_total_amount(p)
    paid = _dec(getattr(p, "payment_amount", None))
    contract_items_total = _dec(contract_items_total)
    items_total = _dec(items_total)
    framework_max_amount = _dec(framework_max_amount)

    is_head = (
        getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
        and getattr(p, "parent_purchase_id", None) is None
    )
    if is_head and framework_max_amount is not None:
        return PurchaseAmounts(plan, contract, fact, paid, framework_max_amount, "contract.max_amount")
    # Голова без явной предельной суммы (framework_max_amount is None) —
    # намеренно падает в обычную формулу по стадии ниже, как и все 9 читателей.

    status = getattr(p, "status", None)
    payment_declared = _dec(getattr(p, "payment_amount_declared", None))

    # Цепочка фолбэков по стадии (владелец, 2026-09-05, вторая волна решения):
    # первое не-NULL звено побеждает; если пусты ВСЕ — effective = None, а
    # effective_source перечисляет всю цепочку (для отладки/аудита).
    if status in PAID_STATUSES:
        chain = [
            (paid, "payment_amount"),
            (payment_declared, "payment_amount_declared"),
            (fact, "acceptance_doc_amount"),
            (contract, "contract_price"),
            (contract_items_total, "sum(contract_items.total)"),
            (plan, "planned_total_price"),
            (items_total, "sum(purchase_items.total_price)"),
        ]
    elif status in DELIVERED_STATUSES:
        chain = [
            (fact, "acceptance_doc_amount"),
            (contract, "contract_price"),
            (contract_items_total, "sum(contract_items.total)"),
            (plan, "planned_total_price"),
            (items_total, "sum(purchase_items.total_price)"),
        ]
    elif status in CONTRACT_STAGE_STATUSES:
        chain = [
            (contract, "contract_price"),
            (contract_items_total, "sum(contract_items.total)"),
            (plan, "planned_total_price"),
            (items_total, "sum(purchase_items.total_price)"),
        ]
    else:
        # До договора — включая cancelled/'planned'/любой незнакомый статус,
        # см. докстринг модуля.
        chain = [
            (plan, "planned_total_price"),
            (items_total, "sum(purchase_items.total_price)"),
        ]

    for value, source in chain:
        if value is not None:
            return PurchaseAmounts(plan, contract, fact, paid, value, source)
    all_sources = "|".join(name for _, name in chain)
    return PurchaseAmounts(plan, contract, fact, paid, None, f"{all_sources} (all NULL)")


async def load_purchase_amounts(db: AsyncSession, purchase_ids: list[int]) -> dict[int, PurchaseAmounts]:
    """Bulk-версия purchase_amounts() для списка закупок — 3 запроса максимум
    (закупки + Σ contract_items + Σ purchase_items), плюс 1 доп. запрос ТОЛЬКО
    если среди них есть рамочные головы со связанным договором (Contract.max_amount).
    Без N+1 независимо от размера purchase_ids.
    """
    purchase_ids = list(dict.fromkeys(purchase_ids))  # de-dup, сохранить порядок не важен
    if not purchase_ids:
        return {}

    purchases = (
        await db.execute(select(Purchase).where(Purchase.id.in_(purchase_ids)))
    ).scalars().all()
    if not purchases:
        return {}

    # Σ contract_items.total per purchase_id — присутствует в словаре ТОЛЬКО для
    # покупок, у которых есть хотя бы одна строка ContractItem (GROUP BY не
    # производит строку для покупок без совпадений) — так 0 (есть строки,
    # сумма 0) отличимо от None (строк нет вообще).
    ci_rows = (await db.execute(
        select(ContractItem.purchase_id, func.coalesce(func.sum(ContractItem.total), 0))
        .where(ContractItem.purchase_id.in_(purchase_ids))
        .group_by(ContractItem.purchase_id)
    )).all()
    contract_totals: dict[int, Decimal] = {pid: Decimal(str(total)) for pid, total in ci_rows}

    pi_rows = (await db.execute(
        select(PurchaseItem.purchase_id, func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .group_by(PurchaseItem.purchase_id)
    )).all()
    item_totals: dict[int, Decimal] = {pid: Decimal(str(total)) for pid, total in pi_rows}

    # Рамочные головы со связанным договором — единственные, кому вообще нужен
    # framework_max_amount (см. is_head в purchase_amounts()).
    framework_heads = [
        p for p in purchases
        if getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
        and getattr(p, "parent_purchase_id", None) is None
        and getattr(p, "contract_id", None) is not None
    ]
    framework_max_by_purchase: dict[int, Decimal] = {}
    if framework_heads:
        from app.models.contract import Contract  # local import: избежать цикла на уровне модуля

        contract_ids = {p.contract_id for p in framework_heads}
        c_rows = (await db.execute(
            select(Contract.id, Contract.max_amount).where(Contract.id.in_(contract_ids))
        )).all()
        max_by_contract = {cid: _dec(ma) for cid, ma in c_rows}

        # Владелец (2026-09-06, прод-находка: contract_id=32 → 5 закупок с
        # parent_purchase_id IS NULL, contract_id=42 → 3): данные допускают
        # НЕСКОЛЬКО «голов» на один и тот же договор (аномалия — по построению
        # рамочного механизма голова должна быть одна). Если применить
        # Contract.max_amount к КАЖДОЙ из них — эффективная сумма договора
        # задвоится/утроится при агрегации. Считаем по ВСЕЙ БД (не только по
        # текущему батчу purchase_ids — другая голова того же contract_id
        # может быть за пределами этого вызова), не только среди framework_heads:
        # max_amount применяется ТОЛЬКО если голова для этого contract_id ровно
        # одна; иначе — обычная цепочка по стадии для ВСЕХ них + warning в лог.
        head_count_rows = (await db.execute(
            select(Purchase.contract_id, func.count())
            .where(
                Purchase.contract_id.in_(contract_ids),
                Purchase.purchase_contract_type.in_(tuple(FRAMEWORK_TYPES)),
                Purchase.parent_purchase_id.is_(None),
            )
            .group_by(Purchase.contract_id)
        )).all()
        head_count_by_contract: dict[int, int] = {cid: cnt for cid, cnt in head_count_rows}

        for p in framework_heads:
            head_count = head_count_by_contract.get(p.contract_id, 0)
            if head_count != 1:
                import logging
                logging.getLogger(__name__).warning(
                    "purchase_amounts.load_purchase_amounts: contract_id=%s имеет %d рамочных голов "
                    "(parent_purchase_id IS NULL) — Contract.max_amount НЕ применяется ни к одной "
                    "(закупка id=%s среди них), effective считается обычной цепочкой по стадии",
                    p.contract_id, head_count, p.id,
                )
                continue
            v = max_by_contract.get(p.contract_id)
            if v is not None:
                framework_max_by_purchase[p.id] = v

    return {
        p.id: purchase_amounts(
            p,
            contract_items_total=contract_totals.get(p.id),
            items_total=item_totals.get(p.id),
            framework_max_amount=framework_max_by_purchase.get(p.id),
        )
        for p in purchases
    }


def effective_amount_expr():
    """SQLAlchemy case()-выражение той же цепочки-по-стадии, для использования
    в агрегатах (Σ effective_amount_expr() ... GROUP BY ...) — БЕЗ обращения к
    contract_items/purchase_items (см. ⚠️ ниже), НО С рамочной головой
    (Contract.max_amount) — правка 2026-09-06: раньше это выражение молча
    пропускало голову (см. git-историю), из-за чего SQL-агрегаты (dashboard.py/
    subsidies.py/feo_categories.py) и purchase_amounts()/load_purchase_amounts()
    (GET /api/purchases/{id}) давали РАЗНЫЕ числа для одной и той же рамочной
    головы (прод-пример: id=773 — 47262.50 в SQL-агрегатах против 600000 в
    GET /api/purchases/773) — ровно то самое «два числа одного показателя»,
    которое всё ПРАВИЛО №6 и должно устранить. Теперь голова определяется
    ТЕМ ЖЕ критерием (FRAMEWORK_TYPES + parent_purchase_id IS NULL), а
    Contract.max_amount достаётся коррелированным подзапросом (contract_id
    закупки может быть NULL — тогда подзапрос просто не находит строку и даёт
    NULL, coalesce проваливается в обычную цепочку по стадии, как и в
    purchase_amounts()).

    ⚠️ НЕСКОЛЬКО ГОЛОВ на один contract_id (владелец, 2026-09-06, прод-
    находка: contract_id=32 → 5 закупок с parent_purchase_id IS NULL,
    contract_id=42 → 3 — по построению рамочного механизма голова должна
    быть одна, но данные это не гарантируют): max_amount применяется ТОЛЬКО
    если голова для этого contract_id ровно одна (доп. коррелированный
    подсчёт голов-«соседей», см. head_count_for_contract ниже) — иначе ВСЕ
    они падают в обычную цепочку по стадии. В отличие от load_purchase_
    amounts() (та же гарантия, но с logging.warning при обнаружении) — SQL-
    выражение внутри case()/scalar_subquery() не может залогировать
    побочный эффект, поэтому здесь тихо (без warning) — обнаружить такой
    случай можно тем же SQL-запросом, что и в тесте
    test_multiple_framework_heads_same_contract_get_no_max_amount.

    ⚠️ Единственное оставшееся расхождение с purchase_amounts()/
    load_purchase_amounts(): цепочка владельца на каждой стадии в итоге
    доходит до Σ contract_items.total и/или Σ purchase_items.total_price —
    тем полям здесь взяться неоткуда без JOIN+GROUP BY, который не
    композируется с произвольным запросом вызывающего (те суммы штучные
    per-purchase, а не per-строка агрегата). Это SQL-выражение реализует
    только ту часть цепочки, что лежит прямо на Purchase/Contract (без join
    на contract_items/purchase_items):
      рамочная голова с Contract.max_amount → max_amount (поверх всего)
      paid      → payment_amount ?? payment_amount_declared ??
                  acceptance_doc_amount ?? contract_price ?? planned_total_price
      delivered → acceptance_doc_amount ?? contract_price ?? planned_total_price
      contract-стадия → contract_price ?? planned_total_price
      до договора     → planned_total_price
    т.е. пропускает оба Σ-шага цепочки и просто перепрыгивает через них к
    planned_total_price — закупка, у которой на её стадии всё вплоть до
    planned_total_price пусто, а сумма нашлась бы только в Σ purchase_items.
    total_price, здесь получит NULL, а не эту сумму (задокументировано и
    покрыто тестом test_sql_expr_diverges_from_python_on_item_fallback).
    Использовать load_purchase_amounts() там, где точность per-закупку (с
    полной цепочкой фолбэков, включая Σ-шаги) важна; это выражение — там, где
    нужен единственный SQL агрегат.

    ⚠️ ДВОЙНОЙ СЧЁТ в агрегатах по субсидии/категории ФЭО: рамочная голова и
    её дочерние закупки обычно делят один subsidy_id/feo_category_id — голова
    теперь даёт ПОЛНУЮ сумму контракта (max_amount), а дети — каждый СВОЮ
    сумму рядом; агрегат Σ по всем закупкам субсидии считает и то, и другое.
    Это НЕ новая проблема этой правки (голова и раньше суммировалась вместе с
    детьми — раньше просто с менее задвоенным числом, своим contract_price/
    planned_total_price, а не max_amount) и её исправление — состав агрегата
    (нужен явный фильтр «голова ИЛИ дети, не оба разом») — сознательно ОТЛОЖЕНО
    на следующую волну (владелец, 2026-09-06: «менять состав агрегата — не в
    этой волне»). Места, где голова и дети сейчас складываются вместе, —
    см. пометки `# ⚠️ ДВОЙНОЙ СЧЁТ` у:
      app/routers/dashboard.py (subsidy_q — общий per-subsidy агрегат)
      app/routers/subsidies.py::_calculate_spent/_calculate_spent_bulk
      app/routers/feo_categories.py::get_purchase_totals
    """
    from app.models.contract import Contract  # локальный импорт — избежать цикла на уровне модуля
    from sqlalchemy.orm import aliased

    is_head_cond = and_(
        Purchase.purchase_contract_type.in_(tuple(FRAMEWORK_TYPES)),
        Purchase.parent_purchase_id.is_(None),
    )
    # Владелец (2026-09-06): несколько «голов» на один contract_id (прод-
    # находка: contract_id=32 → 5, contract_id=42 → 3) не должны каждая
    # получать ПОЛНЫЙ Contract.max_amount — та же гарантия, что и в
    # load_purchase_amounts() (см. её комментарий), здесь — коррелированным
    # подсчётом голов-«соседей» по тому же contract_id.
    _HeadRow = aliased(Purchase)
    head_count_for_contract = (
        select(func.count())
        .select_from(_HeadRow)
        .where(
            _HeadRow.contract_id == Purchase.contract_id,
            _HeadRow.purchase_contract_type.in_(tuple(FRAMEWORK_TYPES)),
            _HeadRow.parent_purchase_id.is_(None),
        )
        .correlate(Purchase)
        .scalar_subquery()
    )
    is_unique_head_cond = and_(is_head_cond, Purchase.contract_id.isnot(None), head_count_for_contract == 1)
    # Коррелированный подзапрос: max_amount контракта ЭТОЙ строки Purchase.
    # contract_id IS NULL -> подзапрос не находит строку -> NULL -> coalesce
    # ниже проваливается в обычную цепочку по стадии (та же семантика, что
    # framework_max_amount=None в purchase_amounts()).
    framework_max_amount = (
        select(Contract.max_amount)
        .where(Contract.id == Purchase.contract_id)
        .correlate(Purchase)
        .scalar_subquery()
    )
    stage_case = case(
        (
            Purchase.status.in_(tuple(PAID_STATUSES)),
            func.coalesce(
                Purchase.payment_amount,
                Purchase.payment_amount_declared,
                Purchase.acceptance_doc_amount,
                Purchase.contract_price,
                Purchase.planned_total_price,
            ),
        ),
        (
            Purchase.status.in_(tuple(DELIVERED_STATUSES)),
            func.coalesce(Purchase.acceptance_doc_amount, Purchase.contract_price, Purchase.planned_total_price),
        ),
        (
            Purchase.status.in_(tuple(CONTRACT_STAGE_STATUSES)),
            func.coalesce(Purchase.contract_price, Purchase.planned_total_price),
        ),
        else_=Purchase.planned_total_price,
    )
    return case(
        (is_unique_head_cond, func.coalesce(framework_max_amount, stage_case)),
        else_=stage_case,
    )


def in_aggregate_scope(
    p: Purchase,
    *,
    parent_max_amount: Optional[Decimal] = None,
    own_max_amount: Optional[Decimal] = None,
    has_children: bool = False,
) -> bool:
    """Решение владельца (05.10.2026, заменяет решение 2026-09-06 для
    framework_with_amount — см. git-историю) — кто участвует в Σ «по статусу»
    (Заказано/Поставлено/Поставлено не оплачено/Оплачено/Ведётся работа) по
    субсидии/категории ФЭО/дашборду:
      - разовый договор / закупка без типа договора: как обычно, не исключается.
      - рамочный (И framework_with_amount, И framework_cumulative) — ГОЛОВА
        (parent_purchase_id IS NULL) исключается из ЭТИХ сумм, ТОЛЬКО если у
        неё есть хотя бы один РЕАЛЬНО связанный ребёнок (parent_purchase_id
        указывает на неё, has_children=True) — её деньги в статусных суммах
        несут сами заказы, голова здесь — организационная запись (даже если
        у неё задан Contract.max_amount: предельная сумма — отдельная
        величина для карточки «Заключено договоров»/«Законтрактовано», см.
        dashboard_charts.py::contract_single_q, а не для Заказано/Ведётся
        работа). Головы БЕЗ ни одного ребёнка (has_children=False, фактическая
        реальность для старых framework_cumulative-записей — см. ⚠️ ниже)
        продолжают считаться обычной закупкой по своей стадии — Σ их не
        теряет.
      - ЛЮБОЙ ребёнок рамочной головы (parent_purchase_id указывает на
        реальную framework-голову) — ВСЕГДА в Σ, своей суммой по стадии
        (effective_amount_expr()). Раньше (до 05.10.2026) дети
        framework_with_amount-головы с заданным max_amount исключались
        (деньги считались «уже внутри потолка головы») — из-за этого
        Заказано/Ведётся работа у ФАДМ_2026 показывали только лимит головы,
        а реальные заказы пропадали из этих карточек; владелец отменил это
        исключение: голова и заказы теперь РАЗНЫЕ карточки (голова — предел
        для «Заключено», заказы — факт для «Заказано» и далее).

    ⚠️ ФАКТ ТЕКУЩИХ ДАННЫХ (владелец, 2026-09-06, остаётся в силе): часть
    старых framework_cumulative-записей на проде связана между собой общим
    contract_id, а НЕ parent_purchase_id (эта FK-колонка занята несвязанной
    фичей «разбить закупку на несколько», purchases.py ~4317) — для таких
    голов has_children=False, и они продолжают считаться обычной закупкой
    (см. test_aggregate_scope_uncapped_cumulative_head_without_children_stays_in_scope).
    Новые загрузчики (ФАДМ 2026_2 и далее) обязаны проставлять
    parent_purchase_id реально, иначе эта функция не увидит связь.

    Используется как дополнительный фильтр в местах, где по субсидии/
    категории считается Σ purchase_amounts()/effective_amount_expr() (см.
    aggregate_scope_expr() — SQL-эквивалент с той же семантикой):
    dashboard_charts.py::subsidy_q, subsidies.py::_calculate_spent(_bulk),
    feo_categories.py::get_purchase_totals, feo_plan_reads.py.

    parent_max_amount — оставлен параметром ради обратной совместимости
    вызовов, но БОЛЬШЕ НЕ ВЛИЯЕТ на результат (раньше решал исключение
    ребёнка — правило 05.10.2026 детей никогда не исключает); own_max_amount/
    has_children резолвятся вызывающим кодом (эта функция не ходит в БД) —
    задан ли Contract.max_amount у СОБСТВЕННОГО договора закупки и есть ли
    хоть одна закупка с parent_purchase_id == p.id, соответственно.
    """
    _ = parent_max_amount  # больше не используется — см. докстринг выше
    is_head = (
        getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
        and getattr(p, "parent_purchase_id", None) is None
    )
    if is_head and has_children:
        return False
    return True


def aggregate_scope_expr():
    """SQL-эквивалент in_aggregate_scope() (см. её докстринг — решение
    владельца 05.10.2026): исключается ТОЛЬКО рамочная ГОЛОВА (framework_
    cumulative ИЛИ framework_with_amount, parent_purchase_id IS NULL) с
    РЕАЛЬНО существующим ребёнком (EXISTS по parent_purchase_id) — её деньги
    в статусных суммах (Заказано/Поставлено/Оплачено/Ведётся работа) несут
    сами заказы. Дети рамочных голов (и вообще любые закупки) больше никогда
    не исключаются этим предикатом — до 05.10.2026 дети framework_with_amount
    с заданным Contract.max_amount исключались («их деньги уже внутри потолка
    головы»), из-за чего статусные карточки у таких субсидий показывали
    только лимит головы без самих заказов; владелец это отменил — голова
    участвует только в отдельной карточке «Заключено договоров»
    (dashboard_charts.py::contract_single_q), не здесь.

    Применять ЧЕРЕЗ JOIN-условие (не отдельным WHERE) там, где Purchase
    LEFT JOIN-ится к родительской сущности (Subsidy и т.п.) — иначе строки
    без закупок (или закупки которых ВСЕ исключены этим предикатом) исчезнут
    из результата вместе с самой родительской строкой (см. пример в
    dashboard_charts.py::subsidy_q — .outerjoin(Purchase, and_(Purchase.
    subsidy_id == Subsidy.id, aggregate_scope_expr()))). В местах без такого
    JOIN (subsidies.py::_calculate_spent, feo_categories.py::
    get_purchase_totals — обычный WHERE-фильтр без родительской сущности,
    которую нужно сохранить) можно и обычным .where(aggregate_scope_expr()).
    """
    from sqlalchemy.orm import aliased

    ChildRow = aliased(Purchase)

    is_head_cond = and_(
        Purchase.purchase_contract_type.in_(tuple(FRAMEWORK_TYPES)),
        Purchase.parent_purchase_id.is_(None),
    )
    # has_children — РЕАЛЬНАЯ проверка (EXISTS): хоть одна закупка, чей
    # parent_purchase_id указывает на ЭТУ строку (а не догадка по типу
    # договора/contract_id — см. ⚠️ в докстринге in_aggregate_scope про
    # старые framework_cumulative-записи без этой связи).
    has_children = (
        select(literal(1))
        .select_from(ChildRow)
        .where(ChildRow.parent_purchase_id == Purchase.id)
        .correlate(Purchase)
        .exists()
    )
    is_excluded_head = and_(is_head_cond, has_children)

    # ⚠️ NULL-ловушка (найдена QA, 2026-09-06, остаётся в силе): `purchase_
    # contract_type IN (...)` для NULL (обычная закупка — таких большинство)
    # даёт NULL, не FALSE; NULL распространяется через AND/OR, и `~NULL` —
    # снова NULL, что в WHERE/JOIN ON означает ОТКАЗ строки. Финальный
    # coalesce(..., True) — «не смогли доказать исключение → включаем».
    return func.coalesce(~is_excluded_head, True)
