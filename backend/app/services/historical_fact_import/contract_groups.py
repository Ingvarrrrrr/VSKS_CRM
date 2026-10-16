"""Группировка по договору (владелец, 16.10.2026, шаг 2): «группировка по
договору, внутри договора — по номерам заказов, делай как GoodsService».

Чистая логика (без БД, без Purchase/Contract) — один источник истины
(ПРАВИЛО №6) для ТРЁХ потребителей:
  - `historical_fact_import/grouping.py` (generic мастер «Импорт факта») —
    ключ группы (ИНН/контрагент + № закупки);
  - `historical_fact_import/columns.py` (определение колонки «Тип договора»
    по значениям, когда заголовок перезаписан) и `rows.py` (нормализация
    сырого текста колонки в один из 3 видов);
  - `scripts/fadm_sheet_load/sheet_v2_build.py` / `sheet_v2_parse.py` —
    загрузчик ФАДМ уже отладил эту логику на проде (build_single/
    build_framework, PLACEHOLDER_CONTRACT_NUMBERS/_real_contract_number,
    valid_inn, natural_purchase_key, LIMIT_MARKER) — здесь их ЕДИНСТВЕННОЕ
    определение, скрипт импортирует отсюда, а не держит вторую копию.
    Переопределения, специфичные для конкретного листа ФАДМ
    (FRAMEWORK_WITH_AMOUNT_OVERRIDE, SINGLE_OVERRIDE, FRAMEWORK_LIMIT_FROM_Y)
    остаются в sheet_v2_parse.py — это не общая логика, а разбор одного
    файла владельца.

Три вида договора (колонка «Тип договора», может быть без заголовка — см.
`detect_contract_kind_column`):
  - «Разовый» → одна закупка на (ИНН|контрагент, № закупки); все строки —
    её позиции, «Номер заказа» не формирует отдельную запись.
  - «Рамочный накопительный» → голова (договор) + дочерний заказ на КАЖДОЕ
    отдельное значение «Номера заказа» (order_no), голова денег не несёт.
  - «Рамочный с суммой» → то же + лимит из служебной строки «Установка
    предельной суммы договора» (её сумма — Contract.max_amount головы, сама
    строка НЕ позиция/заказ).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Виды договора
# ---------------------------------------------------------------------------
KIND_SINGLE = "Разовый"
KIND_FRAMEWORK_CUMULATIVE = "Рамочный накопительный"
KIND_FRAMEWORK_WITH_AMOUNT = "Рамочный с суммой"
FRAMEWORK_KINDS = {KIND_FRAMEWORK_CUMULATIVE, KIND_FRAMEWORK_WITH_AMOUNT}
ALL_KINDS = {KIND_SINGLE, KIND_FRAMEWORK_CUMULATIVE, KIND_FRAMEWORK_WITH_AMOUNT}

# Purchase.purchase_contract_type (app/models/purchase.py) — то же, что
# sheet_v2_build.py::FRAMEWORK_TYPE/"framework_with_amount".
CONTRACT_TYPE_SINGLE = "single"
CONTRACT_TYPE_FRAMEWORK_CUMULATIVE = "framework_cumulative"
CONTRACT_TYPE_FRAMEWORK_WITH_AMOUNT = "framework_with_amount"


def _norm(s: Optional[str]) -> str:
    if s is None:
        return ""
    return " ".join(str(s).replace("\xa0", " ").strip().lower().split())


_KIND_BY_NORM = {_norm(k): k for k in ALL_KINDS}


def classify_contract_kind(raw: Optional[str]) -> Optional[str]:
    """Сырой текст колонки «Тип договора» → один из 3 кодов (ALL_KINDS),
    либо None (пусто/не распознано — считается «Разовый» вызывающим кодом,
    ЭТА функция сама умолчания не навязывает)."""
    return _KIND_BY_NORM.get(_norm(raw))


def detect_contract_kind_column(sample_rows: list[list], candidate_indices: list[int],
                                 min_hits: int = 2) -> Optional[int]:
    """Лист GoodsService владельца (16.10.2026) — заголовок колонки «Тип
    договора» (C) перезаписан номером соглашения («№ 091-10-2026-008 от
    28.01.2026»), по тексту заголовка её не найти. Определяем колонку ПО
    ЗНАЧЕНИЯМ: среди `candidate_indices` (колонки без иного назначения —
    вызывающий код columns.py уже отфильтровал занятые) выбираем ту, где
    больше всего ячеек совпадает буква-в-букву (без учёта регистра/пробелов)
    с одним из 3 известных видов договора; `min_hits` — не сработать на
    случайном совпадении одной ячейки с другим смыслом."""
    best_idx: Optional[int] = None
    best_hits = 0
    for idx in candidate_indices:
        hits = 0
        for row in sample_rows:
            if idx >= len(row):
                continue
            if classify_contract_kind(row[idx]) is not None:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_idx = idx
    return best_idx if best_hits >= min_hits else None


# ---------------------------------------------------------------------------
# Служебная строка-лимит («Установка предельной суммы договора» в колонке
# «Номер заказа») — не заказ, не позиция.
# ---------------------------------------------------------------------------
LIMIT_MARKER = "установка предельной суммы договора"


def is_limit_marker(order_no: Optional[str]) -> bool:
    return LIMIT_MARKER in _norm(order_no)


# ---------------------------------------------------------------------------
# ИНН — настоящий, не текст-заглушка («Не найден» и т.п.).
# ---------------------------------------------------------------------------
def valid_inn(raw: Optional[str]) -> Optional[str]:
    """Настоящий ИНН — только цифры, 10 (организация) или 12 (ИП) знаков.
    Текст-заглушка («Не найден», «не указан» и т.п.) → None, не используется
    как идентификатор (иначе РАЗНЫЕ контрагенты с одной и той же заглушкой
    слиплись бы в одну группу/контрагента — прод-находка sheet_v2_build.py)."""
    v = (raw or "").strip()
    return v if v.isdigit() and len(v) in (10, 12) else None


# ---------------------------------------------------------------------------
# Номер договора — настоящий vs текст-заглушка («нет данных» и подобные).
# ---------------------------------------------------------------------------
PLACEHOLDER_CONTRACT_NUMBERS = {
    "", "нет данных", "без номера", "не указан", "n/a",
    # Лист GoodsService владельца (16.10.2026, шаг 2) — маркеры «не нашли
    # формулой» на листе-источнике: ячейка с ошибкой/не найдена, не настоящий
    # номер договора.
    "не обнаружено", "не найден", "#ref!",
}


def real_contract_number(raw: Optional[str]) -> Optional[str]:
    """Текст колонки «Номер договора» → настоящий номер, либо None (пусто/
    заглушка) — вызывающий код (commit.py/sheet_v2_build.py) присваивает
    временный номер ТОЛЬКО когда здесь None (владелец: «настоящие, а не
    временный номер; временный только если пусто»)."""
    v = (raw or "").strip()
    return None if v.lower() in PLACEHOLDER_CONTRACT_NUMBERS else v


# ---------------------------------------------------------------------------
# Порядок номеров закупки (D) / заказа (E) — числом, если состоит только из
# цифр, иначе (нечисловые — в конец, по алфавиту).
# ---------------------------------------------------------------------------
def natural_purchase_key(no: Optional[str]) -> tuple:
    s = (no or "").strip()
    if s.isdigit():
        return (0, int(s), "")
    return (1, 0, s)


# ---------------------------------------------------------------------------
# Ключ повторной заливки «Импорта факта» (владелец, 16.10.2026, задача 4) —
# gs:{ИНН}:{№ закупки (D)}[:{№ заказа (E), только у рамочных дочерних}].
# ЕДИНСТВЕННОЕ место формата этого ключа (ПРАВИЛО №6) — commit.py (пишет
# Purchase.source_key при создании) и existing_link.py (ищет по нему точное
# совпадение ПРИ повторной заливке того же файла) вызывают эту функцию, а не
# собирают строку сами.
# ---------------------------------------------------------------------------
def build_source_key(
    inn: Optional[str], purchase_no: Optional[str], order_no: Optional[str] = None,
    *, supplier_fallback: Optional[str] = None,
) -> Optional[str]:
    """None, когда нет «№ закупки» (D) — без номера узнать СВОЮ строку при
    повторной заливке нельзя в любом случае. Когда нет ни настоящего ИНН
    (valid_inn), ни нормализованного имени поставщика (`supplier_fallback`,
    задача 4 правка 16.10.2026 — группа без ИНН в файле вообще, только
    название, см. `default_group_key` выше: ТОТ ЖЕ приоритет ИНН-vs-имя, не
    второй) — identity нет, но № закупки (D) есть: ключ строится по D (и E
    у дочернего заказа рамочного) с явным маркером «нет поставщика» вместо
    identity (`-`), правка 16.10.2026 — прод-находка: закупка 40999 без
    контрагента и ИНН писалась с source_key=NULL и задваивалась бы при
    повторной заливке. `supplier_fallback` — ТОЧНОЕ (не fuzzy) совпадение
    нормализованного имени, в отличие от размытого поиска по имени, который
    владелец запретил в find_existing_matches_for_group — тут риска ложного
    срабатывания нет: ключ сравнивается на равенство, а не подстрокой/
    похожестью."""
    identity = inn or supplier_fallback
    purchase_no = (purchase_no or "").strip()
    if not purchase_no:
        return None
    if not identity:
        key = f"gs:-:{purchase_no}"
        order_no = (order_no or "").strip()
        if order_no:
            key += f":{order_no}"
        return key
    prefix = "gs" if inn else "gs-sup"
    key = f"{prefix}:{identity}:{purchase_no}"
    order_no = (order_no or "").strip()
    if order_no:
        key += f":{order_no}"
    return key


# ---------------------------------------------------------------------------
# Группа строк одного договора → разбивка на заказы (для рамочных).
# ---------------------------------------------------------------------------
@dataclass
class OrderGroup:
    order_no: str
    rows: list = field(default_factory=list)   # list[dict] — строки rows.py
    amount: Decimal = Decimal("0")
    status: Optional[str] = None


@dataclass
class ContractGroupInfo:
    kind: str                       # ALL_KINDS — Разовый, если не распознано
    contract_number: Optional[str]  # настоящий номер (real_contract_number) или None
    contract_date: Optional[object]
    orders: list = field(default_factory=list)       # list[OrderGroup] — только для рамочных
    limit_row: Optional[dict] = None
    limit_amount: Optional[Decimal] = None


def _row_amount(row: dict) -> Decimal:
    fact = row.get("fact") or {}
    plan = row.get("plan") or {}
    amt = fact.get("amount") if fact.get("amount") is not None else plan.get("amount")
    return Decimal(str(amt)) if amt is not None else Decimal("0")


def build_contract_group(rows: list[dict], *, status_of: Callable[[dict], Optional[str]],
                          status_rank: dict) -> ContractGroupInfo:
    """rows — строки ОДНОЙ группы (уже объединённые grouping.py по ключу
    ИНН/контрагент+№закупки), словари в формате rows.py (name/path/plan/
    fact/paid/contract_kind/order_no/contract_number/contract_date/...).

    `status_of(row)` — целевой статус ЭТОЙ строки (вызывающий код решает,
    как его получить — preview.py уже умеет statuses.resolve_status);
    `status_rank` — таблица ранга (existing_update.RANK, ПРАВИЛО №6, не
    вторая копия) для «наивысшая стадия заказа»."""
    kinds_present = [classify_contract_kind(r.get("contract_kind")) for r in rows]
    kind = next((k for k in kinds_present if k in FRAMEWORK_KINDS), None) or KIND_SINGLE

    raw_number = next((r.get("contract_number") for r in rows if r.get("contract_number")), None)
    contract_date = next((r.get("contract_date") for r in rows if r.get("contract_date")), None)
    info = ContractGroupInfo(
        kind=kind,
        contract_number=real_contract_number(raw_number),
        contract_date=contract_date,
    )
    if kind not in FRAMEWORK_KINDS:
        return info

    limit_row = next((r for r in rows if is_limit_marker(r.get("order_no"))), None)
    info.limit_row = limit_row
    if limit_row is not None:
        info.limit_amount = _row_amount(limit_row) or None

    order_rows: dict[str, list[dict]] = {}
    for r in rows:
        if r is limit_row:
            continue
        order_no = (r.get("order_no") or "").strip()
        order_rows.setdefault(order_no, []).append(r)

    orders: list[OrderGroup] = []
    for order_no, order_r in sorted(order_rows.items(), key=lambda kv: natural_purchase_key(kv[0])):
        amount = sum((_row_amount(r) for r in order_r), Decimal("0"))
        best_status: Optional[str] = None
        for r in order_r:
            st = status_of(r)
            if st and (best_status is None or status_rank.get(st, 0) > status_rank.get(best_status, 0)):
                best_status = st
        orders.append(OrderGroup(order_no=order_no, rows=order_r, amount=amount, status=best_status))
    info.orders = orders
    return info
