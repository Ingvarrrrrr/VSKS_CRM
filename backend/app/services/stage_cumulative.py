"""stage_cumulative.py — решение владельца 05.10.2026: карточки этапов
«Заключён договор / Заказано / Поставлено / Оплачено» считаются НАКОПИТЕЛЬНО
для ВСЕХ закупок: «Заключён договор» ⊇ «Заказано» ⊇ «Поставлено» ⊇ «Оплачено»
(минус оплаченные авансом и ещё не поставленные) — ПО ПОСТРОЕНИЮ, не
постфактум-проверкой (см. tests/test_stage_cumulative_contractless.py::
test_contracted_ge_ordered_ge_delivered_invariant).

«Заказано»/«Поставлено»/«Оплачено» уже были накопительными в
dashboard_charts.py (widget.ordered включает delivered+paid, widget.delivered
включает paid, paid_declared/paid_confirmed — app/services/subsidy_paid_
breakdown.py, по отметке/выписке независимо от статуса) — не трогаем,
ПРАВИЛО №6, не второй расчёт.

Разрыв (владелец, правка 05.10.2026 после находки «на стенде Заключён
19,05М < Заказано 22,2М») — «Заключён договор» (widget.contracts/
contracts_map в dashboard_charts.py) строился ТОЛЬКО по записям Contract со
status='active' (contract_single_q/contract_fc_q), ДВЕ независимые причины
разрыва на практике (проверено живыми данными стенда, субсидия «ХО»,
id=75):

  1. committed-закупка (committed_status_predicate) НЕ подкреплена активной
     записью Contract нужного типа вовсе — contract_id IS NULL, контракт
     удалён/неактивен, либо contract_type не один из трёх распознаваемых
     (single/framework_with_amount/framework_cumulative). Функция
     committed_uncounted_by_subsidy() ниже — добавочное слагаемое, Σ
     effective_amount_expr() по таким закупкам.

  2. РЕАЛЬНАЯ причина основного разрыва на «ХО»: Contract.contract_type=
     'single', status='active' (контракт СУЩЕСТВУЕТ и формально учтён
     cs_rows), но Contract.max_amount IS NULL (поле не заполнено при
     создании) — cs_rows прежде складывал `Contract.max_amount` буквально,
     SQL SUM игнорирует NULL-строки, поэтому ВСЕ 16 single-договоров «ХО» (их
     закупки на 4 777 721,20 ₽ суммарно) давали 0 в «Заключено договоров»,
     хотя эти же закупки честно входили в «Заказано»/«Поставлено»/
     «Оплачено» по статусу. single_contract_topup_by_subsidy() ниже чинит
     это ТЕМ ЖЕ приёмом, что уже применён к framework_with_amount в
     dashboard_charts.py (`greatest(max_amount, Σ реальных закупок)`,
     _fwa_children_sum) — единственное отличие: здесь считается ДОБАВКА
     (актуальная Σ минус уже учтённый max_amount, не ниже 0), а не замена
     формулы cs_rows целиком (Правило №6 — не переписываем cs_rows второй
     раз, только досчитываем недостающее тем же принципом «максимум из
     двух оценок»).

committed_uncounted_by_subsidy() и single_contract_topup_by_subsidy() вместе
гарантируют «Заключён договор» ⊇ Σ по всем committed-закупкам ПО
ПОСТРОЕНИЮ: либо закупка уже учтена активным Contract известного типа с
реальным max_amount/Σ заказов (cs_rows/cfc_rows), либо она попадает в одну
из этих двух добавок. Двойного счёта нет: committed_uncounted_expr()
намеренно исключает контракты, УЖЕ учтённые (active + известный тип), а
топ-ап считает РАЗНИЦУ (actual − recorded), не Σ заново.

Сумма — effective_amount_expr() (та же величина, что остальные корзины
widgets в dashboard_charts.py), НЕ purchase_item_fact_amount (committed_
amounts.py — это отдельная метрика «деньги субсидии», здесь — показатель
КПИ-карточки, Правило №6 не требует единой суммы между разными по смыслу
метриками, только единого НАБОРА СТАТУСОВ, который и переиспользован).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_ as sqland, case, func, literal, not_ as sqlnot, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.committed_amounts import (
    FRAMEWORK_COMMITTED_STATUSES,
    SINGLE_COMMITTED_STATUSES,
    committed_status_predicate,
)
from app.services.plan_need_level import NEED_LEVEL_NICE_TO_HAVE
from app.services.purchase_amounts import effective_amount_expr

# Контракты этих трёх типов (и ТОЛЬКО этих, СО status='active') уже учтены
# dashboard_charts.py::contract_single_q/contract_fc_q — единственный список,
# больше нигде не копируется (Правило №6, эта константа — предикат «уже
# посчитан где-то ещё», а не самостоятельный бизнес-смысл).
_COUNTED_ELSEWHERE_CONTRACT_TYPES = ("single", "framework_with_amount", "framework_cumulative")


def committed_uncounted_expr():
    """SQL boolean: закупка committed (committed_status_predicate), но её
    Contract НЕ покрыт существующими запросами dashboard_charts.py (причина
    1 докстринга модуля). ТРЕБУЕТ outerjoin(Contract, Purchase.contract_id ==
    Contract.id) в вызывающем запросе."""
    return sqland(
        committed_status_predicate(Purchase),
        sqlor(
            Purchase.contract_id.is_(None),
            Contract.id.is_(None),  # contract_id указывает на несуществующую запись (осиротевший FK)
            Contract.status != "active",
            sqlnot(Contract.contract_type.in_(_COUNTED_ELSEWHERE_CONTRACT_TYPES)),
        ),
    )


async def committed_uncounted_by_subsidy(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, dict]:
    """{subsidy_id: {"amount": float, "count": int}} — причина 1, см.
    докстринг модуля. `subsidy_ids` — список субсидий УЖЕ отфильтрованных по
    видимости/org/sandbox вызывающим кодом (Правило №6 — не второй фильтр
    видимости)."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    stmt = (
        select(
            Purchase.subsidy_id,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
            func.count(Purchase.id).label("cnt"),
        )
        .outerjoin(Contract, Purchase.contract_id == Contract.id)
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(Purchase.stopped_at.is_(None))
        .where(committed_uncounted_expr())
        .group_by(Purchase.subsidy_id)
    )
    rows = (await db.execute(stmt)).all()
    for r in rows:
        result[r.subsidy_id] = {"amount": float(r.amt), "count": int(r.cnt)}
    return result


