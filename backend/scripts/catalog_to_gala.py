"""CLI: конвертация выгрузки поставщика в формат GALA (владелец, 26.10).

Запуск (из backend/, с активным venv):
    python -m scripts.catalog_to_gala --source electro_mpo --in <путь.json> --out <путь.gala.json>

--source выбирает конвертер явно (app/services/catalog_gala/from_*.py) —
автоопределение по форме входа не делается, т.к. electro_mpo/vkusvill/gala_sheet
не всегда различимы по одной лишь структуре верхнего уровня.

Исключение — store_nomenclature (владелец, 2026-10-26, Задача 1): формат
promalp_height_safety/rescue_medical/fire_equipment_nomenclature.json
однозначно узнаётся по наличию У ПЕРВОГО ЭЛЕМЕНТА одновременно ключей
"price_rub" и "source_store" (их нет ни у одного другого источника) —
--source можно не передавать, определяется сам (_detect_source).

Если validate_gala_catalog находит ошибки — они печатаются в stderr, CLI
завершается ненулевым кодом, но результат ВСЁ РАВНО записывается в --out: это
диагностический инструмент разбора чужих выгрузок, где частичный результат
полезнее отсутствия файла (его можно открыть и посмотреть, что сломалось).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from app.services.catalog_gala.format import GALA_FORMAT_NAME, GALA_FORMAT_VERSION, validate_gala_catalog
from app.services.catalog_gala import (
    from_electro_mpo, from_vkusvill, from_gala_sheet, from_baucenter, from_store_nomenclature,
)

_CONVERTERS = {
    "electro_mpo": from_electro_mpo.convert,
    "vkusvill": from_vkusvill.convert,
    "gala_sheet": from_gala_sheet.convert,
    "baucenter": from_baucenter.convert,
    "store_nomenclature": from_store_nomenclature.convert,
}


def _detect_source(raw) -> str:
    """Автоопределение --source store_nomenclature (владелец, 26.10, Задача 1)
    по наличию price_rub+source_store у первого элемента — единственный
    источник с такой парой ключей. Возвращает None, если не распознано
    (вызывающий код тогда требует явный --source)."""
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        if "price_rub" in raw[0] and "source_store" in raw[0]:
            return "store_nomenclature"
    return None


def build_envelope(source: str, in_path: str, converted: dict) -> dict:
    envelope = {
        "format": GALA_FORMAT_NAME,
        "version": GALA_FORMAT_VERSION,
        "source": converted.get("source", source),
        "source_file": os.path.basename(in_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": converted.get("items", []),
    }
    # excluded (владелец, 2026-10-26) — позиции, которые конвертер сознательно
    # не включил (сейчас только from_electro_mpo, кабели с противоречивыми
    # данными, см. electro_consistency.py) — пишем только если непусто,
    # чтобы не раздувать envelope у конвертеров без этой проверки.
    excluded = converted.get("excluded") or []
    if excluded:
        envelope["excluded"] = excluded
    return envelope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=False, choices=sorted(_CONVERTERS.keys()))
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", dest="out_path", required=True)
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    source = args.source
    if not source:
        source = _detect_source(raw)
        if not source:
            print("--source не указан и не распознан автоматически", file=sys.stderr)
            sys.exit(2)
        print(f"--source не указан, распознано автоматически: {source}", file=sys.stderr)

    converter = _CONVERTERS[source]
    converted = converter(raw, args.in_path)
    envelope = build_envelope(source, args.in_path, converted)

    errors = validate_gala_catalog(envelope)

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)

    if errors:
        print(f"Валидация GALA нашла {len(errors)} ошибок в {args.out_path}:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    excluded_count = len(envelope.get("excluded") or [])
    extra = f", отброшено противоречивых: {excluded_count}" if excluded_count else ""
    print(f"OK: {len(envelope['items'])} позиций{extra} -> {args.out_path}")


if __name__ == "__main__":
    main()
