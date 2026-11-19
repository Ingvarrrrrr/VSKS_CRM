"""Единый канонический словарь названий столбцов Excel (Single Source of Truth, Правило №6).

Все шаблоны загрузки и экспорты Excel берут заголовки отсюда, чтобы одни и те же
сущности не назывались по-разному («Цена за ед. плановая» vs «Плановая цена за ед.»).
Парсеры импорта используют `normalize_excel_header(...)` и сохраняют все старые
названия столбцов как алиасы для 100% обратной совместимости.
"""
from __future__ import annotations

import re

# ── Позиция / Товар / Базовые характеристики ──────────────────────────────────
COL_ITEM_NAME = "Наименование позиции"
COL_CATALOG_NAME = "Наименование"
COL_UNIT = "Ед. изм."
COL_QTY = "Количество"
COL_UNIT_PRICE = "Цена за ед."
COL_TOTAL = "Сумма"
COL_DESCRIPTION = "Описание / ТЗ"
COL_ITEM_TYPE = "Тип позиции (Товар/Услуга)"
COL_NOTES = "Комментарий"
COL_CODE = "Код"
COL_APPENDIX = "Приложение"
COL_ACTIVE = "Активна"

# ── Плановые показатели ───────────────────────────────────────────────────────
COL_PLANNED_QTY = "Плановое количество"
COL_PLANNED_UNIT = "Ед. изм."
COL_PLANNED_UNIT_PRICE = "Плановая цена за ед."
COL_PLANNED_TOTAL = "Плановая сумма"

# ── Фактические показатели ────────────────────────────────────────────────────
COL_FACT_QTY = "Фактическое количество"
COL_FACT_UNIT_PRICE = "Фактическая цена за ед."
COL_FACT_TOTAL = "Фактическая сумма"

def feo_level_col(n: int) -> str:
    """Стандартное каноническое название столбца уровня ФЭО / субсидии: «Уровень N» (от 1 до 100+)."""
    return f"Уровень {n}"


_FEO_LEVEL_HEADER_RE = re.compile(
    r"^(?:фэо\s+)?ур(?:овень|\.)\s*(\d+)(?:\s*\(.*?\))?$",
    re.IGNORECASE,
)


def parse_feo_level_header(raw: object) -> int | None:
    """Распознаёт заголовки уровней субсидии / ФЭО:
    «Уровень 1» .. «Уровень 100», «ФЭО Ур.1», «Ур. 1», «Уровень 2 (...)».
    Возвращает целое число 1..100 (или больше) либо None."""
    if raw is None:
        return None
    text = str(raw).replace("\xa0", " ").strip()
    m = _FEO_LEVEL_HEADER_RE.match(text)
    if m:
        try:
            val = int(m.group(1))
            if 1 <= val <= 200:
                return val
        except ValueError:
            pass
    return None


# ── Показатели ФЭО ────────────────────────────────────────────────────────────
COL_FEO_CATEGORY = "Категория ФЭО"
COL_FEO_L1 = feo_level_col(1)
COL_FEO_L2 = feo_level_col(2)
COL_FEO_L3 = feo_level_col(3)
COL_FEO_L4 = feo_level_col(4)
COL_FEO_L5 = feo_level_col(5)
COL_FEO_DIRECTION = COL_FEO_L1
COL_FEO_TYPE = COL_FEO_L2
COL_FEO_SUBDIRECTION = COL_FEO_L3
COL_FEO_QTY = "Количество по ФЭО"
COL_FEO_UNIT = "Ед. изм. по ФЭО"
COL_FEO_UNIT_PRICE = "Цена за ед. по ФЭО"
COL_FEO_TOTAL = "Сумма по ФЭО"

# ── Закупка / Заявка / Договор / Контрагент / Оплата ──────────────────────────
COL_PURCHASE_NUMBER = "Номер закупки"
COL_ORDER_NUMBER = "Номер заявки"
COL_REGISTRY_NUMBER = "Реестровый №"
COL_PURCHASE_SUBJECT = "Предмет закупки"
COL_PURCHASE_METHOD = "Способ закупки"
COL_PURCHASE_AMOUNT = "Сумма закупки"
COL_ORDER_AMOUNT = "Сумма заявки"

COL_CONTRACT_TYPE = "Тип договора"
COL_CONTRACT_NUMBER = "Номер договора"
COL_CONTRACT_DATE = "Дата договора"
COL_CONTRACT_SUBJECT = "Предмет договора"
COL_CONTRACT_AMOUNT = "Сумма договора"
COL_CONTRACT_RESIDUAL = "Остаток по договору"
COL_CONTRACT_END_DATE = "Срок действия договора"

COL_CONTRACTOR = "Контрагент"
COL_CONTRACTOR_INN = "ИНН контрагента"
COL_RESPONSIBLE = "Ответственное лицо"

COL_PAYMENT_DOC_NUMBER = "Номер платёжного документа"
COL_PAYMENT_DATE = "Дата платёжного документа"
COL_PAYMENT_AMOUNT = "Сумма оплаты"
COL_PAYMENT_PURPOSE = "Назначение платежа"
COL_PAID_AMOUNT_MONEY = "Оплачено в деньгах"

COL_ACCEPTANCE_DOC_NAME = "Закрывающий документ: наименование"
COL_ACCEPTANCE_DOC_NUM = "Закрывающий документ: №"
COL_ACCEPTANCE_DOC_DATE = "Закрывающий документ: дата"
COL_ACCEPTANCE_DOC_AMT = "Закрывающий документ: сумма"

COL_VAT_APPLICABLE = "НДС применяется"
COL_VAT_RATE = "Ставка НДС"
COL_VAT_EXEMPTION = "Статья НК РФ"
COL_VAT_MODE = "Режим НДС"

COL_ORDERED = "Заказано"
COL_TO_ORDER = "Надо заказать"
COL_RESIDUAL = "Остаток"

COL_ROW_TYPE = "Тип строки"
COL_ROW_ID = "Хэш / ID строки"

_CURRENCY_SUFFIX_RE = re.compile(
    r"(?:\s*\(\s*[₽р]\s*\)|\s*,\s*[₽р]\.?|\s*,?\s*\(\s*руб\.?\s*\)|\s*,\s*руб\.?)$",
    re.IGNORECASE,
)


def normalize_excel_header(raw: object) -> str:
    """Нормализует заголовок столбца Excel для сопоставления при импорте:
    сжимает пробелы/NBSP, убирает хвостовую `*` и валютные суффиксы `(₽)` / `, ₽` / `руб.`."""
    if raw is None:
        return ""
    text = str(raw).replace("\xa0", " ").strip().lower()
    text = " ".join(text.split())
    if text.endswith("*"):
        text = text[:-1].strip()
    prev = None
    while prev != text:
        prev = text
        text = _CURRENCY_SUFFIX_RE.sub("", text).strip()
    return text
