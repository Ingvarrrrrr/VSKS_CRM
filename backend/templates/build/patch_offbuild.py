"""
patch_offbuild.py — чистит реквизиты ВСКС в шаблонах, которые лежат ВНЕ
сборки (SOURCES в sources.py их не знает — `contract.docx`/`contract_tz.docx`
собираются когда-то вручную и коммитятся как есть, см. задание владельца
05.10.2026). У `contract.docx` реальных данных ВСКС не нашлось — пропускается
без изменений. `contract_tz.docx` содержит реквизиты ВСКС дословно (ИНН
7704190720, ОГРН 1037739183516, адрес Вернадского, р/с 40703810138060100002,
ПАО Сбербанк, БИК 044525225, к/с) — переводятся на customer_* переменные.

Идемпотентно: правила ищут буквальный текст ВСКС, после первой чистки им
нечего заменять — повторный запуск не меняет файл (sha256 стабилен для
--check). Если кто-то вручную вернёт литерал ВСКС в committed-файл, --check
снова найдёт расхождение (чистка даст другой результат, чем в репозитории).

Регенерации «из первоисточника» здесь НЕТ (в отличие от build_one) — нет
достоверного pristine-источника для этого файла (см. отчёт сессии), поэтому
патчится прямо committed-файл.
"""
import pathlib
import re

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = re.DOTALL

PATCHED_FILES = ("contract_tz.docx", "service_note.docx", "service_note_advance.docx",
                  "service_note_delivery.docx", "service_note_payment.docx",
                  "service_note_procurement.docx", "contract.docx")

# Ревью 2026-10-05: «contract.docx — 129 тегов, 0 подсказок; contract_tz.docx
# — 50, 0; tech_spec_request/tech_spec_contract — живые doc_type
# (doc_types.py), 0 подсказок». Эти 4 файла вне SOURCES (SOURCES их не
# знает, не строятся из первоисточника) ИМЕЮТ реальные используемые
# doc_type (contract, contract_tz, tech_spec_request, tech_spec_contract в
# DOC_TYPES) — подсказки нужны так же, как у 7 договорных форм. Источник
# подсказок — ТОТ ЖЕ comments_ru.py/rules_comments.py (ПРАВИЛО №6: один
# словарь, не копия). service_note_* — тоже вне SOURCES, тоже реальные
# doc_type (doc_types.py) и тоже «Президенту ВСКС» (см. SERVICE_NOTE_RULES).
COMMENTED_FILES = (
    "contract.docx",
    "contract_tz.docx",
    "tech_spec_request.docx",
    "tech_spec_contract.docx",
    "service_note.docx",
    "service_note_advance.docx",
    "service_note_delivery.docx",
    "service_note_payment.docx",
    "service_note_procurement.docx",
)


def _make_rules():
    rules = []

    # Абзацы содержат <w:br/> (перенос строки внутри одного <w:p>) — в
    # para_text() это символ «\n», поэтому между склеенными кусками везде
    # \s* (не буквальный пробел).
    rules.append((
        "OFF_01_customer_full_name_inn_kpp_ogrn",
        re.compile(
            r"Всероссийская общественная молодежная организация «ВСКС»\s*"
            r"ИНН:\s*7704190720\s*/\s*КПП:\s*770401001\s*"
            r"ОГРН:\s*1037739183516",
            S,
        ),
        "{{ customer_full_name }} ({{ customer_short_name }}) "
        "ИНН: {{ customer_inn }} / КПП: {{ customer_kpp }} "
        "ОГРН: {{ customer_ogrn }}",
    ))

    rules.append((
        "OFF_02_customer_address",
        re.compile(
            r"Адрес:\s*Пр-т Вернадского, д\. 78, стр\. 8, Москва, 119454",
            S,
        ),
        "Адрес: {{ customer_address }}",
    ))

    rules.append((
        "OFF_03_customer_bank_block",
        re.compile(
            r"р/с\s*40703810138060100002\s*"
            r"ПАО Сбербанк г\. Москва\s*"
            r"БИК\s*044525225\s*\|\s*к/с\s*30101810400000000225",
            S,
        ),
        "р/с {{ customer_settlement_account }} "
        "{{ customer_bank_name }} "
        "БИК {{ customer_bik }} | к/с {{ customer_correspondent_account }}",
    ))

    rules.append((
        "OFF_04_customer_signatory_position",
        re.compile(r"Председатель Совета(?=\s*_+\s*/)", S),
        "{{ customer_signatory_position }}",
    ))

    # «Председатель Совета _______________  /  М.П.» — подпись заказчика
    # между «/» и «М.П.» пуста, заполняем инициалами подписанта.
    rules.append((
        "OFF_05_customer_signatory_initials",
        re.compile(r"(_+\s*/\s*)(М\.П\.)", S),
        r"\g<1>{{ customer_signatory_name_initials }}\g<2>",
    ))

    return rules


