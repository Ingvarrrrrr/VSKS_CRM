"""Описание формата GALA и его валидация — ЕДИНСТВЕННОЕ описание структуры в
проекте (ПРАВИЛО №6); конвертеры (from_electro_mpo.py, from_vkusvill.py,
from_gala_sheet.py) обязаны производить данные в этой форме, а не придумывать
свою.

Структура конверта (JSON):
{
  "format": "gala-catalog",      # GALA_FORMAT_NAME, константа
  "version": 1,                  # GALA_FORMAT_VERSION, константа
  "source": "electro_mpo" | "vkusvill" | "gala_sheet",
  "source_file": "<имя исходного файла>",
  "generated_at": "<ISO-datetime>",
  "items": [ <item>, ... ],
  "excluded": [ {"name": str, "reason": str}, ... ]  # опционально, см. ниже
}

excluded (владелец, 2026-10-26) — позиции, которые конвертер сознательно НЕ
включил в items из-за противоречивых данных у поставщика (сейчас — только
from_electro_mpo: кабели, где «N×S» в названии расходится с характеристиками
"Сечение жилы кабеля"/"Количество жил кабеля", см.
services/catalog_gala/electro_consistency.py). Поле необязательно; его
отсутствие равносильно пустому списку.

Структура item (все поля кроме name — опциональны, см. validate_gala_catalog):
{
  "name": str,                       # ОБЯЗАТЕЛЬНО, непустая строка
  "category": str | None,            # верхнеуровневая категория читателя
  "category_path": [str, ...],       # путь категорий от корня к листу
  "product_type": str | None,        # вид/тип изделия (лист категорий у vkusvill,
                                      #   "Тип изделия"/kind у остальных)
  "item_kind": str | None,           # "товар"/"услуга"/"работа" — см.
                                      #   app.services.item_types.ITEM_TYPES
  "unit": str | None,
  "pack_quantity": number | None,
  "pack_unit": str | None,
  "price": number | None,            # 0 трактуется как «цены нет» → None
  "price_date": str | None,          # ISO-дата "YYYY-MM-DD"
  "currency": str | None,
  "manufacturer": str | None,
  "article": str | None,             # УСТАРЕВШЕЕ (владелец, 27.10.2026, см.
                                      #   ниже) — новые конвертеры должны
                                      #   писать manufacturer_article/
                                      #   store_article, article оставлен для
                                      #   обратной совместимости старых файлов.
  "manufacturer_article": str | None,  # опционально (владелец, 27.10.2026) —
                                      #   артикул ПРОИЗВОДИТЕЛЯ, одинаковый у
                                      #   товара во ВСЕХ магазинах, где он
                                      #   продаётся (пример: 14054DEK у МПО
                                      #   Электромонтаж, M34A TLN у
                                      #   k-spasatel.ru — у обоих эти магазины
                                      #   имеют stores.STORES[...]
                                      #   ["article_is_manufacturer"]=True).
  "store_article": str | None,       # опционально (владелец, 27.10.2026) —
                                      #   номер товара в КОНКРЕТНОМ магазине
                                      #   (специфичен для магазина, пример:
                                      #   "Артикул Сима-ленд" 4878510,
                                      #   «Артикул» Бауцентра 705003235 —
                                      #   у обоих stores.py отмечает
                                      #   article_is_manufacturer=False).
  "region": str | None,               # опционально (владелец, 27.10.2026) —
                                      #   субъект РФ, для которого действует
                                      #   ЭТА цена; null = действует по всей
                                      #   России (не путать с item['category']
                                      #   и т.п. — это гео-регион цены).
  "description": str | None,         # вольный текст поставщика
  "characteristics": [
      {"name": str, "value": str | None, "unit": str | None,
       "in_description": bool | None},  # опционально, default True
      ...
  ],
  "photos": [str, ...],
  "links": [{"url": str, "price": number | None}, ...],
  "source_url": str | None,
  "source_id": str | None,
  "is_reusable": bool | None,
  "is_active": bool | None,
  "country_origin": str | None,      # опционально (baucenter, 26.10) —
                                      #   "Страна производства"; апстрим
                                      #   пишет в Product.country_origin,
                                      #   только если он пуст или = "РФ"
  "seller_inn": str | None,          # опционально (владелец, 26.10) — ИНН
                                      #   юрлица/ИП магазина-источника
                                      #   (ссылка товара → домен →
                                      #   services/catalog_gala/stores.py,
                                      #   ЕДИНСТВЕННЫЙ справочник); неизвестный
                                      #   домен → None. Апстрим
                                      #   (apply_products_import) находит/
                                      #   создаёт по нему контрагента строки
                                      #   цены (ПРАВИЛО №6 — один резолвер,
                                      #   contractor_resolve.find_or_create_
                                      #   contractor).
}

Трактовка устаревшего article (владелец, 27.10.2026, без изменения поведения
старых файлов): если в строке НЕ задано явно manufacturer_article/
store_article — article трактуется по магазину строки (seller_inn →
catalog_gala.stores.article_is_manufacturer_for_inn): True → это
manufacturer_article, False (включая неизвестный seller_inn) → это
store_article. Если manufacturer_article/store_article заданы в самой
строке явно — article для соответствующей трактовки игнорируется (новое
поле приоритетнее). Единственное место этого правила —
catalog_gala.stores.split_legacy_article (ПРАВИЛО №6).
"""

