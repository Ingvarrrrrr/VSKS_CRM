"""feo_payroll.py — ОДНА формула «статья ФОТ по имени» (ПРАВИЛО №6).

Повод: субсидия «ДНР» (прод id 76) — статьи «ФОТ ДНР», «НДФЛ 13%»,
«страховой взнос 7,8%», «командировочные» падали в «без типа» на карточках,
хотя у колонки «Товар/услуга/работа» для СТАТЕЙ типа нет вовсе (это ФОТ, не
товар и не услуга и не «без типа» — см. план .planning/quick/2026-10-07-dnr-
feo-cards/PLAN.md шаг 2). Признак `is_payroll` статьи (ручной переключатель
ИЛИ автоматически при импорте/миграции по этому правилу имени) делает её
позиции (и позиции всех подкатегорий) видом `payroll` в разбивках по типу
(app.services.item_type_split.KIND_PAYROLL), независимо от item_type самой
позиции.

Единственная реализация правила «похоже на ФОТ по названию» — миграция
e3f5g7h9i1j3 (разовый backfill) и импорт ФЭО (feo_import_apply.py, при
создании статьи) обязаны звать ЭТУ функцию, а не копировать regex повторно.

ВАЖНО (найдено при проверке на проде, 07.10.2026): «фот» матчить только как
ОТДЕЛЬНОЕ слово — иначе статья «Расходы на приобретение основных средств
(оргтехника, фото-, видеотехники...)» ложно попадает в ФОТ из-за подстроки
«фот» внутри «фото-». Границы слова — `[^а-яёa-z]` по обе стороны (или
начало/конец строки), а не `\b` (между кириллицей и границей слова `\b`
может вести себя непредсказуемо в зависимости от локали движка regex)."""
import re
from typing import Iterable, Optional

_PAYROLL_RE = re.compile(
    r"(^|[^а-яёa-z])фот([^а-яёa-z]|$)"       # «ФОТ» отдельным словом (не «фото-»)
    r"|оплат[а-яё]*\s+труда"                   # «оплата труда», «оплату труда»...
    r"|выплат[а-яё]*\s+персонал"                # «выплаты персоналу», «выплата персоналу»...
    r"|зар[ао]б[ао]тн[а-яё]*\s+плат"           # «заработная/заробатная/зароботная плата» (опечатки владельца)
    r"|зарплат",                                # «зарплата» слитно
    re.IGNORECASE,
)


def is_payroll_name(name: str | None) -> bool:
    """True, если название статьи ФЭО похоже на «ФОТ и иные выплаты
    персоналу» (ключевые слова «ФОТ» отдельным словом / «оплата труда» /
    «выплаты персоналу», регистронезависимо). Пустое имя → False."""
    if not name:
        return False
    return bool(_PAYROLL_RE.search(name))


async def subsidy_ids_with_payroll(db, subsidy_ids: Optional[Iterable[int]] = None) -> set:
    """Subsidy id, у которых есть хотя бы ОДНА СОБСТВЕННАЯ FeoCategory.
    is_payroll=True (БЕЗ наследования по дереву — для факта «в субсидии
    вообще есть ФОТ» наследование не нужно: у потомка is_payroll=True
    эффективно, только если у какого-то предка стоит собственный флаг, т.е.
    хотя бы одна строка с is_payroll=True в этой субсидии гарантированно
    есть). Координатор (21.10.2026, замер на проде): на сотни субсидий
    аккаунтов таких ~4 — используется ДО дорогой проверки права
    subsidy.view_payroll (app.services.payroll_visibility), чтобы не гонять
    has_org_key по каждой субсидии каждого аккаунта (routers/purchases.py
    список, dashboard_charts scrub, object_visibility._payroll_gate).
    subsidy_ids=None — по ВСЕМ субсидиям (не нужно сперва грузить полный
    список Subsidy.id — сразу фильтр по FeoCategory, которых меньше)."""
    from sqlalchemy import select
    from app.models.feo_category import FeoCategory

    q = select(FeoCategory.subsidy_id).where(FeoCategory.is_payroll == True).distinct()  # noqa: E712
    if subsidy_ids is not None:
        subsidy_ids = list(subsidy_ids)
        if not subsidy_ids:
            return set()
        q = q.where(FeoCategory.subsidy_id.in_(subsidy_ids))
    rows = (await db.execute(q)).scalars().all()
    return set(rows)


async def payroll_category_ids(db, subsidy_ids: Iterable[int]) -> set:
    """ЕДИНСТВЕННЫЙ резолвер «какие категории ФЭО субсидий считаются ФОТ» —
    статья с FeoCategory.is_payroll=True делает payroll СЕБЯ и ЛЮБУЮ
    подкатегорию (наследование по дереву, план .planning/quick/2026-10-07-
    dnr-feo-cards/PLAN.md шаг 2). Везде, где нужно классифицировать позицию
    закупки/ФЭО как payroll по категории (а не по item_type, см.
    app.services.item_type_split.kind_of_for_category) — звать ЭТУ функцию,
    а не ходить в FeoCategory напрямую (ПРАВИЛО №6).

    Возвращает set id ВСЕХ категорий (себя + потомков) в указанных
    субсидиях, которые эффективно payroll."""
    from sqlalchemy import select
    from app.models.feo_category import FeoCategory

    subsidy_ids = list(subsidy_ids)
    if not subsidy_ids:
        return set()
    rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.parent_id, FeoCategory.is_payroll)
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )).all()
    if not rows:
        return set()
    parent_of = {r.id: r.parent_id for r in rows}
    own_payroll = {r.id for r in rows if r.is_payroll}

    _memo: dict = {}

    def _effective(cid: int) -> bool:
        if cid in _memo:
            return _memo[cid]
        if cid in own_payroll:
            _memo[cid] = True
            return True
        parent_id = parent_of.get(cid)
        result = _effective(parent_id) if parent_id is not None and parent_id in parent_of else False
        _memo[cid] = result
        return result

    return {r.id for r in rows if _effective(r.id)}