async def single_contract_topup_by_subsidy(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, dict]:
    """{subsidy_id: {"amount": float, "count": int}} — причина 2, см.
    докстринг модуля: активные Contract(contract_type='single') чья реальная
    Σ committed-закупок (committed_status_predicate, effective_amount_expr)
    ПРЕВЫШАЕТ учтённый cs_rows Contract.max_amount (в т.ч. max_amount IS
    NULL → учтено как 0, SQL SUM молча теряет такие строки целиком — именно
    это произошло на «ХО», 16 договоров, 4 777 721,20 ₽). Добавка = разница
    (actual − recorded), НЕ дублирует то, что cs_rows уже посчитал —
    `greatest()`-приём, идентичный framework_with_amount (_fwa_children_sum,
    dashboard_charts.py), применённый теперь и к single."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    stmt = (
        select(
            Contract.subsidy_id,
            Contract.id,
            Contract.max_amount,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("actual"),
        )
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.subsidy_id.in_(subsidy_ids))
        .where(Contract.status == "active")
        .where(Contract.contract_type == "single")
        .where(committed_status_predicate(Purchase))
        .where(Purchase.stopped_at.is_(None))
        .group_by(Contract.subsidy_id, Contract.id, Contract.max_amount)
    )
    rows = (await db.execute(stmt)).all()
    for r in rows:
        actual = float(r.actual or 0)
        recorded = float(r.max_amount) if r.max_amount is not None else 0.0
        topup = actual - recorded
        if topup > 0.005:
            d = result.setdefault(r.subsidy_id, {"amount": 0.0, "count": 0})
            d["amount"] += topup
            d["count"] += 1
    return result


async def contracted_rows_by_category(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[tuple[int, Optional[int]], float]:
    """{(subsidy_id, feo_category_id|None): amount} — ТЕ ЖЕ четыре слагаемых,
    что contracted_total_by_subsidy() (см. её докстринг), но разрезанные по
    категории ФЭО вместо схлопывания в один subsidy_id. ЕДИНЫЙ источник
    (ПРАВИЛО №6, план .planning/quick/2026-10-06-feo-row-sums/PLAN.md, шаг 2):
    contracted_total_by_subsidy() ниже строит СВОЮ "amount" как Σ ЭТОГО же
    словаря по subsidy_id — не вторая копия SQL, категория — просто более
    мелкий разрез тех же строк.

    Категория закупки — Purchase.feo_category_id (та же гранулярность, что и
    у contracted_total_by_subsidy/dashboard_contracts_drill, которые не делают
    item-level разрез — «законтрактовано» по определению относится к закупке/
    заказу целиком, не к отдельным позициям внутри неё):
      1. single — Σ effective_amount_expr() комитированных закупок, привязанных
         к активному Contract(type='single'), ПО КАТЕГОРИИ ПОКУПКИ; на контракт
         накладывается тот же "greatest(recorded, actual)" приём, что и в
         cs_q + single_contract_topup_by_subsidy (см. их докстринги) — recorded
         (Contract.max_amount) распределяется по категориям ПРОПОРЦИОНАЛЬНО
         их доле в actual (если actual > 0), иначе — поровну между категориями,
         в которых вообще нашлась связанная закупка (на практике всегда одна).
      2. framework_with_amount — ЗАКАЗЫ (ordered+reserved, т.е. объединение
         FRAMEWORK_COMMITTED_STATUSES и reserved_child_predicate) идут в
         СВОИ категории; остаток max(0, лимит − Σзаказов) — в категорию
         ГОЛОВЫ (parent_purchase_id IS NULL), либо, если у головы нет
         категории, в категорию заказов (если она одна), иначе «без
         категории» — пересмотр В3 владельцем (PLAN.md, правка 🔵
         07.10.2026): прод-находка — голова часто в «Не определена», заказы
         в реальной статье; старое правило прятало деньги субсидии в «Не
         определена».
      3. framework_cumulative — Σ effective_amount_expr() заказов-детей
         (ordered+reserved, та же формула sqlor(FRAMEWORK_COMMITTED_STATUSES,
         reserved_child_predicate()), что у framework_with_amount выше —
         владелец, правка 🟣 07.10.2026, закрытие «экзотики»: будущий заказ
         накопительного, договор на партию уже заключён, статус 'contracted'
         — тоже законтрактованные деньги), each ПО СВОЕЙ категории (не головы).
      4. committed-закупки без активного контракта известного типа
         (committed_uncounted_expr()) — по категории самой закупки.

    `subsidy_ids` — уже отфильтрован по видимости вызывающим кодом (тот же
    контракт, что у contracted_total_by_subsidy)."""
    result: dict[tuple[int, Optional[int]], float] = {}
    if not subsidy_ids:
        return result

    def _add(sid: Optional[int], cat_id: Optional[int], amt: float) -> None:
        if sid is None or not amt:
            return
        key = (sid, cat_id)
        result[key] = result.get(key, 0.0) + amt

    # ── 1. single — per (contract, category) actual, затем greatest() по контракту ──
    # (exists-проверка _contracted_purchase_exists из contracted_total_by_subsidy
    # здесь НЕ нужна — JOIN на Purchase с тем же committed-статусным условием
    # уже гарантирует: контракт без ни одной committed-закупки просто не даёт
    # строк. Отдельный EXISTS-подзапрос по тому же Purchase без alias вызывал
    # бы неоднозначную ссылку на таблицу, уже участвующую в FROM через JOIN.)
    single_cat_stmt = (
        select(
            Contract.id.label("contract_id"),
            Contract.subsidy_id,
            Contract.max_amount,
            Purchase.feo_category_id.label("cat_id"),
            func.coalesce(func.sum(effective_amount_expr()), 0).label("actual"),
        )
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "single")
        .where(Contract.subsidy_id.in_(subsidy_ids))
        .where(Purchase.status.in_(list(SINGLE_COMMITTED_STATUSES)))
        .group_by(Contract.id, Contract.subsidy_id, Contract.max_amount, Purchase.feo_category_id)
    )
    single_rows = (await db.execute(single_cat_stmt)).all()
    by_contract: dict[int, list] = {}
    for r in single_rows:
        by_contract.setdefault(r.contract_id, []).append(r)
    for contract_id, rows in by_contract.items():
        sid = rows[0].subsidy_id
        recorded = float(rows[0].max_amount) if rows[0].max_amount is not None else 0.0
        total_actual = sum(float(r.actual or 0) for r in rows)
        final_total = max(recorded, total_actual)
        if final_total <= 0:
            continue
        if total_actual > 0:
            for r in rows:
                share = final_total * (float(r.actual or 0) / total_actual)
                _add(sid, r.cat_id, share)
        else:
            # Ни одна связанная закупка не дала ненулевую сумму, но лимит
            # договора задан (recorded > 0) — распределяем поровну между
            # найденными категориями (на практике их одна).
            n = len(rows)
            for r in rows:
                _add(sid, r.cat_id, final_total / n)

    # ── 2. framework_with_amount (владелец, правка 🔵 07.10.2026 — см. PLAN.md,
    # пересмотр В3) ──────────────────────────────────────────────────────────
    # Прод-находка, приведшая к пересмотру: у 3 из 4 framework_with_amount
    # договоров голова лежит в «Не определена», а её заказы — в реальной
    # статье («Техническое оснащение»); у 21 framework_cumulative голова
    # вовсе без категории. Старое правило «вся сумма в категорию ГОЛОВЫ»
    # прятало реальные деньги субсидии в «Не определена» вместо статьи, где
    # они физически потрачены — владелец это отменил.
    #
    # Новое правило: заказы (И «из них заказано» FRAMEWORK_COMMITTED_STATUSES,
    # И «зарезервировано» reserved_child_predicate — ОБЕ группы, иначе
    # категория заказа показывала бы contracted МЕНЬШЕ ordered+reserved, что
    # и было найденной владельцем ошибкой) несут «законтрактовано» СВОЕЙ
    # категории целиком; остаток лимита max(0, лимит − Σ(ordered+reserved))
    # идёт в категорию ГОЛОВЫ — а если у головы нет категории (или головы нет
    # вовсе), остаток падает в категорию заказов, ЕСЛИ она у всех заказов этого
    # контракта одна, иначе — в «без категории» (None).
    fwa_contracts_stmt = (
        select(Contract.id.label("contract_id"), Contract.subsidy_id, Contract.max_amount)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_with_amount")
        .where(Contract.subsidy_id.in_(subsidy_ids))
    )
    fwa_contracts = (await db.execute(fwa_contracts_stmt)).all()

    fwa_head_cat_stmt = (
        select(Contract.id.label("contract_id"), Purchase.feo_category_id.label("head_cat_id"))
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_with_amount")
        .where(Contract.subsidy_id.in_(subsidy_ids))
        # Голова — parent_purchase_id IS NULL (тот же критерий, что у cs_q/
        # _fwa_children_sum в contracted_total_by_subsidy), БЕЗ проверки
        # Purchase.purchase_contract_type (см. test_dashboard_contracts_drill.py,
        # где этот столбец у фикстур вовсе не заполнен).
        .where(Purchase.parent_purchase_id.is_(None))
    )
    head_cat_by_contract: dict[int, Optional[int]] = {
        r.contract_id: r.head_cat_id for r in (await db.execute(fwa_head_cat_stmt)).all()
    }

    fwa_children_cat_stmt = (
        select(
            Contract.id.label("contract_id"),
            Purchase.feo_category_id.label("cat_id"),
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_with_amount")
        .where(Contract.subsidy_id.in_(subsidy_ids))
        .where(Purchase.parent_purchase_id.isnot(None))
        .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        .group_by(Contract.id, Purchase.feo_category_id)
    )
    fwa_children_by_contract: dict[int, list] = {}
    for r in (await db.execute(fwa_children_cat_stmt)).all():
        fwa_children_by_contract.setdefault(r.contract_id, []).append(r)

    for c in fwa_contracts:
        kids = fwa_children_by_contract.get(c.contract_id, [])
        total_children = 0.0
        for k in kids:
            amt = float(k.amt or 0)
            total_children += amt
            _add(c.subsidy_id, k.cat_id, amt)
        recorded = float(c.max_amount) if c.max_amount is not None else 0.0
        remainder = max(0.0, recorded - total_children)
        if remainder <= 0:
            continue
        head_cat = head_cat_by_contract.get(c.contract_id)
        if head_cat is None:
            kid_cats = {k.cat_id for k in kids}
            head_cat = next(iter(kid_cats)) if len(kid_cats) == 1 else None
        _add(c.subsidy_id, head_cat, remainder)

    # ── 3. framework_cumulative — Σ заказов-детей (ordered+reserved), каждый в
    # СВОЮ категорию (владелец, правка 🟣 07.10.2026 — закрытие «экзотики»,
    # найденной предыдущим тестом: заказ накопительного в статусе 'contracted'
    # — договор на партию уже заключён, заказ как отдельная закупка ещё не
    # оформлен — это ТОЖЕ законтрактованные деньги, не только
    # FRAMEWORK_COMMITTED_STATUSES. ТА ЖЕ формула, что у framework_with_amount
    # выше — sqlor(FRAMEWORK_COMMITTED_STATUSES, reserved_child_predicate()),
    # импорт предиката, не копия). Теперь contracted ≥ ordered+reserved в
    # КАЖДОЙ категории без исключений (кроме экзотики заказа вне committed-
    # статусов, которой на проде не найдено).
    cfc_cat_stmt = (
        select(
            Purchase.subsidy_id,
            Purchase.feo_category_id.label("cat_id"),
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .join(Contract, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        .group_by(Purchase.subsidy_id, Purchase.feo_category_id)
    )
    for r in (await db.execute(cfc_cat_stmt)).all():
        _add(r.subsidy_id, r.cat_id, float(r.amt or 0))

    # ── 4. committed-закупки без активного контракта известного типа ──────────
    uncounted_cat_stmt = (
        select(
            Purchase.subsidy_id,
            Purchase.feo_category_id.label("cat_id"),
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .outerjoin(Contract, Purchase.contract_id == Contract.id)
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(Purchase.stopped_at.is_(None))
        .where(committed_uncounted_expr())
        .group_by(Purchase.subsidy_id, Purchase.feo_category_id)
    )
    for r in (await db.execute(uncounted_cat_stmt)).all():
        _add(r.subsidy_id, r.cat_id, float(r.amt or 0))

    return result


def reserved_child_predicate():
    """«Зарезервировано на ежемесячные платежи» (PLAN.md 2026-10-06, В1🟢):
    заказ рамочного договора (parent_purchase_id IS NOT NULL — ЛЮБОГО из двух
    типов, не только framework_cumulative) в статусе 'contracted' — договор на
    эту партию уже заключён, сам заказ как отдельная закупка ещё не оформлен.
    SQL-эквивалент условия contracted_not_ordered_by_subsidy() ниже, вынесен
    отдельно (ПРАВИЛО №6), чтобы feo_row_contracted.py не копировал тот же
    предикат построчно для разреза по категории ФЭО."""
    return sqland(Purchase.status == "contracted", Purchase.parent_purchase_id.isnot(None))


async def contracted_total_by_subsidy(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, dict]:
    """{subsidy_id: {"amount": float, "count": int}} — ЕДИНЫЙ источник
    «Заключено договоров» (ПРАВИЛО №6). Склеивает ВСЕ четыре слагаемых,
    которые раньше жили только inline в dashboard_charts.py::dashboard_charts
    (карточка «Заключено договоров») и были недоступны вкладке «Договоры»
    (frontend/src/composables/contracts/useContractsFilters.ts::filteredSum
    суммировала голый Contract.max_amount — без greatest()/топ-апов/
    framework_cumulative, отсюда расхождение 9 315 271 vs 12 983 362 на
    ФАДМ 2026_2, прод id=88, найдено 2026-10-06):
      1. cs_rows — single (только если есть привязанная committed-закупка) +
         framework_with_amount (greatest(лимит, Σ заказов-детей)).
      2. cfc_rows — framework_cumulative: Σ committed-закупок, привязанных к
         договору.
      3. committed_uncounted_by_subsidy() — committed-закупки без активного
         контракта известного типа (причина 1, см. докстринг модуля).
      4. single_contract_topup_by_subsidy() — топ-ап single-договоров с
         заниженным/NULL max_amount (причина 2).

    `subsidy_ids` — список субсидий, уже отфильтрованных по видимости/org/
    sandbox вызывающим кодом (эта функция сама не фильтрует видимость).
    Вызывается И из dashboard_charts.py (карточка «Заключено договоров»), И
    из routers/contracts.py (итог вкладки «Договоры» при фильтре по одной
    субсидии) — один расчёт, не два (Правило №6)."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    _contracted_purchase_exists = (
        select(literal(1))
        .where(Purchase.contract_id == Contract.id)
        .where(Purchase.status.in_(list(SINGLE_COMMITTED_STATUSES)))
    )
    _fwa_children_sum = (
        select(func.coalesce(func.sum(effective_amount_expr()), 0))
        .where(Purchase.contract_id == Contract.id)
        .where(Purchase.parent_purchase_id.isnot(None))
        .where(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)))
        .correlate(Contract)
        .scalar_subquery()
    )
    cs_q = (
        select(
            Contract.subsidy_id,
            func.coalesce(func.sum(
                case(
                    (
                        Contract.contract_type == "framework_with_amount",
                        func.greatest(func.coalesce(Contract.max_amount, 0), _fwa_children_sum),
                    ),
                    else_=Contract.max_amount,
                )
            ), 0).label("amt"),
            func.count(Contract.id).label("cnt"),
        )
        .where(Contract.status == "active")
        .where(Contract.subsidy_id.in_(subsidy_ids))
        .where(
            sqlor(
                sqland(Contract.contract_type == "single", _contracted_purchase_exists.exists()),
                Contract.contract_type == "framework_with_amount",
            )
        )
        .group_by(Contract.subsidy_id)
    )
    cs_rows = (await db.execute(cs_q)).all()

    cfc_q = (
        select(
            Purchase.subsidy_id,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
            func.count(func.distinct(Purchase.contract_id)).label("cnt"),
        )
        .join(Contract, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)))
        .group_by(Purchase.subsidy_id)
    )
    cfc_rows = (await db.execute(cfc_q)).all()

    for r in cs_rows:
        d = result.setdefault(r.subsidy_id, {"amount": 0.0, "count": 0})
        d["amount"] += float(r.amt)
        d["count"] += int(r.cnt)
    for r in cfc_rows:
        d = result.setdefault(r.subsidy_id, {"amount": 0.0, "count": 0})
        d["amount"] += float(r.amt)
        d["count"] += int(r.cnt)

    uncounted_map = await committed_uncounted_by_subsidy(db, subsidy_ids=subsidy_ids)
    for sid, d0 in uncounted_map.items():
        d = result.setdefault(sid, {"amount": 0.0, "count": 0})
        d["amount"] += d0["amount"]
        d["count"] += d0["count"]

    topup_map = await single_contract_topup_by_subsidy(db, subsidy_ids=subsidy_ids)
    for sid, d0 in topup_map.items():
        d = result.setdefault(sid, {"amount": 0.0, "count": 0})
        d["amount"] += d0["amount"]
        d["count"] += d0["count"]

    # ПРАВИЛО №6 (план 2026-10-06-feo-row-sums, шаг 2): "amount" — ТЕПЕРЬ Σ по
    # категориям ФЭО того же единого разреза contracted_rows_by_category() (не
    # пересчитывается второй формулой — выше это ровно те же 4 слагаемых, но
    # схлопнутые по subsidy_id; здесь берём их же построчный источник и просто
    # суммируем по субсидии). "count" остаётся посчитан как раньше (выше) —
    # разрез по категориям не обязан сохранять точную семантику "число
    # договоров", она тут не используется ни одним инвариантом.
    cat_rows = await contracted_rows_by_category(db, subsidy_ids=subsidy_ids)
    amount_by_subsidy: dict[int, float] = {}
    for (sid, _cat_id), amt in cat_rows.items():
        amount_by_subsidy[sid] = amount_by_subsidy.get(sid, 0.0) + amt
    for sid, amt in amount_by_subsidy.items():
        d = result.setdefault(sid, {"amount": 0.0, "count": 0})
        d["amount"] = amt
    for sid in list(result.keys()):
        if sid not in amount_by_subsidy:
            result[sid]["amount"] = 0.0

    return result


