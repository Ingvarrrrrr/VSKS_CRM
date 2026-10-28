"""Бланковые поля для ПРОЕКТА договора (fabrikant_contract_project.docx).

Этот документ — один из 5 файлов пакета ЭТП «Фабрикант», но единственный
среди них, что вешается на площадку ДО выбора поставщика и до торгов
(остальные 4 — инструкция/форма заявки/документация/ТЗ — печатают только
данные закупки и Заказчика, которые уже известны на этом этапе). У проекта
договора на этот момент физически не существует: ни поставщика, ни цены
договора (ЕЩЁ не прошли торги), ни номера/даты самого договора, ни номера
протокола закупки, ни ставки НДС (зависит от будущего поставщика). Печатать
туда плановые/подставные значения — ошибка (владелец, 28.10.2026: «там ещё
ни цены, ни поставщика... только переменные заказчика»).

ПРАВИЛО №6: единственное место, где определён список полей, гасимых для
этого документа — здесь. render_fabrikant_package_files (fabrikant_package.py)
применяет apply_contract_project_blanks(context) ТОЛЬКО при рендере doc_key ==
"fabrikant_contract_project"; остальные 4 документа пакета используют общий
context без изменений.
"""

from __future__ import annotations

# "__.__.____" — один источник (ПРАВИЛО №6): не считаем вторую копию этой
# константы, а берём её из общего модуля, который применяет то же гашение
# дат/номеров ко ВСЕМ документам (apply_blank_placeholders/render_docx).
from .blank_placeholders import BLANK_DATE as _BLANK_DATE

# Длина линии подобрана по месту переменной в шаблоне — см. текст вокруг
# подстановки в backend/templates/fabrikant_contract_project.docx:
#   'Договор поставки № {{ contract_number }}'
#   '«{{ contract_date_day }}» {{ contract_date_month }} {{ contract_date_year }} г.'
#   '... (Протокол №{{ procurement_protocol_number }} от___) ...'
#   '{{ contract_price_num }} ({{ contract_price_words }}) рублей 00 копеек, ...'
#   '№ {{ contract_number }} от {{ contract_date }}' (Приложение № 1)
#   'действует ... до {{ contract_end_date }}' / 'поставить товар в срок до {{ delivery_date }}'
_BLANK_DAY = "__"                    # «__» — день
_BLANK_MONTH = "__________"          # месяц словом
_BLANK_YEAR = "____"                 # год (далее в шаблоне литерал " г." → "____ г.")
_BLANK_NUMBER = "__________"         # номер договора / протокола закупки
# _BLANK_DATE — см. импорт BLANK_DATE из blank_placeholders.py выше (ПРАВИЛО №6)
_BLANK_MONEY_NUM = "______________"  # цена цифрами
_BLANK_MONEY_WORDS = "____________________________________"  # цена словами, в скобках
_BLANK_VAT_RATE = "__"               # ставка НДС (на проекте не печатается — vat_undetermined=True,
                                      # но гасим и это поле на случай будущей правки шаблона)
_BLANK_ARTICLE = "_______________"   # основание освобождения от НДС (та же причина)
_BLANK_CONTRACTOR = "____________________________________"  # любое поле contractor_* (имя, подписант, реквизиты)

# customer_*/subsidy_*/contract_city — реквизиты Заказчика и его соглашения
# о субсидии, уже известны на этапе проекта договора; единственный расчёт —
# add_customer_context/add_subsidy_agreement_context в fabrikant_package.py
# (ПРАВИЛО №6) — здесь их не трогаем.
_KEEP_PREFIXES: tuple[str, ...] = ("customer_", "subsidy_")
_KEEP_EXACT: frozenset[str] = frozenset({"contract_city"})

# Поля, гасимые по точному имени (не покрываются префиксом "contractor_").
EXPLICIT_BLANK_FIELDS: dict[str, str] = {
    "contract_number": _BLANK_NUMBER,
    "contract_date": _BLANK_DATE,
    "contract_date_day": _BLANK_DAY,
    "contract_date_month": _BLANK_MONTH,
    "contract_date_year": _BLANK_YEAR,
    "contract_end_date": _BLANK_DATE,
    "delivery_date": _BLANK_DATE,
    "contract_price_num": _BLANK_MONEY_NUM,
    "contract_price_words": _BLANK_MONEY_WORDS,
    "procurement_protocol_number": _BLANK_NUMBER,
    "vat_rate": _BLANK_VAT_RATE,
    "vat_exemption_article": _BLANK_ARTICLE,
}


def apply_contract_project_blanks(context: dict) -> dict:
    """Возвращает НОВЫЙ context для рендера fabrikant_contract_project.docx.

    Исходный `context` не мутируется (используется тем же циклом рендера
    для остальных 4 документов пакета).

    Правила:
    - customer_*/subsidy_*/contract_city — без изменений (данные Заказчика);
    - любой ключ с префиксом "contractor_" (включая те, которых сейчас нет
      в этом шаблоне, но могут появиться при его правке) — линия
      подчёркиваний: поставщик на этапе проекта договора не выбран;
    - поля из EXPLICIT_BLANK_FIELDS — линия подчёркиваний нужной длины
      (цена, номер/дата договора, протокол закупки, ставка НДС/основание);
    - vat_undetermined — всегда True: на проекте договора НДС не может быть
      определён в принципе (зависит от будущего поставщика), независимо от
      того, что посчитано для остальных 4 документов пакета;
    - всё прочее — без изменений.
    """
    out = dict(context)
    for key in list(out.keys()):
        if key in _KEEP_EXACT or key.startswith(_KEEP_PREFIXES):
            continue
        if key.startswith("contractor_"):
            out[key] = _BLANK_CONTRACTOR
            continue
        if key in EXPLICIT_BLANK_FIELDS:
            out[key] = EXPLICIT_BLANK_FIELDS[key]
    out["vat_undetermined"] = True
    return out