async def purchase_payroll_map(db, purchase_ids: Iterable[int]) -> dict:
    """{purchase_id: True/False} — эффективная статья закупки ФОТ (решение
    владельца 21.10.2026, ХРО_2026: закупки «ЗП»/«Отчисления»/«Командировочные»
    несут статью ФОТ на purchases.feo_category_id, у позиции item_type=NULL и
    своей feo_category_id нет — карточки «В работе/Оплачено» должны всё равно
    увидеть их как ФОТ, не «без типа»).

    ЕДИНСТВЕННАЯ проверка «закупка — ФОТ» (ПРАВИЛО №6) — используется везде,
    где разбивка по виду позиции (goods/services/payroll/unspecified) должна
    знать про ФОТ на уровне ЗАКУПКИ целиком (а не только статьи отдельной
    позиции, см. item_type_split.kind_of_for_category для уровня позиции):
    app.services.dashboard_type_split, app.services.paid_over_delivered,
    app.services.subsidy_paid_breakdown, app.services.metric_drill_rows.

    Закупка — ФОТ, если ХОТЯ БЫ один из источников эффективной категории ---
    покупка (Purchase.feo_category_id), любая её позиция (PurchaseItem.
    feo_category_id) ИЛИ категория плановой позиции этой строки
    (PurchaseItem.feo_planned_item_id → FeoPlannedItem.feo_category_id) ---
    попадает в payroll_category_ids() (себя или предка) соответствующей
    субсидии."""
    from sqlalchemy import select
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.feo_planned_item import FeoPlannedItem

    purchase_ids = list(purchase_ids)
    if not purchase_ids:
        return {}

    purchase_rows = (await db.execute(
        select(Purchase.id, Purchase.subsidy_id, Purchase.feo_category_id)
        .where(Purchase.id.in_(purchase_ids))
    )).all()
    subsidy_ids = {r.subsidy_id for r in purchase_rows if r.subsidy_id is not None}
    payroll_ids = await payroll_category_ids(db, subsidy_ids)

    result = {r.id: bool(r.feo_category_id in payroll_ids) for r in purchase_rows}

    item_rows = (await db.execute(
        select(
            PurchaseItem.purchase_id, PurchaseItem.feo_category_id,
            FeoPlannedItem.feo_category_id.label("plan_category_id"),
        )
        .outerjoin(FeoPlannedItem, PurchaseItem.feo_planned_item_id == FeoPlannedItem.id)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )).all()
    for r in item_rows:
        if result.get(r.purchase_id):
            continue
        if r.feo_category_id in payroll_ids or r.plan_category_id in payroll_ids:
            result[r.purchase_id] = True

    for pid in purchase_ids:
        result.setdefault(pid, False)
    return result


async def payroll_purchase_ids_for_subsidies(db, subsidy_ids: Iterable[int]) -> set:
    """Set purchase_id, эффективно ФОТ, для заданных субсидий — та же ТРОЙКА
    источников эффективной категории (purchase.feo_category_id / позиция /
    плановая позиция), что и purchase_payroll_map, ПРАВИЛО №6 — одна формула
    «закупка — ФОТ», но результат как SQL-пригодный set id, а не dict по уже
    выбранному списку purchase_id. Нужна там, где фильтр должен встать В
    ЗАПРОС ДО пагинации/LIMIT/COUNT (app.routers.purchases::list_purchases,
    часть 3 плана владельца 21.10.2026 — «Видеть ФОТ»), а не постфактум в
    Python над уже выбранной страницей."""
    from sqlalchemy import select
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.feo_planned_item import FeoPlannedItem

    subsidy_ids = list(subsidy_ids)
    if not subsidy_ids:
        return set()
    payroll_ids = await payroll_category_ids(db, subsidy_ids)
    if not payroll_ids:
        return set()

    own = (await db.execute(
        select(Purchase.id).where(
            Purchase.subsidy_id.in_(subsidy_ids),
            Purchase.feo_category_id.in_(payroll_ids),
        )
    )).scalars().all()
    via_item = (await db.execute(
        select(PurchaseItem.purchase_id)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .where(
            Purchase.subsidy_id.in_(subsidy_ids),
            PurchaseItem.feo_category_id.in_(payroll_ids),
        )
    )).scalars().all()
    via_plan = (await db.execute(
        select(PurchaseItem.purchase_id)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(FeoPlannedItem, PurchaseItem.feo_planned_item_id == FeoPlannedItem.id)
        .where(
            Purchase.subsidy_id.in_(subsidy_ids),
            FeoPlannedItem.feo_category_id.in_(payroll_ids),
        )
    )).scalars().all()
    return set(own) | set(via_item) | set(via_plan)
