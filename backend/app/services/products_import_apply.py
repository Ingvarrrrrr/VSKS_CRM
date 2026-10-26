"""Применение явного маппинга колонок Excel-файла к каталогу товаров
(создание/обновление `Product`). Единственный цикл создания/обновления
товаров из импорта — им пользуются POST /api/products/import (обратная
совместимость со старым угадыванием колонок — угадывание теперь только
подсказка, см. services/products_import_map.py), POST /api/products/import-mapped
(ручной маппинг с предпросмотром) и scripts/load_gala_catalog.py (загрузка
каталога поставщиков из JSON-выгрузок формата GALA, см.
services/catalog_gala/), чтобы поведение импорта не расходилось между
входами (ПРАВИЛО №6).

Перенесено из routers/products_import.py:214-384 (план
dreamy-booping-piglet.md, задача B, п.3) — сама бизнес-логика (актуализация
цены, докидывание пустых полей, создание PurchaseItem при purchase_id) НЕ
менялась. Новое: явные индексы колонок вместо модуля-глобального `col_idx`,
`dry_run` (flush без commit + rollback), и подробный построчный отчёт `rows`
с причиной пропуска/действия — раньше пустые имена молча пропускались без
счётчика и без номера строки, из-за чего дефект №2 (1022 «товара»-категории)
не был виден в самом отчёте импорта.

Сопоставление строки импорта с существующим товаром (владелец, 2026-10-26,
план «каталог без дублей») — вынесено в отдельный модуль
services/products_import_match.py (ПРАВИЛО №5/№6): раньше ключ сопоставления
был name+description СТРОГО, из-за чего совпадение названия при пустом/другом
описании создавало ДУБЛЬ (на боевом файле — 260 лишних товаров). Теперь
приоритет (а) точное name+description → (б) совпадение по названию при
пустом описании у кандидата/строки → (в) совпадение по названию с другим
непустым описанием — тоже тот же товар. Товары, созданные предыдущими
строками ЭТОГО ЖЕ файла, сразу добавляются в индекс (ProductMatchIndex.add)
— повтор позиции внутри файла даёт 1 товар (created+updated), а не 2 created.
"""
import re as _re
from datetime import date as _date_type, datetime as _dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.product import DEFAULT_PRODUCT_CATEGORY, Product
from app.services.price_actualization import actualize_product_price
from app.services.product_unit import backfill_product_unit
from app.services.product_description_merge import (
    is_new_description_shorter, merge_missing_lines,
)
from app.services.products_import_match import (
    ProductMatchIndex, load_candidate_products, norm_key as _norm_key_for_match,
)
from app.services.text_case import capitalize_first
from app.services.units import is_pack_unit
from app.services.product_description_history import set_product_description
from app.services.product_tech_description import build_tech_description

# Значения категории, которые считаются «пустыми» и в файле, и в БД
# (владелец, 2026-10-26, Задача 4) — «Не указано» (встречается в выгрузках
# JSON) и дефолт DEFAULT_PRODUCT_CATEGORY ("Прочее") никогда не считаются
# осмысленной категорией, которую нельзя затирать.
_EMPTY_CATEGORY_VALUES = {"", "не указано", DEFAULT_PRODUCT_CATEGORY.lower()}


