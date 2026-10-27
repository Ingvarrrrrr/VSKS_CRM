"""CLI: python -m tools.harvest.run --store kuvalda --out <файл> [--limit-categories N]
[--resume] [--pause-per-domain 1.0] [--previous <прошлый файл>] [--prices-only]

Запускает сбор одного магазина целиком (все разделы из STORES[store].SPEC.categories,
если не задан --limit-categories) и прогоняет результат через гейт качества
(tools.harvest.core.quality.write_catalog) перед записью — reject уходит в
<файл>.rejected.json, не в основной файл. НЕ запускать без ограничения в фоне
на реальном магазине без явного согласия владельца (ПРАВИЛО №8 — проверять
последствия перед массовыми операциями).

--previous <файл>: прошлый gala-каталог этого магазина — товары с уже
полными данными (бренд + характеристики/описание) не открываются повторно,
обновляются только цена/дата (core/runner.py). Если не передан — используется
файл по умолчанию из DEFAULT_PREVIOUS_FILES ниже (если он существует), иначе
инкремент просто не применяется (полный сбор, как раньше).

--prices-only: товарные страницы не открываются вовсе — только разделы
(+--previous для всего остального). Для магазинов без цены в разделе
(STORES[x].SPEC.category_has_price=False) печатается честное предупреждение."""
from __future__ import annotations

import argparse
import json
import os

from tools.harvest.core import quality
from tools.harvest.stores import (
    baucenter,
    ice_age,
    inari,
    k_spasatel,
    kns,
    kuvalda,
    magazin01,
    medtehno,
    promalper,
    regard,
    safe,
    sima_land,
)

# Файл по умолчанию для --previous, если флаг не передан явно (владелец
# складывает прошлые выгрузки сюда под этими именами) — используется только
# если существует; CLI-флаг --previous всегда главнее.
DEFAULT_PREVIOUS_DIR = r"C:\Users\1\Downloads\Товары и ТЗ"
DEFAULT_PREVIOUS_FILES = {
    "kuvalda": "kuvalda_tools_hardware_equipment.json",
    "regard": "regard_computers_office_equipment.json",
    "kns": "kns_computers_office_equipment.json",
    "sima_land": "sima_land_catalog_all.json",
    # baucenter собран как 3 отдельных выгрузки (construction/electro/tools) —
    # без --store-специфичного уточнения слага раздела нельзя угадать, какая
    # из трёх нужна; владелец передаёт --previous явно для baucenter.
    "k_spasatel": "k_spasatel_rescue_nomenclature.json",
    "medtehno": "rescue_medical_nomenclature.json",
    "ice_age": "promalp_height_safety_nomenclature.json",
    "promalper": "promalper_height_safety_equipment.json",
    "safe": "safe_promet_metal_furniture_racks.json",
    "magazin01": "fire_equipment_nomenclature.json",
}

STORES = {
    "kuvalda": kuvalda.harvest,
    "regard": regard.harvest,
    "sima_land": sima_land.harvest,
    "baucenter": baucenter.harvest,
    "kns": kns.harvest,
    "k_spasatel": k_spasatel.harvest,
    "magazin01": magazin01.harvest,
    "medtehno": medtehno.harvest,
    "ice_age": ice_age.harvest,
    "promalper": promalper.harvest,
    "safe": safe.harvest,
    "inari": inari.harvest,
}


def _load_previous_items(store: str, explicit_path: str | None) -> list[dict]:
    path = explicit_path
    if not path:
        default_name = DEFAULT_PREVIOUS_FILES.get(store)
        if default_name:
            candidate = os.path.join(DEFAULT_PREVIOUS_DIR, default_name)
            if os.path.exists(candidate):
                path = candidate
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    items = list(data.get("items") or [])
    if items:
        print(f"[{store}] --previous: {path} ({len(items)} позиций)")
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборщик каталога GALA по магазину")
    parser.add_argument("--store", required=True, choices=sorted(STORES.keys()))
    parser.add_argument("--out", required=True, help="Путь к итоговому .json файлу")
    parser.add_argument("--limit-categories", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--pause-per-domain", type=float, default=None,
        help="Переопределяет default_pause_per_domain магазина (по умолчанию — значение, подобранное по старому сборщику этого магазина).",
    )
    parser.add_argument(
        "--previous", default=None,
        help="Прошлый gala-каталог этого магазина — товары с полными данными не открываются повторно.",
    )
    parser.add_argument(
        "--prices-only", action="store_true",
        help="Не открывать товарные страницы вовсе — только разделы (+--previous для остального).",
    )
    parser.add_argument(
        "--with-details", action="store_true",
        help="У магазинов, где раздел уже даёт все обязательные поля (regard) — включает визит ради характеристик/точного артикула.",
    )
    args = parser.parse_args()

    previous_items = _load_previous_items(args.store, args.previous)

    harvest_fn = STORES[args.store]
    manifest = harvest_fn(
        args.out,
        limit_categories=args.limit_categories,
        resume=args.resume,
        pause_per_domain=args.pause_per_domain,
        previous_items=previous_items,
        prices_only=args.prices_only,
        with_details=args.with_details,
    )
    quality.write_catalog(manifest, args.out)


if __name__ == "__main__":
    main()
