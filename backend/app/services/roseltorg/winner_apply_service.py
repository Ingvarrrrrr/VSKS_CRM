"""Сервис применения победителя процедуры и сохранения файлов заявок.

ПРАВИЛО №5: компактный модульный файл (< 200 строк).
ПРАВИЛО №6: единый источник обновления позиций закупки и договора.
ПРАВИЛО №8: безопасность путей файлов, транзакционность БД.
"""
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

logger = logging.getLogger(__name__)

UPLOADS_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "publications"))


def make_safe_filename(original_name: str) -> str:
    """Генерирует безопасное уникальное имя файла для сохранения."""
    base_name = os.path.basename(original_name or "document.bin")
    name_clean = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_.-]", "_", base_name)
    timestamp = int(time.time())
    return f"{timestamp}_{name_clean}"


async def save_publication_file(pub_id: int, file: UploadFile) -> Tuple[str, str, bytes]:
    """Сохраняет загруженный файл в uploads/publications/{pub_id}/ и возвращает (safe_name, url, bytes)."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail=f"Файл {file.filename} пуст")

    pub_dir = os.path.join(UPLOADS_BASE_DIR, str(pub_id))
    os.makedirs(pub_dir, exist_ok=True)

    safe_name = make_safe_filename(file.filename)
    dest_path = os.path.join(pub_dir, safe_name)

    with open(dest_path, "wb") as f:
        f.write(content)

    url = f"/api/publications/{pub_id}/results/files/{safe_name}"
    return safe_name, url, content


def get_publication_file_path(pub_id: int, filename: str) -> str:
    """Возвращает безопасный путь к файлу публикации с защитой от traversal."""
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOADS_BASE_DIR, str(pub_id), safe_name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return file_path


def normalize_item_vat_rate(vat_raw: Any, default_vat_label: str = "Без НДС") -> str:
    """Нормализует ставку НДС позиции к формату GALA: '20%' | '22%' | '10%' | '5%' | '7%' | 'Без НДС'."""
    raw = str(vat_raw or "").strip()
    if not raw or raw.lower() in ("null", "none"):
        raw = str(default_vat_label or "").strip()
    s = raw.lower()
    if not s or "без" in s or "не об" in s or s in ("0", "0%", "none", "-", "нет"):
        return "Без НДС"
    for r in ("22", "20", "10", "5", "7"):
        if r in s:
            return f"{r}%"
    return "Без НДС"


async def apply_winner_positions_and_alternatives(
    db: AsyncSession,
    purchase: Purchase,
    winner: Dict[str, Any],
    contractor: Optional[Contractor] = None,
    apply_positions_prices: bool = True,
    apply_accepted_alternatives: bool = True,
) -> Tuple[int, int, int]:
    """Переносит попозиционные цены, принятые аналоги и НДС победителя в PurchaseItem и ContractItem.

    ПРАВИЛО №6: создание ContractItem если ещё не существовал, автовыбор vat_mode закупки,
    пересчет _recalc_contract_price_from_contract_items.
    """
    positions = winner.get("positions", [])
    if not positions:
        return 0, 0, 0

    p_items_res = await db.execute(
        select(PurchaseItem)
        .where(PurchaseItem.purchase_id == purchase.id)
        .order_by(PurchaseItem.id)
    )
    p_items = p_items_res.scalars().all()
    if not p_items:
        return 0, 0, 0

    # Загружаем также связанные ContractItem (если есть)
    c_items_res = await db.execute(
        select(ContractItem).where(ContractItem.purchase_id == purchase.id)
    )
    c_items = c_items_res.scalars().all()
    c_item_by_source_id = {ci.source_item_id: ci for ci in c_items if ci.source_item_id}

    updated_positions = 0
    applied_alternatives = 0
    created_contract_items = 0
    all_vats: List[str] = []

    # Карта позиций победителя по purchase_item_id и по item_num
    pos_by_item_id = {p.get("purchase_item_id"): p for p in positions if p.get("purchase_item_id")}
    pos_by_num = {p.get("item_num"): p for p in positions if p.get("item_num")}
    default_vat = winner.get("vat_label") or "Без НДС"

    for idx, p_item in enumerate(p_items, start=1):
        matched_pos = pos_by_item_id.get(p_item.id) or pos_by_num.get(idx)
        if not matched_pos:
            continue

        c_item = c_item_by_source_id.get(p_item.id)

        # 1. Наименование товара / согласованного аналога
        offered_name = (matched_pos.get("offered_name") or "").strip()
        is_alt = bool(matched_pos.get("is_alternative"))
        status = matched_pos.get("compliance_status")
        target_name = p_item.item_name

        if apply_accepted_alternatives and offered_name:
            if not is_alt or status in ("analog_accepted", "analog_pending"):
                target_name = offered_name
                p_item.accepted_name = offered_name
                off_specs = (matched_pos.get("offered_specs") or "").strip()
                if off_specs and off_specs != offered_name:
                    p_item.tz_description = f"{p_item.tz_description or ''}\nСогласованный аналог: {offered_name}. Характеристики: {off_specs}".strip()
                if is_alt:
                    applied_alternatives += 1

        # 2. Цены и суммы
        qty = float(p_item.quantity or 1.0)
        u_price = matched_pos.get("unit_price")
        t_price = matched_pos.get("total_price")
        if u_price is not None and float(u_price) >= 0:
            unit_price_dec = Decimal(str(u_price))
        else:
            unit_price_dec = p_item.unit_price or Decimal("0.0")

        if t_price is not None and float(t_price) >= 0:
            total_price_dec = Decimal(str(t_price))
        else:
            total_price_dec = Decimal(str(round(qty * float(unit_price_dec), 2)))

        if apply_positions_prices:
            p_item.unit_price = unit_price_dec
            p_item.total_price = total_price_dec
            p_item.final_unit_price = unit_price_dec
            p_item.final_total = total_price_dec

        # Привязка подрядчика в строке закупки
        if contractor:
            p_item.contractor_id = contractor.id
            p_item.contractor_inn = contractor.inn
            p_item.contractor_name = contractor.name

        # 3. НДС позиции
        item_vat = normalize_item_vat_rate(matched_pos.get("vat_rate"), default_vat)
        p_item.vat_rate = item_vat
        all_vats.append(item_vat)

        # 4. Обновление или создание ContractItem
        if c_item:
            c_item.name = target_name
            if apply_positions_prices:
                c_item.unit_price = unit_price_dec
                c_item.total = total_price_dec
            c_item.vat_rate = item_vat
        else:
            c_item = ContractItem(
                purchase_id=purchase.id,
                source_item_id=p_item.id,
                product_id=p_item.product_id,
                name=target_name,
                quantity=p_item.quantity,
                unit=p_item.unit,
                unit_price=unit_price_dec,
                total=total_price_dec,
                vat_rate=item_vat,
                extra_attrs=getattr(p_item, "extra_attrs", None) or {},
                match_confirmed=True,
            )
            db.add(c_item)
            c_item_by_source_id[p_item.id] = c_item
            created_contract_items += 1

        updated_positions += 1

    # 5. Автоматическая настройка режима НДС закупки
    unique_vats = set(all_vats)
    if len(unique_vats) > 1:
        purchase.vat_mode = "per_item"
        purchase.vat_applicable = any(v != "Без НДС" for v in unique_vats)
    elif len(unique_vats) == 1:
        purchase.vat_mode = "uniform"
        single_vat = list(unique_vats)[0]
        if single_vat == "Без НДС":
            purchase.vat_applicable = False
            purchase.vat_rate = None
        else:
            purchase.vat_applicable = True
            m_v = re.search(r"\d+", single_vat)
            purchase.vat_rate = int(m_v.group(0)) if m_v else 20

    # 6. Пересчет цены договора из ContractItem
    try:
        from app.routers.purchases import _recalc_contract_price_from_contract_items
        await _recalc_contract_price_from_contract_items(purchase.id, db)
    except Exception as e:
        logger.debug("recalc_contract_price_from_contract_items skipped: %s", e)

    return updated_positions, applied_alternatives, created_contract_items


async def apply_winner_full(
    db: AsyncSession,
    purchase: Purchase,
    winner: Dict[str, Any],
    protocol_number: Optional[str] = None,
    apply_positions_prices: bool = True,
    apply_accepted_alternatives: bool = True,
) -> Dict[str, Any]:
    """Находит/создаёт подрядчика, обновляет закупку, переносит цены и согласованные аналоги."""
    winner_name = (winner.get("supplier_name") or winner.get("supplier_short_name") or "").strip()
    winner_short_name = (winner.get("supplier_short_name") or winner_name).strip()
    winner_inn = (winner.get("inn") or "").strip()
    winner_kpp = (winner.get("kpp") or "").strip()

    contractor = None
    if winner_inn:
        c_res = await db.execute(select(Contractor).where(Contractor.inn == winner_inn))
        contractor = c_res.scalars().first()
    elif winner_name:
        c_res = await db.execute(select(Contractor).where(func.lower(Contractor.name) == winner_name.lower()))
        contractor = c_res.scalars().first()

    if not contractor:
        org_type = "ИП" if len(winner_inn) == 12 else "ЮЛ"
        contractor = Contractor(
            name=winner_short_name or winner_name or "Победитель закупки",
            full_name=winner_name or winner_short_name or "Победитель закупки",
            inn=winner_inn or None,
            kpp=winner_kpp or None,
            ogrn=winner.get("ogrn") or None,
            address=winner.get("address") or None,
            phone=winner.get("phone") or None,
            email=winner.get("email") or None,
            org_type=org_type,
        )
        db.add(contractor)
        await db.flush()

    purchase.contractor_id = contractor.id

    winner_price = winner.get("price_with_vat") or winner.get("price_without_vat")
    if winner_price and float(winner_price) > 0:
        purchase.contract_price = Decimal(str(winner_price))

    if protocol_number:
        purchase.procurement_protocol_number = protocol_number

    updated_pos_count, applied_alts_count, created_ci_count = await apply_winner_positions_and_alternatives(
        db=db,
        purchase=purchase,
        winner=winner,
        contractor=contractor,
        apply_positions_prices=apply_positions_prices,
        apply_accepted_alternatives=apply_accepted_alternatives,
    )

    await db.commit()
    await db.refresh(purchase)

    return {
        "ok": True,
        "contractor_id": contractor.id,
        "contractor_name": contractor.name,
        "contract_price": float(purchase.contract_price) if purchase.contract_price else None,
        "procurement_protocol_number": purchase.procurement_protocol_number,
        "updated_positions_count": updated_pos_count,
        "applied_alternatives_count": applied_alts_count,
        "created_contract_items_count": created_ci_count,
        "vat_mode": purchase.vat_mode,
        "vat_applicable": purchase.vat_applicable,
        "vat_rate": purchase.vat_rate,
    }