async def contracted_not_ordered_by_subsidy(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, float]:
    """{subsidy_id: amount} — «Договоры без заказа» (владелец/координатор,
    06.10.2026, план sleepy-fluttering-walrus.md п.1, задача «карточка
    "Можно перераспределить"»): дочерние заказы рамочных договоров
    (Purchase.parent_purchase_id IS NOT NULL) в статусе 'contracted' (договор
    на эту партию уже заключён, сам заказ как отдельная закупка ещё не
    оформлен) — ровно та часть dashboard_charts.py::w_ordered (который
    складывает status IN ('contracted','ordered')), которая НЕ входит в
    total_ordered (только ordered/delivered/paid) — т.е. разрыв «Ведётся
    работа» − «Заказано».

    ИСПРАВЛЕНО (находка координатора 06.10.2026): раньше карточка «Можно
    перераспределить» искала эту сумму через is_monthly_payment-график
    платежей (app.services.dashboard_monthly_accrual.compute_monthly_future_map)
    — на проде id=89 все такие заказы is_monthly_payment=False, разрыв был
    найден нулевым. Реальный источник разницы — именно эти «договор заключён,
    заказ ещё не создан» дочерние закупки. Сумма — effective_amount_expr()
    (ПРАВИЛО №6, та же величина, что и w_ordered/committed в этом модуле, не
    вторая формула «суммы закупки»)."""
    result: dict[int, float] = {sid: 0.0 for sid in (subsidy_ids or [])}
    if subsidy_ids is not None and not subsidy_ids:
        return result

    stmt = (
        select(Purchase.subsidy_id, func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"))
        .where(reserved_child_predicate())
        .where(Purchase.stopped_at.is_(None))
    )
    if subsidy_ids is not None:
        stmt = stmt.where(Purchase.subsidy_id.in_(subsidy_ids))
    stmt = stmt.group_by(Purchase.subsidy_id)
    rows = (await db.execute(stmt)).all()
    for r in rows:
        result[r.subsidy_id] = float(r.amt or 0)
    return result


async def contracted_not_ordered_need_level_split(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, dict]:
    """{subsidy_id: {"nice": float, "likely": float}} — ТА ЖЕ сумма
    contracted_not_ordered_by_subsidy выше, разложенная по need_level
    (app.services.plan_need_level) плановых позиций этих заказов, чтобы
    карточка «Можно перераспределить» могла ВЫЧЕСТЬ её из «хотелось бы»/
    «скорее всего» (а не прибавлять поверх — находка координатора про
    двойной счёт). 'nice' — Σ PurchaseItem.total_price позиций, привязанных
    (feo_planned_item_id) к FeoPlannedItem с need_level='nice_to_have'; 'likely'
    довыводится ОСТАТКОМ (total − nice, тот же приём «likely остатком», что и
    not_committed_likely узла дерева, см. feo_plan_tree.py) — не вторая Σ,
    клэмп в [0, total] на случай расхождения между Σ purchase_items.total_price
    и effective_amount_expr() покупки (см. purchase_amounts.py — у 'contracted'
    контракта фолбэк на Σ items ТОЛЬКО если contract_price пуст)."""
    totals = await contracted_not_ordered_by_subsidy(db, subsidy_ids=subsidy_ids)
    result: dict[int, dict] = {sid: {"nice": 0.0, "likely": totals.get(sid, 0.0)} for sid in totals}
    if not totals:
        return result

    nice_stmt = (
        select(Purchase.subsidy_id, func.coalesce(func.sum(PurchaseItem.total_price), 0).label("amt"))
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(FeoPlannedItem, FeoPlannedItem.id == PurchaseItem.feo_planned_item_id)
        .where(Purchase.status == "contracted")
        .where(Purchase.parent_purchase_id.isnot(None))
        .where(Purchase.stopped_at.is_(None))
        .where(Purchase.subsidy_id.in_(list(totals.keys())))
        .where(FeoPlannedItem.need_level == NEED_LEVEL_NICE_TO_HAVE)
        .group_by(Purchase.subsidy_id)
    )
    nice_rows = (await db.execute(nice_stmt)).all()
    for r in nice_rows:
        total = totals.get(r.subsidy_id, 0.0)
        nice = max(0.0, min(float(r.amt or 0), total))
        result[r.subsidy_id] = {"nice": nice, "likely": total - nice}
    return result


async def contracted_not_ordered_split_by_kind(
    db: AsyncSession, subsidy_id: int,
) -> dict[str, dict]:
    """{kind: {"nice": float, "likely": float}} — ТА ЖЕ сумма
    contracted_not_ordered_by_subsidy (см. её докстринг: reserved_child_predicate()
    + stopped_at IS NULL, effective_amount_expr()), разрезанная по виду позиции
    (app.services.item_type_split.ALL_KINDS — goods/services/payroll/unspecified)
    вместо схлопывания в один total — для листа «Сводная» живого экспорта
    плана-графика (app.services.subsidy_summary_by_kind, Задача А плана
    .planning/quick/2026-10-07-plan-graph-export/PLAN.md). ПРАВИЛО №6 — не
    вторая формула: тот же предикат и та же сумма, просто разрезанная по виду
    вместо subsidy_id.

    "nice" — ТЕМ ЖЕ приёмом, что contracted_not_ordered_need_level_split (Σ
    PurchaseItem.total_price позиций, чья плановая позиция need_level==
    NEED_LEVEL_NICE_TO_HAVE, клэмп в [0, итог вида]); "likely" = итог вида
    − nice. Инвариант (test_subsidy_summary_by_kind.py): Σ по видам nice/likely
    == contracted_not_ordered_need_level_split(db, subsidy_ids=[subsidy_id])
    [subsidy_id]."""
    from app.services.feo_payroll import payroll_category_ids
    from app.services.item_type_split import ALL_KINDS, kind_of_by_category_id

    result: dict[str, dict] = {k: {"nice": 0.0, "likely": 0.0} for k in ALL_KINDS}
    payroll_ids = await payroll_category_ids(db, [subsidy_id])

    rows_stmt = (
        select(
            Purchase.id, Purchase.item_type, Purchase.feo_category_id,
            effective_amount_expr().label("amt"),
        )
        .where(reserved_child_predicate())
        .where(Purchase.stopped_at.is_(None))
        .where(Purchase.subsidy_id == subsidy_id)
    )
    rows = (await db.execute(rows_stmt)).all()
    if not rows:
        return result

    totals_by_kind: dict[str, float] = {k: 0.0 for k in ALL_KINDS}
    purchase_kind: dict[int, str] = {}
    for r in rows:
        kind = kind_of_by_category_id(r.item_type, r.feo_category_id, payroll_ids)
        amt = float(r.amt or 0)
        totals_by_kind[kind] += amt
        purchase_kind[r.id] = kind

    # «nice» — та же техника, что contracted_not_ordered_need_level_split, но
    # сгруппированная по закупке (не по subsidy_id), чтобы потом разложить по
    # виду каждой закупки.
    nice_stmt = (
        select(Purchase.id, func.coalesce(func.sum(PurchaseItem.total_price), 0).label("amt"))
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(FeoPlannedItem, FeoPlannedItem.id == PurchaseItem.feo_planned_item_id)
        .where(Purchase.id.in_(list(purchase_kind.keys())))
        .where(Purchase.status == "contracted")
        .where(Purchase.parent_purchase_id.isnot(None))
        .where(Purchase.stopped_at.is_(None))
        .where(FeoPlannedItem.need_level == NEED_LEVEL_NICE_TO_HAVE)
        .group_by(Purchase.id)
    )
    nice_by_purchase: dict[int, float] = {r.id: float(r.amt or 0) for r in (await db.execute(nice_stmt)).all()}

    nice_by_kind: dict[str, float] = {k: 0.0 for k in ALL_KINDS}
    for pid, kind in purchase_kind.items():
        nice_by_kind[kind] += nice_by_purchase.get(pid, 0.0)

    for k in ALL_KINDS:
        total = totals_by_kind[k]
        nice = max(0.0, min(nice_by_kind[k], total))
        result[k] = {"nice": nice, "likely": total - nice}
    return result