RULES = _make_rules()


def _make_service_note_rules():
    """
    Служебные записки (service_note*.docx) — вне SOURCES, как и
    contract_tz.docx. Шапка «Кому» во всех пяти файлах содержит дословно
    «Президенту ВСКС{{customer_signatory_name_genitive}}» (ревью
    2026-10-05). customer_signatory_position не подходит буквально
    («Президент» в им. падеже, а нужен дательный — и должность у другой
    организации может быть не «Президент») — customer_signatory_position_
    dative переменной в контексте НЕТ (проверено: add_customer_context в
    contexts_extra.py её не строит). Использован ОБЩИЙ дательный оборот
    «Руководителю» (не привязан к конкретной должности) + {{ customer_
    short_name }} — переменная подтверждённо есть в контексте служебки
    (add_customer_context вызывается безусловно для ВСЕХ doc_type в
    generate.py::generate_document_bytes, до доказательства обратного не
    гейтится по doc_type).
    """
    rules = []
    rules.append((
        "SN_01_prezidentu_vsks",
        re.compile(r"Президенту ВСКС", S),
        "Руководителю {{ customer_short_name }}",
    ))
    return rules


SERVICE_NOTE_RULES = _make_service_note_rules()


def _make_contract_offbuild_rules():
    """contract.docx — вне SOURCES, преамбула уже была переведена на jinja-
    теги раньше (не литерал ВСКС, как в contract_tz.docx), поэтому OFF_01..05
    здесь не подходят. Дефект (владелец, 14.10.2026): «в лице …» печатало
    должность в именительном падеже, хотя ФИО рядом уже стояло в родительном
    (`customer_signatory_name_genitive`/`contractor_signatory_name_genitive`)
    — должность не была переведена на `_genitive` вместе с ФИО. Те же теги
    `customer_signatory_position`/`contractor_signatory_position` ВНЕ «в
    лице» (строка подписи «E-mail: ...{{customer_signatory_position}}____»)
    трогать не нужно — там именительный падеж верен, как и в C40/CP14
    (rules_common.py/rules_fabrikant.py) — поэтому шаблон ловит ТОЛЬКО
    точную фразу «в лице {{...position}} {{...name_genitive}}».
    """
    rules = []
    rules.append((
        "OFF_06_customer_signatory_position_genitive",
        re.compile(
            r"в лице \{\{customer_signatory_position\}\} \{\{customer_signatory_name_genitive\}\}",
            S,
        ),
        "в лице {{customer_signatory_position_genitive}} {{customer_signatory_name_genitive}}",
    ))
    rules.append((
        "OFF_07_contractor_signatory_position_genitive",
        re.compile(
            r"в лице \{\{contractor_signatory_position\}\} \{\{contractor_signatory_name_genitive\}\}",
            S,
        ),
        "в лице {{contractor_signatory_position_genitive}} {{contractor_signatory_name_genitive}}",
    ))
    return rules


CONTRACT_RULES = _make_contract_offbuild_rules()


_CONTRACT_AGREEMENT_CLAUSE_RE = re.compile(
    r"^1\.4\.\s*Договор заключ[её]н в рамках реализации\s*\{\{\s*subsidy_agreement_text\s*\}\}\.?\s*$"
)
_CONTRACT_FINAL_HEADING_RE = re.compile(r"АДРЕСА И РЕКВИЗИТЫ СТОРОН", re.I)


