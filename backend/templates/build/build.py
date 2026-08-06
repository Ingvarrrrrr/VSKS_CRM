import argparse
import hashlib
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

_HERE = pathlib.Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent.parent
_TEMPLATES_DIR = _HERE.parent
_DEFAULT_OUT = _HERE / "_out"

sys.path.insert(0, str(_REPO_ROOT))

from backend.templates.build.sources import SOURCES
from backend.templates.build import docxedit
from backend.templates.build.rules_merge import merge_variant
from backend.templates.build.rules_common import (
    RULES as COMMON_RULES,
    apply_common_rules,
    apply_r3_preamble,
    apply_r2_third_party_wrap,
    apply_r5_stages_wrap,
    apply_r6_retroactive_wrap,
    apply_r1_vat_411_wrap,
    apply_r4_delivery_wrap,
    apply_t4_repair_tables,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_BLANK_RE = re.compile(r"_{3,}")
_COMMENT_TAG = f"{{{W}}}commentRangeStart"


def _count_blanks(root) -> int:
    from backend.templates.build.docxedit import para_text
    ns = {"w": W}
    count = 0
    for p in root.findall(".//w:p", ns):
        count += len(_BLANK_RE.findall(para_text(p)))
    return count


def _count_source_comments(zip_bytes: dict) -> int:
    if "word/comments.xml" not in zip_bytes:
        return 0
    try:
        from lxml import etree
        tree = etree.fromstring(zip_bytes["word/comments.xml"])
        return len(tree.findall(f"{{{W}}}comment"))
    except Exception:
        return 0


def _count_paras(root) -> int:
    ns = {"w": W}
    return len(root.findall(".//w:p", ns))


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_METHODOLOGY_DOC_TYPES = ("methodology_large", "methodology_small")
_METHODOLOGY_HEADING_PREFIX = "МЕТОДИЧЕСКИЕ РЕКОМЕНДАЦИИ"


def _build_methodology(
    doc_type: str,
    zip_bytes: dict,
    root,
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """
    Методички — справочный текст, не бланк. Никаких normalize()/rules:
    просто отрезаем от w:body всё, что идёт ДО абзаца-заголовка
    «МЕТОДИЧЕСКИЕ РЕКОМЕНДАЦИИ», сам заголовок и всё после — не трогаем.
    """
    ns = {"w": W}
    body = root.find("w:body", ns)
    if body is None:
        raise RuntimeError(f"{doc_type}: w:body не найден")

    children = list(body)
    heading_idx = None
    for i, el in enumerate(children):
        if el.tag == f"{{{W}}}p":
            text = docxedit.para_text(el).strip()
            if text.startswith(_METHODOLOGY_HEADING_PREFIX):
                heading_idx = i
                break

    if heading_idx is None:
        raise RuntimeError(
            f"{doc_type}: абзац, начинающийся с "
            f"«{_METHODOLOGY_HEADING_PREFIX}», не найден в источнике"
        )

    for el in children[:heading_idx]:
        body.remove(el)

    remaining = list(body)
    sect_pr = body.find("w:sectPr", ns)
    if sect_pr is None or remaining[-1] is not sect_pr:
        raise RuntimeError(
            f"{doc_type}: w:sectPr отсутствует или не является последним "
            f"элементом w:body после отсечения"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc_type}.docx"
    docxedit.save(zip_bytes, root, str(out_path))

    n_paras = _count_paras(root)
    print(f"  {doc_type}: абзацев={n_paras} (методичка, без normalize/правил)")

    return out_path


_CS_PRICE_SECTION_RE = re.compile(r"^4\.\s+Цена Договора")
_CS_VAT_NO_VAT_SEARCH = "возникнет НДС"
_CS_VAT_RATE_CHANGE_SEARCH = "изменится применяемая ставка НДС"


def _cs_body_paragraphs(root) -> list:
    """Прямые дети w:body с тегом w:p (без таблиц) — та же фильтрация,
    что и в rules_merge._body_paragraphs, реализованная локально (правки
    rules_merge.py запрещены для этой задачи)."""
    ns = {"w": W}
    body = root.find("w:body", ns)
    if body is None:
        return []
    return [el for el in body if el.tag == f"{{{W}}}p"]


def _cs_find_price_section_index(paragraphs: list) -> int:
    for i, p in enumerate(paragraphs):
        text = docxedit.para_text(p).strip()
        if _CS_PRICE_SECTION_RE.match(text):
            return i
    raise RuntimeError(
        "contract_services: заголовок «4. Цена Договора и порядок расчетов» "
        "не найден"
    )


def _cs_cut_methodology(doc_type: str, root) -> int:
    """
    contract_services: отрезаем от w:body абзац-заголовок методички
    («МЕТОДИЧЕСКИЕ РЕКОМЕНДАЦИИ...») и ВСЁ, что идёт после него, кроме
    хвостового w:sectPr (в отличие от _build_methodology, которая отрезает
    ДО заголовка — здесь наоборот, отрезаем ОТ заголовка и до конца).
    Возвращает число удалённых элементов.
    """
    ns = {"w": W}
    body = root.find("w:body", ns)
    if body is None:
        raise RuntimeError(f"{doc_type}: w:body не найден")

    children = list(body)
    heading_idx = None
    for i, el in enumerate(children):
        if el.tag == f"{{{W}}}p":
            text = docxedit.para_text(el).strip()
            if text.startswith(_METHODOLOGY_HEADING_PREFIX):
                heading_idx = i
                break

    if heading_idx is None:
        raise RuntimeError(
            f"{doc_type}: абзац, начинающийся с "
            f"«{_METHODOLOGY_HEADING_PREFIX}», не найден при отсечении методички"
        )

    sect_pr = body.find("w:sectPr", ns)
    to_remove = [el for el in children[heading_idx:] if el is not sect_pr]
    for el in to_remove:
        body.remove(el)

    remaining = list(body)
    if sect_pr is None or remaining[-1] is not sect_pr:
        raise RuntimeError(
            f"{doc_type}: w:sectPr отсутствует или не является последним "
            f"элементом w:body после отсечения методички"
        )

    return len(to_remove)


def _cs_strip_style_refs(p) -> None:
    """Та же логика, что rules_merge._clone_paragraph/_strip_style_refs,
    реализованная локально (правки rules_merge.py запрещены)."""
    ns = {"w": W}
    for ppr in p.findall("w:pPr", ns):
        for tag in ("w:pStyle", "w:numPr"):
            for el in ppr.findall(tag, ns):
                ppr.remove(el)
    for rpr in p.iter(f"{{{W}}}rPr"):
        for el in list(rpr):
            if el.tag == f"{{{W}}}rStyle":
                rpr.remove(el)


def _cs_clone_paragraph(p):
    import copy
    new_p = copy.deepcopy(p)
    _cs_strip_style_refs(new_p)
    return new_p


def _cs_insert_vat_rate_change_paragraph(root, food_root) -> None:
    """
    contract_services: вставляет абзац «изменится применяемая ставка НДС»
    (взятый из contract_services_food) сразу после существующей пары
    «возникнет НДС» + пустой абзац-разделитель, плюс добавляет ещё один
    пустой разделитель после вставленного абзаца. Сам абзац НЕ оборачивается
    условным тегом здесь — это делает apply_r1_vat_411_wrap() позже в общем
    конвейере (она ищет его по тексту у ВСЕХ doc_type).
    """
    ns = {"w": W}

    rate_change_p = None
    for p in food_root.findall(".//w:p", ns):
        if _CS_VAT_RATE_CHANGE_SEARCH in docxedit.para_text(p):
            rate_change_p = p
            break
    if rate_change_p is None:
        raise RuntimeError(
            "contract_services: в contract_services_food не найден абзац "
            f"«{_CS_VAT_RATE_CHANGE_SEARCH}»"
        )

    clone = _cs_clone_paragraph(rate_change_p)

    no_vat_p = None
    for p in root.findall(".//w:p", ns):
        if _CS_VAT_NO_VAT_SEARCH in docxedit.para_text(p):
            no_vat_p = p
            break
    if no_vat_p is None:
        raise RuntimeError(
            "contract_services: абзац "
            f"«{_CS_VAT_NO_VAT_SEARCH}» не найден после слияния питания"
        )

    parent = no_vat_p.getparent()
    siblings = list(parent)
    anchor = no_vat_p
    anchor_idx = siblings.index(no_vat_p)
    if anchor_idx + 1 < len(siblings):
        next_el = siblings[anchor_idx + 1]
        if next_el.tag == f"{{{W}}}p" and not docxedit.para_text(next_el).strip():
            anchor = next_el
            anchor_idx += 1

    parent.insert(anchor_idx + 1, clone)
    docxedit.insert_para_after(clone, "")


def build_one(doc_type: str, out_dir: pathlib.Path) -> pathlib.Path:
    rel_path = SOURCES[doc_type]
    src = _REPO_ROOT / rel_path

    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")

    zip_bytes, root = docxedit.load(str(src))

    if doc_type in _METHODOLOGY_DOC_TYPES:
        return _build_methodology(doc_type, zip_bytes, root, out_dir)

    n_comments = _count_source_comments(zip_bytes)

    docxedit.normalize(root)

    counts: dict[str, int] = {}

    # M_gph_rid: слияние формы ГПХ «без РИД» (база) + «+РИД» (вариант) по
    # флагу rid_transfer. Должно идти ПОСЛЕ normalize (принять tracked changes,
    # слить runs — иначе сравнение абзацев base/variant будет ловить шум от
    # раздробленных runs), но ДО остальных правил (R3/C-правил/R1/R2/R5) —
    # чтобы вставленные из варианта абзацы тоже прошли через общие замены
    # (реквизиты Заказчика/Исполнителя, НДС и т.п.), а не остались с сырыми
    # бланками «_____» из образца-варианта.
    if doc_type == "contract_gph_individual":
        rid_src = _REPO_ROOT / SOURCES["contract_gph_individual_rid"]
        if not rid_src.exists():
            raise FileNotFoundError(f"Source not found: {rid_src}")
        _rid_zip_bytes, rid_root = docxedit.load(str(rid_src))
        docxedit.normalize(rid_root)
        merge_variant(root, rid_root, "rid_transfer", counts, "M_gph_rid")

    # contract_services: объединённая форма услуг (large/small/food) без
    # методических рекомендаций. Как и M_gph_rid выше — ПОСЛЕ normalize,
    # ДО R3/common rules, чтобы вставленные из food абзацы тоже прошли
    # через общие замены (реквизиты, НДС и т.п.).
    if doc_type == "contract_services":
        n_cut = _cs_cut_methodology(doc_type, root)

        food_src = _REPO_ROOT / SOURCES["contract_services_food"]
        if not food_src.exists():
            raise FileNotFoundError(f"Source not found: {food_src}")
        _food_zip_bytes, food_root = docxedit.load(str(food_src))
        docxedit.normalize(food_root)

        base_paragraphs = _cs_body_paragraphs(root)
        var_paragraphs = _cs_body_paragraphs(food_root)
        base_end = _cs_find_price_section_index(base_paragraphs)
        var_end = _cs_find_price_section_index(var_paragraphs)

        merge_variant(
            root, food_root, "food_service", counts, "M_services_food",
            handle_delete=False, base_end=base_end, var_end=var_end,
        )

        _cs_insert_vat_rate_change_paragraph(root, food_root)

        counts["CS_methodology_cut"] = n_cut
        counts["CS_vat_rate_change_insert"] = 1

    ns = {"w": W}
    paragraphs = root.findall(".//w:p", ns)

    # R3 должен сработать ДО правил C08/C09 (они заменяют текст ЮЛ/ИП).
    # После вставки {%p if/else/endif %} список paragraphs устарел —
    # пересобираем его заново для apply_common_rules.
    apply_r3_preamble(paragraphs, counts)

    # Пересобираем актуальный список (R3 вставил новые абзацы)
    paragraphs = root.findall(".//w:p", ns)

    # Применяем общие правила к каждому абзацу (inline-замены, включая R1/R2)
    for p in paragraphs:
        apply_common_rules(p, counts)

    # Пересобираем список после inline-замен
    paragraphs = root.findall(".//w:p", ns)

    # R2: третьи лица — абзацный тег вокруг условного абзаца
    apply_r2_third_party_wrap(paragraphs, counts)

    # R1: абзацы 4.1.1 (НДС) — оборачиваем в условные блоки
    paragraphs = root.findall(".//w:p", ns)
    apply_r1_vat_411_wrap(paragraphs, counts)

    # R4: доставка/выборка (только для goods_single)
    if doc_type == "contract_goods_single":
        paragraphs = root.findall(".//w:p", ns)
        apply_r4_delivery_wrap(paragraphs, counts)

    # R6: ретроактивность — абзацный тег вокруг п. 425
    paragraphs = root.findall(".//w:p", ns)
    apply_r6_retroactive_wrap(paragraphs, counts)

    # R5: этапность — абзацный тег вокруг п. 4.5.1 (только ГПХ-шаблоны)
    if doc_type in ("contract_gph_individual", "contract_gph_individual_rid"):
        paragraphs = root.findall(".//w:p", ns)
        apply_r5_stages_wrap(paragraphs, counts)

    # T4: сметные таблицы — {%tr for %} циклы (только repair_framework)
    if doc_type == "contract_repair_framework":
        apply_t4_repair_tables(root, counts)

    n_paras = _count_paras(root)
    n_blanks = _count_blanks(root)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc_type}.docx"
    docxedit.save(zip_bytes, root, str(out_path))

    # Вывод срабатываний
    all_rule_ids = [r[0] for r in COMMON_RULES] + [
        "R3_preamble_ip_ul",
        "R2_third_party_wrap",
        "R1_vat_411_no_vat_wrap",
        "R1_vat_411_with_vat_wrap",
        "R4_delivery_pickup_wrap",
        "R4_delivery_cost_wrap",
        "R5_stages_wrap",
        "R6_retroactive_wrap",
        "T4_repair_works_row",
        "T4_repair_works_removed",
        "T4_repair_parts_row",
        "T4_repair_parts_removed",
        "T4_vat_rate_replaced",
        "M_gph_rid_insert",
        "M_gph_rid_replace",
        "M_gph_rid_delete",
        "M_gph_rid_skipped_empty",
        "M_gph_rid_skipped_same",
        "M_services_food_insert",
        "M_services_food_replace",
        "M_services_food_delete",
        "M_services_food_skipped_empty",
        "M_services_food_skipped_same",
        "CS_methodology_cut",
        "CS_vat_rate_change_insert",
    ]
    hit_rows = []
    zero_rows = []
    for rid in all_rule_ids:
        n = counts.get(rid, 0)
        if n > 0:
            hit_rows.append(f"    {rid}: {n}")
        else:
            zero_rows.append(f"    WARN 0-срабатываний: {rid}")

    print(
        f"  {doc_type}: абзацев={n_paras}, "
        f"бланков(___) после правил={n_blanks}, "
        f"комментариев в источнике={n_comments}"
    )
    for row in hit_rows:
        print(row)
    for row in zero_rows:
        print(row)

    return out_path


def build_all(doc_types: list[str], out_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    results = {}
    for dt in doc_types:
        try:
            p = build_one(dt, out_dir)
            results[dt] = p
        except Exception as e:
            import traceback
            print(f"  ОШИБКА {dt}: {e}")
            traceback.print_exc()
    return results


def check_mode(doc_types: list[str]) -> bool:
    install_dir = _TEMPLATES_DIR
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        print("Пересборка во временную папку...")
        results = build_all(doc_types, tmp_path)

        for dt, built_path in results.items():
            committed = install_dir / f"{dt}.docx"
            if not committed.exists():
                print(f"  {dt}: НЕТ в {install_dir} (новый файл)")
                ok = False
                continue

            h_built = _sha256(built_path)
            h_comm = _sha256(committed)
            if h_built == h_comm:
                print(f"  {dt}: OK (идентично)")
            else:
                print(f"  {dt}: РАСХОЖДЕНИЕ")
                print(f"    committed: {h_comm}")
                print(f"    rebuilt:   {h_built}")
                ok = False
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Сборщик шаблонов договоров из образцов"
    )
    parser.add_argument(
        "--only", metavar="DOC_TYPE",
        help="Собрать только указанный тип (например contract_services_large)"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Собрать во временную папку и сравнить с backend/templates/"
    )
    parser.add_argument(
        "--out", metavar="DIR",
        help="Папка вывода (по умолчанию backend/templates/build/_out/)"
    )
    parser.add_argument(
        "--install", action="store_true",
        help="Записать результат в backend/templates/ (перезапись!)"
    )
    args = parser.parse_args()

    doc_types = [args.only] if args.only else list(SOURCES.keys())

    if args.check:
        print("=== РЕЖИМ ПРОВЕРКИ ===")
        ok = check_mode(doc_types)
        sys.exit(0 if ok else 1)

    if args.install:
        out_dir = _TEMPLATES_DIR
        print(f"=== УСТАНОВКА в {out_dir} ===")
    elif args.out:
        out_dir = pathlib.Path(args.out)
        print(f"=== СБОРКА в {out_dir} ===")
    else:
        out_dir = _DEFAULT_OUT
        print(f"=== СБОРКА в {out_dir} ===")

    results = build_all(doc_types, out_dir)
    print(f"\nСобрано: {len(results)}/{len(doc_types)} файлов")


if __name__ == "__main__":
    main()