def _is_empty_category(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in _EMPTY_CATEGORY_VALUES


def _normalized_category_or_none(value: Optional[str]) -> Optional[str]:
    """Капитализированная категория из файла, если она НЕ входит в список
    «пустых» значений (Задача 4) — иначе None (как если бы колонка была
    пуста)."""
    if _is_empty_category(value):
        return None
    return capitalize_first(value)


def _cell(row, col_idx: dict, field: str):
    idx = col_idx.get(field)
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    return str(v).strip() if v is not None else None


def _raw_cell(row, col_idx: dict, field: str):
    """Как `_cell`, но БЕЗ str()-приведения — нужно для «Дата цены»: ячейка
    Excel с датой приходит из openpyxl уже как datetime/date, str() испортил
    бы её до парсинга (см. `_parse_price_date`)."""
    idx = col_idx.get(field)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


_DATE_DMY_RE = _re.compile(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$")


def _parse_price_date(v) -> Optional[_date_type]:
    """«Дата цены» колонки импорта (владелец, 2026-09-16) — принимает datetime/
    date из openpyxl (Excel-ячейка с датой), ISO-строку 'YYYY-MM-DD' или
    привычный русский 'ДД.ММ.ГГГГ'/'ДД/ММ/ГГГГ'. Не распознано/пусто → None
    (тогда апстрим подставляет дату загрузки файла)."""
    if v is None:
        return None
    if isinstance(v, _dt):
        return v.date()
    if isinstance(v, _date_type):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return _date_type.fromisoformat(s[:10])
    except ValueError:
        pass
    m = _DATE_DMY_RE.match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return _date_type(y, mo, d)
        except ValueError:
            return None
    return None


def _to_bool(v) -> bool:
    if v is None:
        return True
    return str(v).lower().strip() in ("да", "yes", "true", "1", "+")


def _to_dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(" ", "").replace(",", "."))
    except Exception:
        return None


async def apply_products_import(
    db: AsyncSession,
    data_rows: list,
    col_idx: dict,
    *,
    filename: str,
    current_user,
    purchase_id: Optional[int] = None,
    dry_run: bool = False,
    first_row_num: int = 2,
    editor_can_edit_catalog: bool = True,
    replace_descriptions: bool = False,
    supplier_description: bool = False,
) -> dict:
    """data_rows — строки данных БЕЗ строки заголовка. col_idx —
    {field: индекс колонки в data_rows} (name/description/category/
    product_type/price/photo_link/is_reusable/is_active/feo_category_name/
    quantity/unit/link_url_N/link_price_N). first_row_num — номер строки
    Excel (1-based, как видит пользователь), соответствующий data_rows[0] —
    нужен, чтобы номера строк в отчёте указывали на реальную строку файла, а
    не на индекс внутри урезанного списка.

    dry_run=True — цикл выполняется по-настоящему (включая flush, чтобы
    поймать реальные ошибки БД), но транзакция откатывается перед выходом:
    ничего не сохраняется, product_ids не возвращаются.

    editor_can_edit_catalog — есть ли у current_user право
    products.edit_catalog (считает вызывающий роутер один раз через
    app.services.product_catalog_guard.can_edit_catalog, Этап В, 14.10.2026).
    Без этого права строка импорта всё равно создаёт/обновляет товар по
    остальным полям, но описание СУЩЕСТВУЮЩЕГО товара не трогает (новый
    товар получает описание из файла всегда — создание не закрывается).

    replace_descriptions (владелец, 2026-10-26, Задача 3) — что делать, если у
    СУЩЕСТВУЮЩЕГО товара описание уже заполнено и ОТЛИЧАЕТСЯ от файлового:
    False (дефолт, поведение кнопки UI «Импорт») — описание НЕ трогаем и
    дубль не создаём, строка помечается updated (если менялись другие поля)
    или skipped с reason «описание в БД другое, оставлено»; True (кнопка
    скрипта загрузки каталога, scripts/load_gala_catalog.py) — описание
    ЗАМЕНЯЕТСЯ файловым через тот же set_product_description (история
    описаний не теряется — там же пишется старое значение).

    ФИНАЛЬНОЕ РЕШЕНИЕ ВЛАДЕЛЬЦА (26.10.2026, повторное уточнение в тот же
    день) — отменяет предыдущую версию этого докстринга про «правило
    не-затирания»: данные из файла поставщика должны быть ЛУЧШЕ того, что
    было вписано раньше. Если supplier_description=True и в файле для
    товара есть хоть что-то (build_tech_description вернул непустой текст),
    описание ЗАМЕНЯЕТСЯ файловым безусловно — даже если новый текст короче
    старого. Старое значение не теряется: set_product_description сама
    пишет его в product_description_history как предыдущую версию — это не
    отдельная защита, так эта функция уже работает. ЕДИНСТВЕННАЯ защита —
    пустой результат build_tech_description (нет ни текста, ни
    характеристик): такая строка не попадает даже в проверку чуть выше
    (`new_desc_norm` пуст → ветка `if editor_can_edit_catalog and
    new_desc_norm:` не выполняется), старое описание остаётся как есть.

    supplier_description (владелец, 2026-10-26, загрузчик каталогов
    поставщиков GALA) — col_idx может содержать поля "characteristics"
    (список [{"name","value","unit",...}], берётся из row как есть, БЕЗ
    str()-приведения — в отличие от обычных ячеек) и "manufacturer"/"article"
    (обычные текстовые ячейки). Когда True:
      - описание строки заменяется на
        build_tech_description(characteristics, description строки) —
        ЕДИНСТВЕННАЯ сборка техописания (ПРАВИЛО №6, см.
        services/product_tech_description.py) — и ведёт себя как
        replace_descriptions=True (заменяет у существующего товара, через
        set_product_description, с историей);
      - characteristics существующего товара заменяются файловыми, если в
        файле они непустые;
      - manufacturer/article существующего товара заполняются, только если
        у него эти поля были пусты (как и остальные _fill-поля);
      - у НОВОГО товара заполняются все три поля (characteristics,
        manufacturer, article) из файла.
    Без supplier_description (дефолт False) — поведение прежнее, эти три
    поля не читаются и не трогаются.

    Возвращает {created, updated, skipped, errors, product_ids,
    rows: [{row, action, name, reason}]}, action ∈
    created | updated | skipped | error. КАЖДАЯ строка данных (включая
    полностью пустые строки листа — они тоже попадают в отчёт как
    action=skipped/«нет наименования») учтена и видна в отчёте: раньше
    (routers/products_import.py, до правки) строка без имени просто
    молчаливо пропускалась через `continue` без счётчика и без номера —
    именно поэтому дефект №2 плана dreamy-booping-piglet.md (1022
    «товара»-категории) не был виден в самом отчёте импорта. Владелец на
    боевом файле («ТЗ для АПИ (4).xlsx», лист «ТЗ») подтвердил именно такую
    сквозную нумерацию: 1018 создано + 220 пропущено «нет наименования» =
    1238 из 1239 строк данных, первая пропущенная — строка 1019.
    """
    from app.models.feo_category import FeoCategory
    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name = {f.name.lower().strip(): f.id for f in feo_rows}

    # Сужение SQL (владелец, 2026-10-26): раньше здесь был select ВСЕГО
    # каталога без лимита — теперь только товары, чьё normalize-имя
    # встречается среди имён строк ЭТОГО ЖЕ файла (load_candidate_products,
    # services/products_import_match.py) — остальной каталог не может
    # совпасть ни с одной строкой импорта (см. её докстринг).
    file_names = {_cell(row, col_idx, "name") for row in data_rows}
    file_names.discard(None)
    candidate_products = await load_candidate_products(db, file_names)
    # Единственный индекс сопоставления строки импорта с товаром каталога
    # (ПРАВИЛО №6, services/products_import_match.py) — пополняется новыми
    # товарами СРАЗУ после создания (см. match_index.add(p) ниже), поэтому
    # повтор позиции внутри одного файла находит уже созданный товар, а не
    # плодит второй created (Задача 2).
    match_index = ProductMatchIndex(candidate_products)

    created = 0
    updated = 0
    skipped = 0
    errors: list = []
    report_rows: list = []
    all_products: list = []
    product_row_data: list = []
    # Новые товары (и товары, созданные предыдущей строкой ЭТОГО ЖЕ файла, у
    # которых ещё нет product.id) получают реальный product_id только после
    # db.flush() ниже — актуализацию цены (и запись в историю) для них
    # откладываем до post-flush прохода (см. цикл после `await db.flush()`).
    pending_new_price: list = []
    # Виртуальное "текущее" (цена, дата) для товаров без product.id —
    # нужно, чтобы повтор позиции внутри файла применял то же правило
    # «цена обновляется, только если дата строки не старше» (Задача 5), что
    # и для настоящих существующих товаров (у которых роль current играет
    # ep.price_updated_at). Ключ — id() python-объекта (устойчив в рамках
    # одного прогона, product.id ещё не присвоен).
    new_product_price_state: dict = {}

    def _price_is_more_actual(new_price, new_date, current_price, current_date) -> bool:
        """Задача 5: писать цену, только если новая цена >0, отличается от
        текущей, и дата строки не старше даты текущей цены (пустая текущая
        дата — значит обновлять всегда)."""
        if new_price is None or new_price <= 0:
            return False
        if current_price is not None and new_price == current_price:
            return False
        if current_date is not None and new_date is not None and new_date < current_date:
            return False
        return True

    _user_name = getattr(current_user, "full_name", None) or getattr(current_user, "username", "") or ""
    _import_note = (
        f"Импорт каталога из файла «{filename}», "
        f"{_user_name}, {_dt.now().strftime('%d.%m.%Y %H:%M')}"
    )
    # «Дата цены» (владелец, 2026-09-16): заполнена в строке — пишем ею,
    # иначе — датой загрузки файла (одна дата на весь файл, не per-row `now()`).
    _upload_date = _dt.now().date()

    try:
        for i, row in enumerate(data_rows):
            row_num = first_row_num + i
            name = None
            try:
                name = _cell(row, col_idx, "name")
                if not name:
                    skipped += 1
                    report_rows.append({"row": row_num, "action": "skipped", "name": None, "reason": "нет наименования"})
                    continue

                desc_val = _cell(row, col_idx, "description")

                # --- режим загрузчика каталогов поставщиков (Задача 3,
                # scripts/load_gala_catalog.py) ---
                characteristics_val = None
                manufacturer_val = None
                article_val = None
                country_origin_val = None
                if supplier_description:
                    _chars_idx = col_idx.get("characteristics")
                    if _chars_idx is not None and _chars_idx < len(row):
                        characteristics_val = row[_chars_idx] or None
                    manufacturer_val = _cell(row, col_idx, "manufacturer")
                    article_val = _cell(row, col_idx, "article")
                    country_origin_val = _cell(row, col_idx, "country_origin")
                    desc_val = build_tech_description(characteristics_val, desc_val)
                effective_replace_descriptions = replace_descriptions or supplier_description

                price_links = []
                for n in range(1, 10):
                    url = _cell(row, col_idx, f"link_url_{n}")
                    if not url:
                        break
                    price_val = _to_dec(_cell(row, col_idx, f"link_price_{n}"))
                    price_links.append({"url": url, "price": float(price_val) if price_val else None})

                feo_name = _cell(row, col_idx, "feo_category_name")
                feo_id = feo_by_name.get(feo_name.lower().strip()) if feo_name else None

                price = _to_dec(_cell(row, col_idx, "price"))
                if not price and price_links:
                    prices = [l["price"] for l in price_links if l["price"]]
                    if prices:
                        price = Decimal(str(round(sum(prices) / len(prices), 2)))

                price_date_val = _parse_price_date(_raw_cell(row, col_idx, "price_date")) or _upload_date

                qty_str = _cell(row, col_idx, "quantity")
                unit_raw = _cell(row, col_idx, "unit")  # без дефолта — для бэкфилла Product.unit
                unit_str = unit_raw or "шт."
                row_qty = None
                if qty_str:
                    try:
                        row_qty = Decimal(str(qty_str).replace(",", ".").replace(" ", ""))
                    except Exception:
                        pass

                # Упаковка (владелец, 14.10) — валидна только при упаковочном
                # unit (app.services.units.is_pack_unit), иначе игнорируем
                # данные колонок (та же защита, что и в routers/products.py::
                # normalize_pack_fields, ПРАВИЛО №6 — одно правило).
                pack_quantity_val = None
                pack_unit_val = None
                if is_pack_unit(unit_raw):
                    pack_quantity_val = _to_dec(_cell(row, col_idx, "pack_quantity"))
                    pack_unit_val = _cell(row, col_idx, "pack_unit")

                match = match_index.find(name, desc_val)
                ep = match["product"]
                dup_reason = match["reason"]

                if ep is not None:
                    is_new_unflushed = ep.id is None
                    changed = False

                    # --- цена (Задача 5 — «если более актуальная», и Задача 2
                    # — то же правило для повтора позиции внутри файла, когда
                    # у товара ещё нет product_id/price_updated_at) ---
                    if is_new_unflushed:
                        _state = new_product_price_state.get(id(ep))
                        cur_price = _state["price"] if _state else ep.price
                        cur_date = _state["date"] if _state else None
                    else:
                        cur_price = ep.price
                        cur_date = ep.price_updated_at.date() if ep.price_updated_at else None

                    if _price_is_more_actual(price, price_date_val, cur_price, cur_date):
                        if is_new_unflushed:
                            pending_new_price.append((ep, price, price_date_val))
                            new_product_price_state[id(ep)] = {"price": price, "date": price_date_val}
                        else:
                            # Актуализация цены (владелец, 2026-08-29): цена пришла
                            # из импортируемого файла — source='import'.
                            # collected_at (владелец, 2026-09-16) — «Дата цены» из
                            # строки, иначе дата загрузки файла.
                            await actualize_product_price(
                                db, ep, price=price, source="import",
                                source_ref=filename, collected_at=price_date_val,
                                user=current_user,
                            )
                        changed = True

                    def _fill(attr, val):
                        nonlocal changed
                        if val and not getattr(ep, attr):
                            setattr(ep, attr, val)
                            changed = True

                    # --- категория (Задача 4): «Не указано»/«Прочее»/пусто —
                    # считаются пустыми и в файле, и в БД; непустую
                    # существующую категорию файл никогда не затирает. ---
                    cat_val = _normalized_category_or_none(_cell(row, col_idx, "category"))
                    if cat_val and _is_empty_category(ep.category):
                        ep.category = cat_val
                        changed = True

                    _fill("product_type", _cell(row, col_idx, "product_type"))
                    _fill("photo_link", _cell(row, col_idx, "photo_link"))

                    # --- характеристики/производитель/артикул (Задача 3,
                    # режим supplier_description) ---
                    if supplier_description:
                        if characteristics_val:
                            ep.characteristics = characteristics_val
                            flag_modified(ep, "characteristics")
                            changed = True
                        _fill("manufacturer", manufacturer_val)
                        _fill("article", article_val)
                        # "Страна производства" (Задача baucenter, 2026-10-26)
                        # — заполняем, только если у товара её нет или стоит
                        # дефолт "РФ" (не считаем это осмысленно заполненным
                        # значением, которое нельзя перезаписать файлом).
                        if country_origin_val and (ep.country_origin or "").strip().lower() in ("", "рф"):
                            ep.country_origin = country_origin_val
                            changed = True

                    # --- описание (Задача 3) --- Защита каталога (Этап В, план
                    # item-tz-description.md, 14.10.2026, ПРАВИЛО №6): описание
                    # СУЩЕСТВУЮЩЕГО товара меняется ТОЛЬКО через
                    # set_product_description (история + право
                    # products.edit_catalog) — и только если у запускающего
                    # импорт это право есть. Без права строка всё равно
                    # создаётся/обновляется по остальным полям, описание
                    # каталога не трогаем.
                    #
                    # Задача 1 (26.10.2026, ПРАВИЛО №6, повод — 41 товар с
                    # потерей техданных в прошлом dry-run
                    # rebuild_descriptions_from_sources.py при безусловной
                    # замене): если файловое описание ЗАМЕТНО КОРОЧЕ старого
                    # (is_new_description_shorter — тот же критерий, что в
                    # rebuild-скрипте, 20% по непробельным символам), не
                    # заменяем целиком, а объединяем через
                    # merge_missing_lines — старое сохраняется целиком, в
                    # конец дописываются только недостающие строки файла.
                    desc_reason = None
                    existing_desc = (ep.description or "").strip()
                    new_desc_norm = (desc_val or "").strip()

                    async def _set_description(value):
                        # Повтор позиции внутри ЭТОГО файла (Задача 2) может
                        # найти товар, созданный предыдущей строкой того же
                        # прогона — у него ещё нет product.id (flush будет
                        # позже), а set_product_description пишет историю с
                        # product_id СРАЗУ → NOT NULL violation. У такого
                        # товара ещё нет ни одной сохранённой версии описания
                        # — присваиваем значение прямо, без истории (история
                        # не теряет ничего, т.к. до flush у товара нет
                        # персистентного состояния вообще).
                        if ep.id is None:
                            setattr(ep, "description", value)
                        else:
                            await set_product_description(
                                db, ep, "description", value, current_user, source="edit",
                            )

                    if editor_can_edit_catalog and new_desc_norm:
                        if not existing_desc:
                            await _set_description(desc_val)
                            changed = True
                        elif _norm_key_for_match(existing_desc) != _norm_key_for_match(new_desc_norm):
                            if effective_replace_descriptions:
                                if is_new_description_shorter(existing_desc, desc_val):
                                    final_desc_val = merge_missing_lines(existing_desc, desc_val)
                                else:
                                    final_desc_val = desc_val
                                await _set_description(final_desc_val)
                                changed = True
                            else:
                                desc_reason = "описание в БД другое, оставлено"

                    _fill("pack_quantity", pack_quantity_val)
                    _fill("pack_unit", pack_unit_val)

                    ep.import_note = _import_note
                    ep.updated_at = _dt.utcnow()
                    ep.updated_by = _user_name

                    if feo_id and not ep.feo_category_id:
                        ep.feo_category_id = feo_id
                        changed = True

                    if price_links and not ep.price_links:
                        ep.price_links = price_links
                        flag_modified(ep, "price_links")
                        changed = True

                    # Единица измерения (владелец, 2026-09-01): не трогаем уже
                    # заполненную; иначе — из самого импорта, иначе — из истории
                    # закупок этого товара (единственная встречавшаяся).
                    await backfill_product_unit(db, ep, import_unit=unit_raw)

                    all_products.append(ep)
                    product_row_data.append({"qty": row_qty, "unit": unit_str, "price": price or ep.price})

                    reasons = [r for r in (dup_reason, desc_reason) if r]
                    if desc_reason and not changed:
                        skipped += 1
                        report_rows.append({"row": row_num, "action": "skipped", "name": name, "reason": "; ".join(reasons)})
                    else:
                        updated += 1
                        base_reason = "уже в каталоге — обновлён"
                        report_rows.append({
                            "row": row_num, "action": "updated", "name": name,
                            "reason": "; ".join([base_reason] + reasons),
                        })
                    continue

                new_category = _normalized_category_or_none(_cell(row, col_idx, "category")) or DEFAULT_PRODUCT_CATEGORY
                p = Product(
                    name=name,
                    description=desc_val,
                    category=new_category,
                    product_type=_cell(row, col_idx, "product_type"),
                    unit=(unit_raw or "").strip() or None,  # брэнд-новый товар — истории покупок ещё нет
                    pack_quantity=pack_quantity_val,
                    pack_unit=pack_unit_val,
                    # price НЕ задаём здесь напрямую (ПРАВИЛО №6 — единственный
                    # писатель product.price это actualize_product_price, см.
                    # пост-flush проход ниже, `pending_new_price`) — иначе
                    # у только что созданного товара цена есть, а строки в
                    # истории (product_price_history) — нет.
                    photo_link=_cell(row, col_idx, "photo_link"),
                    is_reusable=_to_bool(_cell(row, col_idx, "is_reusable")),
                    is_active=_to_bool(_cell(row, col_idx, "is_active")),
                    characteristics=characteristics_val,
                    manufacturer=manufacturer_val,
                    article=article_val,
                    feo_category_id=feo_id,
                    price_links=price_links or [],
                    import_note=_import_note,
                    updated_at=_dt.utcnow(),
                    updated_by=_user_name,
                )
                if country_origin_val:
                    # Не передаём country_origin в конструктор Product(...)
                    # напрямую — там нет дефолта кроме None/"РФ" из модели, а
                    # передача None затёрла бы его; ставим после, только если
                    # файл реально принёс значение.
                    p.country_origin = country_origin_val
                db.add(p)
                # Задача 2: сразу делаем видимым для последующих строк ЭТОГО
                # ЖЕ файла — повтор позиции внутри файла находит этот товар
                # (updated), а не создаёт второй created.
                match_index.add(p)
                all_products.append(p)
                product_row_data.append({"qty": row_qty, "unit": unit_str, "price": price})
                if price is not None and price > 0:
                    pending_new_price.append((p, price, price_date_val))
                    new_product_price_state[id(p)] = {"price": price, "date": price_date_val}
                created += 1
                report_rows.append({"row": row_num, "action": "created", "name": name, "reason": None})
            except Exception as e:
                errors.append({"row": row_num, "name": name or "?", "message": str(e)})
                report_rows.append({"row": row_num, "action": "error", "name": name, "reason": str(e)})

        # Flush to get product IDs (и поймать реальные ошибки БД до commit/rollback)
        await db.flush()

        # Актуализация цены для НОВЫХ товаров (владелец, 2026-09-16) — только
        # теперь у них есть product.id (нужен для ProductPriceHistory.product_id
        # NOT NULL). Одна и та же функция-писатель, что и для существующих
        # (см. actualize_product_price выше) — не вторая формула/копия.
        for _p, _price, _price_date in pending_new_price:
            await actualize_product_price(
                db, _p, price=_price, source="import",
                source_ref=filename, collected_at=_price_date,
                user=current_user,
            )

        product_ids = [p.id for p in all_products]

        # Если purchase_id передан — добавить ВСЕ товары (новые + существующие)
        # позициями закупки. В dry_run закупку не трогаем — она может быть
        # реальной и уже содержать позиции, которые нельзя откатывать вместе с
        # пробным прогоном каталога.
        if purchase_id and all_products and not dry_run:
            from app.models.purchase_item import PurchaseItem
            from app.services.item_amounts import line_total
            for idx_p, p in enumerate(all_products):
                rd = product_row_data[idx_p] if idx_p < len(product_row_data) else {}
                qty = rd.get("qty") or Decimal("1")
                unit = rd.get("unit") or "шт."
                unit_price = rd.get("price") or p.price
                total = line_total(qty, unit_price) if unit_price else None
                db.add(PurchaseItem(
                    purchase_id=purchase_id,
                    product_id=p.id,
                    item_name=p.name[:500],
                    item_type=p.product_type or "товар",
                    quantity=qty,
                    unit=unit,
                    unit_price=unit_price,
                    total_price=total,
                ))
            await db.flush()

        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "product_ids": [] if dry_run else product_ids,
        "rows": report_rows,
    }
