"""Гейт качества перед сдачей файла — ЕДИНСТВЕННОЕ место, решающее
ok/reject для каталога, собранного tools/harvest (ПРАВИЛО №6: store-модули
не пишут собственную проверку "норм ли файл")."""
from __future__ import annotations

import json
import os
import re

from tools.harvest.core.gala_contracts import load_gala_contracts

_CONTRACTS = load_gala_contracts()

_PLACEHOLDER_SPEC_RE = re.compile(r"^(параметр|спецификация)\s*\d+$", re.IGNORECASE)

# Пороги reject — единственное место, где они заданы (можно подвинуть по
# факту накопленных файлов).
THRESHOLDS = {
    "mfr_bogus_rate": 0.15,
    "inn_invalid_rate": 0.05,
    "placeholder_specs_rate": 0.10,
    "no_price_or_link_rate": 0.20,
}


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def quality_report(data: dict) -> dict:
    """Возвращает {metrics, schema_errors, verdict: "ok"|"reject", reasons,
    warnings}."""
    schema_errors = _CONTRACTS.validate_gala_catalog(data)
    items = data.get("items") or []
    n = len(items)

    mfr_checked = mfr_bogus = 0
    inn_checked = inn_invalid = 0
    spec_total = spec_placeholder = 0
    no_price_or_link = 0
    country_values: set[str] = set()
    country_filled = 0

    for item in items:
        manufacturer = item.get("manufacturer")
        if manufacturer is not None:
            mfr_checked += 1
            if _CONTRACTS.is_bogus_manufacturer(manufacturer, item.get("name")):
                mfr_bogus += 1

        seller_inn = item.get("seller_inn")
        if seller_inn:
            inn_checked += 1
            if not _CONTRACTS.inn_checksum_valid(seller_inn):
                inn_invalid += 1

        for c in item.get("characteristics") or []:
            spec_total += 1
            if _PLACEHOLDER_SPEC_RE.match((c.get("name") or "").strip()):
                spec_placeholder += 1

        has_price = item.get("price") is not None
        has_link = bool(item.get("links"))
        if not has_price and not has_link:
            no_price_or_link += 1

        country = item.get("country_origin")
        if country:
            country_filled += 1
            country_values.add(country)

    metrics = {
        "n_items": n,
        "mfr_bogus_rate": _rate(mfr_bogus, mfr_checked),
        "inn_invalid_rate": _rate(inn_invalid, inn_checked),
        "placeholder_specs_rate": _rate(spec_placeholder, spec_total),
        "no_price_or_link_rate": _rate(no_price_or_link, n),
        "country_filled_rate": _rate(country_filled, n),
        "country_unique_values": len(country_values),
    }

    reasons = []
    if schema_errors:
        reasons.append(f"схема невалидна: {len(schema_errors)} ошибок (см. schema_errors)")
    if metrics["mfr_bogus_rate"] > THRESHOLDS["mfr_bogus_rate"]:
        reasons.append(
            f"mfr_bogus_rate={metrics['mfr_bogus_rate']:.2%} > {THRESHOLDS['mfr_bogus_rate']:.0%}"
        )
    if metrics["inn_invalid_rate"] > THRESHOLDS["inn_invalid_rate"]:
        reasons.append(
            f"inn_invalid_rate={metrics['inn_invalid_rate']:.2%} > {THRESHOLDS['inn_invalid_rate']:.0%}"
        )
    if metrics["placeholder_specs_rate"] > THRESHOLDS["placeholder_specs_rate"]:
        reasons.append(
            f"placeholder_specs_rate={metrics['placeholder_specs_rate']:.2%} > "
            f"{THRESHOLDS['placeholder_specs_rate']:.0%}"
        )
    if metrics["no_price_or_link_rate"] > THRESHOLDS["no_price_or_link_rate"]:
        reasons.append(
            f"no_price_or_link_rate={metrics['no_price_or_link_rate']:.2%} > "
            f"{THRESHOLDS['no_price_or_link_rate']:.0%}"
        )

    warnings = []
    if metrics["country_filled_rate"] > 0.9 and metrics["country_unique_values"] <= 1 and n > 5:
        warnings.append(
            "подозрение на умолчание: country_origin заполнена у >90% строк одним "
            "и тем же значением — проверить, что это не захардкоженная страна"
        )

    return {
        "metrics": metrics,
        "schema_errors": schema_errors,
        "verdict": "reject" if reasons else "ok",
        "reasons": reasons,
        "warnings": warnings,
    }


def _atomic_write(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _rejected_path(out_path: str) -> str:
    if out_path.endswith(".json"):
        return out_path[: -len(".json")] + ".rejected.json"
    return out_path + ".rejected.json"


def write_catalog(data: dict, out_path: str) -> dict:
    """verdict=="reject" → пишет в <out_path>.rejected.json и НЕ пишет под
    основным именем; verdict=="ok" → пишет под основным именем, атомарно
    (.tmp + os.replace)."""
    report = quality_report(data)

    if report["verdict"] == "reject":
        rejected_path = _rejected_path(out_path)
        _atomic_write(data, rejected_path)
        print(f"[quality] REJECT: {out_path} -> {rejected_path}")
        for reason in report["reasons"]:
            print(f"  - {reason}")
    else:
        _atomic_write(data, out_path)
        print(f"[quality] OK: {out_path} ({report['metrics']['n_items']} items)")
        for warning in report["warnings"]:
            print(f"  ! {warning}")

    return report
