"""payroll_visibility.py — ЕДИНАЯ проверка «виден ли пользователю ФОТ
конкретной субсидии» (ПРАВИЛО №6, план владельца 21.10.2026, часть 1 —
право «Видеть ФОТ»).

Повод: «для того чтобы в статистике ФОТ отображался у человека должна быть
отдельная галочка. Если её нет, то он видит только товары и услуги» — на
вопрос «где прятать» ответ «Везде» (карточки дашборда, расшифровки, реестр
закупок, дерево ФЭО, выгрузка в Excel). Действие `subsidy.view_payroll`
(app.startup.permission_seeds._subsidy_view_payroll_action) — orgRole-
дефолт ИЛИ персональный override (UserOrgPermissionOverride на орг-доступ,
UserSubsidyPermissionOverride на субсидийный грант) — та же схема, что у
`purchase.tz_waive`/`plan_excess_decide`.

ВСЕ места, которым нужно решить «показывать ФОТ этой субсидии этому
пользователю» (payroll_category_ids/purchase_payroll_map из feo_payroll.py
уже решают «закупка/статья — ФОТ по сути», этот модуль решает ОРТОГОНАЛЬНЫЙ
вопрос «имеет ли право видеть») — ОБЯЗАНЫ звать функции отсюда, а не
`has_org_key(..., 'subsidy.view_payroll', ...)` напрямую: вторая формула
«кэшировать по org_id или не кэшировать» не вводится."""
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import has_org_key
from app.models.subsidy import Subsidy
from app.models.user import User

ACTION_KEY = "subsidy.view_payroll"


async def payroll_visible_subsidy_ids(
    user: User, db: AsyncSession, subsidy_ids: Iterable[int],
) -> set[int]:
    """{subsidy_id, ...} — подмножество subsidy_ids, где ФОТ пользователю
    НЕ нужно прятать: либо в субсидии вообще нет ФОТ-статей (нечего прятать —
    тривиально «видимо»), либо есть, и у user есть право `subsidy.view_payroll`
    (орг-дефолт роли ИЛИ персональный грант на именно эту субсидию).
    superadmin — видит все, без обращения к БД.

    Перф (координатор, 21.10.2026, прод-замер): has_org_key — не бесплатная
    проверка (запросы UserOrgAccess/overrides), гонять её по КАЖДОЙ субсидии
    КАЖДОГО аккаунта не нужно — субсидий с хоть одной ФОТ-статьёй на проде
    ~4 из сотен (app.services.feo_payroll.subsidy_ids_with_payroll, ОДНО
    место, которое это знает). Короткий путь: сузить subsidy_ids до тех, где
    ФОТ реально есть, ПЕРЕД has_org_key; остальные — сразу в результат."""
    ids = [sid for sid in dict.fromkeys(subsidy_ids) if sid is not None]
    if not ids:
        return set()
    if user.role == "superadmin":
        return set(ids)

    from app.services.feo_payroll import subsidy_ids_with_payroll
    with_payroll = await subsidy_ids_with_payroll(db, ids)
    visible: set[int] = set(ids) - with_payroll  # нечего прятать — видимо тривиально
    if not with_payroll:
        return visible

    rows = (await db.execute(
        select(Subsidy.id, Subsidy.org_id).where(Subsidy.id.in_(with_payroll))
    )).all()
    org_of = {r.id: r.org_id for r in rows}

    org_cache: dict = {}
    for sid in with_payroll:
        org_id = org_of.get(sid)
        if org_id not in org_cache:
            org_cache[org_id] = await has_org_key(user, db, org_id, ACTION_KEY)
        if org_cache[org_id]:
            visible.add(sid)
            continue
        if await has_org_key(user, db, org_id, ACTION_KEY, subsidy_id=sid):
            visible.add(sid)
    return visible


_BY_KIND_PAIRS = (
    # (сумма-агрегат, её разбивка по видам) — ОБЕ ВСЕГДА присутствуют в
    # subsidy_stats[i] независимо от ?type_split (см. app/routers/
    # dashboard_charts.py: _money/paid_breakdown/delivered_unpaid_residual/
    # paid_over_delivered считаются безусловно). Скраб вычитает payroll-долю
    # из суммы и зануляет её в разбивке — ПРАВИЛО №6, никакая payroll-сумма
    # не считается здесь заново, берётся из уже готового ключа "payroll".
    ("committed", "committed_by_kind"),
    ("planned_not_committed", "planned_not_committed_by_kind"),
    ("redistributable", "redistributable_by_kind"),
    ("paid_declared", "paid_declared_by_kind"),
    ("paid_confirmed", "paid_confirmed_by_kind"),
    ("total_delivered_unpaid", "delivered_unpaid_declared_by_kind"),
    ("paid_over_delivered", "paid_over_delivered_by_kind"),
)

