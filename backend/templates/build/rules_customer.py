"""
rules_customer.py — доп. правила замены литералов ВСКС, не покрытых
rules_common.py (найдено аудитом 2026-10-05, задача "шаблоны договоров:
подсказки, выдуманные примеры, реквизиты исполнителя, оплата").

Отдельный файл по ПРАВИЛУ №5 (модульность) — не раздувать rules_common.py.
Все замены — на {{ customer_short_name }} / {{ customer_correspondent_account }},
переменные уже существуют в contexts_extra.py и описаны в comments_ru.py,
новых переменных эта правка не вводит.

Порядок важен: CUST_C (Наименование: ВСКС) должен идти ДО CUST_D (голое
«ВСКС Адрес местонахождения:», без префикса «Наименование:» — так устроен
contract_repair_vehicle), иначе CUST_D захватит ВСКС ещё до того, как CUST_C
успеет его заменить в паре «Наименование: ВСКС Адрес...».
"""
import re

S = re.DOTALL


def _make_rules():
    rules = []

    # п.1.3 (services/services_food): «в рамках реализации ВСКС Соглашения»
    rules.append((
        "CUST_I_realization_vsks",
        re.compile(r"в рамках реализации ВСКС Соглашения", S),
        "в рамках реализации {{ customer_short_name }} Соглашения",
    ))

    # «Субсидии для ВСКС» (п.4.5/4.6) и методичка «... услуг для ВСКС)» —
    # один общий литерал «для ВСКС», граница \b отделяет от других слов.
    rules.append((
        "CUST_B_dlya_vsks",
        re.compile(r"для ВСКС\b", S),
        "для {{ customer_short_name }}",
    ))

    # «Наименование: ВСКС Адрес местонахождения...» (услуги/товары/ГПХ)
    rules.append((
        "CUST_C_naimenovanie_vsks",
        re.compile(r"Наименование:\s+ВСКС\s", S),
        "Наименование: {{ customer_short_name }} ",
    ))

    # «Единый казначейский счет: 40102810545370000003» — реальный ЕКС ВСКС,
    # не пойман C26/C27 (они ловят другой лейбл «Казначейский счет:»).
    rules.append((
        "CUST_F_treasury_unified_account",
        re.compile(r"Единый казначейский счет:\s*40102810545370000003", S),
        "Единый казначейский счет: {{ customer_correspondent_account }}",
    ))

    # ГПХ с РИД: «направить через месенджеры или эл.почту ВСКС.»
    rules.append((
        "CUST_G_email_vsks",
        re.compile(r"эл\.почту ВСКС", S),
        "эл.почту {{ customer_short_name }}",
    ))

    # ГПХ: «обработку персональных данных ВСКС вправе продолжить»
    rules.append((
        "CUST_H_pd_vsks_vprave",
        re.compile(r"персональных данных ВСКС вправе", S),
        "персональных данных {{ customer_short_name }} вправе",
    ))

    # «ОКПО 17777419» — реальный код ВСКС. Поля customer_okpo в системе
    # нет (ревью 2026-10-05: grep пуст) — пустая линия с подсказкой
    # (BLANK_COMMENTS в comments_ru.py), а не переменная.
    rules.append((
        "CUST_K_okpo_blank",
        re.compile(r"^ОКПО\s+17777419$", S),
        "ОКПО __________",
    ))

    return rules


RULES = _make_rules()

_BARE_VSKS_RE = re.compile(r"^ВСКС$")
_TREASURY_NUMBER_RE = re.compile(r"^40102810545370000003$")
_TREASURY_LABEL_RE = re.compile(r"Единый казначейский счет")


def apply_customer_cross_paragraph_rules(paragraphs: list, counts: dict) -> None:
    """
    Два случая, где ВСКС-литерал — ЦЕЛЫЙ отдельный абзац (не ран внутри
    абзаца с другим текстом), поэтому их не поймать обычным regex внутри
    одного para_text() (как это уже устроено в rules_order.py для похожего
    случая с многоабзацной ячейкой шапки приказа):

      1. Подпись Заказчика: абзац «Заказчик»/«Покупатель»/«Исполнитель»
         (ярлык), ЗА НИМ отдельным абзацем голое «ВСКС» (значение) —
         во всех 7 договорных формах.
      2. ГПХ: абзац «Единый казначейский счет:» (ярлык), за ним отдельным
         абзацем голое «40102810545370000003» (значение, ЕКС).
    """
    from backend.templates.build.docxedit import para_text, replace_in_para

    for i, p in enumerate(paragraphs):
        txt = para_text(p).strip()

        if _BARE_VSKS_RE.match(txt):
            full_text = para_text(p)
            replace_in_para(p, 0, len(full_text), "{{ customer_short_name }}")
            counts["CUST_D_bare_vsks_paragraph"] = counts.get("CUST_D_bare_vsks_paragraph", 0) + 1
            continue

        if _TREASURY_NUMBER_RE.match(txt) and i > 0 and _TREASURY_LABEL_RE.search(para_text(paragraphs[i - 1])):
            full_text = para_text(p)
            replace_in_para(p, 0, len(full_text), "{{ customer_correspondent_account }}")
            counts["CUST_F2_treasury_split_paragraph"] = counts.get("CUST_F2_treasury_split_paragraph", 0) + 1


def apply_customer_rules(p, counts: dict) -> int:
    """Применяет RULES к абзацу p — та же схема, что apply_common_rules."""
    from backend.templates.build.docxedit import para_text, replace_in_para

    total = 0
    for rule_id, pattern, repl in RULES:
        text = para_text(p)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        for m in reversed(matches):
            replacement = repl(m) if callable(repl) else m.expand(repl)
            replace_in_para(p, m.start(), m.end(), replacement)
            counts[rule_id] = counts.get(rule_id, 0) + 1
            total += 1
    return total