GALA_FORMAT_NAME = "gala-catalog"
GALA_FORMAT_VERSION = 1

_KNOWN_STRING_FIELDS = (
    "category", "product_type", "item_kind", "unit", "pack_unit",
    "price_date", "currency", "manufacturer", "article", "description",
    "source_url", "source_id", "country_origin", "seller_inn",
    "manufacturer_article", "store_article", "region",
)
_KNOWN_NUMBER_OR_NULL_FIELDS = ("pack_quantity", "price")
_KNOWN_BOOL_OR_NULL_FIELDS = ("is_reusable", "is_active")


def _err(errors: list, idx: int, msg: str) -> None:
    errors.append(f"items[{idx}]: {msg}")


def validate_gala_catalog(data: dict) -> list:
    """Проверяет конверт GALA. Возвращает список текстов ошибок (пустой — всё ок)."""
    errors: list = []

    if not isinstance(data, dict):
        return ["верхний уровень должен быть объектом"]

    if data.get("format") != GALA_FORMAT_NAME:
        errors.append(f"format должен быть '{GALA_FORMAT_NAME}'")
    if data.get("version") != GALA_FORMAT_VERSION:
        errors.append(f"version должен быть {GALA_FORMAT_VERSION}")

    items = data.get("items")
    if not isinstance(items, list):
        errors.append("items должен быть списком")
        return errors

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            _err(errors, idx, "должен быть объектом")
            continue

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            _err(errors, idx, "name должен быть непустой строкой")

        for field in _KNOWN_STRING_FIELDS:
            if field in item and item[field] is not None and not isinstance(item[field], str):
                _err(errors, idx, f"{field} должен быть строкой или null")

        if "category_path" in item and item["category_path"] is not None:
            cp = item["category_path"]
            if not isinstance(cp, list) or not all(isinstance(x, str) for x in cp):
                _err(errors, idx, "category_path должен быть списком строк")

        for field in _KNOWN_NUMBER_OR_NULL_FIELDS:
            if field in item and item[field] is not None and not isinstance(item[field], (int, float)):
                _err(errors, idx, f"{field} должен быть числом или null")

        for field in _KNOWN_BOOL_OR_NULL_FIELDS:
            if field in item and item[field] is not None and not isinstance(item[field], bool):
                _err(errors, idx, f"{field} должен быть bool или null")

        if "characteristics" in item and item["characteristics"] is not None:
            chars = item["characteristics"]
            if not isinstance(chars, list):
                _err(errors, idx, "characteristics должен быть списком")
            else:
                for c_idx, c in enumerate(chars):
                    if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c.get("name", "").strip():
                        _err(errors, idx, f"characteristics[{c_idx}].name должен быть непустой строкой")
                    if "value" in c and c["value"] is not None and not isinstance(c["value"], str):
                        _err(errors, idx, f"characteristics[{c_idx}].value должен быть строкой или null")
                    if "unit" in c and c["unit"] is not None and not isinstance(c["unit"], str):
                        _err(errors, idx, f"characteristics[{c_idx}].unit должен быть строкой или null")
                    if isinstance(c, dict) and "in_description" in c and c["in_description"] is not None \
                            and not isinstance(c["in_description"], bool):
                        _err(errors, idx, f"characteristics[{c_idx}].in_description должен быть bool или null")

        if "photos" in item and item["photos"] is not None:
            if not isinstance(item["photos"], list) or not all(isinstance(p, str) for p in item["photos"]):
                _err(errors, idx, "photos должен быть списком строк")

        if "links" in item and item["links"] is not None:
            links = item["links"]
            if not isinstance(links, list):
                _err(errors, idx, "links должен быть списком")
            else:
                for l_idx, link in enumerate(links):
                    if not isinstance(link, dict) or not isinstance(link.get("url"), str) or not link.get("url", "").strip():
                        _err(errors, idx, f"links[{l_idx}].url должен быть непустой строкой")
                    if "price" in link and link["price"] is not None and not isinstance(link["price"], (int, float)):
                        _err(errors, idx, f"links[{l_idx}].price должен быть числом или null")

    if "excluded" in data and data["excluded"] is not None:
        excluded = data["excluded"]
        if not isinstance(excluded, list):
            errors.append("excluded должен быть списком")
        else:
            for e_idx, e in enumerate(excluded):
                if not isinstance(e, dict) or not isinstance(e.get("reason"), str) or not e.get("reason", "").strip():
                    errors.append(f"excluded[{e_idx}]: reason должен быть непустой строкой")

    return errors
