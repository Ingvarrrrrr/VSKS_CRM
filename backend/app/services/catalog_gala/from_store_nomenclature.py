"""Конвертер общего формата выгрузок магазинов (promalp_height_safety_
nomenclature.json, rescue_medical_nomenclature.json, fire_equipment_
nomenclature.json, sima_land_catalog_all.json) → формат GALA (см. format.py).
Владелец, 2026-10-26, Задача 1; Сима-ленд (152 652 позиции) добавлена тем же
днём — тот же конвертер, формат совпадает, плюс верхнеуровневые brand/article.

Вход (raw) — список объектов вида:
  {name, category, unit, price_rub, source_store, link_1, photo_url,
   description, brand, article, specifications: {"<ключ>": "<значение>", ...}}
  brand/article — опциональные верхнеуровневые поля (есть у Сима-ленда, нет у
  трёх старых выгрузок).

Правила отображения полей:
  - name чистится через catalog_gala.clean.clean_text.
  - category → category как есть; product_type НЕ задаётся (владелец:
    у этих трёх выгрузок категория и так достаточно конкретна, второй
    уровень не нужен); category_path=[category], если category есть.
  - unit → unit как есть.
  - price_rub: null/0 → None (как у остальных конвертеров).
  - brand (верхнеуровневое, Сима-ленд) → manufacturer, приоритет над
    характеристиками specifications ("Производитель"/"Бренд"/"Торговая
    марка"): если они заданы и равны brand — в characteristics не
    дублируются; если отличаются — остаются обычной характеристикой (как и
    раньше у "Бренд" при несовпадении с "Производитель").
  - article (верхнеуровневое, Сима-ленд) → article, приоритет над
    характеристикой "Артикул"/"Артикул <магазин>" из specifications: ключ,
    начинающийся с "артикул" (без учёта регистра), со значением, равным
    итоговому article — не пишется в characteristics (дубль, не вторая
    характеристика); отличается по значению — остаётся обычной
    характеристикой.
  - "Страна-производитель"/"Страна производства" (дефис или пробел —
    нормализуются перед сравнением) → ТАКЖЕ item["country_origin"] (как у
    baucenter, format.py); характеристика из characteristics НЕ убирается —
    видна в карточке тоже (то же решение владельца, что у baucenter).
  - "Торговая марка" — если значение совпадает с итоговым manufacturer (без
    учёта регистра/пробелов), в characteristics НЕ дублируется; отличается
    или manufacturer не задан — остаётся обычной характеристикой.
  - "Габариты (ДхШхВ)" и "Вес брутто" — характеристики упаковки товара (не
    самого товара), in_description=False; значение в карточке остаётся.
  - source_store → characteristic "Магазин-источник" (in_description=False —
    это данные о логистике, не о товаре), НЕ в manufacturer (это не
    производитель, а магазин, у которого выгрузка).
  - link_1 → source_url и links=[{"url","price"}], если непусто.
  - photo_url → photos=[photo_url], если непусто.
  - description НЕ переносится (SEO-реклама магазина, решение владельца).
  - specifications → characteristics, с чисткой (_clean_characteristics):
      * ключ ПОСЛЕ clean_text, с обрезанным хвостовым ":" (двоеточие в конце
        ключа — артефакт выгрузки, не часть имени).
      * выбрасываем характеристику целиком, если после чистки:
          - ключ пуст;
          - ключ состоит только из цифр/пробелов/"№";
          - ключ или значение — заглушка вида "#...#" (fire_equipment:
            "#PROP_TITLE#": "#PROP_VALUE#");
          - значение пусто после clean_text;
          - значение длиннее 300 символов (кусок разобранной таблицы
            размеров у части rescue_medical-позиций, см. тест);
          - ключ — мусор по _is_junk_key (владелец, 2026-10-26, фильтр
            ключей характеристик): обрывок фразы разобранного описания
            (начинается со строчной буквы — у части позиций specifications
            содержит фрагменты предложений вида «неблагоприятных
            климатических воздействий», «по основе»/«по утку», «от -40⁰С
            до +40⁰С», разобранные как отдельные ключи), маркер списка
            ("-"/"•"/"–"/"*" в начале), текст про логистику/цену магазина
            ("руб", "₽", "мкад", "доставк", "уценк" — без учёта регистра),
            код/артикул поставщика (без пробелов и с цифрой — "DSUS003",
            "БВ-3-1", "01-2611" — либо "б/н") или слишком длинный
            (>60 символов или >6 слов — тоже обрывок описания, не название
            свойства). Нормальные короткие ключи с единицами ("Вес (кг)",
            "Диаметр, мм", "Ширина сиденья") не задевает: в них есть
            пробелы и начинаются они с заглавной буквы.
            ПОБОЧНЫЙ ЭФФЕКТ правила "строчная буква" (владелец принял
            осознанно): часть выгрузок пишет нормальные короткие названия
            свойств самого товара с маленькой буквы ("длина", "масса",
            "наружный диаметр") — такие ключи тоже выбрасываются вместе с
            обрывками фраз, см. отчёт конвертации.
      * "Артикул" → article (не дублируется в characteristics).
      * "Производитель"/"Бренд" → manufacturer: "Производитель" имеет
        приоритет; если оба заданы и совпадают (без учёта регистра/
        пробелов) — "Бренд" не дублируется, иначе остаётся обычной
        характеристикой со своим именем.
      * остальные ключи — через spec_parse.split_key_unit (единица после
        запятой в конце ключа, "Диаметр, мм" → name "Диаметр", unit "мм" —
        тот же разбор, что у electro_mpo/baucenter, ПРАВИЛО №6).
      * rescue_medical (определяется по source_file, т.к. все три выгрузки
        идут через один конвертер): "Длина"/"Ширина"/"Высота"/"Вес" БЕЗ
        уточнения — габариты/вес упаковки магазина, не самого товара (у
        самого товара везде более точные ключи типа "Ширина сиденья",
        "Длина ленты") → in_description=False. Значения вида "2.9 кг"
        (единица внутри значения, не ключа) оставляются как есть — это
        value, split_key_unit его не касается.
  - item_kind = "товар". is_reusable/is_active/manufacturer(без спецификации)/
    article/pack_quantity/pack_unit/price_date/source_id — не определены в
    исходнике → None.
"""
import re

