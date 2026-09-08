"""Org-matching + preview-payload assembly for vehicles import — extracted
from app/routers/vehicles_import.py (Правило №5, разрезание 2026-09-08).

Сопоставление организации-собственника/эксплуатанта — ИНН приоритетнее
названия, сама логика сопоставления живёт в
app/services/vehicle_org_matching.py, здесь только группировка строк файла
и сборка ответа preview (переиспользуется POST /preview и GET /preview/{sid}).
"""
from datetime import datetime
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.vehicle_pass import VehiclePass
from app.services.vehicle_org_matching import (
    build_inn_index,
    build_name_index,
    resolve_org_for_text,
)

async def _apply_row_passes(db: AsyncSession, vehicle_id: int, row_passes: Dict[str, dict]) -> None:
    """Записать пропуска строки импорта в vehicle_passes (2026-09).

    Upsert по (vehicle_id, name): существующий пропуск с тем же именем
    обновляется (status/expires_at — только те поля, что реально пришли в
    строке файла, остальное не трогаем), новый — создаётся. Данные и статус,
    и "до" могут прийти из РАЗНЫХ колонок файла — row_passes[name] мержит их
    заранее в _parse_xlsx_to_rows.
    """
    for name, pdata in row_passes.items():
        status = pdata.get("status")
        until_str = pdata.get("until")
        until_date = None
        if isinstance(until_str, str) and until_str:
            try:
                until_date = datetime.strptime(until_str, "%Y-%m-%d").date()
            except ValueError:
                until_date = None

        existing_pass = (await db.execute(
            select(VehiclePass).where(VehiclePass.vehicle_id == vehicle_id, VehiclePass.name == name)
        )).scalar_one_or_none()

        if existing_pass is None:
            db.add(VehiclePass(vehicle_id=vehicle_id, name=name, status=status, expires_at=until_date))
        else:
            if status is not None:
                existing_pass.status = status
            if until_date is not None:
                existing_pass.expires_at = until_date


async def _build_org_indexes(db: AsyncSession) -> tuple[Dict[str, int], Dict[str, int]]:
    """Возвращает (inn_index, name_index) по всем организациям в БД."""
    result = await db.execute(select(Organization.id, Organization.name, Organization.inn))
    org_rows = [(row.id, row.name, row.inn) for row in result.all()]
    return build_inn_index(org_rows), build_name_index(org_rows)


def _classify_rows_by_org(
    valid_rows: list[dict],
    text_key: str,
    inn_key: str,
    inn_index: Dict[str, int],
    name_index: Dict[str, int],
) -> tuple[Dict[str, dict], list[dict]]:
    """Группирует строки по значению text_key и определяет org_id (ИНН → название).

    Возвращает (matched, unmapped):
      matched  — {raw_text: {"raw_text", "org_id", "org_name" (== raw_text отображаемо), "method"}}
      unmapped — [{"raw_text", "occurrences"}] — то, что не сопоставилось ни по
                 ИНН, ни по названию; строка ОБЯЗАНА попасть сюда, а не
                 получить организацию по умолчанию молча.
    """
    counter: Dict[str, int] = {}
    matched: Dict[str, dict] = {}
    for row in valid_rows:
        txt = row.get(text_key) or ""
        if not txt:
            continue
        counter[txt] = counter.get(txt, 0) + 1
        if txt not in matched:
            org_id, method = resolve_org_for_text(txt, row.get(inn_key), inn_index, name_index)
            if org_id is not None:
                matched[txt] = {"raw_text": txt, "org_id": org_id, "org_name": txt, "method": method}

    unmapped = [
        {"raw_text": txt, "occurrences": cnt}
        for txt, cnt in counter.items()
        if txt not in matched
    ]
    return matched, unmapped


def _build_preview_payload(
    parsed_rows: list[dict],
    inn_index: Dict[str, int],
    name_index: Dict[str, int],
) -> dict:
    """Общая сборка ответа preview — переиспользуется POST /preview и GET /preview/{sid},
    чтобы не разъезжаться логикой (было продублировано до правки)."""
    valid_rows = [r for r in parsed_rows if not r.get("_skip")]
    invalid_rows = [r for r in parsed_rows if r.get("_skip")]

    matched_owners, unmapped_owners = _classify_rows_by_org(
        valid_rows, "owner_text", "owner_inn", inn_index, name_index
    )
    matched_orgs, unmapped_regions = _classify_rows_by_org(
        valid_rows, "assigned_text", "assigned_inn", inn_index, name_index
    )

    preview_items = []
    for row in valid_rows[:10]:
        owner_txt = row.get("owner_text") or ""
        assigned_txt = row.get("assigned_text") or ""
        owner_match = matched_owners.get(owner_txt)
        assigned_match = matched_orgs.get(assigned_txt)
        preview_items.append({
            "row_n": row["_row_n"],
            "plate": row.get("plate"),
            "brand": row.get("brand"),
            "model": row.get("model"),
            "owner_text": row.get("owner_text"),
            "owner_org_id": owner_match["org_id"] if owner_match else None,
            "owner_match_method": owner_match["method"] if owner_match else None,
            "assigned_text": row.get("assigned_text"),
            "assigned_org_id": assigned_match["org_id"] if assigned_match else None,
            "assigned_match_method": assigned_match["method"] if assigned_match else None,
            "type": row.get("type"),
            "state": row.get("state"),
            "fuel_type": row.get("fuel_type"),
        })

    def _stats(matched: Dict[str, dict]) -> dict:
        return {
            "matched_by_inn": sum(1 for m in matched.values() if m["method"] == "inn"),
            "matched_by_name": sum(1 for m in matched.values() if m["method"] == "name"),
        }

    return {
        "rows_total": len(parsed_rows),
        "rows_valid": len(valid_rows),
        "rows_invalid": len(invalid_rows),
        "unmapped_regions": unmapped_regions,
        "matched_orgs": list(matched_orgs.values()),
        "unmapped_owners": unmapped_owners,
        "matched_owners": list(matched_owners.values()),
        "owner_stats": _stats(matched_owners),
        "assigned_stats": _stats(matched_orgs),
        "preview_items": preview_items,
    }


# ─────────────────────────── POST /preview ───────────────────────────────────