# Поля, которые НЕ имеют разбивки по видам ни при каких условиях (чистые
# SQL-агрегаты по статусу закупки без типа товар/услуга/ФОТ) — вычесть из
# них payroll нельзя без второй формулы (ПРАВИЛО №6 запрещает), поэтому они
# НЕ скрабятся: total_planned/total_confirmed/total_paid, total_plan_schedule/
# total_ordered/total_work/total_contracts/total_delivered, economy_total,
# balance_paid_marked/confirmed, balance_by_marks/by_statement,
# plan_over_ceiling_amount, feo_ceiling, redistributable_unplanned,
# widgets[stage]["amount"]/widget[stage]["amount"] БЕЗ ?type_split=true
# (разбивка *_payroll тогда не вычисляется вовсе, см. dashboard_charts.py
# ~строка 897). Эти числа перечисляются как несепарабельные в отчёте
# исполнителя, а не исправляются второй формулой здесь.


# ИСПРАВЛЕНО (D1, живая приёмка 21.10.2026, ХРО_2026): локальный список стадий
# не включал "contracts" — другой набор, чем настоящий STAGE_KEYS
# (app.services.dashboard_type_split), из-за чего widget["contracts"]["amount"]
# (карточка «Заключено договоров») и contracts_payroll НИКОГДА не вычищались
# (единственная стадия, которую этот модуль пропускал) — ПРАВИЛО №6, читаем
# ОДИН канонический список, а не держим свою отдельную копию, рискующую
# разойтись с ним снова.
from app.services.dashboard_type_split import STAGE_KEYS as _STAGE_KEYS


async def _on_demand_stage_payroll(db: AsyncSession, invisible_ids: list, rows_by_id: dict) -> dict:
    """{sid: {stage: payroll_amt}} — считается ТОЛЬКО когда запрос пришёл
    БЕЗ ?type_split=true (иначе widget[stage][f"{stage}_payroll"] уже готов
    обычным путём dashboard_charts.py, вторая формула не нужна). ТА ЖЕ
    функция, что считает стадийную разбивку при ?type_split=true —
    app.services.dashboard_type_split.compute_type_split_raw/reconcile_split
    (ПРАВИЛО №6), просто вызванная отдельно и ТОЛЬКО по узкому списку
    субсидий, где ФОТ скрыт (координатор, 21.10.2026: на проде их единицы —
    не гонять эту довольно тяжёлую функцию по всем видимым субсидиям)."""
    from app.services.dashboard_type_split import compute_type_split_raw, reconcile_split
    from app.models.purchase import Purchase

    def _filter(q):
        return q.where(Purchase.subsidy_id.in_(invisible_ids))

    raw_split = await compute_type_split_raw(
        db, apply_filter=_filter, use_sids=True,
        visible_subsidy_ids=set(invisible_ids), org_ids=None,
    )
    out: dict = {}
    for sid in invisible_ids:
        row = rows_by_id.get(sid)
        if row is None:
            continue
        widget = row.get("widget") or {}
        per_sub_raw = raw_split["per_subsidy"].get(sid, {})
        out[sid] = {}
        for stage in _STAGE_KEYS:
            bucket = widget.get(stage)
            if not bucket or f"{stage}_payroll" in bucket:
                continue  # уже посчитан обычным путём (?type_split=true) — не дублируем
            reconciled = reconcile_split(per_sub_raw.get(stage, [0, 0, 0, 0]), bucket.get("amount", 0.0))
            out[sid][stage] = reconciled.get("payroll", 0.0)
    return out


