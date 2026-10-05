"""Разовый загрузчик «ФАДМ 2026_2» — чтение CSV и группировка строк.

Формат CSV (готовит другой агент, фиксирован, см. docstring __main__.py):
    row;kind;status;basis;contractor;purchase_no;order_no;name;amount
UTF-8, разделитель «;». kind: goods|services. status: yes|monthly_future|
reserve|likely. order_no — строка, может быть «1,2» (несколько заказов/
месяцев одной строкой — см. ЕГОРОВА 6 в задании). amount — с точкой.

Группировка закупок: ключ = (нормализованный контрагент, purchase_no) —
задание владельца, п.1: «одинаковый номер у разных контрагентов — разные
закупки». reserve/likely НЕ группируются — каждая строка своя плановая
позиция (п.7 задания).
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from .contractor_norm import normalize_contractor_name

STATUS_YES = "yes"
STATUS_MONTHLY_FUTURE = "monthly_future"
STATUS_RESERVE = "reserve"
STATUS_LIKELY = "likely"
ROW_STATUSES = {STATUS_YES, STATUS_MONTHLY_FUTURE, STATUS_RESERVE, STATUS_LIKELY}
PLANNED_ITEM_STATUSES = {STATUS_RESERVE, STATUS_LIKELY}

KIND_GOODS = "goods"
KIND_SERVICES = "services"

# Правило владельца (п.2): группа признаётся помесячной, если встречается в
# этом списке — матч по ПОДСТРОКЕ нормализованного имени контрагента (та же
# практика, что matched по normalize_org_name везде в проекте), + её
# purchase_no как строка.
MONTHLY_FORCE_LIST: tuple[tuple[str, str], ...] = (
    ("ростелеком", "1"),
    ("предрейсовый", "8"),
    ("егорова", "6"),
    ("егорова", "98"),
    ("ремстрой", "2"),
)


@dataclass
class SheetRow:
    row: int
    kind: str
    status: str
    basis: str
    contractor: str
    purchase_no: str
    order_no: str
    name: str
    amount: Decimal

    @property
    def contractor_norm(self) -> str:
        return normalize_contractor_name(self.contractor)

    @property
    def order_tokens(self) -> list[str]:
        """order_no расщеплён по запятой («1,2» → ["1","2"]); пусто → []."""
        raw = (self.order_no or "").strip()
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]


@dataclass
class PurchaseGroup:
    contractor: str
    contractor_norm: str
    purchase_no: str
    rows: list[SheetRow] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.contractor_norm, self.purchase_no)

    @property
    def distinct_order_nos(self) -> list[str]:
        """Заказы рамочного — уникальные ЗНАЧЕНИЯ order_no (не расщеплённые
        токены: «1,2» как order_no рамочного заказа была бы одним заказом;
        расщепление на токены имеет смысл только для помесячных месяцев —
        см. docstring is_monthly_group/framework-ветки в build.py)."""
        seen: list[str] = []
        for r in self.rows:
            v = (r.order_no or "").strip()
            if v and v not in seen:
                seen.append(v)
        return seen

    @property
    def total_amount(self) -> Decimal:
        return sum((r.amount for r in self.rows), Decimal("0"))

    @property
    def kind_set(self) -> set:
        return {r.kind for r in self.rows}

    @property
    def first_name(self) -> str:
        return self.rows[0].name if self.rows else ""


def _parse_decimal(raw: str, row_num: int) -> Decimal:
    raw = (raw or "").strip().replace(" ", "").replace("\xa0", "")
    if not raw:
        raise ValueError(f"Строка {row_num}: пустая сумма")
    try:
        return Decimal(raw)
    except InvalidOperation as e:
        raise ValueError(f"Строка {row_num}: не могу разобрать сумму {raw!r}") from e


def parse_csv(path: str | Path) -> list[SheetRow]:
    path = Path(path)
    rows: list[SheetRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for raw in reader:
            if not raw or not (raw.get("row") or "").strip():
                continue
            try:
                row_num = int(str(raw["row"]).strip())
            except (KeyError, ValueError) as e:
                raise ValueError(f"Строка файла без валидного номера row: {raw!r}") from e
            kind = (raw.get("kind") or "").strip().lower()
            if kind not in (KIND_GOODS, KIND_SERVICES):
                raise ValueError(f"Строка {row_num}: неизвестный kind {kind!r}")
            status = (raw.get("status") or "").strip().lower()
            if status not in ROW_STATUSES:
                raise ValueError(f"Строка {row_num}: неизвестный status {status!r}")
            amount = _parse_decimal(raw.get("amount", ""), row_num)
            rows.append(SheetRow(
                row=row_num,
                kind=kind,
                status=status,
                basis=(raw.get("basis") or "").strip(),
                contractor=(raw.get("contractor") or "").strip(),
                purchase_no=(raw.get("purchase_no") or "").strip(),
                order_no=(raw.get("order_no") or "").strip(),
                name=(raw.get("name") or "").strip(),
                amount=amount,
            ))
    return rows


def is_monthly_group(group: PurchaseGroup) -> bool:
    """Правило №2 владельца: есть monthly_future ИЛИ пара (контрагент,
    purchase_no) есть в MONTHLY_FORCE_LIST (матч по подстроке)."""
    if any(r.status == STATUS_MONTHLY_FUTURE for r in group.rows):
        return True
    for substr, pno in MONTHLY_FORCE_LIST:
        if substr in group.contractor_norm and group.purchase_no == pno:
            return True
    return False


def monthly_schedule(group: PurchaseGroup) -> dict:
    """Параметры помесячной закупки (правило №2): monthly_payment_count — Σ
    расщеплённых месячных токенов order_no по всем строкам (строка «1,2» =
    2 месяца); monthly_payment_amount — самая частая точная сумма строки."""
    month_count = 0
    for r in group.rows:
        toks = r.order_tokens
        month_count += len(toks) if toks else 1
    amounts = Counter(r.amount for r in group.rows)
    monthly_amount = amounts.most_common(1)[0][0] if amounts else Decimal("0")
    return {
        "monthly_payment_count": month_count,
        "monthly_payment_amount": monthly_amount,
        "total_amount": group.total_amount,
    }


def group_rows(rows: list[SheetRow]) -> tuple[list[PurchaseGroup], list[SheetRow]]:
    """Возвращает (группы-закупки, строки reserve/likely без группировки)."""
    by_key: dict[tuple[str, str], PurchaseGroup] = {}
    planned_only: list[SheetRow] = []
    order: list[tuple[str, str]] = []
    for r in rows:
        if r.status in PLANNED_ITEM_STATUSES:
            planned_only.append(r)
            continue
        key = (r.contractor_norm, r.purchase_no)
        if key not in by_key:
            by_key[key] = PurchaseGroup(contractor=r.contractor, contractor_norm=r.contractor_norm, purchase_no=r.purchase_no)
            order.append(key)
        by_key[key].rows.append(r)
    groups = [by_key[k] for k in order]
    return groups, planned_only


def totals_by_kind(rows: list[SheetRow]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        out[r.kind] += r.amount
    return dict(out)


def totals_by_status(rows: list[SheetRow]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        out[r.status] += r.amount
    return dict(out)


@dataclass
class MatchUnit:
    """Единица сопоставления со старой субсидией И единица создания закупки —
    ОДИН и тот же объект для обоих (ПРАВИЛО №6: отчёт сопоставления и
    реальная раскладка не должны разойтись, используют общий список).

    Для разовой/помесячной группы unit = вся группа целиком. Для рамочной
    (≥2 различных order_no, не помесячная) — КАЖДЫЙ order_no свой unit
    (правило владельца, п.1в: «рамочные сопоставлять заказ за заказом»);
    сама рамочная ГОЛОВА не матчится вообще (организационная запись, у неё
    нет двойника в старой субсидии)."""
    kind: str                      # 'single' | 'monthly' | 'framework_order'
    label: str                     # человекочитаемая подпись для отчёта
    contractor: str
    contractor_norm: str
    purchase_no: str
    order_no: Optional[str]
    rows: list

    @property
    def key(self) -> tuple:
        return (self.contractor_norm, self.purchase_no, self.order_no)

    @property
    def total_amount(self) -> Decimal:
        return sum((r.amount for r in self.rows), Decimal("0"))

    @property
    def first_name(self) -> str:
        return self.rows[0].name if self.rows else ""


def iter_match_units(groups: list[PurchaseGroup]) -> list[MatchUnit]:
    units: list[MatchUnit] = []
    for g in groups:
        if is_monthly_group(g):
            units.append(MatchUnit(
                kind="monthly", label=f"{g.contractor} №{g.purchase_no} (помесячная)",
                contractor=g.contractor, contractor_norm=g.contractor_norm,
                purchase_no=g.purchase_no, order_no=None, rows=list(g.rows),
            ))
        elif len(g.distinct_order_nos) >= 2:
            order_rows: dict[str, list[SheetRow]] = {}
            for r in g.rows:
                order_rows.setdefault(r.order_no or "", []).append(r)
            for order_no, rows in order_rows.items():
                units.append(MatchUnit(
                    kind="framework_order", label=f"{g.contractor} №{g.purchase_no}, заказ {order_no}",
                    contractor=g.contractor, contractor_norm=g.contractor_norm,
                    purchase_no=g.purchase_no, order_no=order_no, rows=rows,
                ))
        else:
            units.append(MatchUnit(
                kind="single", label=f"{g.contractor} №{g.purchase_no}",
                contractor=g.contractor, contractor_norm=g.contractor_norm,
                purchase_no=g.purchase_no, order_no=None, rows=list(g.rows),
            ))
    return units
