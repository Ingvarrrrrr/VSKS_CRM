"""
rules_payment.py — пункт об оплате по переключателю «предоплата/постоплата»
(контекстные переменные is_prepayment, prepayment_date — добавляет агент Б
в app/services/documents/*, здесь только разметка шаблона) + жёсткие
«15 рабочих дней» в договорах на услуги/ремонт заменяются на
payment_term_days. Отдельный файл по ПРАВИЛУ №5.

contract_goods_single уже печатает ОБА варианта п.4.3 подряд (постоплата +
100% предоплата) — здесь они оборачиваются в {%p if %}/{%p else %}/{%p endif %}.
contract_services/contract_services_food/contract_repair_framework печатают
ТОЛЬКО постоплату (жёстко «15 (пятнадцати) рабочих дней») — здесь перед этим
абзацем вставляется клон-вариант предоплаты и оба оборачиваются тем же
способом.
"""
import re

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = re.DOTALL

# ── contract_goods_single: обёртка уже существующей пары абзацев ──────────

_GOODS_NO_ADVANCE_RE = re.compile(
    r"Расчеты осуществляются без авансирования в безналичной форме путем "
    r"перечисления денежных средств на расчетный счет Поставщика за "
    r"фактически полученные и принятые Покупателем товары"
)
_GOODS_PREPAY_RE = re.compile(
    r"Расчеты осуществляются в формате 100% предоплаты"
)


def apply_goods_prepayment_wrap(paragraphs: list, counts: dict) -> None:
    """
    contract_goods_single: два соседних абзаца п.4.3 (без аванса / 100%
    предоплата) оборачиваются в {%p if not is_prepayment %} ... {%p else %}
    ... {%p endif %} (в документе постоплата идёт первой).
    """
    from backend.templates.build.docxedit import (
        para_text, insert_para_before, insert_para_after, replace_in_para,
    )

    no_advance_p = None
    prepay_p = None
    for p in paragraphs:
        txt = para_text(p)
        if no_advance_p is None and _GOODS_NO_ADVANCE_RE.search(txt):
            no_advance_p = p
        elif prepay_p is None and _GOODS_PREPAY_RE.search(txt):
            prepay_p = p

    if no_advance_p is None or prepay_p is None:
        return

    insert_para_before(no_advance_p, "{%p if not is_prepayment %}")
    insert_para_after(no_advance_p, "{%p else %}")
    insert_para_after(prepay_p, "{%p endif %}")
    counts["PAY_goods_prepayment_wrap"] = counts.get("PAY_goods_prepayment_wrap", 0) + 1

    # В варианте предоплаты — упоминание суммы аванса, если она задана
    # (полная 100% предоплата не исключает частичного аванса по факту
    # перечисления, см. план владельца).
    txt = para_text(prepay_p)
    marker = "при условии получения Покупателем от Поставщика счета на оплату."
    idx = txt.find(marker)
    if idx != -1:
        # replace_in_para не умеет вставку «в точку» (start==end — no-op),
        # поэтому переписываем сам маркер целиком, приклеивая предложение
        # об авансе после него.
        replace_in_para(
            prepay_p, idx, idx + len(marker),
            marker + " {% if advance_amount %}Сумма аванса: {{ advance_amount }} руб.{% endif %}",
        )
        counts["PAY_goods_advance_amount_mention"] = 1


# ── contract_services / contract_services_food / contract_repair_framework:
#    только постоплата жёстко «15 (пятнадцати) рабочих дней» — добавляем
#    вариант предоплаты и переводим срок на payment_term_days ──────────────

_SERVICES_POSTPAY_ANCHOR_RE = re.compile(
    r"Расчеты осуществляются без авансирования в безналичной форме путем "
    r"перечисления денежных средств на расчетный счет Исполнителя за "
    r"фактически оказанные Услуги"
)
# Захватываем ВСЮ фразу «(в) течение 15 (пятнадцати) рабочих дней» целиком —
# замена ниже восстанавливает «в» (в исходнике опечатка «Услуги течение»,
# без «в») и сохраняет «рабочих дней» (баг 2026-10-05: замена заменяла
# только числительное, роняя «рабочих дней» целиком).
_SERVICES_15_DAYS_RE = re.compile(
    r"(?:в\s+)?течение\s+15\s*\(пятнадцати\)\s*рабочих дней"
)

_SERVICES_PREPAY_TEXT = (
    "4.2. Расчеты осуществляются с предоплатой в безналичной форме путем "
    "перечисления денежных средств на расчетный счет Исполнителя в течение "
    "{{ payment_term_days or '____' }} ({{ payment_term_days_words or '____' }}) рабочих дней с момента "
    "заключения настоящего Договора{% if advance_amount %} в размере аванса "
    "{{ advance_amount }} руб.{% endif %}, при условии получения Исполнителем "
    "от Заказчика счета на оплату. Платеж считается осуществленным с момента "
    "списания денежных средств со счета Заказчика."
)