async def _on_demand_budget_planned_payroll(db: AsyncSession, invisible_ids: list, rows_by_id: dict) -> dict:
    """{sid: {"feo_payroll": x, "plan_payroll": y}} — та же функция, что
    строит budget_payroll/planned_payroll при ?type_split=true
    (app.routers.subsidies._calculate_feo_planned_tree_bulk(type_split=True)),
    вызванная отдельно ТОЛЬКО для субсидий без права и ТОЛЬКО если строка ещё
    не несёт budget_payroll (т.е. запрос пришёл без ?type_split=true).
    tree не передаём — для узкого списка субсидий дешевле построить заново,
    чем тащить сюда весь request-scoped кэш дерева."""
    need_ids = [sid for sid in invisible_ids if "budget_payroll" not in (rows_by_id.get(sid) or {})]
    if not need_ids:
        return {}
    from app.routers.subsidies import _calculate_feo_planned_tree_bulk
    return await _calculate_feo_planned_tree_bulk(db, need_ids, type_split=True)


async def _payroll_balance_amounts(db: AsyncSession, invisible_ids: list) -> dict:
    """{sid: {"paid_marked": x, "paid_confirmed": y}} — payroll-доля
    balance_paid_marked/balance_paid_confirmed («Остаток субсидии»).
    ПЕРЕИСПОЛЬЗУЕТ ТОТ ЖЕ построчный источник, что и сама расшифровка
    карточки (metric_drill_rows.balance_drill → feo_plan_payments.
    paid_consumption_rows), а не paid_breakdown_rows (другая техника подсчёта,
    см. докстринг subsidy_money_summary.py про «тот же источник данных, НО
    другая» — пересчитывать balance_paid_marked из paid_declared было бы
    второй формулой, этого делать нельзя, см. отчёт)."""
    from app.services.feo_plan_payments import paid_consumption_rows
    from app.services.feo_payroll import purchase_payroll_map

    rows = await paid_consumption_rows(db, invisible_ids, exclude_planned_item_linked=False)
    purchase_ids = {r["purchase_id"] for r in rows}
    pmap = await purchase_payroll_map(db, purchase_ids) if purchase_ids else {}
    out: dict = {}
    for r in rows:
        if not pmap.get(r["purchase_id"]):
            continue
        bucket = out.setdefault(r["subsidy_id"], {"paid_marked": 0.0, "paid_confirmed": 0.0})
        bucket["paid_marked"] += r.get("paid_marked", 0.0) or 0.0
        bucket["paid_confirmed"] += r.get("paid_confirmed", 0.0) or 0.0
    return out


