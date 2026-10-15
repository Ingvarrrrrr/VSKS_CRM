"""monthly_future_payments.py — ЕДИНСТВЕННОЕ место расчёта «ещё уйдёт
помесячно до конца года» (план владельца abstract-noodling-pelican.md, разделы
🟡/🟢/🔵, п.B, 15.10.2026) и месяца заказа рамочного договора.

Два источника месячных платежей (ПРАВИЛО №6 — ни один не дублирует другой):
  (а) framework_order — заказы рамочных договоров (Purchase.parent_purchase_id
      IS NOT NULL, status='contracted' — app.services.stage_cumulative.
      reserved_child_predicate()). Сам договор — организационная запись без
      своей суммы, платит каждый размещённый внутри заказ отдельно. Месяц
      заказа, по порядку источников (владелец, правки 🟢2/🔵3):
        1. Purchase.planned_payment_month, если заполнено;
        2. иначе, если у заказа задан период оказания услуги
           (service_start_date (+service_end_date)) — заказ считается ОДНИМ
           месяцем (month = месяц service_start_date), ЕСЛИ period вообще не
           задан (end отсутствует/не позже start); если период РЕАЛЬНО
           растянут на несколько месяцев (service_end_date > service_start_date),
           сумма заказа делится по месяцам ТОЙ ЖЕ календарной формулой
           (app.services.feo_monthly_schedule.split_amount_by_calendar_period)
           пропорционально дням — тогда у заказа НЕСКОЛЬКО строк (по одной на
           месяц), не одна;
        3. иначе — по порядку purchase_number среди ВСЕХ неостановленных
           заказов ТОГО ЖЕ родителя (parent_purchase_id): последний (самый
           большой номер) = декабрь года субсидии, каждый заказ с бОльшим
           номером сдвигает месяц текущего на месяц раньше.
      Для «ещё уйдёт» считаются ТОЛЬКО месяцы ПОСЛЕ текущего (месяц > today).
      Месяцы ≤ текущего — «занято» (см. app.services.committed_amounts).

      SQL-эквивалент источников 1+3 (БЕЗ разбиения периода по дням — для
      ОДНОЙ границы «этот месяц уже начался или нет», используемой в
      committed_status_predicate при массовых WHERE-агрегатах, период
      service_start_date, если он задан, тоже учитывается как месяц без
      разбиения — см. докстринг framework_child_month_expr) —
      framework_child_month_expr() ниже. Источник 2 с РЕАЛЬНЫМ разбиением по
      дням (несколько месяцев на один заказ) считается ТОЛЬКО на построчном,
      python-уровне (monthly_future_rows/framework_order_month_rows) — две
      формы одного правила: SQL не умеет вызвать calendar_month_payments, а
      bulk-предикату committed_status_predicate для единственной проверки
      «месяц уже начался?» разбиение по дням и не нужно (span начинается с
      service_start_date в любом случае).

  (б) monthly_contract — помесячные договоры с графиком платежей
      (Purchase.is_monthly_payment=True) — уже разбирает ПОСТРОЧНО
      app.services.dashboard_monthly_accrual.compute_monthly_future_rows
      (calendar_month_payments, текущий месяц там уже считается начатым —
      ПЕРЕИСПОЛЬЗУЕТСЯ здесь, не копируется).

Читают этот модуль:
  - карточка «Заключено договоров» (dashboard_charts.py, строка
    monthly_future_to_year_end) — monthly_future_totals_by_subsidy();
  - карточка «Можно перераспределить» (subsidy_money_summary.py/
    redistributable_raw.py, поле monthly_future_not_started) — ТОЛЬКО
    источник (а): договор с графиком (б) уже занимает деньги в момент
    заключения, его сумма НЕ подлежит перераспределению;
  - окно «ещё уйдёт помесячно» (дерево договор → месяцы) — monthly_future_rows().
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.feo_monthly_schedule import split_amount_by_calendar_period
from app.services.purchase_amounts import effective_amount_expr
from app.services.stage_cumulative import reserved_child_predicate

SOURCE_FRAMEWORK_ORDER = "framework_order"
SOURCE_MONTHLY_CONTRACT = "monthly_contract"


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def framework_child_month_expr(purchase=Purchase, subsidy_year_col=Subsidy.year):
    """SQL-выражение (-> date, 1-е число месяца) месяца заказа рамочного
    договора — используется committed_status_predicate (app.services.
    committed_amounts) для единственной проверки «этот заказ уже начал
    действовать (committed) или ещё нет» в массовых WHERE-агрегатах, без
    разбиения суммы по дням (см. докстринг модуля за объяснением, почему это
    не вторая формула, а другая форма той же):

        coalesce(
            date_trunc('month', planned_payment_month),
            date_trunc('month', service_start_date),
            декабрь года субсидии − число неостановленных заказов ТОГО ЖЕ
            родителя (parent_purchase_id) с БОЛЬШИМ purchase_number,
        )

    Вызывающий код обязан СОЕДИНИТЬ запрос с Subsidy (или передать
    subsidy_year_col — любое выражение года субсидии из уже выполненного
    JOIN), месяц без известного года субсидии не определить."""
    sibling = aliased(Purchase)
    greater_siblings = (
        select(func.count())
        .select_from(sibling)
        .where(sibling.parent_purchase_id == purchase.parent_purchase_id)
        .where(sibling.stopped_at.is_(None))
        .where(sibling.purchase_number > purchase.purchase_number)
        .correlate(purchase)
        .scalar_subquery()
    )
    december_first = func.make_date(subsidy_year_col, 12, 1)
    order_based_month = cast(
        december_first - func.make_interval(0, cast(greater_siblings, Integer)),
        Date,
    )
    return func.coalesce(
        func.date_trunc("month", purchase.planned_payment_month),
        func.date_trunc("month", purchase.service_start_date),
        order_based_month,
    )


async def framework_order_month_rows(
    db: AsyncSession, subsidy_ids: Optional[list] = None,
) -> list:
    """[{contract_id, parent_purchase_id, purchase_id, purchase_number,
    subject, subsidy_id, month, amount, source='framework_order'}] — ВСЕ
    (не только будущие) строки заказов рамочных договоров, с разбиением по
    дням для заказов, у которых задан РЕАЛЬНЫЙ период (service_end_date >
    service_start_date, источник 2 докстринга модуля) — такой заказ даёт
    НЕСКОЛЬКО строк, по одной на месяц. Остальные (planned_payment_month,
    одномесячный service_start_date без периода, по порядку номеров) — ОДНА
    строка на заказ, на полную сумму effective_amount_expr().

    Построено на Python-уровне (не framework_child_month_expr) — нужно
    разбиение суммы по дням, которое SQL здесь не делает (см. докстринг
    модуля)."""
    stmt = (
        select(
            Purchase.id, Purchase.parent_purchase_id, Purchase.purchase_number,
            Purchase.subject, Purchase.item_name, Purchase.subsidy_id,
            Purchase.planned_payment_month, Purchase.service_start_date, Purchase.service_end_date,
            Subsidy.year.label("subsidy_year"),
            effective_amount_expr().label("amount"),
        )
        .join(Subsidy, Subsidy.id == Purchase.subsidy_id)
        .where(reserved_child_predicate())
        .where(Purchase.stopped_at.is_(None))
    )
    if subsidy_ids is not None:
        if not subsidy_ids:
            return []
        stmt = stmt.where(Purchase.subsidy_id.in_(subsidy_ids))
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    # Группировка по родителю — для правила «по порядку номеров» (источник 3)
    # нужны ВСЕ неостановленные заказы ТОГО ЖЕ родителя, не только те, что
    # попали в subsidy_ids выше (родитель всегда в той же субсидии, что и
    # дети — фильтр subsidy_ids не теряет siblings).
    by_parent: dict = {}
    for r in rows:
        by_parent.setdefault(r.parent_purchase_id, []).append(r)

    out: list = []
    for parent_id, siblings in by_parent.items():
        siblings_sorted = sorted(siblings, key=lambda r: (r.purchase_number is None, r.purchase_number or 0))
        n = len(siblings_sorted)
        for idx, r in enumerate(siblings_sorted):
            subsidy_year = r.subsidy_year
            subject = r.subject or r.item_name
            amount = float(r.amount or 0)
            # Источник 1 — planned_payment_month.
            if r.planned_payment_month is not None:
                out.append({
                    "contract_id": parent_id, "parent_purchase_id": parent_id,
                    "purchase_id": r.id, "purchase_number": r.purchase_number,
                    "subject": subject, "subsidy_id": r.subsidy_id,
                    "month": _month_start(r.planned_payment_month), "amount": amount,
                    "source": SOURCE_FRAMEWORK_ORDER,
                })
                continue
            # Источник 2 — период оказания услуги.
            if r.service_start_date is not None:
                if r.service_end_date is not None and r.service_end_date > r.service_start_date:
                    payments = split_amount_by_calendar_period(
                        r.service_start_date, r.service_end_date, Decimal(str(amount)),
                    )
                    for p in payments:
                        out.append({
                            "contract_id": parent_id, "parent_purchase_id": parent_id,
                            "purchase_id": r.id, "purchase_number": r.purchase_number,
                            "subject": subject, "subsidy_id": r.subsidy_id,
                            "month": p.month, "amount": float(p.amount),
                            "source": SOURCE_FRAMEWORK_ORDER,
                        })
                    continue
                out.append({
                    "contract_id": parent_id, "parent_purchase_id": parent_id,
                    "purchase_id": r.id, "purchase_number": r.purchase_number,
                    "subject": subject, "subsidy_id": r.subsidy_id,
                    "month": _month_start(r.service_start_date), "amount": amount,
                    "source": SOURCE_FRAMEWORK_ORDER,
                })
                continue
            # Источник 3 — по порядку номеров: последний (самый большой номер
            # среди СУЩЕСТВУЮЩИХ в выборке siblings) = декабрь года субсидии,
            # остальные — по месяцу раньше на каждого «более старшего» соседа.
            if subsidy_year is None:
                continue  # нечем ограничить месяц — пропускаем (не должно случаться, FK NOT NULL)
            greater_count = n - 1 - idx
            y, m = subsidy_year, 12 - greater_count
            while m <= 0:
                m += 12
                y -= 1
            out.append({
                "contract_id": parent_id, "parent_purchase_id": parent_id,
                "purchase_id": r.id, "purchase_number": r.purchase_number,
                "subject": subject, "subsidy_id": r.subsidy_id,
                "month": date(y, m, 1), "amount": amount,
                "source": SOURCE_FRAMEWORK_ORDER,
            })
    return out


async def monthly_future_rows(
    db: AsyncSession, subsidy_ids: list, today: Optional[date] = None,
) -> list:
    """[{contract_id, parent_purchase_id, purchase_id, purchase_number,
    subject, month, amount, source}] — строки «ещё уйдёт помесячно до конца
    года», ОБЪЕДИНЕНИЕ источников (а)+(б), ТОЛЬКО месяцы ПОСЛЕ текущего
    (`today`, параметр — для тестов; по умолчанию date.today()). Источник (б)
    — app.services.dashboard_monthly_accrual.compute_monthly_future_rows,
    ПЕРЕИСПОЛЬЗУЕТСЯ (ПРАВИЛО №6), month не разбит по месяцам внутри одного
    заказа (там уже даётся готовая Σ будущих месяцев ОДНОЙ строкой на
    покупку — у неё month=None, для дерева «договор → месяцы» это итоговая
    ветка без дальнейшего деления; на проде таких договоров 0)."""
    today = today or date.today()
    cur_month = _month_start(today)

    fw_rows = await framework_order_month_rows(db, subsidy_ids)
    out = [r for r in fw_rows if r["month"] is not None and r["month"] > cur_month]

    def _apply_filter(q):
        return q.where(Purchase.subsidy_id.in_(subsidy_ids)) if subsidy_ids else q

    if subsidy_ids:
        from app.services.dashboard_monthly_accrual import compute_monthly_future_rows as _mc_future_rows
        mc_rows = await _mc_future_rows(db, _apply_filter, today=today)
        for r in mc_rows:
            out.append({
                "contract_id": r["purchase_id"], "parent_purchase_id": None,
                "purchase_id": r["purchase_id"], "purchase_number": None, "subject": None,
                "subsidy_id": r["subsidy_id"], "month": None, "amount": r["amount"],
                "source": SOURCE_MONTHLY_CONTRACT,
            })
    return out


async def monthly_future_totals_by_subsidy(
    db: AsyncSession, subsidy_ids: list, today: Optional[date] = None,
) -> dict:
    """{subsidy_id: {"framework_order": float, "monthly_contract": float,
    "total": float}} — ЕДИНСТВЕННЫЙ агрегат карточки «ещё уйдёт помесячно до
    конца года» (dashboard_charts.py::monthly_future_to_year_end), Σ
    monthly_future_rows по субсидии/источнику (ПРАВИЛО №6 — не вторая
    формула)."""
    result = {sid: {"framework_order": 0.0, "monthly_contract": 0.0, "total": 0.0} for sid in subsidy_ids}
    if not subsidy_ids:
        return result
    rows = await monthly_future_rows(db, subsidy_ids, today=today)
    for r in rows:
        d = result.setdefault(r["subsidy_id"], {"framework_order": 0.0, "monthly_contract": 0.0, "total": 0.0})
        d[r["source"]] += r["amount"]
        d["total"] += r["amount"]
    return result


async def monthly_future_not_started_by_subsidy(
    db: AsyncSession, subsidy_ids: list, today: Optional[date] = None,
) -> dict:
    """{subsidy_id: float} — строка «ещё уйдёт помесячно» карточки «Можно
    перераспределить» (поле monthly_future_not_started, план п.C): ТОЛЬКО
    источник (а) framework_order — договор с графиком (б) уже занимает деньги
    в момент заключения, перераспределить его нельзя (см. докстринг модуля)."""
    totals = await monthly_future_totals_by_subsidy(db, subsidy_ids, today=today)
    return {sid: d["framework_order"] for sid, d in totals.items()}
