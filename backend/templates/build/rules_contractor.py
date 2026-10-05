"""
rules_contractor.py — заполняет пустые реквизиты ИСПОЛНИТЕЛЯ/ПОСТАВЩИКА в
разделе «Адреса и реквизиты Сторон» (сейчас пустые подписи: «Банк
получателя:», «Р/с:», «БИК:», «ФИО»). Переменные contractor_* — из
app/services/documents/contexts_extra.py / generate.py (не трогаются этим
агентом, см. задание). Отдельный файл по ПРАВИЛУ №5 — не раздувать
rules_common.py.

Банковские поля (р/с, банк, БИК, к/с) печатают «__________» если значение
пустое (контрагент не заполнил реквизиты в карточке) — `{{ x or '__________' }}`
в docxtpl/Jinja2 работает и для None, и для пустой строки.
"""
import re

S = re.DOTALL

_BLANK = "'__________'"


def _or_blank(var: str) -> str:
    return "{{ " + var + " or " + _BLANK + " }}"


def _make_rules():
    """
    В разделе «Адреса и реквизиты Сторон» каждый лейбл Исполнителя/Поставщика
    — ОТДЕЛЬНЫЙ абзац сам по себе, без значения и без склейки с соседними
    абзацами (проверено docxedit-дампом источников: «Наименование:»,
    «Адрес местонахождения:», «ИНН/КПП», «ОГРН», «ИНН», «ОГРНИП», «р/с:»,
    «в», «БИК:», «к/с:», «Тел.:» — каждый в своём <w:p>). Поэтому все
    правила ниже — точное совпадение ВСЕГО абзаца (^...$), а не regex,
    ожидающий соседний текст в том же абзаце. Это одновременно и безопасно
    (не трогает уже заполненные/customer-абзацы — те содержат кроме лейбла
    ещё текст или тег, под ^...$ не подходят) и само повторяется на ВСЕХ
    местах документа, где встречается точно такой же пустой лейбл
    (основной блок реквизитов + сокращённые подписи в приложениях).
    """
    rules = []

    rules.append((
        "CTR_01_name_label",
        re.compile(r"^Наименование:?$", S),
        lambda m: "Наименование: {{ contractor_full_name }}" if m.group(0).endswith(":")
        else "Наименование {{ contractor_full_name }}",
    ))

    rules.append((
        "CTR_02_address_label",
        re.compile(r"^Адрес местонахождения:$", S),
        "Адрес местонахождения: {{ contractor_address }}",
    ))

    rules.append((
        "CTR_03_postal_address_label",
        re.compile(r"^Почтовый адрес:$", S),
        "Почтовый адрес: {{ contractor_postal_address }}",
    ))

    # ИНН/КПП + ОГРН + ИНН + ОГРНИП — обёртка в if/else по
    # contractor_org_type теперь кросс-абзацная, см.
    # apply_contractor_inn_ogrn_wrap ниже (ревью 2026-10-05: печатались ОБА
    # варианта подряд — ОГРН у юрлица И ОГРНИП одновременно).

    # «р/с:» / «в» / «БИК:» / «к/с:» — четыре отдельных абзаца подряд
    # (банк контрагента — «в» как предлог перед наименованием банка).
    rules.append((
        "CTR_05a_settlement_account",
        re.compile(r"^р/с:$", S),
        "р/с: " + _or_blank("contractor_settlement_account"),
    ))
    rules.append((
        "CTR_05b_bank_name",
        re.compile(r"^в$", S),
        "в " + _or_blank("contractor_bank_name"),
    ))
    rules.append((
        "CTR_05c_bik",
        re.compile(r"^БИК:$", S),
        "БИК: " + _or_blank("contractor_bik"),
    ))
    rules.append((
        "CTR_05d_correspondent_account",
        re.compile(r"^к/с:$", S),
        "к/с: " + _or_blank("contractor_correspondent_account"),
    ))

    rules.append((
        "CTR_06_phone_label",
        re.compile(r"^Тел\.:$", S),
        "Тел.: {{ contractor_phone }}",
    ))

    # Подпись: «____________________ / ФИО» → инициалы подписанта
    # (contractor_signatory_initials, формат «Фамилия И.О.» — см. сверку
    # агента Б).
    rules.append((
        "CTR_07_signatory_fio",
        re.compile(r"/ ФИО\b", S),
        "/ {{ contractor_signatory_initials }}",
    ))

    return rules


RULES = _make_rules()