from app.services.catalog_gala.clean import clean_text
from app.services.catalog_gala.spec_parse import split_key_unit

_PURE_DIGIT_RE = re.compile(r"^[\d\s№]+$")
_STUB_RE = re.compile(r"^#.+#$")

# Фильтр мусорных ключей характеристик (владелец, 2026-10-26) — см. докстринг
# модуля (_clean_characteristics) для разбора правил.
_LEADING_BULLET_RE = re.compile(r"^[-•–*]")
_HAS_DIGIT_RE = re.compile(r"\d")
# "руб" — отдельная регулярка с negative lookbehind на кириллическую букву:
# как ПОДСТРОКА "руб" ложно совпадает с "тРУБка"/"патРУБок"/"стРУБцине" —
# слова со смыслом "труба/зажим", никак не про рубли (владелец, 26.10, см.
# test_store_nomenclature_rub_substring_does_not_match_truba_words).
_RUB_RE = re.compile(r"(?<![а-яёА-ЯЁa-zA-Z])руб")
_JUNK_KEY_SUBSTRINGS = ("₽", "мкад", "уценк", "доставк")


def _is_junk_key(key: str) -> bool:
    """True, если ключ характеристики — обрывок фразы, маркер списка, код/
    артикул поставщика или текст про логистику/цену магазина, а не название
    свойства товара. См. докстринг модуля."""
    if not key:
        return True
    if key[0].islower():
        return True
    if _LEADING_BULLET_RE.match(key):
        return True
    key_lower = key.lower()
    if key_lower == "б/н":
        return True
    if any(substr in key_lower for substr in _JUNK_KEY_SUBSTRINGS):
        return True
    if _RUB_RE.search(key_lower):
        return True
    if " " not in key and _HAS_DIGIT_RE.search(key):
        return True  # код/артикул без пробелов: "DSUS003", "БВ-3-1", "01-2611"
    if len(key) > 60 or len(key.split()) > 6:
        return True
    return False

# Владелец, 2026-10-26: в rescue_medical эти ключи без уточнения — габариты/
# вес упаковки магазина, не самого товара (см. докстринг модуля).
_PACKAGE_DIM_NAMES = {"длина", "ширина", "высота", "вес"}

# Сима-ленд (26.10): габариты/вес упаковки товара — всегда, независимо от
# source_file (в отличие от _PACKAGE_DIM_NAMES выше, которые только у
# rescue_medical и без уточнения в ключе).
_SIMA_PACKAGE_KEY_NAMES = {"вес брутто", "габариты (дхшхв)"}


def _is_rescue_medical(source_file: str) -> bool:
    return "rescue_medical" in (source_file or "").lower()


def _norm_country_key(key_lower: str) -> str:
    return key_lower.replace("-", " ").strip()


_COUNTRY_KEY_NAMES = {"страна производитель", "страна производства"}


