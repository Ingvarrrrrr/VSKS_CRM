"""ПРАВИЛО №6 (2026-09-07, группа D4) — единственный писатель/читатель
Purchase.acceptance_docs (JSONB) + вычисляемых legacy-скаляров
acceptance_doc_name/date/number/amount.

Контекст (инвентаризация): закрывающие документы закупки хранились ДВАЖДЫ —
в JSONB-массиве `acceptance_docs` (`[{name, number, date, amount, receipt_id,
file_id, type?, source?}, ...]`) и в 4 скалярных колонках Purchase
(`acceptance_doc_name/date/number/amount`), которые исторически держали ровно
ОДИН документ. Три места писали в оба хранилища параллельно
(`routers/purchase_receipts.py`, `routers/purchases.py` PUT/PATCH,
`services/purchase_import_parser.py`), рискуя разойтись; чтения были
разбросаны по ~15 файлам, часть — напрямую по скалярам без фолбэка на JSONB.

РЕШЕНИЕ: источник истины — JSONB `acceptance_docs`. Скаляры
acceptance_doc_name/date/number/amount — ПРОИЗВОДНЫЙ КЭШ (правка координатора,
2026-09-07): report-builder (field_registry.py/pivot_engine.py) читает их как
сырые SQL-колонки и не может звать Python derived_scalars() (JSONB-выражение
там ломает _build_filters()/_extract_value(), см. field_registry.py) — поэтому
колонки ОСТАЮТСЯ, но пишет их ТОЛЬКО этот модуль, одним триггером —
sync_scalars(p), вызываемым в конце add_doc/remove_doc/replace_docs. Прямая
запись в эти 4 колонки где-либо ещё запрещена (см. комментарий у
Purchase.acceptance_doc_* в app/models/purchase.py).

Все читатели, кроме report-builder'а, обязаны использовать derived_scalars()/
total_amount() НАПРЯМУЮ (единый читатель, вычисляется из JSONB на лету), а НЕ
кэш-колонки — так сериализатор (PurchaseOut) остаётся верным даже если кэш
почему-то разошёлся.

Публичное API:
  dedup(docs)                — убрать дубли по ключу (type, number, amount)
                                (та же семантика, что backfill Phase 26-ooo).
  add_doc(p, doc)             — добавить документ (append + dedup + flag_modified
                                 + sync_scalars).
  remove_doc(p, predicate)    — удалить документы, для которых predicate(doc)
                                 True (+ sync_scalars, если что-то удалено).
  replace_docs(p, docs)       — заменить весь список (dedup + flag_modified +
                                 sync_scalars).
  sum_docs_amount(docs)       — Σ amount по списку документов (без обращения к Purchase).
  derived_scalars(p)          — {name, number, date, amount} ПЕРВОГО документа
                                 (docs[0]) с фолбэком на текущие значения
                                 скаляров, если acceptance_docs пуст.
  sync_scalars(p)             — пишет derived_scalars(p) в 4 колонки-кэш
                                 (единственное разрешённое место записи).
  total_amount(p)             — Σ amount по ВСЕМ документам с фолбэком на
                                 legacy acceptance_doc_amount, если пуст.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from sqlalchemy.orm.attributes import flag_modified


def _dec(v: Any) -> Optional[Decimal]:
    """None остаётся None; всё прочее (Decimal/float/int/str-число) → Decimal."""
    if v is None or v == "":
        return None
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _doc_key(d: dict) -> tuple:
    """Ключ дедупа — ЗЕРКАЛО app.startup.backfills._phase26_ooo_acceptance_docs_dedup
    (type, number, round(amount, 2)). Не переиспользуется напрямую оттуда, чтобы
    не тянуть startup-модуль как зависимость сервисного слоя — но обязана
    остаться идентичной (см. её докстринг про «Документ 1/Документ 2» дубли)."""
    return (
        d.get("type") or "",
        str(d.get("number") or ""),
        round(float(d.get("amount") or 0), 2),
    )


def dedup(docs: list) -> list:
    """Убрать дубли по (type, number, amount) — дубль считается только при
    непустом number (пустой number = легаси-запись без идентификатора, не
    дедуплицируется вслепую). При обнаружении дубля с file_id, отсутствующим
    у уже сохранённой (kept) записи — file_id переносится на неё, чтобы не
    потерять привязку файла. Порядок сохранённых записей не меняется."""
    seen: set = set()
    kept: list = []
    for d in docs:
        if not isinstance(d, dict):
            kept.append(d)
            continue
        key = _doc_key(d)
        if key in seen and key[1] != "":
            if d.get("file_id"):
                for k in kept:
                    if isinstance(k, dict) and _doc_key(k) == key and not k.get("file_id"):
                        k["file_id"] = d.get("file_id")
                        break
            continue
        seen.add(key)
        kept.append(d)
    return kept


def replace_docs(p, docs: list) -> None:
    """Заменить весь acceptance_docs целиком — с дедупом + flag_modified +
    sync_scalars. Единственный способ ЗАПИСАТЬ acceptance_docs, которым
    обязаны пользоваться все писатели (PUT/PATCH закупки, импорт,
    авто-добавление чека)."""
    p.acceptance_docs = dedup(list(docs or []))
    flag_modified(p, "acceptance_docs")
    sync_scalars(p)


def add_doc(p, doc: dict) -> bool:
    """Добавить один документ к существующему списку (append + dedup +
    flag_modified + sync_scalars). Возвращает True, если документ реально
    добавлен (не был дублем уже существующей записи по ключу (type, number,
    amount)) — вызывающий код, которому нужна более тонкая проверка «этот же
    чек/receipt_id уже записан», обязан проверить это САМ до вызова
    (см. purchase_receipts.py)."""
    original = list(getattr(p, "acceptance_docs", None) or [])
    deduped = dedup(original + [doc])
    p.acceptance_docs = deduped
    flag_modified(p, "acceptance_docs")
    sync_scalars(p)
    return len(deduped) > len(original)


def remove_doc(p, predicate: Callable[[dict], bool]) -> list:
    """Удалить документы, для которых predicate(doc) истинен (+ sync_scalars,
    если что-то реально удалено). Возвращает список УДАЛЁННЫХ документов
    (пустой, если ничего не удалено — в этом случае acceptance_docs НЕ
    трогается, flag_modified/sync_scalars не вызываются)."""
    existing = list(getattr(p, "acceptance_docs", None) or [])
    kept = [d for d in existing if not (isinstance(d, dict) and predicate(d))]
    removed = [d for d in existing if isinstance(d, dict) and predicate(d)]
    if removed:
        p.acceptance_docs = kept
        flag_modified(p, "acceptance_docs")
        sync_scalars(p)
    return removed


def sum_docs_amount(docs: list) -> Optional[Decimal]:
    """Σ amount по списку документов. None, если список пуст ИЛИ ни у одного
    документа нет amount (чтобы вызывающий код мог отличить «нет данных» от
    легитимного нуля)."""
    total: Optional[Decimal] = None
    for d in docs or []:
        if not isinstance(d, dict):
            continue
        amt = _dec(d.get("amount"))
        if amt is None:
            continue
        total = amt if total is None else total + amt
    return total


def _parse_doc_date(raw: Any) -> Optional[_date]:
    """acceptance_docs хранит дату как ISO-строку ('YYYY-MM-DD'); legacy-
    колонка — как date. Нормализуем к date для единообразия у читателей,
    которые форматируют её как обычную дату Purchase."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, _date):
        return raw
    if isinstance(raw, str):
        try:
            return _date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def derived_scalars(p) -> dict:
    """{name, number, date, amount} — ПЕРВЫЙ документ (docs[0], в порядке
    списка — так их писал purchase_import_parser.py при заполнении ОБОИХ
    хранилищ одновременно, и так их добавляет purchase_receipts.py) с
    фолбэком на legacy-скаляры, если acceptance_docs пуст (немигрированные
    закупки до backfill / до этой волны).
    """
    docs = list(getattr(p, "acceptance_docs", None) or [])
    if docs and isinstance(docs[0], dict):
        first = docs[0]
        return {
            "name": first.get("name") or None,
            "number": first.get("number") or None,
            "date": _parse_doc_date(first.get("date")),
            "amount": _dec(first.get("amount")),
        }
    return {
        "name": getattr(p, "acceptance_doc_name", None),
        "number": getattr(p, "acceptance_doc_number", None),
        "date": getattr(p, "acceptance_doc_date", None),
        "amount": _dec(getattr(p, "acceptance_doc_amount", None)),
    }


