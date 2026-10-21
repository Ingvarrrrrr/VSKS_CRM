"""План B (ancient-prancing-music.md, раздел B/1) — товары/услуги/без типа по
каждому накопительному этапу дашборда (plan_schedule/work/ordered/contracts/
delivered/delivered_unpaid/paid), и глобально, и per-subsidy.

Извлечено рядом с dashboard_charts.py (Правило №5 — не раздувать роутер) по
образцу app.services.dashboard_monthly_accrual: чистый агрегат, видимость
приходит СНАРУЖИ колбэком/параметрами, здесь своей логики видимости нет.

НЕ второй набор корзин (Правило №6): суммы по этапу — ровно те же значения,
что basket_q/subsidy_q/contract_*_q в dashboard_charts.py (effective_amount_expr/
planned_total_price, тот же набор статусов) — здесь они лишь РАСКЛАДЫВАЮТСЯ по
типу через app.services.item_type_split (purchase_type_shares/kind_of,
единственный источник правила типа/долей).

Метод: для каждой закупки в скоупе — доля товары/услуги/без типа по ЕЁ
собственным PurchaseItem (purchase_type_shares), помноженная на сумму, которой
закупка засчитывается в тот или иной этап (та же сумма, что и в существующих
корзинах). Раскладка НАКАПЛИВАЕТСЯ «сырыми» (нераскруглёнными) Decimal —
округление до копейки происходит РОВНО ОДИН РАЗ, в reconcile_split(), против
уже посчитанного (существующего) значения этапа — так сумма трёх частей
конструктивно совпадает с прежним числом, а не проверяется постфактум.

«Заключено договоров» — то же самое для framework_cumulative (доля по
позициям привязанных закупок) и для single/framework_with_amount (доля по
ПУЛУ позиций ВСЕХ закупок, привязанных к договору через Purchase.contract_id —
сам договор своих позиций не имеет). Договор без единой привязанной закупки
(или без единой позиции в привязанных закупках) — целиком «без типа»
(см. reconcile_split: raw_total == 0 → всё в unspecified).

Помесячное начисление (dashboard_monthly_accrual.py) НЕ входит в раскладку
здесь — оно не привязано к позициям конкретной закупки (агрегат по графику
платежей); вызывающая сторона (dashboard_charts.py) добавляет его к
«ordered» ЦЕЛИКОМ как «без типа» (решение владельца, план раздел B/1).

compute_type_split_detail() (2026-09-21, расшифровка карточки этапа,
dashboard_type_drill.py) — построчный (по позициям) вывод ТОЙ ЖЕ раскладки
для одного этапа: тот же _stage_contributions/purchase_type_shares/kind_of,
что и compute_type_split_raw выше (никакой второй формулы, Правило №6),
только суммы не агрегируются в 3 числа, а остаются построчно — по одной
записи на позицию закупки (или на закупку/договор целиком, если позиций нет).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Dict, List, Optional

from sqlalchemy import select, or_ as sqlor
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
# ПРАВИЛО №6 (02.10.2026): единственный источник статусов «законтрактовано» —
# committed_amounts.py. Рамочный (framework_cumulative) — FRAMEWORK_COMMITTED_STATUSES
# (ordered/delivered/paid, не contracted — см. докстринг модуля); сумма single/
# framework_with_amount целиком строится через
# stage_cumulative.single_fwa_rows_by_contract_subsidy() (см. ниже), которая
# сама использует SINGLE_COMMITTED_STATUSES/FRAMEWORK_COMMITTED_STATUSES.
from app.services.committed_amounts import FRAMEWORK_COMMITTED_STATUSES
# Решение владельца 05.10.2026 («любая оплата = был договор, хоть
# упрощённый») — тот же добавочный источник, что и contracts_map в
# dashboard_charts.py (Правило №6, см. докстринг stage_cumulative.py).
# single_fwa_rows_by_contract_subsidy/reserved_child_predicate (ИСПРАВЛЕНО
# 15.10.2026, ФАДМ 2026_2 id=7320, Σ chip-ов контура "contracts" была БОЛЬШЕ
# карточки на 39 661,80 — та же причина, что и в докстринге
# single_fwa_rows_by_contract_subsidy: single/framework_with_amount считались
# здесь ВТОРОЙ, более старой формулой — без greatest(лимит, факт) и без учёта
# «заказ рамочного в статусе contracted» (reserved_child_predicate). ПРАВИЛО
# №6 — amount единого источника (contracted_total_by_subsidy его же и
# использует), здесь он только РАСКЛАДЫВАЕТСЯ по типу позиций.
from app.services.stage_cumulative import (
    committed_uncounted_expr, single_fwa_rows_by_contract_subsidy, reserved_child_predicate,
)
from app.services.item_type_split import (
    ALL_KINDS, KIND_GOODS, KIND_PAYROLL, KIND_SERVICES, KIND_UNSPECIFIED,
    TypeShares, kind_of, purchase_type_shares, split_amount_by_kind_pool,
)
from app.services.purchase_amounts import effective_amount_expr, aggregate_scope_expr
# Четвёртая корзина «ФОТ» на карточках-этапах (задача владельца 21.10.2026,
# ХРО_2026) — ЕДИНСТВЕННАЯ проверка «закупка — ФОТ» (ПРАВИЛО №6), см.
# докстринг purchase_payroll_map: эффективная категория закупки/её позиций/
# её плановых позиций, с наследованием по дереву. ФОТ закупки перебивает
# item_type её позиций целиком (collapse, не делится между goods/services) —
# тот же принцип, что item_type_split.collapse_kind_dict_to_payroll на
# уровне статьи ФЭО, здесь применяется на уровне закупки дашборда.
from app.services.feo_payroll import purchase_payroll_map

STAGE_KEYS: tuple = (
    "plan_schedule", "work", "ordered", "contracts", "delivered", "delivered_unpaid", "paid",
)

_CENT = Decimal("0.01")


def _zero4() -> List[Decimal]:
    """[goods, services, payroll, unspecified] — порядок ALL_KINDS (item_type_
    split.py), 4 корзины (задача владельца 21.10.2026, ХРО_2026)."""
    return [Decimal(0), Decimal(0), Decimal(0), Decimal(0)]


def _add4(acc: List[Decimal], amt: Decimal, is_payroll: bool, shares: TypeShares) -> None:
    """ФОТ закупки (is_payroll=True, см. purchase_payroll_map) перебивает
    item_type её позиций — вся amt целиком в payroll (тот же принцип, что
    item_type_split.collapse_kind_dict_to_payroll). Иначе — как раньше,
    goods/services/unspecified по shares (purchase_type_shares)."""
    if is_payroll:
        acc[2] += amt
        return
    acc[0] += amt * shares.goods
    acc[1] += amt * shares.services
    acc[3] += amt * shares.unspecified


def reconcile_split(raw: List[Decimal], target) -> Dict[str, float]:
    """raw = [raw_goods, raw_services, raw_payroll, raw_unspecified] (Decimal,
    нераскруглённые). target — уже посчитанное (существующее) значение этапа
    (float/Decimal/None). Возвращает {"goods","services","payroll",
    "unspecified"} (float), сумма которых РОВНО target (до копейки) — через
    split_amount_by_kind_pool (item_type_split.py, единственная формула
    4-корзинного округления с сохранением суммы, ПРАВИЛО №6: та же функция,
    что используется в feo_plan_tree.py для своих rollup-ов)."""
    target_dec = Decimal(str(target)) if target is not None else Decimal(0)
    pool = {
        KIND_GOODS: float(raw[0]), KIND_SERVICES: float(raw[1]),
        KIND_PAYROLL: float(raw[2]), KIND_UNSPECIFIED: float(raw[3]),
    }
    split = split_amount_by_kind_pool(target_dec, pool)
    return {k: float(split[k]) for k in ALL_KINDS}


async def _resolve_contract_subsidy_ids(
    db: AsyncSession, use_sids: bool, visible_subsidy_ids: Optional[set], org_ids: Optional[list],
) -> List[int]:
    """Список subsidy_id для single_fwa_rows_by_contract_subsidy() (та функция
    требует явный список, не умеет «без ограничения») — тот же набор субсидий,
    который раньше контролировал contract_q.where(...) построчно здесь
    (use_sids→visible_subsidy_ids, иначе org_ids, иначе вообще без фильтра)."""
    if use_sids:
        if visible_subsidy_ids is not None:
            return list(visible_subsidy_ids)
        return list((await db.execute(select(Subsidy.id))).scalars().all())
    if org_ids is not None:
        return list((await db.execute(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        )).scalars().all())
    return list((await db.execute(select(Subsidy.id))).scalars().all())


async def _items_by_purchase(db: AsyncSession, purchase_ids: List[int]) -> Dict[int, list]:
    """Строки PurchaseItem по списку закупок — один загрузчик (Правило №6) и для
    агрегатных долей (compute_type_split_raw читает item_type/total_price), и
    для построчной раскладки (compute_type_split_detail читает дополнительно
    id/item_name/purchase_id) — набор колонок общий, вызывающая сторона берёт
    только нужные ей атрибуты."""
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(
            PurchaseItem.id, PurchaseItem.purchase_id, PurchaseItem.item_name,
            PurchaseItem.item_type, PurchaseItem.total_price,
        ).where(PurchaseItem.purchase_id.in_(purchase_ids))
    )).all()
    out: Dict[int, list] = {}
    for row in rows:
        out.setdefault(row.purchase_id, []).append(row)
    return out


def _stage_contributions(status: str, plan_amt: Decimal, eff_amt: Decimal) -> Dict[str, Decimal]:
    """Единственный источник «статус закупки → в какие этапы и какой суммой
    она засчитывается» (кроме этапа "contracts" — тот собирается отдельно,
    по договорам, см. compute_type_split_raw/compute_type_split_detail ниже).
    Один-в-один повторяет накопительные корзины basket_q/subsidy_q в
    dashboard_charts.py. И агрегатный расчёт (compute_type_split_raw), и
    построчная раскладка (compute_type_split_detail) читают ТОЛЬКО отсюда —
    Правило №6, вторая копия этого if/elif запрещена."""
    out: Dict[str, Decimal] = {}
    if status == "plan_schedule":
        out["plan_schedule"] = plan_amt
    elif status == "work_in_progress":
        out["plan_schedule"] = plan_amt
        out["work"] = plan_amt
    elif status in ("contracted", "ordered"):
        out["plan_schedule"] = eff_amt
        out["work"] = eff_amt
        if status == "ordered":
            out["ordered"] = eff_amt
    elif status == "delivered":
        out["plan_schedule"] = eff_amt
        out["work"] = eff_amt
        out["ordered"] = eff_amt
        out["delivered"] = eff_amt
        out["delivered_unpaid"] = eff_amt
    elif status == "paid":
        out["plan_schedule"] = eff_amt
        out["work"] = eff_amt
        out["ordered"] = eff_amt
        out["delivered"] = eff_amt
        out["paid"] = eff_amt
    return out


def _split_amount_across_items(amount: Decimal, weights: List[Decimal]) -> List[Decimal]:
    """Делит amount на len(weights) частей пропорционально weights, округляя до
    копейки так, чтобы сумма частей была РОВНО amount (тот же принцип, что
    split_amount_by_shares в item_type_split.py — остаток округления уходит в
    часть с наибольшим весом, — но на N позиций закупки вместо фиксированных
    3 корзин goods/services/unspecified)."""
    total = sum(weights) if weights else Decimal(0)
    if not weights or total == 0:
        return [Decimal(0) for _ in weights]
    raw = [amount * (w / total) for w in weights]
    rounded = [r.quantize(_CENT, rounding=ROUND_HALF_UP) for r in raw]
    target = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    diff = target - sum(rounded)
    if diff != 0:
        idx = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[idx] += diff
    return rounded


def _emit_item_rows(
    rows: List[dict], raw_acc: List[Decimal], *,
    purchase_id: Optional[int], amt: Decimal, items, contract_id: Optional[int] = None,
    is_payroll: bool = False,
) -> None:
    """Строит по одной строке на каждую позицию items, деля amt между ними
    пропорционально total_price (_split_amount_across_items) — либо ОДНУ
    строку «без позиции» (kind=unspecified/payroll, вся сумма), если позиций
    нет или Σ total_price == 0 (тот же случай, что purchase_type_shares
    трактует как «без типа»). raw_acc — 4-корзинный аккумулятор
    [goods,services,payroll,unspecified] (см. _zero4), копится тем же
    способом, что global_split в compute_type_split_raw (для самопроверки/
    отладки на стороне вызывающего). is_payroll=True (закупка — ФОТ, см.
    purchase_payroll_map) — ВСЕ строки этой закупки идут с kind=payroll,
    item_type позиций не играет роли (collapse, как у _add4)."""
    item_list = list(items)
    weights = [
        Decimal(str(it.total_price)) if getattr(it, "total_price", None) is not None else Decimal(0)
        for it in item_list
    ]
    total_sum = sum(weights) if weights else Decimal(0)
    if not item_list or total_sum == 0:
        k = KIND_PAYROLL if is_payroll else KIND_UNSPECIFIED
        raw_acc[2 if is_payroll else 3] += amt
        rows.append({
            "purchase_id": purchase_id,
            "contract_id": contract_id,
            "item_id": None,
            "item_name": "— (без позиции)",
            "item_type": None,
            "kind": k,
            "amount": amt,
        })
        return
    parts = _split_amount_across_items(amt, weights)
    for it, part in zip(item_list, parts):
        k = KIND_PAYROLL if is_payroll else kind_of(getattr(it, "item_type", None))
        if k == KIND_GOODS:
            raw_acc[0] += part
        elif k == KIND_SERVICES:
            raw_acc[1] += part
        elif k == KIND_PAYROLL:
            raw_acc[2] += part
        else:
            raw_acc[3] += part
        rows.append({
            "purchase_id": getattr(it, "purchase_id", purchase_id),
            "contract_id": contract_id,
            "item_id": getattr(it, "id", None),
            "item_name": getattr(it, "item_name", None),
            "item_type": getattr(it, "item_type", None),
            "kind": k,
            "amount": part,
        })


async def compute_type_split_raw(
    db: AsyncSession,
    *,
    apply_filter: Callable,
    use_sids: bool,
    visible_subsidy_ids: Optional[set],
    org_ids: Optional[list],
) -> dict:
    """Возвращает {"global": {stage: [g,s,u]}, "per_subsidy": {sid: {stage: [g,s,u]}}}
    — Decimal-триплеты, НЕраскруглённые. Вызывающий код обязан прогнать каждую
    через reconcile_split() против уже посчитанного значения этапа.

    apply_filter — тот же колбэк-фильтр видимости покупок, что и
    compute_monthly_ordered_map (_apply_purchase_org_filter, применённый
    вызывающей стороной с нужными current_user/org_ids/visible_subsidy_ids).
    use_sids/visible_subsidy_ids/org_ids — те же переменные, что
    dashboard_charts.py использует для contract_single_q/contract_fc_q (эти два
    запроса фильтруются НЕ через apply_filter, а напрямую по Contract/Purchase —
    та же логика видимости, продублированная и в самом dashboard_charts.py
    для каждого из shared-запросов)."""
    global_split: Dict[str, List[Decimal]] = {stage: _zero4() for stage in STAGE_KEYS}
    per_subsidy_split: Dict[int, Dict[str, List[Decimal]]] = {}

    def _sid_bucket(sid) -> Optional[Dict[str, List[Decimal]]]:
        if sid is None:
            return None
        if sid not in per_subsidy_split:
            per_subsidy_split[sid] = {stage: _zero4() for stage in STAGE_KEYS}
        return per_subsidy_split[sid]

    # ── Покупки, попадающие хотя бы в одну корзину (те же 6, что basket_q) ──
    # aggregate_scope_expr() (ИСПРАВЛЕНО 15.10.2026, ФАДМ 2026_2 id=7320:
    # drill «Ведётся работа» 16 252 487,61 vs карточка 13 949 555,61, разница
    # 2 302 932,00 — ровно Σ max_amount трёх рамочных голов с реальными
    # заказами: 1 400 000 + 207 900 + 584 032 + 111 000). Причина: subsidy_q
    # в dashboard_charts.py считает total_work/widget[stage] ЧЕРЕЗ JOIN с
    # aggregate_scope_expr() — рамочная голова (framework_cumulative/
    # framework_with_amount) с реальным заказом-ребёнком НЕ входит в
    # статусные суммы (её деньги несут сами заказы, см. докстринг
    # aggregate_scope_expr); base_q здесь этот фильтр не применял — голова
    # (её Contract.max_amount через effective_amount_expr) считалась ЕЩЁ РАЗ
    # поверх уже посчитанных заказов-детей. ПРАВИЛО №6 — тот же предикат, что
    # и у карточки, не второй набор правил.
    base_q = (
        select(
            Purchase.id, Purchase.status, Purchase.subsidy_id,
            Purchase.planned_total_price, effective_amount_expr().label("effective"),
        )
        .where(Purchase.status.notin_(["cancelled", "wishes"]))
        .where(aggregate_scope_expr())
    )
    base_q = apply_filter(base_q)
    purchase_rows = (await db.execute(base_q)).all()

    # ── «Заключено договоров», framework_cumulative — те же покупки, что
    # contracted_rows_by_category::cfc_cat_stmt (ИСПРАВЛЕНО 15.10.2026: раньше
    # здесь стоял только FRAMEWORK_COMMITTED_STATUSES, без reserved_child_
    # predicate() — заказ рамочного в статусе 'contracted' (договор на партию
    # уже заключён, заказ как отдельная закупка ещё не оформлен) пропускался,
    # хотя карточка его уже считает «законтрактованным» — ПРАВИЛО №6). ──
    fc_q = (
        select(Purchase.id, Purchase.subsidy_id, effective_amount_expr().label("effective"))
        .join(Contract, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            fc_q = fc_q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        fc_q = fc_q.where(Purchase.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    fc_rows = (await db.execute(fc_q)).all()

    # ── «Заключено договоров», single/framework_with_amount — ЕДИНЫЙ источник
    # суммы (ПРАВИЛО №6, см. импорт выше): stage_cumulative.
    # single_fwa_rows_by_contract_subsidy() — та же функция, что строит amount
    # для contracted_total_by_subsidy() (карточка «Заключено договоров»).
    # Раньше здесь жила вторая, более старая формула (голый Contract.max_amount
    # без greatest(лимит, факт) для single и без топ-апа остатка лимита
    # framework_with_amount по его заказам-детям) — на ФАДМ 2026_2 id=7320 она
    # давала на 39 661,80 больше карточки. Доля по типу — ПУЛ позиций ВСЕХ
    # закупок, привязанных к договору В ЭТОЙ субсидии (не ко всему договору —
    # у «общих» между копиями субсидии договоров своя доля на каждую, тот же
    # принцип, что Purchase.subsidy_id в single_fwa_rows_by_contract_subsidy). ──
    contract_subsidy_ids = await _resolve_contract_subsidy_ids(db, use_sids, visible_subsidy_ids, org_ids)
    fwa_buckets = await single_fwa_rows_by_contract_subsidy(db, subsidy_ids=contract_subsidy_ids)
    contract_ids = list({cid for (cid, _sid) in fwa_buckets})
    linked_purchase_rows: list = []
    if contract_ids:
        linked_purchase_rows = (await db.execute(
            select(Purchase.id, Purchase.contract_id, Purchase.subsidy_id)
            .where(Purchase.contract_id.in_(contract_ids))
        )).all()
    linked_purchase_ids_by_contract_subsidy: Dict[tuple, list] = {}
    for pid, cid, psid in linked_purchase_rows:
        linked_purchase_ids_by_contract_subsidy.setdefault((cid, psid), []).append(pid)

    # ── Один общий запрос позиций закупок на объединение всех участвующих id ──
    all_purchase_ids = list({
        *[r.id for r in purchase_rows],
        *[r.id for r in fc_rows],
        *[pid for pid, _cid, _psid in linked_purchase_rows],
    })
    items_by_purchase = await _items_by_purchase(db, all_purchase_ids)
    # ФОТ закупки (задача владельца 21.10.2026, ХРО_2026) — ЕДИНСТВЕННАЯ
    # проверка purchase_payroll_map (ПРАВИЛО №6, см. импорт выше), один запрос
    # на весь набор id этого вызова.
    payroll_map = await purchase_payroll_map(db, all_purchase_ids)

    # ── 6-корзинная раскладка (см. widgets в dashboard_charts.py) — статус →
    # {stage: amt} из ЕДИНОГО источника _stage_contributions (Правило №6, тот
    # же, что читает compute_type_split_detail). ──
    for r in purchase_rows:
        shares = purchase_type_shares(items_by_purchase.get(r.id, ()))
        is_payroll = payroll_map.get(r.id, False)
        sid_bucket = _sid_bucket(r.subsidy_id)
        plan_amt = Decimal(str(r.planned_total_price)) if r.planned_total_price is not None else Decimal(0)
        eff_amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)

        for stage, amt in _stage_contributions(r.status, plan_amt, eff_amt).items():
            _add4(global_split[stage], amt, is_payroll, shares)
            if sid_bucket is not None:
                _add4(sid_bucket[stage], amt, is_payroll, shares)

    # ── «Заключено договоров»: framework_cumulative ──
    for r in fc_rows:
        shares = purchase_type_shares(items_by_purchase.get(r.id, ()))
        is_payroll = payroll_map.get(r.id, False)
        amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)
        _add4(global_split["contracts"], amt, is_payroll, shares)
        sid_bucket = _sid_bucket(r.subsidy_id)
        if sid_bucket is not None:
            _add4(sid_bucket["contracts"], amt, is_payroll, shares)

    # ── «Заключено договоров»: single/framework_with_amount (greatest(лимит,
    # факт) + топ-ап уже внутри bucket["amount"], см. комментарий выше).
    # ФОТ — если ХОТЯ БЫ одна из пулированных закупок договора ФОТ (несколько
    # закупок на один рамочный договор с разными статьями — редкий случай;
    # упрощение: вся сумма договора в payroll, не делится дальше). ──
    for (cid, sid), bucket in fwa_buckets.items():
        amt = Decimal(str(bucket["amount"]))
        if amt == 0:
            continue
        linked_ids = linked_purchase_ids_by_contract_subsidy.get((cid, sid), [])
        pooled_items: list = []
        for pid in linked_ids:
            pooled_items.extend(items_by_purchase.get(pid, ()))
        is_payroll = any(payroll_map.get(pid, False) for pid in linked_ids)
        shares = purchase_type_shares(pooled_items)
        _add4(global_split["contracts"], amt, is_payroll, shares)
        sid_bucket = _sid_bucket(sid)
        if sid_bucket is not None:
            _add4(sid_bucket["contracts"], amt, is_payroll, shares)

    # ── «Заключено договоров»: committed-закупки, НЕ покрытые активным
    # Contract известного типа (владелец, 05.10.2026) — добавочное слагаемое,
    # та же выборка, что committed_uncounted_by_subsidy (ПРАВИЛО №6, включая
    # её stopped_at-фильтр — отсутствие которого здесь раньше НЕ создавало
    # видимой разницы с card только потому, что он не затрагивал найденные
    # прод-кейсы; добавлен для полной параллели предикату), своими позициями. ──
    contractless_q = (
        select(Purchase.id, Purchase.subsidy_id, effective_amount_expr().label("effective"))
        .outerjoin(Contract, Purchase.contract_id == Contract.id)
        .where(committed_uncounted_expr())
        .where(Purchase.stopped_at.is_(None))
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            contractless_q = contractless_q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        contractless_q = contractless_q.where(Purchase.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    contractless_rows = (await db.execute(contractless_q)).all()
    if contractless_rows:
        _cl_items = await _items_by_purchase(db, [r.id for r in contractless_rows])
        _cl_payroll_map = await purchase_payroll_map(db, [r.id for r in contractless_rows])
        for r in contractless_rows:
            shares = purchase_type_shares(_cl_items.get(r.id, ()))
            is_payroll = _cl_payroll_map.get(r.id, False)
            amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)
            _add4(global_split["contracts"], amt, is_payroll, shares)
            sid_bucket = _sid_bucket(r.subsidy_id)
            if sid_bucket is not None:
                _add4(sid_bucket["contracts"], amt, is_payroll, shares)

    return {
        "global": global_split,
        "per_subsidy": per_subsidy_split,
    }


async def compute_type_split_detail(
    db: AsyncSession,
    *,
    apply_filter: Callable,
    use_sids: bool,
    visible_subsidy_ids: Optional[set],
    org_ids: Optional[list],
    stage: str,
) -> dict:
    """Построчная (по позициям закупки/договора) раскладка ОДНОГО этапа —
    расшифровка строки «товары/услуги/без типа» карточки этапа
    (dashboard_type_drill.py). Использует РОВНО те же корзины/статусы/суммы,
    что compute_type_split_raw выше (_stage_contributions для не-"contracts"
    этапов, тот же контур framework_cumulative/single/framework_with_amount
    для "contracts") — не вторая формула (Правило №6), только вывод построчно
    вместо агрегата в 3 числа.

    Возвращает {"raw": [g,s,u] (Decimal, нераскруглённый триплет — для
    самопроверки, ту же сумму даёт compute_type_split_raw для этого stage),
    "rows": [{"purchase_id","contract_id","item_id","item_name","item_type",
    "kind","amount"(Decimal)}]}. Разбиение суммы закупки/договора между её
    позициями — _split_amount_across_items (та же идея округления с переносом
    остатка, что split_amount_by_shares в item_type_split.py, только на N
    позиций вместо 3 корзин)."""
    if stage not in STAGE_KEYS:
        raise ValueError(f"unknown stage {stage!r}")

    rows: List[dict] = []
    raw = _zero4()

    if stage == "contracts":
        # framework_cumulative — тот же контур, что compute_type_split_raw
        # выше (ИСПРАВЛЕНО 15.10.2026 вместе с ним: + reserved_child_predicate()
        # — заказ рамочного в статусе 'contracted' тоже «законтрактован»). ──
        fc_q = (
            select(Purchase.id, Purchase.subsidy_id, effective_amount_expr().label("effective"))
            .join(Contract, Purchase.contract_id == Contract.id)
            .where(Contract.status == "active")
            .where(Contract.contract_type == "framework_cumulative")
            .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        )
        if use_sids:
            if visible_subsidy_ids is not None:
                fc_q = fc_q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
        elif org_ids is not None:
            fc_q = fc_q.where(Purchase.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
            ))
        fc_rows = (await db.execute(fc_q)).all()

        # single/framework_with_amount — ЕДИНЫЙ источник суммы (ПРАВИЛО №6,
        # см. комментарий в compute_type_split_raw выше): stage_cumulative.
        # single_fwa_rows_by_contract_subsidy(), не вторая формула.
        contract_subsidy_ids = await _resolve_contract_subsidy_ids(db, use_sids, visible_subsidy_ids, org_ids)
        fwa_buckets = await single_fwa_rows_by_contract_subsidy(db, subsidy_ids=contract_subsidy_ids)
        contract_ids = list({cid for (cid, _sid) in fwa_buckets})
        linked_purchase_rows: list = []
        if contract_ids:
            linked_purchase_rows = (await db.execute(
                select(Purchase.id, Purchase.contract_id, Purchase.subsidy_id)
                .where(Purchase.contract_id.in_(contract_ids))
            )).all()
        linked_purchase_ids_by_contract_subsidy: Dict[tuple, list] = {}
        for pid, cid, psid in linked_purchase_rows:
            linked_purchase_ids_by_contract_subsidy.setdefault((cid, psid), []).append(pid)

        all_purchase_ids = list({
            *[r.id for r in fc_rows],
            *[pid for pid, _cid, _psid in linked_purchase_rows],
        })
        items_by_purchase = await _items_by_purchase(db, all_purchase_ids)
        payroll_map = await purchase_payroll_map(db, all_purchase_ids)

        for r in fc_rows:
            amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)
            _emit_item_rows(
                rows, raw, purchase_id=r.id, amt=amt, items=items_by_purchase.get(r.id, ()),
                is_payroll=payroll_map.get(r.id, False),
            )

        for (cid, sid), bucket in fwa_buckets.items():
            amt = Decimal(str(bucket["amount"]))
            if amt == 0:
                continue
            linked_ids = linked_purchase_ids_by_contract_subsidy.get((cid, sid), [])
            pooled_items: list = []
            for pid in linked_ids:
                pooled_items.extend(items_by_purchase.get(pid, ()))
            # Договор сам не имеет позиций — они принадлежат привязанным
            # закупкам ЭТОЙ субсидии (может быть больше одной), поэтому
            # purchase_id=None здесь: каждая строка ниже несёт СВОЙ
            # purchase_id (из items), только строка «без позиции» (пустой
            # пул) остаётся без закупки. ФОТ — если хотя бы одна из
            # пулированных закупок ФОТ (см. compute_type_split_raw выше).
            is_payroll = any(payroll_map.get(pid, False) for pid in linked_ids)
            _emit_item_rows(
                rows, raw, purchase_id=None, amt=amt, items=pooled_items, contract_id=cid,
                is_payroll=is_payroll,
            )

        # ── committed-закупки, НЕ покрытые активным Contract известного типа
        # (владелец, 05.10.2026) — НЕДОСТАЮЩЕЕ слагаемое (ИСПРАВЛЕНО
        # 15.10.2026: при переходе на single_fwa_rows_by_contract_subsidy для
        # этой функции оно было пропущено целиком — на субсидиях 51/ДНР id=7
        # drill оказался МЕНЬШЕ карточки на 54 318,00 / 341 565,00, ровно Σ
        # этого слагаемого). Та же выборка, что committed_uncounted_by_
        # subsidy() (ПРАВИЛО №6), своими позициями — см. compute_type_split_raw. ──
        contractless_q = (
            select(Purchase.id, Purchase.subsidy_id, effective_amount_expr().label("effective"))
            .outerjoin(Contract, Purchase.contract_id == Contract.id)
            .where(committed_uncounted_expr())
            .where(Purchase.stopped_at.is_(None))
        )
        if use_sids:
            if visible_subsidy_ids is not None:
                contractless_q = contractless_q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
        elif org_ids is not None:
            contractless_q = contractless_q.where(Purchase.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
            ))
        contractless_rows = (await db.execute(contractless_q)).all()
        if contractless_rows:
            _cl_items = await _items_by_purchase(db, [r.id for r in contractless_rows])
            _cl_payroll_map = await purchase_payroll_map(db, [r.id for r in contractless_rows])
            for r in contractless_rows:
                amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)
                _emit_item_rows(
                    rows, raw, purchase_id=r.id, amt=amt, items=_cl_items.get(r.id, ()),
                    is_payroll=_cl_payroll_map.get(r.id, False),
                )

        return {"raw": raw, "rows": rows}

    # ── не-"contracts" этапы: та же корзина покупок, что base_q в
    # compute_type_split_raw, разложенная по _stage_contributions ──
    # aggregate_scope_expr() — см. комментарий в compute_type_split_raw выше
    # (та же правка 15.10.2026): без него рамочная голова с реальным заказом
    # считалась и сама, и через своих детей — drill был больше карточки.
    base_q = (
        select(
            Purchase.id, Purchase.status, Purchase.subsidy_id,
            Purchase.planned_total_price, effective_amount_expr().label("effective"),
        )
        .where(Purchase.status.notin_(["cancelled", "wishes"]))
        .where(aggregate_scope_expr())
    )
    base_q = apply_filter(base_q)
    purchase_rows = (await db.execute(base_q)).all()
    items_by_purchase = await _items_by_purchase(db, [r.id for r in purchase_rows])
    payroll_map = await purchase_payroll_map(db, [r.id for r in purchase_rows])

    for r in purchase_rows:
        plan_amt = Decimal(str(r.planned_total_price)) if r.planned_total_price is not None else Decimal(0)
        eff_amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)
        amt = _stage_contributions(r.status, plan_amt, eff_amt).get(stage)
        if amt is None:
            continue
        _emit_item_rows(
            rows, raw, purchase_id=r.id, amt=amt, items=items_by_purchase.get(r.id, ()),
            is_payroll=payroll_map.get(r.id, False),
        )

    return {"raw": raw, "rows": rows}