async def scrub_payroll_from_dashboard_charts(
    user: User, db: AsyncSession, subsidy_stats: list, widgets: dict,
    dashboard_type_totals: Optional[dict] = None,
) -> None:
    """Пост-обработка ответа GET /api/dashboard/charts (мутирует переданные
    subsidy_stats/widgets/dashboard_type_totals IN PLACE, вызывается ПОСЛЕ
    того, как они полностью посчитаны обычным путём). Для субсидий, где у
    user нет subsidy.view_payroll (их единицы, см. feo_payroll.
    subsidy_ids_with_payroll — именно по ним считается invisible_rows ниже,
    остальные payroll_visible_subsidy_ids уже тривиально включила как
    «видимые», ничего считать для них не нужно):

      - committed/planned_not_committed/redistributable/paid_declared/
        paid_confirmed/total_delivered_unpaid/paid_over_delivered — ФОТ
        вычитается из by_kind (ВСЕГДА присутствуют, независимо от ?type_split);
      - widget[stage]["amount"] (6 накопительных стадий) и ГЛОБАЛЬНЫЕ
        widgets[stage] — ФОТ вычитается ВСЕГДА (если ?type_split=true уже
        посчитал widget[stage][f"{stage}_payroll"] — берём готовое число;
        иначе считаем его здесь же ОТДЕЛЬНЫМ вызовом compute_type_split_raw,
        см. _on_demand_stage_payroll, ТОЛЬКО для этих субсидий — координатор
        21.10.2026, п.2);
      - feo_budget_total/total_feo_planned/remaining — ФОТ вычитается ВСЕГДА
        (budget_payroll/planned_payroll — готовые при ?type_split=true, иначе
        считаются отдельно _on_demand_budget_planned_payroll); remaining
        пересчитывается ТОЙ ЖЕ формулой free_basis=budget_basis−planned
        (subsidy_money_summary.py), просто на уже вычищенных budget/planned —
        не вторая формула;
      - balance_paid_marked/confirmed и balance_by_marks/by_statement —
        payroll-доля из paid_consumption_rows (тот же источник, что и сама
        расшифровка «Остаток субсидии», см. _payroll_balance_amounts), затем
        balance_by_marks/by_statement = feo_budget_total(вычищенный) −
        balance_paid_marked/confirmed(вычищенный) — та же формула
        subsidy_money_summary.py, не вторая.

      - not_committed_nice/not_committed_likely/redistributable_unplanned/
        monthly_future_not_started (D7, живая приёмка 21.10.2026, ДНР id 61) —
        4 подстроки карточки «Можно перераспределить», payroll-доля читается
        ИЗ subsidy_money_summary.py (not_committed_*_payroll/redistributable_
        unplanned_payroll — та же Σ, что уже вычтена из redistributable_by_kind
        ['payroll'] выше, ПРАВИЛО №6, не вторая формула).

    НЕ трогает row["planned_tree"] (объект кэша дерева ФЭО, with_feo_plan_tree_
    cache) — скрытие статей ФОТ В ДЕРЕВЕ — Часть 4 (GET /feo-categories/plan-tree).
    НЕ скрабится (нет by-kind источника без второй формулы — см. отчёт):
    total_planned/total_confirmed/total_paid, total_work/total_contracts/
    total_ordered/monthly_*, economy_total, plan_over_ceiling_amount/feo_ceiling,
    redistributable_unplanned (отдельное поле — не равно remaining, не трогаем)."""
    from app.services.item_type_split import KIND_PAYROLL

    ids = [row.get("id") for row in subsidy_stats if row.get("id") is not None]
    visible = await payroll_visible_subsidy_ids(user, db, ids)
    invisible_rows = [row for row in subsidy_stats if row.get("id") not in visible]
    if not invisible_rows:
        return
    invisible_ids = [row["id"] for row in invisible_rows]
    rows_by_id = {row["id"]: row for row in invisible_rows}

    for row in invisible_rows:
        for total_key, by_kind_key in _BY_KIND_PAIRS:
            by_kind = row.get(by_kind_key)
            if not by_kind:
                continue
            amt = by_kind.get(KIND_PAYROLL, 0.0) or 0.0
            if not amt:
                continue
            by_kind[KIND_PAYROLL] = 0.0
            if row.get(total_key) is not None:
                row[total_key] = round(row[total_key] - amt, 2)

    # ── Подстроки карточки «Можно перераспределить» (D7, живая приёмка
    # 21.10.2026, ДНР id 61) ──────────────────────────────────────────────
    # redistributable/redistributable_by_kind уже гашены циклом выше (_BY_KIND_
    # PAIRS включает эту пару) — ИТОГ карточки для пользователя без права уже
    # верный. Но её 4 подстроки (not_committed_nice/likely, redistributable_
    # unplanned, monthly_future_not_started) читаются dashboard_charts.py НЕ из
    # by_kind, отдельными ключами — этот цикл их не трогал вовсе, и они
    # оставались владельческими целиком (находка владельца: «не запланировано»/
    # «скорее всего понадобится» не совпадали с «Свободно»/«Запланировано» без
    # ФОТ). Payroll-доля каждой подстроки — ТА ЖЕ Σ, что уже вычтена из
    # redistributable_by_kind['payroll'] (см. subsidy_money_summary.py
    # not_committed_*_payroll/redistributable_unplanned_payroll, ПРАВИЛО №6 —
    # не вторая формула, просто читаем уже посчитанные поля).
    from app.services.subsidy_money_summary import subsidy_money_summary as _subsidy_money_summary
    _payroll_sub_summary = await _subsidy_money_summary(db, invisible_ids)
    for row in invisible_rows:
        sid = row["id"]
        _psum = _payroll_sub_summary.get(sid) or {}
        for field, payroll_field in (
            ("not_committed_nice", "not_committed_nice_payroll"),
            ("not_committed_likely", "not_committed_likely_payroll"),
            ("monthly_future_not_started", "monthly_future_not_started_payroll"),
            ("redistributable_unplanned", "redistributable_unplanned_payroll"),
        ):
            amt = _psum.get(payroll_field, 0.0) or 0.0
            if not amt or row.get(field) is None:
                continue
            row[field] = round(row[field] - amt, 2)

    # ── Стадийные виджеты (всегда, type_split или нет) ──────────────────────
    on_demand_stage = await _on_demand_stage_payroll(db, invisible_ids, rows_by_id)
    for row in invisible_rows:
        sid = row["id"]
        widget = row.get("widget") or {}
        for stage in _STAGE_KEYS:
            bucket = widget.get(stage)
            if not bucket:
                continue
            payroll_key = f"{stage}_payroll"
            if payroll_key in bucket:
                amt = bucket.get(payroll_key) or 0.0
                bucket[payroll_key] = 0.0
            else:
                amt = (on_demand_stage.get(sid) or {}).get(stage, 0.0)
            if not amt:
                continue
            bucket["amount"] = round(bucket["amount"] - amt, 2)
            g = widgets.get(stage)
            if g is not None:
                g["amount"] = round(g["amount"] - amt, 2)
                if g.get(payroll_key) is not None:
                    g[payroll_key] = round(g[payroll_key] - amt, 2)

    # ── Бюджет ФЭО / Запланировано / Свободно (всегда) ──────────────────────
    on_demand_budget = await _on_demand_budget_planned_payroll(db, invisible_ids, rows_by_id)
    budget_payroll_amt: dict = {}
    planned_payroll_amt: dict = {}
    for row in invisible_rows:
        sid = row["id"]
        if "budget_payroll" in row:
            b_amt = row.get("budget_payroll") or 0.0
            row["budget_payroll"] = 0.0
        else:
            b_amt = (on_demand_budget.get(sid) or {}).get("feo_payroll", 0.0)
        if "planned_payroll" in row:
            p_amt = row.get("planned_payroll") or 0.0
            row["planned_payroll"] = 0.0
        else:
            p_amt = (on_demand_budget.get(sid) or {}).get("plan_payroll", 0.0)
        budget_payroll_amt[sid] = b_amt
        planned_payroll_amt[sid] = p_amt
        if b_amt and row.get("feo_budget_total") is not None:
            row["feo_budget_total"] = round(row["feo_budget_total"] - b_amt, 2)
            # ИСПРАВЛЕНО (D3, живая приёмка 21.10.2026, ДНР id 61): "calculated_budget"
            # и "feo_budget_total" — ОДНО И ТО ЖЕ число (dashboard_charts.py кладёт
            # budget_basis в оба ключа отдельными строками, см. её docstring) — но
            # calculated_budget читает фронт (useFeoTreeAmounts.selectedBudget,
            # ПЕРВЫМ, до feo_budget_total) для карточек «Бюджет (ФЭО)»/«Свободно»/
            # «Остаток субсидии». Раньше вычищался только feo_budget_total —
            # calculated_budget оставался НЕОЧИЩЕННЫМ, и фронт показывал владельческое
            # число целиком (ПРАВИЛО №6 — один показатель, значит оба ключа одного
            # показателя синхронно, не отдельно).
            if row.get("calculated_budget") is not None:
                row["calculated_budget"] = row["feo_budget_total"]
        if p_amt:
            row["total_feo_planned"] = round((row.get("total_feo_planned") or 0.0) - p_amt, 2)
            # ИСПРАВЛЕНО (D6, живая приёмка 21.10.2026, ДНР id 61): "planned_tree" —
            # «единый источник: план дерева ФЭО» (см. dashboard_charts.py docstring
            # у этого поля) — ИМЕННО его читает сводная таблица субсидий/панель
            # итогов (SubsidiesView.vue: `planned: s.planned_tree ?? s.total_planned`)
            # и фолбэк useFeoTreeAmounts.selectedPlannedTotal. "total_feo_planned"
            # выше — другое, более старое поле (Σ FeoPlannedItem.amount), вычищалось
            # оно одно — planned_tree оставался владельческим числом целиком, из-за
            # чего сводная таблица у сотрудника показывала «Запланировано» и
            # «Свободно» не по той формуле/не вычищенными (budget уже вычищен,
            # план — нет, разность уходила в минус).
            if row.get("planned_tree") is not None:
                row["planned_tree"] = round(row["planned_tree"] - p_amt, 2)
        if (b_amt or p_amt) and row.get("remaining") is not None:
            # Та же формула, что subsidy_money_summary.free_basis = budget_basis
            # − planned, просто на уже вычищенных значениях (не вторая формула).
            row["remaining"] = round(row["remaining"] - b_amt + p_amt, 2)

    # ── Остаток субсидии (balance_paid_marked/confirmed, balance_by_marks/
    # by_statement) — переиспользует тот же источник, что и сама расшифровка. ──
    balance_payroll = await _payroll_balance_amounts(db, invisible_ids)
    for row in invisible_rows:
        sid = row["id"]
        bp = balance_payroll.get(sid) or {}
        marked_amt = bp.get("paid_marked", 0.0) or 0.0
        confirmed_amt = bp.get("paid_confirmed", 0.0) or 0.0
        b_amt = budget_payroll_amt.get(sid, 0.0)
        # ИСПРАВЛЕНО (D5, живая приёмка 21.10.2026, ДНР id 61): раньше пропускали
        # ВСЮ строку (continue), когда у субсидии нет ОПЛАЧЕННЫХ закупок ФОТ
        # (bp пуст) — у ДНР статья ФОТ есть (бюджет 33 881 012,80), но закупок
        # ФОТ нет вовсе, поэтому marked_amt/confirmed_amt всегда 0, и
        # balance_by_marks/by_statement («Остаток субсидии») оставались
        # НЕВЫЧИЩЕННЫМИ (budget_basis целиком, включая ФОТ). «Остаток» обязан
        # вычитать payroll-долю БЮДЖЕТА (b_amt) независимо от того, была ли по
        # ФОТ хоть одна оплата — иначе это другая формула для subsidies с
        # ФОТ-бюджетом без ФОТ-закупок, чем для subsidies с ФОТ-закупками
        # (ПРАВИЛО №6, одна формула для всех).
        if not marked_amt and not confirmed_amt and not b_amt:
            continue
        if marked_amt and row.get("balance_paid_marked") is not None:
            row["balance_paid_marked"] = round(row["balance_paid_marked"] - marked_amt, 2)
        if confirmed_amt and row.get("balance_paid_confirmed") is not None:
            row["balance_paid_confirmed"] = round(row["balance_paid_confirmed"] - confirmed_amt, 2)
        if (marked_amt or b_amt) and row.get("balance_by_marks") is not None:
            row["balance_by_marks"] = round(row["balance_by_marks"] + marked_amt - b_amt, 2)
        if (confirmed_amt or b_amt) and row.get("balance_by_statement") is not None:
            row["balance_by_statement"] = round(row["balance_by_statement"] + confirmed_amt - b_amt, 2)

    if dashboard_type_totals is not None:
        for key in ("budget_payroll", "planned_payroll"):
            if key not in dashboard_type_totals:
                continue
            # dashboard_type_totals — Σ уже ОБНУЛЁННЫХ по невидимым строкам
            # row[key] (цикл выше отработал раньше) — пересуммировать дешевле,
            # чем трекать дельты, и это не вторая формула (Σ той же колонки).
            dashboard_type_totals[key] = round(
                sum((r.get(key) or 0.0) for r in subsidy_stats), 2,
            )


