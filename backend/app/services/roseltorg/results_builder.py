"""Построитель структуры результатов закупки по умолчанию.

ПРАВИЛО №5: компактный модульный файл (< 150 строк).
ПРАВИЛО №6: единый источник состава комиссии и адреса заказчика.
"""
import json
from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.documents.formatting import _fmt_date


def _normalize_commission_members(raw_list: Any, *, from_subsidy: bool = True) -> list[Dict[str, Any]]:
    norm: list[Dict[str, Any]] = []
    for m in (raw_list or []):
        if isinstance(m, dict):
            norm.append({
                "user_id": m.get("user_id"),
                "full_name": (m.get("full_name") or m.get("name") or "").strip(),
                "position": (m.get("position") or "").strip(),
                "role": (m.get("role") or "Член Комиссии").strip(),
                "present": m.get("present", True) is not False,
                "from_subsidy": m.get("from_subsidy", from_subsidy),
            })
        elif isinstance(m, str) and m.strip():
            norm.append({
                "user_id": None,
                "full_name": m.strip(),
                "position": "",
                "role": "Член Комиссии",
                "present": True,
                "from_subsidy": from_subsidy,
            })
    return norm


async def get_or_build_default_results(
    db: AsyncSession,
    purchase: Purchase,
    pub: Optional[PlatformPublication],
) -> Dict[str, Any]:
    """Возвращает сохранённый results_data или строит дефолтный объект из данных закупки и субсидии."""
    subsidy = await db.get(Subsidy, purchase.subsidy_id) if purchase.subsidy_id else None

    if pub and pub.results_data:
        try:
            stored = json.loads(pub.results_data) if isinstance(pub.results_data, str) else pub.results_data
            if isinstance(stored, dict) and stored.get("applications") is not None:
                # Автоподтягивание стандартной комиссии из субсидии, если в stored список пуст
                cur_members = stored.get("commission_members")
                if (not cur_members or len(cur_members) == 0) and subsidy:
                    raw_sub = subsidy.commission_members
                    if isinstance(raw_sub, str):
                        try:
                            raw_sub = json.loads(raw_sub)
                        except Exception:
                            raw_sub = []
                    if raw_sub:
                        stored["commission_members"] = _normalize_commission_members(raw_sub, from_subsidy=True)
                # Автоподтягивание реквизитов приказа из субсидии, если в stored они пустые
                if subsidy:
                    if not stored.get("commission_order_number") and subsidy.commission_order_number:
                        stored["commission_order_number"] = subsidy.commission_order_number
                    if not stored.get("commission_order_date") and subsidy.commission_order_date:
                        stored["commission_order_date"] = subsidy.commission_order_date.isoformat()
                return stored
        except Exception:
            pass

    from app.services.documents.stages_relations import load_customer
    from app.services.documents.contexts_extra import add_customer_context

    customer_org, customer_ctr = await load_customer(db, subsidy)
    cust_ctx: dict[str, Any] = {}
    if customer_org or customer_ctr:
        add_customer_context(cust_ctx, customer_org, customer_ctr)

    cust_addr = cust_ctx.get("customer_address") or ""
    if not cust_addr:
        if customer_ctr:
            cust_addr = getattr(customer_ctr, "address", "") or getattr(customer_ctr, "legal_address", "")
        elif customer_org:
            cust_addr = getattr(customer_org, "address", "") or getattr(customer_org, "contract_address", "")

    reg_num = (
        (pub.platform_number if pub else None)
        or getattr(purchase, "procurement_notice_number", None)
        or ""
    )

    raw_members = subsidy.commission_members if subsidy else None
    if isinstance(raw_members, str):
        try:
            raw_members = json.loads(raw_members)
        except Exception:
            raw_members = []
    commission_members = _normalize_commission_members(raw_members, from_subsidy=True)

    defaults = {
        "procedure_id": (pub.procedure_id if pub else "") or "",
        "lot_id": (pub.lot_id if pub else "") or "",
        "registration_number": reg_num,
        "notice_date": _fmt_date(date.today()),
        "published_at": "",
        "submission_deadline": "",
        "summing_up_date": "",
        "procedure_state": (pub.platform_state if pub else "") or "",
        "initial_sum": float(getattr(purchase, "nmck", None) or getattr(purchase, "planned_total_price", None) or getattr(purchase, "contract_price", None) or 0.0),
        "protocol_number": f"№{reg_num}-1" if reg_num else "",
        "protocol_date": date.today().isoformat(),
        "meeting_time": "16:30",
        "meeting_address": cust_addr or "г. Москва",
        "commission_order_number": (subsidy.commission_order_number if subsidy else "") or "",
        "commission_order_date": (subsidy.commission_order_date.isoformat() if subsidy and subsidy.commission_order_date else "") or "",
        "commission_members": commission_members,
        "applications": [],
        "total_applications": 0,
        "admitted_count": 0,
        "rejected_count": 0,
    }
    return defaults