def apply_contractor_inn_ogrn_wrap(paragraphs: list, counts: dict) -> None:
    """
    Блок «ИНН/КПП» / «ОГРН» / «ИНН» / «ОГРНИП» — четыре отдельных абзаца
    подряд (первая пара — для юрлица, вторая — альтернативная пара для ИП,
    тот же смысл, что у R3 в преамбуле). Ревью 2026-10-05: раньше печатались
    ВСЕ четыре строки одновременно (ОГРН пустой + ИНН-дубль + ОГРНИП пустой)
    — оборачиваем первую пару в {%p if contractor_org_type != 'ИП' %},
    вторую — в {%p else %}, как и в R3. Пустые значения — «__________».
    Применяется один раз на документ (repair_framework исключён — там
    своя двух-блочная структура без ОГРНИП, см. apply_framework_dual_requisites).
    """
    from backend.templates.build.docxedit import para_text, insert_para_before, insert_para_after, replace_in_para

    n = len(paragraphs)
    i = 0
    while i < n:
        if para_text(paragraphs[i]).strip() != "ИНН/КПП":
            i += 1
            continue

        inn_kpp_p = paragraphs[i]

        ogrn_p = None
        for j in range(i + 1, min(i + 4, n)):
            if para_text(paragraphs[j]).strip() == "ОГРН":
                ogrn_p = paragraphs[j]
                ogrn_idx = j
                break
        if ogrn_p is None:
            i += 1
            continue

        inn_p = None
        for k in range(ogrn_idx + 1, min(ogrn_idx + 4, n)):
            if para_text(paragraphs[k]).strip() == "ИНН":
                inn_p = paragraphs[k]
                inn_idx = k
                break
        if inn_p is None:
            i += 1
            continue

        ogrnip_p = None
        for m_ in range(inn_idx + 1, min(inn_idx + 3, n)):
            if para_text(paragraphs[m_]).strip() == "ОГРНИП":
                ogrnip_p = paragraphs[m_]
                ogrnip_idx = m_
                break
        if ogrnip_p is None:
            i += 1
            continue

        replace_in_para(
            inn_kpp_p, 0, len(para_text(inn_kpp_p)),
            "ИНН/КПП " + _or_blank("contractor_inn") + "/" + _or_blank("contractor_kpp"),
        )
        replace_in_para(ogrn_p, 0, len(para_text(ogrn_p)), "ОГРН " + _or_blank("contractor_ogrn"))
        replace_in_para(inn_p, 0, len(para_text(inn_p)), "ИНН " + _or_blank("contractor_inn"))
        replace_in_para(ogrnip_p, 0, len(para_text(ogrnip_p)), "ОГРНИП " + _or_blank("contractor_ogrnip"))

        insert_para_before(inn_kpp_p, "{%p if contractor_org_type != 'ИП' %}")
        insert_para_after(ogrn_p, "{%p else %}")
        insert_para_after(ogrnip_p, "{%p endif %}")
        counts["CTR_04_inn_ogrn_wrap"] = counts.get("CTR_04_inn_ogrn_wrap", 0) + 1

        i = ogrnip_idx + 1


# ── repair_framework: «Адреса и реквизиты Сторон» — ДВА одинаковых по
# тексту блока лейблов подряд (Заказчик, затем Исполнитель), каждый
# label-абзац САМ ПО СЕБЕ (без значения, без склейки с соседями) — generic
# RULES выше их не ловят (нет чем отличить соседние абзацы), а наивный
# regex по каждому абзацу отдельно не может понять, какой блок перед ним.
# rules_common.py уже тегирует «Наименование:» ЗАКАЗЧИКА (C00d/C00c, другой
# литерал — «региональное отделение...»); секция НИЖЕ начинается именно с
# результата этой замены как с якоря «Заказчик», а блок ИСПОЛНИТЕЛЯ находит
# по оставшемуся пустому «Наименование: _______».
_FW_CUSTOMER_NAME_DONE = "Наименование: {{ customer_full_name }}"
_FW_CONTRACTOR_NAME_BLANK_RE = re.compile(r"^Наименование:\s+_+\s*$")
# Подписи — уникальные по форме для этого шаблона (Заказчик: длинное тире
# без «/»; Исполнитель: короткое тире с «/.», М.П. отдельным абзацем).
_FW_CUSTOMER_SIGNATURE_RE = re.compile(r"^_+\s{2,}М\.П\.$")
_FW_CONTRACTOR_SIGNATURE_RE = re.compile(r"^_+\s*/\.$")