async def strip_invisible_payroll_drill_rows(
    user: User, db: AsyncSession, sid_list, result: dict,
    *, amount_key: str = "amount", total_key: str = "total",
) -> dict:
    """Общий фильтр построчных окон-расшифровок (dashboard_metric_drill.py,
    ПРАВИЛО №6 — одна проверка для всех): строки ФОТ субсидий, где у user
    нет subsidy.view_payroll, убираются из result["rows"], result["total"]
    уменьшается на их Σ amount. result["card_total"] НЕ трогаем — он должен
    остаться тем же (уже скрабленным) числом, что отдаёт /dashboard/charts
    (scrub_payroll_from_dashboard_charts) для карточки; расхождение
    total/card_total для ЭТОГО пользователя ожидаемо и уже показывается
    фронтом как предупреждение (MetricDrillDialog.vue mismatch), владелец
    такого сценария не просил — здесь только убираем строки, не подгоняем.

    Строка — ФОТ, если: у неё purchase_id → purchase_payroll_map (закупка
    эффективно ФОТ); иначе (row_type='planned_item') → её feo_category_id
    (или category id предка) входит в payroll_category_ids() субсидии
    (feo_payroll.py — ЕДИНСТВЕННАЯ формула «это ФОТ», вторая не вводится)."""
    from app.services.feo_payroll import payroll_category_ids, purchase_payroll_map

    sid_list = list(sid_list)
    if not sid_list or not result.get("rows"):
        return result
    invisible = set(sid_list) - await payroll_visible_subsidy_ids(user, db, sid_list)
    if not invisible:
        return result

    rows = result["rows"]
    purchase_ids = {r["purchase_id"] for r in rows if r.get("purchase_id") is not None}
    pmap = await purchase_payroll_map(db, purchase_ids) if purchase_ids else {}
    payroll_cat_ids = await payroll_category_ids(db, invisible)

    kept = []
    removed_amount = 0.0
    for r in rows:
        sid = r.get("subsidy_id")
        if sid in invisible:
            is_payroll_row = False
            if r.get("purchase_id") is not None:
                is_payroll_row = bool(pmap.get(r["purchase_id"]))
            elif r.get("feo_category_id") is not None:
                is_payroll_row = r["feo_category_id"] in payroll_cat_ids
            if is_payroll_row:
                removed_amount += r.get(amount_key, 0.0) or 0.0
                continue
        kept.append(r)
    result["rows"] = kept
    if removed_amount:
        result[total_key] = round((result.get(total_key) or 0.0) - removed_amount, 2)
    return result


