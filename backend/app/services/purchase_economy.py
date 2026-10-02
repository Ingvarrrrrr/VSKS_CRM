"""purchase_economy.py — «экономия по закупке»: ТОЛЬКО расчёт (владелец,
02.10.2026, план .planning/quick/2026-10-02-money-redistribution/PLAN.md, шаг 3,
ИСПРАВЛЕНО 02.10.2026 — владелец отверг базу planned_total: на боевых данных
во всех 22 законтрактованных закупках planned_total равен сумме договора
(снимок цены ТЗ = цене договора) → экономия всегда 0, цифра бессмысленна).

Purchase.economy (колонка БД) формулой больше не заполняется — читатели
переводятся на функции этого модуля (ПРАВИЛО №6 — единственная точка расчёта;
список переведённых мест см. PLAN.md раздел «ПРАВИЛО №6» и отчёт сессии
02.10.2026): purchase_export.py, documents/contexts_build.py,
documents/fabrikant_package.py, field_registry.py, schemas/purchases.py,
purchase_serializers.py, dashboard_analytics.py (plan_contract_delta).

НОВАЯ ФОРМУЛА (владелец, 02.10.2026, правка после ревью): «позиции договора
дороже/дешевле ПЛАНОВЫХ» — база экономии ПОЗИЦИИ ЗАКУПКИ — это её ПЛАНОВАЯ
ПОЗИЦИЯ (FeoPlannedItem, Ур.5 дерева ФЭО), НЕ PurchaseItem.planned_total
(снимок цены ТЗ — на практике совпадает с ценой договора и даёт 0 экономии).

Для ЗАКОНТРАКТОВАННОЙ позиции закупки (committed_status_predicate/
is_purchase_committed, app.services.committed_amounts — тот же предикат, что
и шаг 1 плана, ПРАВИЛО №6: вторая формула статусов здесь не заводится), с
фактом из fact_amounts_for_rows (ЕДИНАЯ формула факта, app.services.
feo_plan_fact — не дублируется):

  0. Нет факта (fact_amounts_for_rows не вернула сумму — ещё нет ни
     contract_price, ни ContractItem) → НЕ меряется, причина 'no_fact'.
     Проверяется ПЕРЕД всем остальным — без факта сравнивать не с чем.
  1. Привязана к активной FeoPlannedItem P (PurchaseItem.feo_planned_item_id,
     payment_mode='one_time'):
       а) НЕ составная (P.is_composite=False), на уровне СТРОКИ закупки:
          - P.unit_price задан → база = P.unit_price × PurchaseItem.quantity;
          - иначе P.quantity > 0 и P.amount задан → база = P.amount ×
            PurchaseItem.quantity / P.quantity — это ДОЛЯ плана позиции по
            количеству строки в общем количестве плана, А НЕ «цена за
            единицу» (в проекте запрещено подменять PurchaseItem.unit_price
            делением amount/quantity, см. feo_planned_item.py docstring
            unit_price — здесь то же самое поле ничем не подменяется, просто
            пропорционально делится СУММА, храним её только в локальной
            переменной расчёта);
          - иначе (ни unit_price, ни quantity+amount) → НЕ меряется,
            причина 'no_plan_price'.
          Экономия строки = база − факт строки.
       б) СОСТАВНАЯ (P.is_composite=True) — несколько строк ОДНОЙ закупки на
          одну позицию (напр. «проживание» 133 чел. + «питание» 133 чел.,
          см. committed_by_planned_item/planned_item_consumption, ПРАВИЛО
          №6 — тот же приём, переиспользуем идею, не копируем SQL):
          количество группы = MAX(PurchaseItem.quantity) строк ЭТОЙ закупки
          на эту позицию (не Σ); факт группы = Σ фактов её строк; база =
          P.amount × max_qty / P.quantity (P.quantity > 0 и P.amount заданы,
          иначе — 'no_plan_price' для всех строк группы). Экономия
          считается на уровне (закупка, позиция), НЕ по отдельным строкам
          группы — группа учитывается в Σ экономии закупки один раз.
          Проверка на примере владельца: P = «Бензопила» 2 шт / 200 000,
          закупка А 1 шт за 101 000 → −1 000, закупка Б 1 шт за 80 000 →
          +20 000; Σ = 19 000 = savings позиции (amount − committed) —
          покрыто test_money_committed.py.
  2. Привязана к ежемесячной P (payment_mode='monthly') → НЕ меряется,
     причина 'monthly' (ежемесячные резервируются целиком, план.md шаг 2).
  3. Не привязана ни к одной FeoPlannedItem, либо привязана на
     несуществующую/неактивную позицию → НЕ меряется, причина 'unlinked'
     (невалидная привязка равнозначна отсутствию — тот же приём, что
     exclude_planned_item_linked в committed_amounts.py/feo_plan_fact.py).
  4. over_plan=true строки — НЕ фильтруются отдельно: если привязаны к P,
     считаются ПО ПРАВИЛУ 1 (переплата сверх плана выйдет отрицательной
     экономией — согласованное превышение, видно сразу); непривязанные —
     причина 'unlinked', как и везде.

Экономия закупки = Σ экономии её измеренных строк/групп. Если НИ ОДНА строка
не измерена — economy=None (нечего сравнивать, НЕ 0).

Выдача (контракт с фронтом, имена существующих полей НЕ меняются):
  закупка: economy (число|null), economy_no_planned_price_items (теперь —
    ЧИСЛО НЕизмеренных законтрактованных СТРОК закупки, любая причина, не
    только 'no_plan_price' — имя поля оставлено ради обратной совместимости
    схемы/фронта), economy_unmeasured_by_reason (НОВОЕ) — счётчики
    {unlinked, no_plan_price, monthly, no_fact}.
  субсидия (/api/dashboard/charts subsidy_stats): economy_total,
    economy_no_planned_price_items, economy_unmeasured_by_reason.
  GET /api/dashboard/economy-by-method: plan (Σ баз измеренных), fact (Σ
    фактов измеренных), economy, economy_pct = economy/plan,
    no_planned_price_items (неизмеренные, любая причина),
    unmeasured_by_reason.

ИСПРАВЛЕНО 02.10.2026 (приёмка по скриншотам ФАДМ_2026 — 39/39 законтрактованных
позиций без привязки к плановой, ни одна не измерена, карточки/таблица
показывали 0 ₽, читалось как «экономии нет»): если по субсидии/группе способа
НЕ измерена НИ ОДНА позиция — economy_total (субсидия) = None, а в
by-method-группе plan/fact/economy/economy_pct = None (не 0.0). Как только
измерена хотя бы одна — числа считаются как раньше. purchases/
no_planned_price_items/unmeasured_by_reason — всегда числа, null не
принимают.

Функции:
  purchase_economy_bulk — пакетная (без N+1) экономия списка закупок.
  purchase_economy_one — экономия ОДНОЙ закупки (тонкая обёртка, не вторая формула).
  purchase_economy_by_subsidy — агрегат по субсидии (dashboard_charts.subsidy_stats).
  purchase_economy_by_method — агрегация по способу закупки (purchase_method/
    competitive_form) — GET /api/dashboard/economy-by-method.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.committed_amounts import is_purchase_committed
from app.services.feo_plan_fact import fact_amounts_for_rows

_CENTS = Decimal("0.01")
_UNMEASURED_REASONS = ("unlinked", "no_plan_price", "monthly", "no_fact")


def _empty_bucket() -> dict:
    return {
        "economy": None,           # Decimal|None — None, когда считать было не из чего
        "planned_sum": Decimal("0"),   # Σ баз измеренных строк/групп (не "план закупки")
        "fact_sum": Decimal("0"),      # Σ фактов измеренных строк/групп
        "items_considered": 0,         # измеренных строк (составная группа считается как кол-во её строк)
        "unmeasured_total": 0,         # Σ unmeasured_by_reason.values() — удобства ради
        "unmeasured_by_reason": {r: 0 for r in _UNMEASURED_REASONS},
    }


def _mark_unmeasured(bucket: dict, reason: str, count: int = 1) -> None:
    bucket["unmeasured_by_reason"][reason] += count
    bucket["unmeasured_total"] += count


def _apply_measured(bucket: dict, base: Decimal, fact: Decimal, rows_count: int) -> None:
    base_q = base.quantize(_CENTS)
    fact_q = fact.quantize(_CENTS)
    if bucket["economy"] is None:
        bucket["economy"] = Decimal("0")
    bucket["economy"] += (base_q - fact_q)
    bucket["planned_sum"] += base_q
    bucket["fact_sum"] += fact_q
    bucket["items_considered"] += rows_count


async def purchase_economy_bulk(db: AsyncSession, purchase_ids) -> dict[int, dict]:
    """{purchase_id: {"economy": Decimal|None, "planned_sum", "fact_sum",
    "items_considered", "unmeasured_total", "unmeasured_by_reason"}} —
    пакетная (без N+1) экономия закупок, формула — см. докстринг модуля.
    economy=None, когда у закупки нет НИ ОДНОЙ измеримой строки/группы —
    нечего сравнивать (НЕ 0)."""
    purchase_ids = list(purchase_ids)
    result = {pid: _empty_bucket() for pid in purchase_ids}
    if not purchase_ids:
        return result

    rows = (await db.execute(
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.id.in_(purchase_ids))
    )).all()
    if not rows:
        return result

    committed_rows = [r for r in rows if is_purchase_committed(r.Purchase)]
    if not committed_rows:
        return result

    fact_by_item = await fact_amounts_for_rows(db, committed_rows)

    # Шаг 0 (см. докстринг): строки без факта — 'no_fact', отсеиваются
    # ПЕРЕД классификацией по привязке (нечего сравнивать).
    measured_rows: list[tuple] = []  # (pi, p, fact: Decimal)
    for r in committed_rows:
        pi, p = r.PurchaseItem, r.Purchase
        fact = fact_by_item.get(pi.id)
        if fact is None:
            _mark_unmeasured(result[p.id], "no_fact")
            continue
        measured_rows.append((pi, p, fact))

    if not measured_rows:
        return result

    fpi_ids = {pi.feo_planned_item_id for pi, _p, _f in measured_rows if pi.feo_planned_item_id is not None}
    fpi_map: dict[int, FeoPlannedItem] = {}
    if fpi_ids:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(fpi_ids))
        )).scalars().all()
        fpi_map = {f.id: f for f in fpi_rows}

    # Составные позиции группируются по (purchase_id, feo_planned_item_id) —
    # экономия считается НА УРОВНЕ ГРУППЫ (закупка, позиция), не по строкам.
    composite_groups: dict[tuple, dict] = {}
    for pi, p, fact in measured_rows:
        bucket = result[p.id]
        fpi = fpi_map.get(pi.feo_planned_item_id) if pi.feo_planned_item_id is not None else None
        if fpi is None or not fpi.is_active:
            # Шаг 3: нет привязки ЛИБО привязка невалидна (удалена/деактивирована) —
            # равнозначно отсутствию (тот же приём, что committed_amounts.py).
            _mark_unmeasured(bucket, "unlinked")
            continue
        payment_mode = fpi.payment_mode or "one_time"
        if payment_mode == "monthly":
            # Шаг 2: ежемесячные резервируются целиком, экономией не меряются.
            _mark_unmeasured(bucket, "monthly")
            continue
        if fpi.is_composite:
            key = (p.id, fpi.id)
            g = composite_groups.setdefault(key, {"purchase_id": p.id, "fpi": fpi, "rows": []})
            g["rows"].append((pi, fact))
            continue

        # Шаг 1а: строка, не составная позиция.
        qty = Decimal(str(pi.quantity or 0))
        if fpi.unit_price is not None:
            base = Decimal(str(fpi.unit_price)) * qty
        elif fpi.quantity is not None and Decimal(str(fpi.quantity)) > 0 and fpi.amount is not None:
            # ДОЛЯ плана позиции по количеству строки — НЕ «цена за единицу»
            # (см. докстринг модуля, запрет на подмену unit_price делением).
            base = Decimal(str(fpi.amount)) * qty / Decimal(str(fpi.quantity))
        else:
            _mark_unmeasured(bucket, "no_plan_price")
            continue
        _apply_measured(bucket, base, fact, rows_count=1)

    # Шаг 1б: составные группы — MAX(quantity) строк группы, Σ фактов группы.
    for (pid, _fpid), g in composite_groups.items():
        bucket = result[pid]
        fpi: FeoPlannedItem = g["fpi"]
        rows_ = g["rows"]
        if fpi.quantity is None or Decimal(str(fpi.quantity)) <= 0 or fpi.amount is None:
            _mark_unmeasured(bucket, "no_plan_price", count=len(rows_))
            continue
        max_qty = max(Decimal(str(pi.quantity or 0)) for pi, _f in rows_)
        fact_sum = sum((f for _pi, f in rows_), Decimal("0"))
        base = Decimal(str(fpi.amount)) * max_qty / Decimal(str(fpi.quantity))
        _apply_measured(bucket, base, fact_sum, rows_count=len(rows_))

    return result


async def purchase_economy_one(db: AsyncSession, purchase_id: int) -> Optional[Decimal]:
    """Экономия ОДНОЙ закупки — тонкая обёртка над purchase_economy_bulk
    (ПРАВИЛО №6, вторая формула для одиночного случая не заводится)."""
    res = await purchase_economy_bulk(db, [purchase_id])
    return res.get(purchase_id, _empty_bucket())["economy"]


def _method_key(purchase_method: Optional[str], competitive_form: Optional[str]) -> tuple:
    """Ключ группировки агрегата по способу закупки (PLAN.md шаг 4): ед.
    поставщик ('single'), конкурентная ('competitive' — дробится ещё по
    competitive_form: запрос цен/аукцион/конкурс), авансовый ('advance'),
    НЕ заполнено (None/'') — отдельная корзина 'unspecified', не исключается
    из агрегата молча."""
    method = purchase_method or "unspecified"
    if method == "competitive":
        return (method, competitive_form or "unspecified")
    return (method, None)


def _sum_unmeasured(buckets) -> dict:
    total = {r: 0 for r in _UNMEASURED_REASONS}
    for b in buckets:
        for r in _UNMEASURED_REASONS:
            total[r] += b["unmeasured_by_reason"][r]
    return total


async def purchase_economy_by_subsidy(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {"economy_total": Decimal, "economy_no_planned_price_items": int,
    "economy_unmeasured_by_reason": {...}}} — контракт API (PLAN.md шаг 1-2,
    п. A — GET /api/dashboard/charts subsidy_stats и KPI вкладки «Субсидии»):
    Σ economy (purchase_economy_bulk, ЕДИНАЯ точка выше в этом модуле) по
    ВСЕМ закупкам субсидии, не только законтрактованным — purchase_economy_bulk
    сама отфильтрует незаконтрактованные (economy=None для них, в сумму не
    входят)."""
    # ИСПРАВЛЕНО 02.10.2026 (приёмка по скриншотам ФАДМ_2026 — 0 ₽ читался как
    # «экономии нет», хотя НИ ОДНА позиция не измерена): economy_total=None,
    # пока у субсидии нет НИ ОДНОЙ измеренной закупки — Decimal("0") заводится
    # лениво, только когда встретилась первая измеренная.
    result: dict[int, dict] = {
        sid: {
            "economy_total": None,
            "economy_no_planned_price_items": 0,
            "economy_unmeasured_by_reason": {r: 0 for r in _UNMEASURED_REASONS},
        }
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    p_rows = (await db.execute(
        select(Purchase.id, Purchase.subsidy_id).where(Purchase.subsidy_id.in_(subsidy_ids))
    )).all()
    if not p_rows:
        return result

    sid_by_purchase = {r.id: r.subsidy_id for r in p_rows}
    econ = await purchase_economy_bulk(db, list(sid_by_purchase.keys()))
    for pid, sid in sid_by_purchase.items():
        bucket = econ.get(pid) or _empty_bucket()
        if sid not in result:
            continue
        if bucket["economy"] is not None:
            if result[sid]["economy_total"] is None:
                result[sid]["economy_total"] = Decimal("0")
            result[sid]["economy_total"] += bucket["economy"]
        result[sid]["economy_no_planned_price_items"] += bucket["unmeasured_total"]
        for r in _UNMEASURED_REASONS:
            result[sid]["economy_unmeasured_by_reason"][r] += bucket["unmeasured_by_reason"][r]
    return result


async def purchase_economy_by_method(
    db: AsyncSession,
    subsidy_id: Optional[int] = None,
    year: Optional[int] = None,
    visible_subsidy_ids: Optional[list] = None,
) -> list[dict]:
    """Агрегация экономии по способу закупки (purchase_method/competitive_form,
    PLAN.md шаг 4) — число закупок, Σ план (баз измеренных), Σ факт, Σ
    экономия, неизмеренных строк (любая причина) + разбивка по причине, на
    КАЖДУЮ группу (_method_key). Остановленные закупки (stopped_at IS NOT
    NULL) исключены — та же трактовка, что и везде в feo_plan_fact.py/
    committed_amounts.py.

    Контракт API (PLAN.md шаг 4, п. F — GET /api/dashboard/economy-by-method):
    subsidy_id — фильтр ОДНОЙ субсидии (карточка субсидии); year — фильтр года
    субсидии (дашборд); visible_subsidy_ids — ЗАКРЫВАЮЩИЙ список id субсидий,
    видимых пользователю (тот же набор, что /dashboard/charts — передаётся
    вызывающим роутером, здесь своя формула видимости НЕ заводится, ПРАВИЛО
    №6); None — без ограничения (использовать только из кода с уже применённым
    фильтром видимости выше по стеку)."""
    q = select(Purchase.id, Purchase.purchase_method, Purchase.competitive_form).where(
        Purchase.stopped_at.is_(None)
    )
    if subsidy_id is not None:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if visible_subsidy_ids is not None:
        q = q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
    if year is not None:
        from app.models.subsidy import Subsidy
        q = q.where(Purchase.subsidy_id.in_(select(Subsidy.id).where(Subsidy.year == year)))
    purchases = (await db.execute(q)).all()
    if not purchases:
        return []

    purchase_ids = [p.id for p in purchases]
    econ = await purchase_economy_bulk(db, purchase_ids)

    groups: dict[tuple, dict] = {}
    for p in purchases:
        key = _method_key(p.purchase_method, p.competitive_form)
        g = groups.setdefault(key, {
            "purchase_method": key[0], "competitive_form": key[1],
            "purchase_count": 0, "planned_sum": Decimal("0"), "fact_sum": Decimal("0"),
            "economy_sum": Decimal("0"), "unmeasured_total": 0,
            "unmeasured_by_reason": {r: 0 for r in _UNMEASURED_REASONS},
            # ИСПРАВЛЕНО 02.10.2026 (приёмка — 0 ₽/0 ₽/0 ₽ при 34/13/4/16
            # закупках читалось как «ничего не измерено = экономия нулевая»):
            # True, как только хоть одна закупка группы дала bucket["economy"]
            # not None — иначе план/факт/экономия группы уходят в API как null
            # (см. _format_method_group), а не ложный 0.
            "any_measured": False,
        })
        g["purchase_count"] += 1
        bucket = econ.get(p.id) or _empty_bucket()
        g["planned_sum"] += bucket["planned_sum"]
        g["fact_sum"] += bucket["fact_sum"]
        if bucket["economy"] is not None:
            g["economy_sum"] += bucket["economy"]
            g["any_measured"] = True
        g["unmeasured_total"] += bucket["unmeasured_total"]
        for r in _UNMEASURED_REASONS:
            g["unmeasured_by_reason"][r] += bucket["unmeasured_by_reason"][r]

    # Контракт API п. F (ИСПРАВЛЕНО 02.10.2026 — дубль строки, приёмка
    # владельца: при единственной форме конкурентной закупки выводились ОБЕ
    # «Конкурентная: <форма>» и «Конкурентная» с теми же числами). Правило:
    # подстроки по competitive_form показываются, ТОЛЬКО если у конкурентных
    # закупок ≥ 2 разных значений формы — тогда ДОБАВЛЯЕТСЯ итоговая строка
    # «Конкурентная — всего» (is_total=True). При ОДНОЙ форме — ни одной
    # отдельной строки-итога не заводим, оставляем единственную существующую
    # подстроку как есть (is_total=False), кроме формы 'unspecified' — её
    # ярлык меняется с «Конкурентная: форма не указана» на просто
    # «Конкурентная» (не «подформа», раз другой формы и не было).
    competitive_keys = [key for key in groups if key[0] == "competitive"]
    distinct_forms = {key[1] for key in competitive_keys}
    if len(distinct_forms) >= 2:
        competitive_total = {
            "purchase_method": "competitive", "competitive_form": None,
            "purchase_count": 0, "planned_sum": Decimal("0"), "fact_sum": Decimal("0"),
            "economy_sum": Decimal("0"), "unmeasured_total": 0,
            "unmeasured_by_reason": {r: 0 for r in _UNMEASURED_REASONS},
            "any_measured": False,
            "is_total": True, "label_override": "Конкурентная — всего",
        }
        for key in competitive_keys:
            g = groups[key]
            competitive_total["purchase_count"] += g["purchase_count"]
            competitive_total["planned_sum"] += g["planned_sum"]
            competitive_total["fact_sum"] += g["fact_sum"]
            competitive_total["economy_sum"] += g["economy_sum"]
            competitive_total["unmeasured_total"] += g["unmeasured_total"]
            competitive_total["any_measured"] = competitive_total["any_measured"] or g["any_measured"]
            for r in _UNMEASURED_REASONS:
                competitive_total["unmeasured_by_reason"][r] += g["unmeasured_by_reason"][r]
        groups[("competitive", None)] = competitive_total
    elif len(distinct_forms) == 1:
        only_form = next(iter(distinct_forms))
        only_key = ("competitive", only_form)
        if only_form == "unspecified":
            groups[only_key]["label_override"] = "Конкурентная"
    # len(distinct_forms) == 0 — нет конкурентных закупок вовсе, ничего не делаем.

    return [_format_method_group(g) for g in groups.values()]


_METHOD_LABELS = {
    ("single", None): "Единственный поставщик",
    ("competitive", None): "Конкурентная",
    ("competitive", "price_request"): "Конкурентная: запрос цен",
    ("competitive", "auction"): "Конкурентная: аукцион",
    ("competitive", "tender"): "Конкурентная: конкурс",
    ("competitive", "unspecified"): "Конкурентная: форма не указана",
    ("advance", None): "Авансовый отчёт",
    ("unspecified", None): "Способ не указан",
}


def _format_method_group(g: dict) -> dict:
    """Переводит внутренний накопитель группы в форму контракта API (п. F):
    {method, competitive_form, label, purchases, plan, fact, economy,
    economy_pct, no_planned_price_items, unmeasured_by_reason, is_total}.
    is_total=True — строка-итог «Конкурентная — всего» (только когда у
    конкурентных закупок ≥ 2 разных значений формы, см. вызывающий код) —
    фронт выделяет такую строку жирным (EconomyByMethodTable.vue)."""
    method = g["purchase_method"]
    comp_form = g["competitive_form"]
    label = g.get("label_override") or _METHOD_LABELS.get((method, comp_form)) or _METHOD_LABELS.get((method, None)) or method
    # ИСПРАВЛЕНО 02.10.2026 (приёмка — ФАДМ_2026: 39/39 позиций не привязаны к
    # плановой, группа показывала План 0 ₽/Договор 0 ₽/Экономия 0 ₽ при 34
    # закупках — читалось как «экономии нет», хотя не измерено ни одной):
    # plan/fact/economy/economy_pct = null, пока ни одна закупка группы не
    # дала economy не-None (any_measured) — purchases/no_planned_price_items/
    # unmeasured_by_reason остаются числами как есть.
    any_measured = bool(g.get("any_measured", False))
    plan = g["planned_sum"]
    economy = g["economy_sum"]
    economy_pct = float((economy / plan) * 100) if (any_measured and plan > 0) else None
    return {
        "method": method,
        "competitive_form": comp_form,
        "label": label,
        "purchases": g["purchase_count"],
        "plan": float(plan) if any_measured else None,
        "fact": float(g["fact_sum"]) if any_measured else None,
        "economy": float(economy) if any_measured else None,
        "economy_pct": economy_pct,
        "no_planned_price_items": g["unmeasured_total"],
        "unmeasured_by_reason": dict(g["unmeasured_by_reason"]),
        "is_total": bool(g.get("is_total", False)),
    }