def _clean_characteristics(specs: dict, is_rescue_medical: bool, top_manufacturer, top_article) -> tuple:
    """Возвращает (characteristics, manufacturer, article, country_origin).
    top_manufacturer/top_article — верхнеуровневые brand/article (Сима-ленд),
    имеют приоритет над характеристиками из specifications."""
    characteristics = []
    article = top_article
    country_origin = None

    # Предварительный проход — найти manufacturer-кандидата из "Производитель"
    # (он главнее "Бренда" независимо от порядка ключей в исходнике).
    # Верхнеуровневый brand (Сима-ленд) приоритетнее — если задан, спецификации
    # его не переопределяют.
    manufacturer = top_manufacturer or None
    if manufacturer is None:
        for raw_key, raw_value in (specs or {}).items():
            key = clean_text(raw_key)
            if key and key.rstrip(":").strip().lower() == "производитель":
                manufacturer = clean_text(raw_value)
                break

    for raw_key, raw_value in (specs or {}).items():
        key = clean_text(raw_key)
        if not key:
            continue
        key = key.rstrip(":").strip()
        if not key:
            continue
        if _PURE_DIGIT_RE.match(key) or _STUB_RE.match(key):
            continue

        value = clean_text(raw_value)
        if not value:
            continue
        if len(value) > 300:
            continue
        if _STUB_RE.match(value):
            continue

        key_lower = key.lower()

        if key_lower == "артикул":
            if article is None:  # верхнеуровневый article (Сима-ленд) приоритетнее
                article = value
            continue

        if key_lower.startswith("артикул"):
            # "Артикул Сима-ленд" и т.п. — дубль итогового article (верхний
            # уровень или "Артикул" выше) той же выгрузки: не пишем вторую
            # характеристику с тем же значением. Отличается — остаётся
            # обычной характеристикой (падает в общий разбор ниже).
            if article and value.strip().lower() == article.strip().lower():
                continue

        if key_lower == "производитель":
            continue  # уже взят в предварительном проходе

        if key_lower == "бренд":
            if manufacturer and manufacturer.strip().lower() == value.strip().lower():
                continue  # дубль "Производителя" — не повторяем
            if manufacturer is None:
                manufacturer = value
                continue
            # отличается от "Производителя" — остаётся обычной характеристикой
            characteristics.append({"name": key, "value": value, "unit": None})
            continue

        if key_lower == "торговая марка":
            # Сима-ленд: аналог "Бренда", но без фолбэка "взять как
            # manufacturer, если он не задан" — так решил владелец только для
            # "Бренд"/"Производитель" у трёх старых выгрузок.
            if manufacturer and manufacturer.strip().lower() == value.strip().lower():
                continue
            characteristics.append({"name": key, "value": value, "unit": None})
            continue

        if _norm_country_key(key_lower) in _COUNTRY_KEY_NAMES:
            country_origin = value
            characteristics.append({"name": key, "value": value, "unit": None})
            continue

        name, unit = split_key_unit(key)
        # Фильтр мусора (владелец, 26.10) — проверяем ИМЯ после отделения
        # единицы, не ключ целиком: единица в хвосте ключа ("..., лет")
        # иначе раздувает число "слов" у совершенно нормального длинного
        # названия ("Срок службы до перезарядки (не более), лет").
        if _is_junk_key(name):
            continue
        c = {"name": name, "value": value, "unit": unit}
        if is_rescue_medical and name.lower() in _PACKAGE_DIM_NAMES:
            c["in_description"] = False
        elif name.lower() in _SIMA_PACKAGE_KEY_NAMES:
            c["in_description"] = False
        characteristics.append(c)

    return characteristics, manufacturer, article, country_origin


def convert(raw: list, source_file: str) -> dict:
    is_rescue_medical = _is_rescue_medical(source_file)
    items = []
    for row in raw or []:
        price = row.get("price_rub") or None
        if price == 0:
            price = None

        category = row.get("category") or None

        top_manufacturer = clean_text(row.get("brand")) or None
        top_article = clean_text(row.get("article")) or None

        characteristics, manufacturer, article, country_origin = _clean_characteristics(
            row.get("specifications") or {}, is_rescue_medical, top_manufacturer, top_article
        )

        store = clean_text(row.get("source_store"))
        if store:
            characteristics.append({
                "name": "Магазин-источник", "value": store, "unit": None, "in_description": False,
            })

        url = row.get("link_1") or None
        links = [{"url": url, "price": price}] if url else []

        photo = row.get("photo_url") or None
        photos = [photo] if photo else []

        items.append({
            "name": clean_text(row.get("name")),
            "category": category,
            "category_path": [category] if category else [],
            "product_type": None,
            "item_kind": "товар",
            "unit": row.get("unit") or None,
            "pack_quantity": None,
            "pack_unit": None,
            "price": price,
            "price_date": None,
            "currency": "RUB" if price is not None else None,
            "manufacturer": manufacturer,
            "article": article,
            "description": None,  # реклама магазина — не переносим (владелец, 26.10)
            "characteristics": characteristics,
            "country_origin": country_origin,
            "photos": photos,
            "links": links,
            "source_url": url,
            "source_id": None,
            "is_reusable": None,
            "is_active": None,
        })

    return {"source": "store_nomenclature", "items": items}