async def hidden_payroll_category_ids(user: User, db: AsyncSession, subsidy_ids) -> set[int]:
    """Set FeoCategory.id (себя + поддерево), которые НЕ положено видеть user
    по праву subsidy.view_payroll — для субсидий из subsidy_ids, где право
    есть или ФОТ-статей нет вовсе, возвращает пустой вклад (ничего скрывать).
    Единственная формула «категория — ФОТ (с наследованием)» — feo_payroll.
    payroll_category_ids (ПРАВИЛО №6); эта функция добавляет ТОЛЬКО проверку
    права поверх неё. Используется деревом ФЭО (feo_categories.py/
    feo_planned_items.py, часть 4 плана 21.10.2026) — узлы с id из результата
    убираются из ответа целиком (и сами, и их план)."""
    from app.services.feo_payroll import payroll_category_ids

    subsidy_ids = list(dict.fromkeys(sid for sid in subsidy_ids if sid is not None))
    if not subsidy_ids:
        return set()
    visible = await payroll_visible_subsidy_ids(user, db, subsidy_ids)
    invisible = set(subsidy_ids) - visible
    if not invisible:
        return set()
    return await payroll_category_ids(db, invisible)


async def exclude_hidden_payroll_purchases(query, user: User, db: AsyncSession):
    """ЕДИНСТВЕННОЕ место, добавляющее `WHERE Purchase.id NOT IN (...)` для
    закупок ФОТ скрытых субсидий — вызывать на КАЖДЫЙ select(Purchase), из
    которого закупки уходят пользователю напрямую (списки/канбан), а не
    только на GET /api/purchases/ (найдено координатором 21.10.2026: /purchases/
    my-tasks и /purchases/kanban-all строят СВОИ select(Purchase), в обход
    list_purchases). Перф — short-circuit через feo_payroll.
    subsidy_ids_with_payroll (их единицы на проде), см. её докстринг."""
    from sqlalchemy import select as _select
    from app.models.purchase import Purchase
    from app.services.feo_payroll import payroll_purchase_ids_for_subsidies, subsidy_ids_with_payroll

    payroll_sids = await subsidy_ids_with_payroll(db)
    if not payroll_sids:
        return query
    visible = await payroll_visible_subsidy_ids(user, db, payroll_sids)
    invisible_sids = payroll_sids - visible
    if not invisible_sids:
        return query
    hidden_ids = await payroll_purchase_ids_for_subsidies(db, invisible_sids)
    if not hidden_ids:
        return query
    return query.where(~Purchase.id.in_(hidden_ids))


