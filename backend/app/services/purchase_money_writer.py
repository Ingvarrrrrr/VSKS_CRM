"""purchase_money_writer.py — ЕДИНСТВЕННЫЙ писатель денежных колонок Purchase
(planned_total_price / total_nmck / nmck / contract_price).

Контекст (ПРАВИЛО №6, задача 2026-09-05, вторая волна): до этого модуля этот
пересчёт был продублирован минимум в четырёх местах (create_purchase, PUT
update_purchase, `_recalc_purchase_totals`, `_recalc_contract_price_from_
contract_items` в app/routers/purchases.py, плюс похожие блоки в wishes.py и
purchase_transitions.py) — и они расходились: например `_recalc_purchase_
totals` и оба create/PUT-блока писали `contract_price = Σ purchase_items` в
ЛЮБОМ статусе, включая `wishes` — то самое «второе перо», которое конкурировало
с настоящей ценой договора (`Σ contract_items.total`, введённой позже как
источник истины для этого поля, см. `_recalc_contract_price_from_contract_
items`). С этого модуля у обеих денежных пар — «план» (planned_total_price/
total_nmck/nmck) и «цена договора» (contract_price) — ровно один писатель;
все перечисленные выше места теперь ТОЛЬКО зовут `recalc_purchase_money`.

НОВОЕ ПОВЕДЕНИЕ (отличия от кода, который этот модуль заменяет):

1. planned_total_price = total_nmck = nmck = Σ purchase_items.total_price —
   ВСЕГДА одно и то же число, пока статус закупки НЕ в TZ_FROZEN_STATUSES
   (см. app.routers.purchases.TZ_FROZEN_STATUSES — {work_in_progress,
   contracted, ordered, delivered, paid}; статус «до договора» — wishes/
   plan_schedule/cancelled/легаси 'planned'/что угодно незнакомое). Раньше
   `_recalc_purchase_totals` писала `total_nmck = items_sum` безусловно, но
   `planned_total_price = items_sum or p.planned_total_price` — Python-truthy
   баг: сумма ровно 0 тихо оставляла старое planned_total_price, а total_nmck
   в этот момент уже был 0 — те же самые «два числа одного показателя»,
   которые всё это правило и должно устранить. Теперь оба поля (и их
   deprecated-алиас nmck) синхронно получают Σ purchase_items.total_price,
   включая 0 как законное значение (см. ПРАВИЛО №0 модуля purchase_amounts.py
   — «ноль — значение, а не пусто»).
   С момента заморозки (TZ_FROZEN_STATUSES) эти три поля НЕ трогаются вообще —
   они остаются зафиксированным снимком плана на момент объявления закупки.
   Отдельно: если у закупки вообще нет ни одной строки PurchaseItem (например,
   авансовый отчёт, который целиком ведётся через ContractItem, а не через
   позиции ТЗ) — эти три поля тоже не трогаются, им просто неоткуда взяться
   (см. п.3 ниже про полностью безпозиционные закупки — здесь тот же принцип
   применён к паре «план», а не к обеим денежным парам сразу).

2. contract_price:
     - если у закупки есть хотя бы одна строка ContractItem —
       contract_price = Σ ContractItem.total, КРОМЕ рамочной головы
       (is_framework_head — см. FRAMEWORK_TYPES в purchase_amounts.py:
       purchase_contract_type in {framework_cumulative, framework_with_amount}
       И parent_purchase_id IS NULL) — там ручное значение НЕ перезаписывается
       (см. `_recalc_contract_price_from_contract_items`,
       test_purchase_contract_price_recalc.py). Это применяется НЕЗАВИСИМО от
       статуса — как и в старом `_recalc_contract_price_from_contract_items`,
       который вызывается сразу при правке ContractItem, до перехода закупки в
       «после договора».
     - иначе (нет ContractItem вообще), если статус УЖЕ в TZ_FROZEN_STATUSES
       (закупка объявлена, но по каким-то причинам договорные позиции не
       заведены) И contract_price ещё пуст — Σ purchase_items.total_price.
       Пишем ТОЛЬКО если contract_price сейчас None — не перетираем то, что
       туда уже вписали руками/из акта.
     - иначе (до договора, договорных позиций нет) — НЕ ПИШЕМ вообще. Это и
       есть устранённое «второе перо»: раньше create_purchase/update_purchase
       писали `contract_price = Σ purchase_items` для закупки на статусе
       `wishes`, из-за чего «цена договора» показывала число раньше, чем
       договор вообще появился.
   Рамочная голова никогда не получает автоматически посчитанный
   contract_price (ни из ContractItem, ни из purchase_items) — это ручное
   поле по построению рамочного механизма (см. purchase_budget.py).

3. Если у закупки НЕТ ни PurchaseItem, ни ContractItem вообще (легаси-импорт
   из старого Excel, часть которого не дозаполнена позициями) — функция не
   трогает ни одну из денежных колонок: применить Σ по пустому множеству
   значило бы обнулить существующие цифры такой закупки, а не пересчитать их.

Вызывается ИЛИ с уже посчитанными суммами (items_total/contract_items_total —
Decimal или None = "строк нет вообще", НЕ 0 — тот случай уже пришёл бы как
Decimal("0")), ИЛИ без них — тогда функция сама делает ровно 2 SQL-запроса
(по одному на каждую сумму) для этой закупки. bulk_recalc_purchase_money —
вариант без N+1 для списка закупок (тот же приём, что и
purchase_amounts.load_purchase_amounts: 2 GROUP BY запроса на весь список,
затем чистый Python-цикл).
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.purchase_amounts import FRAMEWORK_TYPES


def _is_framework_head(p: Purchase) -> bool:
    """Зеркало app.routers.purchases.is_framework_head и app.services.
    purchase_amounts — та же формула в трёх местах намеренно (см. комментарий
    там же: локальный импорт роутера из сервисного модуля создал бы циклы
    импорта на уровне модуля, дублировать эти 2 строки дешевле)."""
    return (
        getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
        and getattr(p, "parent_purchase_id", None) is None
    )


async def _load_items_total(db: AsyncSession, purchase_id: int) -> Optional[Decimal]:
    row = (await db.execute(
        select(func.count(PurchaseItem.id), func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .where(PurchaseItem.purchase_id == purchase_id)
    )).one()
    count, total = row
    return Decimal(str(total)) if count else None


async def _load_contract_items_total(db: AsyncSession, purchase_id: int) -> Optional[Decimal]:
    row = (await db.execute(
        select(func.count(ContractItem.id), func.coalesce(func.sum(ContractItem.total), 0))
        .where(ContractItem.purchase_id == purchase_id)
    )).one()
    count, total = row
    return Decimal(str(total)) if count else None


async def recalc_purchase_money(
    db: AsyncSession,
    purchase: Purchase,
    *,
    items_total: Optional[Decimal] = None,
    contract_items_total: Optional[Decimal] = None,
) -> None:
    """Пересчитывает planned_total_price/total_nmck/nmck и contract_price по
    правилам из докстринга модуля. Мутирует `purchase` in-place — не коммитит
    и не делает flush (вызывающий код сам решает, когда сохранять — как и
    раньше делали _recalc_purchase_totals/_recalc_contract_price_from_
    contract_items).

    items_total/contract_items_total — Σ уже посчитана вызывающим кодом
    (например: только что импортировали позиции и знаем сумму без похода в
    БД). None означает «не передано — посчитать самому», а НЕ «сумма 0» (0
    приходит как Decimal("0")).
    """
    from app.routers.purchases import TZ_FROZEN_STATUSES  # локальный импорт — избежать цикла на уровне модуля (purchases.py импортирует этот модуль)

    if items_total is None:
        items_total = await _load_items_total(db, purchase.id)
    if contract_items_total is None:
        contract_items_total = await _load_contract_items_total(db, purchase.id)

    if items_total is None and contract_items_total is None:
        # Легаси-импорт без единой позиции — нечего пересчитывать, старые
        # значения (какими бы они ни были) не трогаем.
        return

    frozen = purchase.status in TZ_FROZEN_STATUSES
    is_head = _is_framework_head(purchase)

    # План (planned_total_price/total_nmck/nmck) пересчитывается ТОЛЬКО пока
    # закупка не заморожена И только если у неё вообще есть PurchaseItem-строки
    # (items_total is not None) — закупка без единой позиции (например,
    # авансовый отчёт, который ведётся целиком через ContractItem) не должна
    # обнуляться только из-за того, что мы сюда зашли по поводу contract_price.
    if not frozen and items_total is not None:
        purchase.planned_total_price = items_total
        purchase.total_nmck = items_total
        purchase.nmck = items_total  # deprecated-алиас, всегда = total_nmck

    if contract_items_total is not None:
        # ВАЖНО: здесь НЕ переиспользуется app.services.purchase_amounts.
        # contract_amount() — та функция для ЧТЕНИЯ («что показать», текущий
        # contract_price приоритетнее Σci, если уже заполнен). Здесь же —
        # ЗАПИСЬ: раз пришли свежие ContractItem, contract_price ОБЯЗАН
        # обновиться до их суммы (та же семантика, что была у
        # _recalc_contract_price_from_contract_items) — контракт-price
        # текущий заведомо устарел, его как раз и обновляем.
        if not is_head:
            purchase.contract_price = contract_items_total
        # рамочная голова — ручное значение, не перезаписываем (см. докстринг)
    elif frozen and not is_head and purchase.contract_price is None:
        item_value = items_total if items_total is not None else Decimal("0")
        purchase.contract_price = item_value
    # иначе (до договора, нет ContractItem) — НЕ пишем contract_price вообще.


async def bulk_recalc_purchase_money(db: AsyncSession, purchases: list[Purchase]) -> None:
    """Вариант recalc_purchase_money() без N+1 для списка закупок — 2
    GROUP BY запроса на весь список (не по одному на закупку), затем чистый
    Python-цикл. Использовать при массовых операциях (импорт позиций пачкой,
    массовый пересчёт после миграции и т.п.)."""
    ids = [p.id for p in purchases]
    if not ids:
        return

    pi_rows = (await db.execute(
        select(PurchaseItem.purchase_id, func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .where(PurchaseItem.purchase_id.in_(ids))
        .group_by(PurchaseItem.purchase_id)
    )).all()
    items_totals = {pid: Decimal(str(total)) for pid, total in pi_rows}

    ci_rows = (await db.execute(
        select(ContractItem.purchase_id, func.coalesce(func.sum(ContractItem.total), 0))
        .where(ContractItem.purchase_id.in_(ids))
        .group_by(ContractItem.purchase_id)
    )).all()
    contract_totals = {pid: Decimal(str(total)) for pid, total in ci_rows}

    for p in purchases:
        await recalc_purchase_money(
            db, p,
            items_total=items_totals.get(p.id),
            contract_items_total=contract_totals.get(p.id),
        )