def _apply_contract_subsidy_clauses(root) -> int:
    """
    contract.docx (вне SOURCES): владелец 21.10.2026 — пункт 1.4 «Договор
    заключён в рамках реализации {{subsidy_agreement_text}}.» уже есть в
    этом файле (в отличие от 7 собираемых форм, см.
    rules_subsidy_clauses.py), его только оборачивают в {%p if
    subsidy_agreement_text %} / {%p endif %} (не дублируют). Плюс — два
    доп. пункта {{subsidy_extra_clause_1}}/{{subsidy_extra_clause_2}}
    последними пунктами раздела 6 «СРОК ДЕЙСТВИЯ И ПОРЯДОК РАСТОРЖЕНИЯ
    ДОГОВОРА» (последний раздел перед «7. АДРЕСА И РЕКВИЗИТЫ СТОРОН» —
    текстовая нумерация, следующие номера 6.3/6.4).

    Идемпотентно: текст 1.4 не меняется при обёртке, поэтому регэксп сам по
    себе совпал бы и на уже обёрнутом абзаце — проверяем явно предыдущего
    соседа (если это уже «{%p if subsidy_agreement_text %}», повторно не
    оборачиваем). Финальные пункты — по наличию уже вставленного
    {{subsidy_extra_clause_1}} где-либо в документе, повторный --install
    их не дублирует.
    """
    from backend.templates.build import docxedit

    ns = {"w": W}
    n = 0
    paragraphs = root.findall(".//w:p", ns)

    agreement_p = None
    for p in paragraphs:
        if _CONTRACT_AGREEMENT_CLAUSE_RE.match(docxedit.para_text(p).strip()):
            agreement_p = p
            break
    if agreement_p is not None:
        parent = agreement_p.getparent()
        siblings = list(parent)
        idx = siblings.index(agreement_p)
        prev_text = None
        for i in range(idx - 1, -1, -1):
            if siblings[i].tag == f"{{{W}}}p":
                prev_text = docxedit.para_text(siblings[i]).strip()
                break
        if prev_text != "{%p if subsidy_agreement_text %}":
            docxedit.insert_para_before(agreement_p, "{%p if subsidy_agreement_text %}")
            docxedit.insert_para_after(agreement_p, "{%p endif %}")
            n += 1

    paragraphs = root.findall(".//w:p", ns)
    heading_p = None
    for p in paragraphs:
        text = docxedit.para_text(p).strip()
        if len(text) < 60 and _CONTRACT_FINAL_HEADING_RE.search(text):
            heading_p = p
            break
    if heading_p is not None:
        already = False
        for p in paragraphs:
            if "subsidy_extra_clause_1" in docxedit.para_text(p):
                already = True
                break
        if not already:
            parent = heading_p.getparent()
            idx = list(parent).index(heading_p)
            siblings = list(parent)
            template_p = None
            for i in range(idx - 1, -1, -1):
                if siblings[i].tag == f"{{{W}}}p":
                    template_p = siblings[i]
                    break
            if template_p is not None:
                new_p2 = docxedit.clone_para_with_text(
                    template_p,
                    "{% if subsidy_extra_clause_1 %}6.4{% else %}6.3{% endif %}."
                    " {{subsidy_extra_clause_2}}",
                )
                parent.insert(idx, new_p2)
                docxedit.insert_para_before(new_p2, "{%p if subsidy_extra_clause_2 %}")
                docxedit.insert_para_after(new_p2, "{%p endif %}")

                new_p1 = docxedit.clone_para_with_text(
                    template_p, "6.3. {{subsidy_extra_clause_1}}",
                )
                parent.insert(idx, new_p1)
                docxedit.insert_para_before(new_p1, "{%p if subsidy_extra_clause_1 %}")
                docxedit.insert_para_after(new_p1, "{%p endif %}")
                n += 1

    return n


_RULES_BY_FILE = {
    "service_note.docx": SERVICE_NOTE_RULES,
    "service_note_advance.docx": SERVICE_NOTE_RULES,
    "service_note_delivery.docx": SERVICE_NOTE_RULES,
    "service_note_payment.docx": SERVICE_NOTE_RULES,
    "service_note_procurement.docx": SERVICE_NOTE_RULES,
    "contract.docx": CONTRACT_RULES,
}


