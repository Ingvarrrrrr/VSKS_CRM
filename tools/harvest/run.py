"""CLI: python -m tools.harvest.run --store kuvalda --out <файл> [--limit-categories N]
[--resume] [--pause-per-domain 1.0]

Запускает сбор одного магазина целиком (все разделы из STORES[store].SPEC.categories,
если не задан --limit-categories) и прогоняет результат через гейт качества
(tools.harvest.core.quality.write_catalog) перед записью — reject уходит в
<файл>.rejected.json, не в основной файл. НЕ запускать без ограничения в фоне
на реальном магазине без явного согласия владельца (ПРАВИЛО №8 — проверять
последствия перед массовыми операциями)."""
from __future__ import annotations

import argparse

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборщик каталога GALA по магазину")
    parser.add_argument("--store", required=True, choices=sorted(STORES.keys()))
    parser.add_argument("--out", required=True, help="Путь к итоговому .json файлу")
    parser.add_argument("--limit-categories", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--pause-per-domain", type=float, default=1.0)
    args = parser.parse_args()

    harvest_fn = STORES[args.store]
    manifest = harvest_fn(
        args.out,
        limit_categories=args.limit_categories,
        resume=args.resume,
        pause_per_domain=args.pause_per_domain,
    )
    quality.write_catalog(manifest, args.out)


if __name__ == "__main__":
    main()