# Поля узла дерева ФЭО (GET /feo-categories/plan-tree, app.routers.
# feo_plan_reads_tree), которые СУММИРУЮТСЯ снизу вверх (ребёнок → родитель)
# — у них предок несёт Σ своего поддерева, поэтому убрать ветку ФОТ из
# ответа целиком (hidden_payroll_category_ids) ещё не убирает её вклад из
# ПРЕДКОВ/итога субсидии — находка владельца 21.10.2026, часть 3 плана
# «Видеть ФОТ». Поля-флаги/признаки превышения (excess_amount/excess_pending/
# excess_approved и т.п.) здесь НЕ перечислены — они не аддитивны по дереву
# (это состояние узла, не Σ поддерева), трогать их второй формулой не нужно.
_ADDITIVE_TREE_FIELDS = (
    "plan_manual", "plan_items_raw", "order_overspend", "order_economy",
    "ordered_qty", "ordered_sum", "plan", "budget", "display", "residual",
    "forecast", "forecast_over", "consumed", "consumed_quantity", "qty_plan",
    "display_quantity", "fact", "fact_quantity", "plan_goods", "plan_services",
    "plan_unspecified", "feo_goods", "feo_services", "feo_unspecified",
    "fact_goods", "fact_services", "fact_unspecified", "paid_marked",
    "paid_confirmed", "plan_floor_added",
    # ПРАВИЛО №6 (22.10.2026) — plan_typed_goods/services (typed-базис
    # excess_plan_over_feo_*, app.services.feo_type_excess_basis) аддитивны
    # по тому же построению, что и plan_goods/plan_services (разница —
    # вычитаемое exclusion тоже Σ по поддереву, см. её докстринг), поэтому
    # ФОТ-ветка вычитается из них ТЕМ ЖЕ способом.
    "plan_typed_goods", "plan_typed_services",
)