def sync_scalars(p) -> None:
    """Пишет derived_scalars(p) в 4 колонки-кэш acceptance_doc_name/number/
    date/amount — ЕДИНСТВЕННОЕ разрешённое место записи в них (координатор,
    2026-09-07): report-builder (field_registry.py/pivot_engine.py) читает их
    как сырые SQL-колонки и не умеет вычислять derived_scalars() на лету.
    Вызывается автоматически из add_doc/remove_doc/replace_docs — отдельно
    звать обычно не нужно, разве что после ручной правки acceptance_docs в
    обход этих трёх функций (см. purchase_import_parser.py — новый Purchase
    ещё не имеет ORM-истории для add_doc/replace_docs)."""
    derived = derived_scalars(p)
    p.acceptance_doc_name = derived["name"]
    p.acceptance_doc_number = derived["number"]
    p.acceptance_doc_date = derived["date"]
    p.acceptance_doc_amount = derived["amount"]


def total_amount(p) -> Optional[Decimal]:
    """Σ amount по ВСЕМ документам acceptance_docs; фолбэк на legacy
    acceptance_doc_amount, если JSONB пуст/все amount пусты."""
    docs = list(getattr(p, "acceptance_docs", None) or [])
    total = sum_docs_amount(docs)
    if total is not None:
        return total
    return _dec(getattr(p, "acceptance_doc_amount", None))