_FRAMEWORK_POSTPAY_ANCHOR_RE = re.compile(
    r"Оплата всех денежных платежей может быть произведена в форме "
    r"безналичного перечисления на расчетный счет Исполнителя"
)
_FRAMEWORK_PREPAY_TEXT = (
    "4.5. Оплата всех денежных платежей может быть произведена в форме "
    "предоплаты, путём перечисления денежных средств на расчетный счет "
    "Исполнителя в течение {{ payment_term_days or '____' }} ({{ payment_term_days_words or '____' }}) "
    "рабочих дней с момента заключения настоящего Договора{% if advance_amount %} "
    "в размере аванса {{ advance_amount }} руб.{% endif %}, на основании "
    "выставленного Исполнителем счета на оплату и счет-фактуры (если применимо)."
)


def _wrap_postpay_with_new_prepay_before(
    paragraphs: list, anchor_re, prepay_text: str, counts: dict, rule_id: str,
) -> None:
    from backend.templates.build.docxedit import (
        para_text, insert_para_before, insert_para_after, replace_in_para,
    )

    postpay_p = None
    for p in paragraphs:
        if anchor_re.search(para_text(p)):
            postpay_p = p
            break
    if postpay_p is None:
        return

    # «(в) течение 15 (пятнадцати) рабочих дней» → payment_term_days (только
    # в НАЙДЕННОМ абзаце постоплаты — не трогаем другие «15 рабочих дней»,
    # например срок приёмки услуг в п.3.2). Восстанавливаем «в» (в
    # исходнике опечатка «Услуги течение», без «в») и сохраняем «рабочих
    # дней» целиком (баг 2026-10-05: предыдущая замена роняла оба).
    txt = para_text(postpay_p)
    m = _SERVICES_15_DAYS_RE.search(txt)
    if m:
        replace_in_para(
            postpay_p, m.start(), m.end(),
            "в течение {{ payment_term_days or '____' }} ({{ payment_term_days_words or '____' }}) рабочих дней",
        )

    prepay_p = insert_para_before(postpay_p, prepay_text)
    insert_para_before(prepay_p, "{%p if is_prepayment %}")
    insert_para_after(prepay_p, "{%p else %}")
    insert_para_after(postpay_p, "{%p endif %}")
    counts[rule_id] = counts.get(rule_id, 0) + 1


def apply_payment_prepayment_wrap(doc_type: str, paragraphs: list, counts: dict) -> None:
    """Диспетчер: вызывает нужный враппер по doc_type."""
    if doc_type == "contract_goods_single":
        apply_goods_prepayment_wrap(paragraphs, counts)
    elif doc_type in ("contract_services", "contract_services_food"):
        _wrap_postpay_with_new_prepay_before(
            paragraphs, _SERVICES_POSTPAY_ANCHOR_RE, _SERVICES_PREPAY_TEXT,
            counts, "PAY_services_prepayment_wrap",
        )
    elif doc_type == "contract_repair_framework":
        _wrap_postpay_with_new_prepay_before(
            paragraphs, _FRAMEWORK_POSTPAY_ANCHOR_RE, _FRAMEWORK_PREPAY_TEXT,
            counts, "PAY_framework_prepayment_wrap",
        )


# ── contract_services / contract_services_food: место и срок оказания услуг
#    (delivery_location / delivery_date) — п.1.3 сейчас отдаёт точное время
#    и место через ТЗ без переменных; здесь подставляем явную строку места,
#    если в тексте остался пустой бланк. ──────────────────────────────────

_SERVICE_PLACE_BLANK_RE = re.compile(
    r"Точное время и место оказания Услуг определяются в соответствии с "
    r"условиями, установленными в Техническом"
)


def apply_services_delivery_rules(doc_type: str, p, counts: dict) -> int:
    """
    Для contract_services/contract_services_food добавляет явную строку
    «Место оказания Услуг: {{ delivery_location }}.» перед действующей
    фразой про ТЗ (которая остаётся как есть — она описывает ВРЕМЯ, место
    теперь указывается явно отдельным предложением).
    """
    if doc_type not in ("contract_services", "contract_services_food"):
        return 0
    from backend.templates.build.docxedit import para_text, replace_in_para

    text = para_text(p)
    m = _SERVICE_PLACE_BLANK_RE.search(text)
    if not m:
        return 0
    # replace_in_para не поддерживает вставку «в точку» (start==end —
    # no-op), поэтому переписываем найденный анкор целиком, приклеивая
    # новое предложение перед ним.
    replace_in_para(
        p, m.start(), m.end(),
        "Место оказания Услуг: {{ delivery_location }}. " + m.group(0),
    )
    counts["PAY_services_delivery_location"] = counts.get("PAY_services_delivery_location", 0) + 1
    return 1