def strip_hidden_payroll_from_tree_result(
    tree: dict, result: dict, hidden_cat_ids: set,
) -> None:
    """Пост-обработка ответа GET /feo-categories/plan-tree (мутирует `result`
    IN PLACE, вызывается ПОСЛЕ обычного построения result, ПЕРЕД тем, как
    вызывающий код убирает ключи hidden_cat_ids из result) — вычитает из
    КАЖДОГО ПРЕДКА скрытой ветки ФОТ (и из корня, транзитивно) числовые
    аддитивные поля этой ветки, чтобы Σ видимых дочерних узлов СОВПАДАЛА с
    суммой предка/корня (владелец 21.10.2026, часть 3 — «итог дерева без
    права должен быть равен Σ видимых строк»).

    НЕ строит дерево заново и НЕ трогает `tree` (кэш compute_feo_plan_tree) —
    читает его ТОЛЬКО для parent_id (узлы с кэша read-only), значения берёт
    из уже спроецированного `result` (если у узла деньги уже null —
    feo_budget.view_tree_amounts запретил их раньше, вычитать из None нечего,
    пропускаем). Вычитает значение ТОЛЬКО с «верхних» узлов скрытого
    поддерева (parent не входит в hidden_cat_ids) — вложенные ФОТ-категории
    внутри уже вычтены как часть Σ родителя-ФОТ, повторное вычитание их же
    отдельно было бы задвоением (их own-вклад уже включён в rolled-up число
    узла-родителя-ФОТ, см. compute_feo_plan_tree — суммирование снизу вверх)."""
    if not hidden_cat_ids:
        return
    roots_to_subtract = [
        cid for cid in hidden_cat_ids
        if (tree.get(cid) or {}).get("parent_id") not in hidden_cat_ids
    ]
    for cat_id in roots_to_subtract:
        node = result.get(cat_id) or tree.get(cat_id)
        if node is None:
            continue
        parent_id = (tree.get(cat_id) or {}).get("parent_id")
        while parent_id is not None:
            ancestor = result.get(parent_id)
            if ancestor is None:
                break
            for field in _ADDITIVE_TREE_FIELDS:
                amt = node.get(field)
                cur = ancestor.get(field)
                if amt is None or cur is None:
                    continue
                ancestor[field] = round(float(cur) - float(amt), 2)
            parent_id = (tree.get(parent_id) or {}).get("parent_id")


def strip_hidden_payroll_from_type_totals(type_totals: Optional[dict], hidden: bool) -> None:
    """subsidy_type_totals (compute_subsidy_type_summary) уже раскладывает
    Σ корневых узлов ПО ВИДУ (goods/services/payroll/unspecified, ПРАВИЛО
    №6, см. feo_plan_tree.compute_subsidy_type_summary) — ФОТ здесь уже
    СВОЙ вид, зануляем plan_payroll/feo_payroll/fact_payroll целиком, когда у
    субсидии есть хоть одна скрытая ФОТ-категория (hidden=True — остальные
    виды не трогаются, они не содержат вклад ФОТ по построению kind_of)."""
    if not hidden or not type_totals:
        return
    for key in ("plan_payroll", "feo_payroll", "fact_payroll"):
        if key in type_totals:
            type_totals[key] = 0.0


async def can_view_subsidy_payroll(user: User, db: AsyncSession, subsidy_id: int, org_id=None) -> bool:
    """Точечная проверка для одной субсидии/закупки/статьи (GET по id → 404
    без права, см. ПРАВИЛО №8 п.2 — скрытая сущность отвечает как
    несуществующая). `org_id` можно передать, если уже известен (экономит
    один SELECT Subsidy); иначе подтягивается отсюда."""
    if user.role == "superadmin":
        return True
    if org_id is None:
        row = (await db.execute(select(Subsidy.org_id).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
        org_id = row
    return await has_org_key(user, db, org_id, ACTION_KEY, subsidy_id=subsidy_id)