def _fill_framework_block(paragraphs: list, start_idx: int, prefix: str, counts: dict) -> None:
    from backend.templates.build.docxedit import para_text, replace_in_para

    n = len(paragraphs)
    j = start_idx + 1

    if j < n and para_text(paragraphs[j]).strip() == "Адрес местонахождения:":
        full = para_text(paragraphs[j])
        replace_in_para(paragraphs[j], 0, len(full), f"Адрес местонахождения: {{{{ {prefix}_address }}}}")
        counts[f"CTR_FW_address_{prefix}"] = counts.get(f"CTR_FW_address_{prefix}", 0) + 1
        j += 1

    if j < n:
        stripped = para_text(paragraphs[j]).strip()
        if stripped == "ИНН\nКПП":
            full = para_text(paragraphs[j])
            replace_in_para(
                paragraphs[j], 0, len(full),
                f"ИНН {{{{ {prefix}_inn }}}}\nКПП {{{{ {prefix}_kpp }}}}",
            )
            counts[f"CTR_FW_inn_kpp_{prefix}"] = counts.get(f"CTR_FW_inn_kpp_{prefix}", 0) + 1
            j += 1
        elif stripped == "ИНН":
            full = para_text(paragraphs[j])
            replace_in_para(paragraphs[j], 0, len(full), f"ИНН {{{{ {prefix}_inn }}}}")
            counts[f"CTR_FW_inn_{prefix}"] = counts.get(f"CTR_FW_inn_{prefix}", 0) + 1
            j += 1
            if j < n and para_text(paragraphs[j]).strip() == "КПП":
                full = para_text(paragraphs[j])
                replace_in_para(paragraphs[j], 0, len(full), f"КПП {{{{ {prefix}_kpp }}}}")
                counts[f"CTR_FW_kpp_{prefix}"] = counts.get(f"CTR_FW_kpp_{prefix}", 0) + 1
                j += 1

    if j < n and para_text(paragraphs[j]).strip().rstrip() == "ОГРН":
        full = para_text(paragraphs[j])
        replace_in_para(paragraphs[j], 0, len(full), f"ОГРН {{{{ {prefix}_ogrn }}}}")
        counts[f"CTR_FW_ogrn_{prefix}"] = counts.get(f"CTR_FW_ogrn_{prefix}", 0) + 1
        j += 1

    if j < n and para_text(paragraphs[j]).strip() == "Банковские реквизиты":
        full = para_text(paragraphs[j])
        bank_text = (
            f"Банковские реквизиты: {_or_blank(prefix + '_bank_name')}, "
            f"р/с {_or_blank(prefix + '_settlement_account')}, "
            f"БИК {_or_blank(prefix + '_bik')}, "
            f"к/с {_or_blank(prefix + '_correspondent_account')}"
        )
        replace_in_para(paragraphs[j], 0, len(full), bank_text)
        counts[f"CTR_FW_bank_{prefix}"] = counts.get(f"CTR_FW_bank_{prefix}", 0) + 1


def apply_framework_dual_requisites(paragraphs: list, counts: dict) -> None:
    """contract_repair_framework: заполняет оба блока (Заказчик/Исполнитель)
    реквизитов — см. докстринг выше."""
    from backend.templates.build.docxedit import para_text, replace_in_para

    for i, p in enumerate(paragraphs):
        txt = para_text(p).strip()
        if txt == _FW_CUSTOMER_NAME_DONE:
            _fill_framework_block(paragraphs, i, "customer", counts)
        elif _FW_CONTRACTOR_NAME_BLANK_RE.match(txt):
            full = para_text(p)
            replace_in_para(p, 0, len(full), "Наименование: {{ contractor_full_name }}")
            counts["CTR_FW_name_contractor"] = counts.get("CTR_FW_name_contractor", 0) + 1
            _fill_framework_block(paragraphs, i, "contractor", counts)
        elif _FW_CUSTOMER_SIGNATURE_RE.match(txt):
            full = para_text(p)
            replace_in_para(p, 0, len(full), "_________________ / {{ customer_signatory_name_initials }}М.П.")
            counts["CTR_FW_signature_customer"] = counts.get("CTR_FW_signature_customer", 0) + 1
        elif _FW_CONTRACTOR_SIGNATURE_RE.match(txt):
            full = para_text(p)
            replace_in_para(p, 0, len(full), "____________________ / {{ contractor_signatory_initials }}.")
            counts["CTR_FW_signature_contractor"] = counts.get("CTR_FW_signature_contractor", 0) + 1


def apply_contractor_rules(doc_type: str, p, counts: dict) -> int:
    """Применяет RULES к абзацу p — та же схема, что apply_common_rules.

    contract_repair_framework пропускает этот generic-проход целиком: там
    реквизиты — голые лейблы без склейки с соседями (см.
    apply_framework_dual_requisites выше), а не единый текст в одном
    абзаце, который ловят CTR_01..CTR_07.
    """
    if doc_type == "contract_repair_framework":
        return 0

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