def _fix_service_note_delivery_tr_placement(root) -> int:
    """
    service_note_delivery.docx: TemplateSyntaxError: Encountered unknown tag
    'tr' на ЛЮБОМ render(), включая пустой контекст (обход 14.10.2026 —
    зафиксировано в test_template_vars_all_defined.py::_SKIP_FILES, причина
    там указана неверно: сам текст тега цифрой-в-цифру правильный,
    «{%tr for item in items %}» без пробела, как в tech_spec_request.docx /
    approval_sheet.docx / fabrikant_application_form.docx / contract_tz.docx /
    contract_repair_framework.docx — все пятеро рендерятся штатно).

    Настоящая причина — СТРУКТУРНАЯ, не опечатка в тексте: тег-строка лежит
    как обычный <w:p> ПЕРЕД <w:tbl> (для «for») и ПОСЛЕ </w:tbl> (для
    «endfor»), а не ВНУТРИ <w:tr> таблицы. docxtpl узнаёт {%tr/{%tr endfor%}
    только когда это содержимое целой строки таблицы — его regex в
    docxtpl/template.py буквально ищет
    `<w:tr ...>...{%tr ... %}...</w:tr>` и заменяет НА bare `{% ... %}`,
    чтобы Jinja2 увидел нормальный `{% for %}`/`{% endfor %}`. Тег вне
    <w:tr> этой подстановки не получает и попадает в Jinja2 как литеральный
    неизвестный тег «tr» — отсюда ошибка независимо от пробелов.

    Фикс переносит текст тегов в НОВЫЕ строки таблицы (прямо перед/после
    строки данных {{item.num}}/.../{{item.total_price}}) тем же механизмом
    клонирования строки, которым contract_repair_framework.docx решает
    точно такую же задачу (rules_common.py::_make_tag_row — ПРАВИЛО №6,
    переиспользуем, а не копируем вторую реализацию), и удаляет исходные
    параграфы-обёртки снаружи таблицы, чтобы их буквальный текст не остался
    дублем в документе.

    Идемпотентно: после первого прогона внутри таблицы уже стоят
    for/endfor-строки, а внешних параграфов с таким текстом больше нет —
    повторный вызов не находит, что переносить, и не меняет файл (sha256
    стабилен для --check).
    """
    from backend.templates.build import docxedit
    from backend.templates.build.rules_common import _make_tag_row

    ns = {"w": W}
    FOR_TEXT = "{%tr for item in items %}"
    ENDFOR_TEXT = "{%tr endfor %}"

    for_p = None
    endfor_p = None
    for p in root.findall(".//w:p", ns):
        # Пропускаем параграфы, которые уже находятся внутри строки таблицы
        # (<w:tr>) — они там, где и должны быть, трогать не нужно.
        if p.xpath("ancestor::w:tr", namespaces=ns):
            continue
        text = docxedit.para_text(p).strip()
        if text == FOR_TEXT:
            for_p = p
        elif text == ENDFOR_TEXT:
            endfor_p = p

    if for_p is None and endfor_p is None:
        return 0  # уже перенесено (повторный --install) или структура другая

    if for_p is None or endfor_p is None:
        raise RuntimeError(
            "service_note_delivery.docx: найден только один из тегов "
            f"for_p={for_p is not None} endfor_p={endfor_p is not None} — "
            "структура документа изменилась непредсказуемо, автофикс "
            "остановлен, чтобы не испортить файл дальше."
        )

    # Таблица идёт сразу за параграфом for_p в теле документа.
    body = for_p.getparent()
    idx = list(body).index(for_p)
    tbl = None
    for sibling in list(body)[idx:]:
        if sibling.tag == f"{{{W}}}tbl":
            tbl = sibling
            break
    if tbl is None:
        raise RuntimeError("service_note_delivery.docx: <w:tbl> не найден после тега for")

    rows = tbl.findall("w:tr", ns)
    data_row = None
    for row in rows:
        cells_text = "".join(docxedit.para_text(p2) for p2 in row.findall(".//w:p", ns))
        if "{{item." in cells_text:
            data_row = row
            break
    if data_row is None:
        raise RuntimeError("service_note_delivery.docx: строка данных {{item.*}} не найдена в таблице")

    for_row = _make_tag_row(data_row, FOR_TEXT)
    tbl.insert(list(tbl).index(data_row), for_row)

    endfor_row = _make_tag_row(data_row, ENDFOR_TEXT)
    tbl.insert(list(tbl).index(data_row) + 1, endfor_row)

    for_p.getparent().remove(for_p)
    endfor_p.getparent().remove(endfor_p)

    return 1


