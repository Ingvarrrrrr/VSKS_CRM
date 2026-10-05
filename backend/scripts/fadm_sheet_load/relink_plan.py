"""--relink, шаг 1: позиционная реконструкция «какая закупка создана какой
строкой/группой таблицы» — БЕЗ task_comment.

Находка на проде (id=80, задача 04.10.2026): build.py действительно
проставляет `task_comment=f"Таблица: закупка {...}"` в PurchaseCreate, но
схема `app.schemas.purchases.PurchaseCreate` НЕ объявляет поле task_comment
вообще — pydantic молча отбрасывает незнакомый kwarg (extra не forbid), и
insert_purchase_with_items его никогда не видит. Проверено SQL на проде:
`SELECT task_comment FROM purchases WHERE subsidy_id=80` — ВСЕ 136 строк
task_comment IS NULL. Метка никогда не долетала до БД ни у одной закупки.
Это отдельный баг (см. __main__.py::main — build.py здесь же поправлен, чтобы
будущие прогоны проставляли её напрямую через ORM-атрибут после insert, а не
через схему).

Раз метки нет, единственный надёжный способ сопоставить уже существующую
закупку субсидии со строкой таблицы — ПОЗИЦИОННЫЙ: build.py и match_only.py
строят ОДНУ и ту же последовательность «событий создания закупки» из ОДНОГО
и того же (groups, matches) — детерминированно, без побочных веток (нет
try/except, которые могли бы пропустить группу). Поэтому: пересобрать ту же
последовательность здесь (build_creation_plan, порядок ТОЧНО как в
run_build::for group in groups: monthly → framework → single) и склеить (zip)
её с Purchase.subsidy_id==target.id ORDER BY id ASC — тот же порядок, в
котором build.py их создавал (один процесс, без параллелизма, автоинкремент
id изнутри транзакции). Длины ДОЛЖНЫ совпасть (136 на проде, проверено
пересчётом из CSV, scripts/data/fadm_2026_sheet.csv, без обращения к БД:
71 single + 5 monthly + 11 framework heads + 49 framework orders = 136,
совпадает с count(*) на проде); несовпадение — сигнал, что её собирали НЕ
этим build.py (другая версия CSV/правок) — тогда relink ОБЯЗАН остановиться
(RelinkPlanMismatch), а не гадать парами по смещению.

Прод-субсидия id=80 создана СТАРЫМ build.py (до правок 04.10.2026 этой
сессии) — порядок обхода здесь строится из parse.py/match.py (group_rows/
iter_match_units/run_matching), которых правки build.py НЕ касались вообще
(только постфактум-присвоение полей на УЖЕ созданном Purchase). Порядок
«group → (monthly|framework head+orders|single)» идентичен старому и новому
build.py — см. run_build в обеих версиях.

Страховка (владелец, правки после прод-отчёта): совпадение длин — условие
НЕОБХОДИМОЕ, но НЕ достаточное (две разные закупки могли случайно оказаться
на тех же позициях). zip_plan_with_purchases ДОПОЛНИТЕЛЬНО сверяет КАЖДУЮ
пару:
  1) сумма — match._canonical_amount (тот же каскад contract_price →
     final_total_amount → planned_total_price → Σ PurchaseItem.total_price,
     ПРАВИЛО №6 — не второй расчёт) закупки из БД == ожидаемая сумма этой
     единицы плана (PlanEntry.expected_amount — Σ сумм её строк CSV: для
     головы рамочного это Σ ВСЕХ строк группы, т.к. все они размещены в её
     заказах), допуск 0.01 ₽;
  2) тип — голова рамочного: purchase_contract_type начинается с 'framework'
     И parent_purchase_id IS NULL; заказ: parent_purchase_id указывает ИМЕННО
     на закупку, сопоставленную голове ЭТОЙ ЖЕ группы (не любую голову);
     помесячная: is_monthly_payment; разовая: не помесячная и не framework-тип.
Любое расхождение (хоть по сумме, хоть по типу) → RelinkPlanMismatch со
списком первых 10 расхождений — транзакция откатывается вызывающим
(__main__.py), ничего не пишется."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .match import OldPurchase, _canonical_amount
from .parse import PurchaseGroup, SheetRow, is_monthly_group

AMOUNT_TOLERANCE = Decimal("0.01")


class RelinkPlanMismatch(Exception):
    pass


@dataclass
class PlanEntry:
    role: str                       # 'single' | 'monthly' | 'framework_head' | 'framework_order'
    group: PurchaseGroup
    order_no: Optional[str]
    twin: Optional[OldPurchase]      # СВОЙ двойник по ключу этой единицы (НЕ head-фолбэк)
    label: str
    expected_amount: Decimal = Decimal("0")


def build_creation_plan(groups: list[PurchaseGroup], matches: dict) -> list[PlanEntry]:
    """ТОЧНО тот же порядок обхода, что run_build (build.py) — см. докстринг
    модуля. Не вызывать отдельно от того же (groups, matches), что отдал
    match.run_matching на ЭТОМ ЖЕ прогоне (match.Matcher стейтфул)."""
    plan: list[PlanEntry] = []
    for g in groups:
        if is_monthly_group(g):
            key = (g.contractor_norm, g.purchase_no, None)
            m = matches.get(key)
            plan.append(PlanEntry(
                role="monthly", group=g, order_no=None, twin=m.twin if m else None,
                label=f"{g.contractor} №{g.purchase_no} (помесячная)",
                expected_amount=g.total_amount,
            ))
            continue

        if len(g.distinct_order_nos) >= 2:
            head_key = (g.contractor_norm, g.purchase_no, None)
            head_match = matches.get(head_key)
            plan.append(PlanEntry(
                role="framework_head", group=g, order_no=None,
                twin=head_match.twin if head_match else None,
                label=f"{g.contractor} №{g.purchase_no} (рамочная голова)",
                expected_amount=g.total_amount,  # Σ всех заказов — голова сама по себе без суммы
            ))
            order_rows: dict[str, list[SheetRow]] = {}
            for r in g.rows:
                order_rows.setdefault(r.order_no or "", []).append(r)
            for order_no, rows in order_rows.items():
                key = (g.contractor_norm, g.purchase_no, order_no)
                m = matches.get(key)
                plan.append(PlanEntry(
                    role="framework_order", group=g, order_no=order_no, twin=m.twin if m else None,
                    label=f"{g.contractor} №{g.purchase_no}, заказ {order_no}",
                    expected_amount=sum((r.amount for r in rows), Decimal("0")),
                ))
            continue

        key = (g.contractor_norm, g.purchase_no, None)
        m = matches.get(key)
        plan.append(PlanEntry(
            role="single", group=g, order_no=None, twin=m.twin if m else None,
            label=f"{g.contractor} №{g.purchase_no}",
            expected_amount=g.total_amount,
        ))
    return plan


def _is_framework_type(purchase) -> bool:
    t = getattr(purchase, "purchase_contract_type", None)
    return bool(t and t.startswith("framework"))


def _purchase_amount(purchase) -> Decimal:
    item_totals = [Decimal(str(it.total_price)) for it in purchase.items if it.total_price is not None]
    return _canonical_amount(purchase, item_totals)


def zip_plan_with_purchases(plan: list[PlanEntry], purchases: list) -> list[tuple[PlanEntry, object]]:
    """purchases — Purchase.subsidy_id==target.id ORDER BY id ASC. Бросает
    RelinkPlanMismatch при расхождении длин — см. докстринг модуля (НЕ
    привязывать по смещению вслепую)."""
    if len(plan) != len(purchases):
        raise RelinkPlanMismatch(
            f"Реконструированный план создания ({len(plan)} закупок) не совпадает "
            f"с фактическим числом закупок целевой субсидии ({len(purchases)}) — "
            f"возможно, субсидия создана другой версией CSV/build.py. Останов без записи."
        )
    pairs = list(zip(plan, purchases))

    # Голова нужна ДО основного цикла — заказ сверяется, что его parent_purchase_id
    # указывает именно на закупку, сопоставленную ГОЛОВЕ ЕГО ЖЕ группы.
    head_purchase_by_group_id: dict[int, object] = {
        id(entry.group): purchase for entry, purchase in pairs if entry.role == "framework_head"
    }

    mismatches: list[str] = []
    for idx, (entry, purchase) in enumerate(pairs):
        actual_amount = _purchase_amount(purchase)
        amount_ok = abs(actual_amount - entry.expected_amount) <= AMOUNT_TOLERANCE

        if entry.role == "framework_head":
            type_ok = _is_framework_type(purchase) and purchase.parent_purchase_id is None
        elif entry.role == "framework_order":
            head_purchase = head_purchase_by_group_id.get(id(entry.group))
            type_ok = (
                purchase.parent_purchase_id is not None
                and head_purchase is not None
                and purchase.parent_purchase_id == head_purchase.id
            )
        elif entry.role == "monthly":
            type_ok = bool(purchase.is_monthly_payment)
        else:  # single
            type_ok = not purchase.is_monthly_payment and not _is_framework_type(purchase)

        if not (amount_ok and type_ok):
            mismatches.append(
                f"#{idx}: план «{entry.label}» (роль={entry.role}, ожидалось {entry.expected_amount}) "
                f"↔ закупка id={purchase.id} (сумма={actual_amount}, amount_ok={amount_ok}, type_ok={type_ok})"
            )

    if mismatches:
        raise RelinkPlanMismatch(
            f"Позиционная сверка провалена ({len(mismatches)} расхождений из {len(pairs)}), "
            f"первые {min(10, len(mismatches))}:\n" + "\n".join(mismatches[:10])
        )

    return pairs
