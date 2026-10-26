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
  - "Страна-производитель"/"Страна производства"/"Страна изготовитель"
    (дефис или пробел — нормализуются перед сравнением; список имён ключа —
    app.services.catalog_gala.country_names, ПРАВИЛО №6, тот же модуль
    использует from_baucenter.py) → ТАКЖЕ item["country_origin"] (как у
    baucenter, format.py); характеристика из characteristics НЕ убирается —
    видна в карточке тоже (то же решение владельца, что у baucenter).
    ДОПОЛНЕНО 26.10.2026 (находка владельца: country_origin='РФ' дефолт у
    товаров ряда выгрузок, перенос страны из файла появился позже загрузки):
    "страна изготовитель" добавлена в общий список (country_names.py);
    "страна-изготовитель" покрывается тем же вариантом после нормализации
    дефиса — отдельной записи не требует.
  - "Торговая марка" — если значение совпадает с итоговым manufacturer (без
    учёта регистра/пробелов), в characteristics НЕ дублируется; отличается
    или manufacturer не задан — остаётся обычной характеристикой.
  - "Габариты (ДхШхВ)" и "Вес брутто" (Сима-ленд) — владелец УТОЧНИЛ
    26.10.2026 на примере товара id 152085 («Ластик фигурный «Панда»»,
    sima_land_catalog_all.json): это технические параметры товара, которые
    ДОЛЖНЫ идти в описание (как и остальные характеристики) — НЕ помечаются
    in_description=False. Прежнее решение дня (упаковка, не товар) отменено
    этим же днём.
  - source_store → characteristic "Магазин-источник" (in_description=False —
    это данные о логистике, не о товаре), НЕ в manufacturer (это не
    производитель, а магазин, у которого выгрузка).
  - link_1 → source_url и links=[{"url","price"}], если непусто.
  - photo_url → photos=[photo_url], если непусто.
  - description ПЕРЕСМОТРЕНО 26.10.2026 (Задача 1, решение владельца): у всех
    товаров в этих выгрузках в description — технический текст поставщика
    (описание и состоит из технических параметров), не реклама. Переносится
    как base_text (item["description"]): чистится через clean_text, затем
    срезается служебный префикс "Описание <название товара>" или просто
    "Описание" в начале (см. _strip_description_prefix) — это не часть
    текста, а заголовок-повтор, который магазин ставит перед описанием.
    Остальной текст (технические параметры в свободной форме) остаётся как
    есть. build_tech_description (другой модуль, см. ПРАВИЛО №6 — там
    единственная сборка текста из base_text+характеристик) дальше склеивает
    этот base_text с characteristics — здесь, в конвертере, эта склейка НЕ
    вызывается, только формируется base_text.
    ДОПОЛНЕНО 26.10.2026 (тем же днём, после среза префикса): у части товаров
    (fire_equipment: "Гидроэлеватор пожарный Г-600", "Колонка пожарная КПА",
    "ШКПС (шлем-каска пожарного спасателя) с пелериной (черная)") остаток
    текста — не технический, а реклама магазина ("... по низким ценам в
    Москве в компании Magazin01. На нашем сайте большой выбор... купить ...
    с доставкой по России."). После _strip_description_prefix текст
    дополнительно прогоняется через strip_ad_sentences (см.
    app.services.catalog_gala.ad_text_filter, ПРАВИЛО №6 — единственное
    место такой фильтрации) — рекламные предложения удаляются целиком; если
    весь текст был рекламой, base_text становится None (как у Г-600/КПА).
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

from app.services.catalog_gala.ad_text_filter import strip_ad_sentences
from app.services.catalog_gala.clean import clean_text
from app.services.catalog_gala.country_names import COUNTRY_KEY_NAMES, norm_country_key
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

# Сима-ленд (26.10, уточнение владельца тем же днём на примере товара
# id 152085 «Ластик фигурный «Панда»»): "Вес брутто"/"Габариты (ДхШхВ)" —
# технические параметры ТОВАРА, не только упаковки — больше НЕ помечаются
# in_description=False (пустое множество, прежнее решение отменено).
_SIMA_PACKAGE_KEY_NAMES: set = set()


def _is_rescue_medical(source_file: str) -> bool:
    return "rescue_medical" in (source_file or "").lower()


# Владелец, 2026-10-26, Задача 1 (пересмотр): выгрузки ставят перед
# технический текстом поставщика служебный заголовок-повтор "Описание
# <название товара>" (например "Описание Шлем ШКПС серебряный Соответствует
# требованиям ГОСТ..." — всё после заголовка это нормальный технический текст
# поставщика). Срезаем только этот заголовок, регистронезависимо.
_DESCRIPTION_WORD_RE = re.compile(r"^описание\b", re.IGNORECASE)


def _strip_description_prefix(description, name) -> "str | None":
    """Срезает служебный префикс "Описание <название>" (или просто
    "Описание") из начала текста description, если он там есть. Остаток —
    обычный технический текст поставщика, остаётся как есть. См. докстринг
    модуля (Задача 1, 26.10.2026)."""
    if not description:
        return None
    text = description.strip()
    if not text:
        return None

    clean_name = clean_text(name) or ""
    if clean_name:
        prefix_with_name_re = re.compile(
            r"^описание\s+" + re.escape(clean_name), re.IGNORECASE
        )
        match = prefix_with_name_re.match(text)
        if match:
            remainder = text[match.end():].strip()
            return remainder or None

    match = _DESCRIPTION_WORD_RE.match(text)
    if match:
        remainder = text[match.end():].lstrip(" :.-").strip()
        return remainder or None

    return text


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

        if norm_country_key(key_lower) in COUNTRY_KEY_NAMES:
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

        item_name = clean_text(row.get("name"))
        description = _strip_description_prefix(clean_text(row.get("description")), item_name)
        # 26.10.2026, Задача 1 (решение владельца тем же днём): после срезки
        # служебного заголовка вырезаем рекламные предложения магазина — см.
        # app.services.catalog_gala.ad_text_filter (ЕДИНСТВЕННОЕ место этого
        # фильтра, ПРАВИЛО №6).
        description = strip_ad_sentences(description)

        items.append({
            "name": item_name,
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
            "description": description,  # base_text поставщика, см. докстринг модуля (26.10, Задача 1)
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