def patch_file(path: pathlib.Path) -> dict[str, int]:
    from backend.templates.build import docxedit

    rules = _RULES_BY_FILE.get(path.name, RULES)

    zip_bytes, root = docxedit.load(str(path))
    # normalize() убирает commentRangeStart/End и runs с commentReference —
    # обязательно ДО повторной навески подсказок (attach_hints), иначе
    # старые границы комментариев остаются в document.xml даже после того,
    # как docxedit.save() выбросил сам word/comments.xml, и повторный
    # --install плодит дубли комментариев (видно по РАСХОЖДЕНИЕ в --check).
    docxedit.normalize(root)
    ns = {"w": W}
    counts: dict[str, int] = {}

    if path.name == "service_note_delivery.docx":
        n_moved = _fix_service_note_delivery_tr_placement(root)
        if n_moved:
            counts["SND_01_tr_rows_moved_into_table"] = n_moved

    if path.name == "contract.docx":
        n_sub = _apply_contract_subsidy_clauses(root)
        if n_sub:
            counts["OFF_08_subsidy_clauses"] = n_sub

    for p in root.findall(".//w:p", ns):
        for rule_id, pattern, repl in rules:
            text = docxedit.para_text(p)
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            for m in reversed(matches):
                replacement = repl(m) if callable(repl) else m.expand(repl)
                docxedit.replace_in_para(p, m.start(), m.end(), replacement)
                counts[rule_id] = counts.get(rule_id, 0) + 1

    # Правила выше иногда захватывают span, пересекающий <w:br/> (перенос
    # строки внутри абзаца) — docxedit.replace_in_para оставляет "осиротевшие"
    # <w:t> с text="" на хвостовых ранах после такого span. lxml на ПЕРВОЙ
    # сериализации пишет такой узел как <w:t ...></w:t>, а при повторном
    # parse→save (--check) тот же пустой текст становится None → на выходе
    # self-closing <w:t .../> — отличается от первого сейва байт-в-байт,
    # ломая идемпотентность sha256. Схлопываем text="" → None сразу, чтобы
    # оба прохода писали одинаково.
    for t in root.iter(f"{{{W}}}t"):
        if t.text == "":
            t.text = None

    docxedit.save(zip_bytes, root, str(path))
    return counts


def _strip_comments_only(path: pathlib.Path) -> None:
    """Для файлов без контент-правил (не в PATCHED_FILES) — load+normalize+
    save через docxedit. normalize() убирает commentRangeStart/End/
    commentReference из document.xml, save() не копирует сам
    word/comments.xml — вместе это полностью снимает уже навешанные
    подсказки. Нужно, чтобы attach_hints() не плодил дубли при повторном
    запуске (--install второй раз подряд, см. docstring patch_file)."""
    from backend.templates.build import docxedit

    zip_bytes, root = docxedit.load(str(path))
    docxedit.normalize(root)
    docxedit.save(zip_bytes, root, str(path))


def attach_hints(path: pathlib.Path) -> tuple[int, list[str]]:
    """Вешает Word-комментарии (подсказки) на теги уже зачищенного файла —
    тот же механизм, что build.py использует для 7 форм договора +
    order_purchase (rules_comments.apply_comments_to_file, словарь
    comments_ru.py)."""
    from backend.templates.build import rules_comments

    return rules_comments.apply_comments_to_file(path)


def patch_all(templates_dir: pathlib.Path) -> dict[str, dict]:
    results: dict[str, dict] = {}

    for name in PATCHED_FILES:
        path = templates_dir / name
        if not path.exists():
            continue
        results[name] = {"content_rules": patch_file(path)}

    for name in COMMENTED_FILES:
        path = templates_dir / name
        if not path.exists():
            continue
        if name not in PATCHED_FILES:
            _strip_comments_only(path)
        n_comments, uncovered = attach_hints(path)
        results.setdefault(name, {})["comments"] = n_comments
        results[name]["uncovered"] = uncovered

    return results
