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
                  "service_note_procurement.docx")

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

_RULES_BY_FILE = {
    "service_note.docx": SERVICE_NOTE_RULES,
    "service_note_advance.docx": SERVICE_NOTE_RULES,
    "service_note_delivery.docx": SERVICE_NOTE_RULES,
    "service_note_payment.docx": SERVICE_NOTE_RULES,
    "service_note_procurement.docx": SERVICE_NOTE_RULES,
}


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
