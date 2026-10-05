"""Загрузчик v2 «ФАДМ 2026_2» — чтение листа GoodsService (см. задание
05.10.2026) из scripts/data/fadm_2026_goodsservice.csv (74 колонки A..BV,
заголовки строки 3 оригинальной таблицы, данные с 4-й; экспортирован из
Google-таблицы владельца один раз, в репозитории — без 14-МБ книги).

В отличие от первого загрузчика (parse.py/build.py — собирали «ФАДМ 2026_2»
по урезанному PDF, угадывая вид договора) здесь вид договора, ИНН, номер
договора/даты, номер платёжного документа и флаги статуса читаются НАПРЯМУЮ
из таблицы владельца — ничего не угадывается.

КЛЮЧ ЗАКУПКИ — (ИНН, Номер закупки) — задание владельца: один номер D у
разных ИНН — разные закупки, название контрагента не входит в ключ (в
отличие от parse.py::PurchaseGroup, где ключа ИНН тогда не было).

Вид договора (колонка C):
  - «Разовый»               → одна закупка на пару (ИНН, D); позиции строки
                               этой пары (может быть несколько строк с разным
                               E — тогда E трактуется как номер заказа
                               разовой закупки, не формирует отдельную
                               дочернюю запись — все идут одной закупкой).
  - «Рамочный накопительный» → голова на (ИНН, D), дочерний заказ на КАЖДОЕ
                               отдельное значение E.
  - «Рамочный с суммой»      → как накопительный, но среди строк есть одна
                               служебная — колонка E содержит буквально
                               «Установка предельной суммы договора» — её E
                               не создаёт заказ, а значение «Итоговая цена за
                               объём» (O), либо «Плановая стоимость» (L) этой
                               строки, если O=0/пусто, идёт в Contract.max_amount
                               головы (лимит рамки хранится штатно в этом
                               поле — см. app/models/contract.py:14).

Авансовые (п. задания «Авансовые»): контрагент (H) — ФИО сотрудника (через
app.services.person_name/employees-lookup на стороне build) и/или номер
договора (S) вида «АВАНСОВЫЙ ОТЧЕТ N» — извлекаем номер отчёта для отчёта
загрузчика, сам признак авансового выставляет build.py по совпадению H с
живым сотрудником (как в parse.py/advance.py первого загрузчика — ПРАВИЛО
№6, тот же employees-lookup, не второй).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

# Индексы колонок (0-based) — см. docstring __main__.py / задание 05.10.2026,
# сверено построчно с заголовками экспортированного CSV (scripts/data/
# fadm_2026_goodsservice.csv), см. headers.txt в отчёте загрузчика.
IDX_NO = 0
IDX_EVENT = 1
IDX_CONTRACT_KIND = 2
IDX_PURCHASE_NO = 3
IDX_ORDER_NO = 4
IDX_SUBJECT = 5
IDX_ITEM_NAME = 6
IDX_CONTRACTOR = 7
IDX_QTY = 8
IDX_UNIT = 9
IDX_PLAN_PRICE = 10
IDX_PLAN_SUM = 11
IDX_CONFIRMED = 12
IDX_FINAL_PRICE = 13
IDX_FINAL_SUM = 14
IDX_SUM_TO_PAY_DELIVERY = 15
IDX_SUM_TO_PAY_CONTRACT = 16
IDX_INN = 17
IDX_CONTRACT_NUMBER = 18
IDX_CONTRACT_DATE = 19
IDX_PAYMENT_DOC = 20
IDX_PAYMENT_PURPOSE = 21
IDX_PAYMENT_DATE = 22
IDX_GOODS_SERVICES = 29
IDX_FEO_DIRECTION = 30      # AE
IDX_FEO_TYPE = 31           # AF
IDX_FEO_APPENDIX_DIRECTION = 32  # AG
IDX_PURCHASE_METHOD = 35    # AJ
IDX_QUARTER = 37            # AL
IDX_CONTRACT_TERM = 39      # AN
IDX_PURCHASE_DONE = 44      # AS
IDX_CONTRACT_SIGNED = 45    # AT
IDX_ORDERED = 46            # AU
IDX_DELIVERED = 47          # AV
IDX_PAID = 48               # AW
IDX_UPD_NUMBER = 64         # BM
IDX_EXPENSE_CODE = 71       # BT

KIND_SINGLE = "Разовый"
KIND_FRAMEWORK_CUMULATIVE = "Рамочный накопительный"
KIND_FRAMEWORK_WITH_AMOUNT = "Рамочный с суммой"
FRAMEWORK_KINDS = {KIND_FRAMEWORK_CUMULATIVE, KIND_FRAMEWORK_WITH_AMOUNT}

LIMIT_MARKER = "установка предельной суммы договора"

# Номер соглашения о субсидии — владелец подтвердил формулы листа 05.10.2026:
# V/U/W/S/T в GoodsService производны от поиска в листе Scroller выписки
# строки с ИНН=R, суммой=P, статус «Исполнен», «Документ-основание» содержит
# ИМЕННО этот номер соглашения — та же строка, что в bank_payments.basis_doc_text
# (проверено на реальных данных: «№ 091-10-2026-008 от 28.01.2026»). Без этого
# фильтра платежи ПРОШЛЫХ лет того же контрагента (иное соглашение, то же ИНН,
# случайно совпавшая сумма) ложно матчились бы.
AGREEMENT_NUMBER = "091-10-2026-008"

_WS_RE = re.compile(r"\s+")


def _norm(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    return _WS_RE.sub(" ", str(raw).strip())


def _parse_decimal(raw: str) -> Decimal:
    raw = (raw or "").strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal("0")


def _parse_bool(raw: str) -> bool:
    v = (raw or "").strip().lower()
    return v in ("true", "1", "да", "истина", "yes")


def _parse_date(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_payment_numbers(raw: str) -> list[str]:
    """U может содержать несколько номеров п/п через разделитель (','/';'/'/'),
    либо текст «Платёж не проходил» (не номер — отбрасываем)."""
    raw = (raw or "").strip()
    if not raw or "не проход" in raw.lower():
        return []
    parts = re.split(r"[,;/]", raw)
    return [p.strip() for p in parts if p.strip()]


@dataclass
class SheetRowV2:
    row: int
    event: str
    contract_kind: str
    purchase_no: str
    order_no: str
    subject: str
    item_name: str
    contractor: str
    qty: Decimal
    unit: str
    plan_price: Decimal
    plan_sum: Decimal
    confirmed: bool
    final_price: Decimal
    final_sum: Decimal
    sum_to_pay_delivery: Decimal
    sum_to_pay_contract: Decimal
    inn: str
    contract_number: str
    contract_date: Optional[date]
    payment_numbers: list[str]
    payment_purpose: str
    payment_date: Optional[date]
    goods_services: str
    feo_direction: str
    feo_type: str
    feo_appendix_direction: str
    purchase_done: bool
    contract_signed: bool
    ordered: bool
    delivered: bool
    paid: bool

    @property
    def is_limit_row(self) -> bool:
        return LIMIT_MARKER in _norm(self.order_no).lower()

    @property
    def amount(self) -> Decimal:
        """Сумма ЭТОЙ строки (позиции) — «Итоговая цена за объём» (O), если
        заполнена и отлична от 0, иначе плановая стоимость (L). НЕ путать с
        P (sum_to_pay_delivery) — P это АГРЕГАТ по ВСЕЙ паре (закупка D,
        заказ E, ИНН R) через SUMIFS (владелец подтвердил 05.10.2026) и
        ОДИНАКОВ у всех строк одной пары — суммировать P построчно (как было
        ошибочно сделано при первой попытке этой правки, см. git history)
        задваивает/утраивает группу, если у неё больше одной строки-позиции
        (прод-находка: «ЦЕНТРАВТО» заказ 5 — 20 строк с одним и тем же P).
        Контрольные суммы AT/AV/AW/BE/BF листа совпадают ИМЕННО при
        построчном O (проверено), P используется ОТДЕЛЬНО, только для
        поиска платежа по сумме — см. delivery_payment_target ниже и
        sheet_v2_payments.py."""
        return self.final_sum or self.plan_sum

    @property
    def delivery_payment_target(self) -> Decimal:
        """P — агрегированная (SUMIFS) сумма поставки ВСЕЙ пары (D,E,ИНН),
        одинаковая у каждой строки этой пары — то, что реально стоит в
        назначении платежа банка (владелец, уточнение 05.10.2026). Использовать
        ТОЛЬКО для поиска/проверки суммы платежа, не для сумм позиций/групп."""
        return self.sum_to_pay_delivery or self.amount

    @property
    def item_kind(self) -> str:
        """AD «Товары/Услуги» → 'goods'/'services', иначе по умолчанию
        'services' (не блокирует загрузку — используется только для
        item_type позиции)."""
        v = _norm(self.goods_services).lower()
        if "товар" in v:
            return "goods"
        return "services"

    @property
    def report_number(self) -> Optional[str]:
        """Авансовый отчёт — номер из S вида «АВАНСОВЫЙ ОТЧЕТ N»."""
        m = re.search(r"авансов\w*\s*отч[её]т\D*(\d+)", self.contract_number, re.IGNORECASE)
        return m.group(1) if m else None


def _row(raw: list[str], row_num: int) -> SheetRowV2:
    def g(idx: int) -> str:
        return raw[idx] if idx < len(raw) else ""

    return SheetRowV2(
        row=row_num,
        event=_norm(g(IDX_EVENT)),
        contract_kind=_norm(g(IDX_CONTRACT_KIND)),
        purchase_no=_norm(g(IDX_PURCHASE_NO)),
        order_no=_norm(g(IDX_ORDER_NO)),
        subject=_norm(g(IDX_SUBJECT)),
        item_name=_norm(g(IDX_ITEM_NAME)),
        contractor=_norm(g(IDX_CONTRACTOR)),
        qty=_parse_decimal(g(IDX_QTY)),
        unit=_norm(g(IDX_UNIT)),
        plan_price=_parse_decimal(g(IDX_PLAN_PRICE)),
        plan_sum=_parse_decimal(g(IDX_PLAN_SUM)),
        confirmed=_parse_bool(g(IDX_CONFIRMED)),
        final_price=_parse_decimal(g(IDX_FINAL_PRICE)),
        final_sum=_parse_decimal(g(IDX_FINAL_SUM)),
        sum_to_pay_delivery=_parse_decimal(g(IDX_SUM_TO_PAY_DELIVERY)),
        sum_to_pay_contract=_parse_decimal(g(IDX_SUM_TO_PAY_CONTRACT)),
        inn=_norm(g(IDX_INN)),
        contract_number=_norm(g(IDX_CONTRACT_NUMBER)),
        contract_date=_parse_date(g(IDX_CONTRACT_DATE)),
        payment_numbers=_parse_payment_numbers(g(IDX_PAYMENT_DOC)),
        payment_purpose=_norm(g(IDX_PAYMENT_PURPOSE)),
        payment_date=_parse_date(g(IDX_PAYMENT_DATE)),
        goods_services=_norm(g(IDX_GOODS_SERVICES)),
        feo_direction=_norm(g(IDX_FEO_DIRECTION)),
        feo_type=_norm(g(IDX_FEO_TYPE)),
        feo_appendix_direction=_norm(g(IDX_FEO_APPENDIX_DIRECTION)),
        purchase_done=_parse_bool(g(IDX_PURCHASE_DONE)),
        contract_signed=_parse_bool(g(IDX_CONTRACT_SIGNED)),
        ordered=_parse_bool(g(IDX_ORDERED)),
        delivered=_parse_bool(g(IDX_DELIVERED)),
        paid=_parse_bool(g(IDX_PAID)),
    )


def parse_goodsservice_csv(path: str | Path) -> list[SheetRowV2]:
    path = Path(path)
    out: list[SheetRowV2] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)
        for i, raw in enumerate(reader, start=4):  # данные с 4-й строки таблицы
            if not raw or not any((c or "").strip() for c in raw):
                continue
            if not (raw[IDX_PURCHASE_NO] or "").strip():
                continue
            out.append(_row(raw, i))
    return out


def resolve_status(row: "SheetRowV2") -> str:
    """Статус по флагам (задание, п.2): AW→delivered, AV→delivered,
    AU→ordered, AT→contracted, AS→work_in_progress. «Оплачено» НЕ ставится
    напрямую — оплата только через привязку платежа + подтверждение
    согласующих (см. sheet_v2_build.py), поэтому AW трактуется так же, как
    AV (готово к поставке/оплате, но статус закупки — delivered, а не paid)."""
    if row.paid or row.delivered:
        return "delivered"
    if row.ordered:
        return "ordered"
    if row.contract_signed:
        return "contracted"
    if row.purchase_done:
        return "work_in_progress"
    return "draft"


def is_plan_only(row: "SheetRowV2") -> bool:
    """Строка — плановая позиция, а не закупка: нет подтверждения поставки
    (M=False) И ни один из флагов действия (AS..AW) не взведён (задание:
    «строки без подтверждения и «будущие траты» — не закупки, а плановые
    позиции»)."""
    if row.is_limit_row:
        return False
    if row.confirmed:
        return False
    return not (row.purchase_done or row.contract_signed or row.ordered or row.delivered or row.paid)


def need_level_for(row: "SheetRowV2") -> str:
    """Классификация плановой позиции на need_level — см.
    app.services.plan_need_level (NEED_LEVEL_LIKELY/NEED_LEVEL_NICE_TO_HAVE).
    Эвристика (нет прямой колонки need_level в GoodsService): AJ «способ
    закупки» заполнен и квартал (AL) близкий → вероятно понадобится (likely);
    иначе — резерв/можно отказаться (nice_to_have). Расхождения с прежним
    fadm_2026_sheet.csv — в отчёт загрузчика (см. sheet_v2_report.py)."""
    if _norm(row.event) or _norm(row.subject):
        return "likely"
    return "nice_to_have"


def valid_inn(raw: Optional[str]) -> Optional[str]:
    """R иногда содержит текст-заглушку («Не найден», «не указан») вместо
    настоящего ИНН (прод-находка dry-run 05.10.2026 — буквальная передача
    такого текста как ИНН в find_or_create_contractor роняла вставку
    UniqueViolationError на ix_contractors_inn_unique: несколько РАЗНЫХ
    контрагентов с одной и той же заглушкой-«ИНН»). Настоящий ИНН — только
    цифры, 10 или 12 знаков (организации/ИП). Общая для sheet_v2_build.py
    (резолв контрагента) и sheet_v2_payments.py (поиск платежа по ИНН) —
    ПРАВИЛО №6, один источник, не копия."""
    v = (raw or "").strip()
    return v if v.isdigit() and len(v) in (10, 12) else None


@dataclass
class PurchaseKey:
    inn: str
    purchase_no: str

    def __hash__(self):
        return hash((self.inn, self.purchase_no))


@dataclass
class PurchaseGroupV2:
    inn: str
    purchase_no: str
    contract_kind: str
    contractor: str
    rows: list[SheetRowV2] = field(default_factory=list)
    limit_row: Optional[SheetRowV2] = None

    @property
    def is_framework(self) -> bool:
        return self.contract_kind in FRAMEWORK_KINDS

    @property
    def distinct_orders(self) -> list[str]:
        seen: list[str] = []
        for r in self.rows:
            if r.is_limit_row:
                continue
            v = r.order_no
            if v and v not in seen:
                seen.append(v)
        return seen

    @property
    def total_amount(self) -> Decimal:
        return sum((r.amount for r in self.rows if not r.is_limit_row), Decimal("0"))

    @property
    def first_name(self) -> str:
        for r in self.rows:
            if not r.is_limit_row:
                return r.subject or r.item_name
        return self.purchase_no

    @property
    def limit_amount(self) -> Optional[Decimal]:
        if not self.limit_row:
            return None
        return self.limit_row.final_sum or self.limit_row.plan_sum or None


def group_rows_v2(rows: list[SheetRowV2]) -> tuple[list[PurchaseGroupV2], list[SheetRowV2]]:
    """Возвращает (группы-закупки, строки-плановые-позиции (is_plan_only))."""
    by_key: dict[tuple[str, str], PurchaseGroupV2] = {}
    order: list[tuple[str, str]] = []
    plan_rows: list[SheetRowV2] = []

    for r in rows:
        if is_plan_only(r):
            plan_rows.append(r)
            continue
        key = (r.inn, r.purchase_no)
        if key not in by_key:
            by_key[key] = PurchaseGroupV2(
                inn=r.inn, purchase_no=r.purchase_no,
                contract_kind=r.contract_kind, contractor=r.contractor,
            )
            order.append(key)
        group = by_key[key]
        if r.is_limit_row:
            group.limit_row = r
        else:
            group.rows.append(r)

    groups = [by_key[k] for k in order if by_key[k].rows or by_key[k].limit_row]
    return groups, plan_rows


def totals_report(rows: list[SheetRowV2]) -> dict:
    """Контрольные суммы для сверки со строкой 1 листа (задание, п.3)."""
    contracted = sum((r.amount for r in rows if r.contract_signed and not r.is_limit_row), Decimal("0"))
    delivered = sum((r.amount for r in rows if r.delivered and not r.is_limit_row), Decimal("0"))
    paid = sum((r.amount for r in rows if r.paid and not r.is_limit_row), Decimal("0"))
    goods = sum((r.amount for r in rows if r.item_kind == "goods" and not r.is_limit_row), Decimal("0"))
    services = sum((r.amount for r in rows if r.item_kind == "services" and not r.is_limit_row), Decimal("0"))
    plan_total = sum((r.plan_sum for r in rows if not r.is_limit_row), Decimal("0"))
    return {
        "contracted": contracted,
        "delivered": delivered,
        "paid": paid,
        "goods": goods,
        "services": services,
        "plan_total": plan_total,
    }
