"""ЕДИНСТВЕННЫЙ генератор технического задания по 44-ФЗ (ст. 33) из карточки
товара каталога (владелец, 26.10.2026). ПРАВИЛО №6 — других мест, которые
строят текст Product.description_44fz из characteristics/description, в
проекте быть не должно: preview-роутер (app/routers/products_tz44.py) и
скрипт массового заполнения (backend/scripts/fill_description_44fz.py)
вызывают ТОЛЬКО build_tz_44fz() из этого модуля — единственная публичная
сигнатура, остальное (имя/бренды/числа/многострочные пары) разрезано по
соседним модулям (ПРАВИЛО №5, QA-ревью 26.10.2026, п.3):
  - product_tz_44fz_name.py — чистка названия, вырезание брендов из
    названия/значений (_clean_name, _collect_local_brand_words,
    _global_brand_pattern, _strip_brand_mentions, _resolve_name_source).
  - product_tz_44fz_values.py — направление (не менее/не более/точное/
    диапазон), допуск ±10%, разбор "чистого"/"грязного" числового значения
    (_direction_for_name, _format_numeric_value).
  - product_tz_44fz_multiline.py — разбор многострочных значений/описаний
    на пары метка-значение, fallback из свободного текста description
    (_build_param_lines, _parse_description_fallback).

Не путать с app/services/product_tech_description.py (build_tech_description) —
тот собирает «техописание поставщика» (с брендом/артикулом, для карточки
товара), этот — ТЗ для госзакупки (без указаний на конкретного
производителя). Общих хелперов между ними нет — разные правила.

Правило №6 про бренды каталога: "каталожный список брендов" (distinct
Product.manufacturer + значения характеристик «Бренд/Производитель/
Торговая марка» по ВСЕМ товарам) грузит ОДНА функция —
collect_catalog_brands() в app/services/product_tz_44fz_brands.py — и
передаёт сюда параметром `brands`; сама build_tz_44fz() остаётся чистой
(без обращений к БД), только принимает готовый set.

История ревью владельца 26.10.2026 (полный список правил см. в соседних
модулях, куда они физически переехали при разрезании):
  v1 (20 примеров, tz44_samples.md): латиница из названия, допуск только к
     "чистым" числам, EXACT-словарь счётных характеристик, явные
     направления в значении побеждают словарь имени, штампы/дубли имени
     выбрасываются, характеристика "Наименование" не дублируется.
  v2: каталожный список брендов (manufacturer + характеристики Бренд/
     Производитель), допуск только к чистому значению строже, направления
     "максимальн..." само по себе не триггерит "не более", голые числа
     после бренда убираются, многострочные значения — пары.
  v3: вложенные группы в description (заголовок-заголовок), "время
     работы" форсированно "не менее", удаление голых чисел — ТОЛЬКО сразу
     после убранного токена (цепочкой), не везде после первого удаления.
  QA после v3: _SECTION_HEADER_LINES (список слов) заменён на структурную
     проверку без хардкода (product_tz_44fz_multiline._parse_pairs);
     латинские бренды >=4 символов вырезаются регистронезависимо как
     префикс слова ("eskaro" в "Eskarocolor"); это разрезание на модули.
"""
from typing import Optional

from app.services.product_tz_44fz_multiline import _build_param_lines, _parse_description_fallback
from app.services.product_tz_44fz_name import _clean_name, _collect_local_brand_words, _resolve_name_source


def build_tz_44fz(
    name: Optional[str],
    characteristics: Optional[list],
    description: Optional[str],
    manufacturer: Optional[str] = None,
    article: Optional[str] = None,
    brands: Optional[frozenset] = None,
    product_type: Optional[str] = None,
) -> tuple:
    """Собирает текст ТЗ 44-ФЗ. Возвращает (text, needs_review); text is
    None, если параметров нет вообще (ни характеристик, ни пригодного для
    разбора description) — см. докстринг модуля.

    brands — каталожный набор известных брендов/производителей (distinct
    Product.manufacturer + значения характеристик «Бренд/Производитель/
    Торговая марка» по всему каталогу, длина >= 3), собирает вызывающий
    через collect_catalog_brands() (product_tz_44fz_brands.py), ПРАВИЛО №6 —
    эта функция остаётся чистой и не трогает БД сама.

    product_type — Product.product_type («Тип товара»), владелец 26.10.2026:
    приоритет источника наименования — product_type > характеристика
    «Наименование» > Product.name (_resolve_name_source). Непустой
    product_type прогоняется через ТУ ЖЕ чистку брендов/моделей (_clean_name
    — второго места не заводим, ПРАВИЛО №6); если результат чистки непустой,
    он и есть наименование, needs_review форсируется False (тип товара —
    короткая точная строка, ревью не нужно), даже если сама _clean_name
    решила иначе (осталось < 2 слов). Пустой product_type или пустой
    результат чистки — откат к прежней логике (характеристика/название)."""
    characteristics = characteristics or []
    source_items = characteristics
    if not source_items and description:
        source_items = _parse_description_fallback(description)

    product_type_value = (product_type or "").strip()
    force_name_no_review = False
    name_source = ""
    if product_type_value:
        name_source = product_type_value
        force_name_no_review = True

    if not name_source:
        name_source = _resolve_name_source(name, characteristics)
        force_name_no_review = False

    product_name_lower = name_source.strip().lower() if name_source else ""
    # Бренд-слова собираем из source_items (а не только "сырых"
    # characteristics) — у товаров без JSON-характеристик (characteristics
    # пуст) "Производитель"/"Бренд" может прийти ТОЛЬКО из fallback-разбора
    # description.
    local_brand_words = _collect_local_brand_words(source_items, manufacturer, article)

    # Имя чистим СНАЧАЛА (а не после сборки строк) — removed_tokens (бренд/
    # модель-коды, реально вырезанные из названия) нужны ДАЛЬШЕ, чтобы
    # вычистить те же слова и из значений характеристик этого товара —
    # второго места, где эти слова собираются, не заводим (ПРАВИЛО №6).
    clean_name, needs_review, removed_name_tokens = _clean_name(
        name_source, source_items, manufacturer, article, brands,
    )

    if force_name_no_review and not clean_name.strip():
        # Чистка product_type ушла в пустоту (крайний случай) — откат к
        # прежнему источнику наименования (характеристика/Product.name).
        force_name_no_review = False
        name_source = _resolve_name_source(name, characteristics)
        product_name_lower = name_source.strip().lower() if name_source else ""
        clean_name, needs_review, removed_name_tokens = _clean_name(
            name_source, source_items, manufacturer, article, brands,
        )

    if force_name_no_review:
        needs_review = False

    value_strip_words = list(local_brand_words) + removed_name_tokens

    lines = []
    for item in source_items:
        lines.extend(_build_param_lines(item, value_strip_words, brands, product_name_lower))

    if not lines:
        return None, False

    text = f"Наименование: {clean_name}\n\n" + "\n".join(lines)
    return text, needs_review
