"""Получение и обработка результатов процедур с площадки Росэлторг.Бизнес.

ПРАВИЛО №5: компактный модуль (< 400 строк).
ПРАВИЛО №6: переиспользование авторизации и общих хелперов, без дублирования.
ПРАВИЛО №8: валидные HTTP-коды и понятные русские сообщения об ошибках.
"""
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.models.platform_publication import PlatformPublication
from .auth import (
    ROSELTORG_BASE_URL,
    get_roseltorg_jwt,
    rb_call,
    rb_ok,
    rb_error_text,
    RoseltorgAuthError,
)
from .client import _resolve_roseltorg_token
from .winner_apply_service import normalize_item_vat_rate

logger = logging.getLogger(__name__)


def recalculate_places(applications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Пересчитывает места участников закупки.

    Среди заявок с admitted == True сортирует по возрастанию цены:
    (price_with_vat or price_without_vat), при равенстве — по дате подачи.
    Присваивает place = 1, 2, 3...
    Для отклонённых заявок place = None.
    """
    for app in applications:
        # Убедимся, что поле admitted имеет булево значение
        app["admitted"] = bool(app.get("admitted"))

    admitted_apps = [a for a in applications if a.get("admitted")]
    rejected_apps = [a for a in applications if not a.get("admitted")]

    def _sort_key(a: Dict[str, Any]):
        p_with = float(a.get("price_with_vat") or 0.0)
        p_without = float(a.get("price_without_vat") or 0.0)
        effective_price = p_with if p_with > 0 else p_without
        submitted = str(a.get("submitted_at") or "")
        return (effective_price, submitted)

    admitted_apps.sort(key=_sort_key)

    for idx, a in enumerate(admitted_apps, start=1):
        a["place"] = idx

    for a in rejected_apps:
        a["place"] = None

    return applications


def format_vat_label(vat_raw: str | None) -> str:
    """Форматирует ставку НДС в читаемую строку по правилам протоколов."""
    if not vat_raw:
        return "Без НДС"
    s = str(vat_raw).strip()
    s_lower = s.lower()
    if "без ндс" in s_lower or s_lower in ("no", "0", "0%", "none", "-", "нет"):
        return "Без НДС"
    if "22" in s_lower:
        return "в т.ч. НДС 22%"
    if "20" in s_lower:
        return "в т.ч. НДС 20%"
    if "10" in s_lower:
        return "в т.ч. НДС 10%"
    if "5" in s_lower:
        return "в т.ч. НДС 5%"
    if "7" in s_lower:
        return "в т.ч. НДС 7%"
    if "с ндс" in s_lower:
        return "с НДС"
    return f"в т.ч. НДС {s}"


async def fetch_roseltorg_procedure_results(
    pub: PlatformPublication,
    user_id: Optional[int] = None,
    manual_reg_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Получает результаты процедуры и рассмотрения заявок с Росэлторг.Бизнес API.

    Сливает полученные данные с сохранёнными пользователем решениями.
    """
    token = await _resolve_roseltorg_token(user_id)
    if not token:
        raise HTTPException(
            status_code=422,
            detail="Не задан интеграционный токен Росэлторг.Бизнес (в профиле пользователя или в настройках окружения)",
        )

    try:
        jwt = await get_roseltorg_jwt(token)
    except RoseltorgAuthError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка авторизации Росэлторг: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Не удалось связаться с сервером авторизации Росэлторг: {e}")

    base = ROSELTORG_BASE_URL
    procedure_id = pub.procedure_id
    reg_num = manual_reg_number or pub.platform_number

    # Шаг 1: если есть external_id (noticeId) и он числовой, узнаем статус и procedureId
    if pub.external_id and str(pub.external_id).isdigit():
        n_res, n_status = await rb_call(jwt, f"{base}/notices/{pub.external_id}/status", method="GET")
        if rb_ok(n_res, n_status):
            n_data = n_res.get("data") or {}
            procedure_id = str(n_data.get("procedureId") or procedure_id or "")
            reg_num = n_data.get("procedureRegistrationNumber") or reg_num

    # Если procedure_id ещё неизвестен, пробуем найти по registrationNumber
    if not procedure_id and reg_num:
        p_list_res, pl_status = await rb_call(jwt, f"{base}/procedures?registrationNumber={reg_num}", method="GET")
        if rb_ok(p_list_res, pl_status):
            items = p_list_res.get("items") or p_list_res.get("data") or []
            if isinstance(items, list) and items:
                procedure_id = str(items[0].get("id") or items[0].get("procedureId") or "")
            elif isinstance(items, dict):
                procedure_id = str(items.get("id") or items.get("procedureId") or "")

    if not procedure_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Не удалось определить процедуру на Росэлторге по номеру {reg_num or pub.external_id or '—'}. "
                "Проверьте правильность номера извещения (например, B3004261856309) или загрузите файл протокола."
            ),
        )

    # Шаг 2: детальная информация о процедуре
    proc_res, p_status = await rb_call(jwt, f"{base}/procedures/{procedure_id}", method="GET")
    if not rb_ok(proc_res, p_status):
        err = rb_error_text(proc_res)
        raise HTTPException(status_code=502, detail=f"Ошибка получения процедуры #{procedure_id}: {err}")

    proc_data = proc_res.get("data") or proc_res
    registration_number = (
        proc_data.get("procedureRegistrationNumber")
        or proc_data.get("registrationNumber")
        or reg_num
        or ""
    )
    published_at = proc_data.get("publishedDateTime") or proc_data.get("publishedAt") or ""
    procedure_state = proc_data.get("state") or proc_data.get("procedureState") or proc_data.get("status") or ""

    submission_deadline = ""
    summing_up_date = ""
    order_stages = proc_data.get("order") or proc_data.get("stages") or []
    if isinstance(order_stages, list):
        for stage in order_stages:
            stype = stage.get("type") or stage.get("stageType")
            if stype == "AcceptanceApplicationsDateEnd":
                submission_deadline = stage.get("time") or stage.get("date") or ""
            elif stype == "SummingUp":
                summing_up_date = stage.get("time") or stage.get("date") or ""

    # Шаг 2б: список лотов процедуры
    lots_res, l_status = await rb_call(jwt, f"{base}/procedures/{procedure_id}/lots/list", method="GET")
    lot_id = pub.lot_id
    initial_sum = 0.0
    lots_items = lots_res.get("items") or lots_res.get("data") or []
    if isinstance(lots_items, list) and lots_items:
        first_lot = lots_items[0]
        lot_id = str(first_lot.get("id") or first_lot.get("lotId") or lot_id or "")
        initial_sum = float(first_lot.get("startingPrice") or first_lot.get("price") or 0.0)
    elif isinstance(lots_items, dict):
        lot_id = str(lots_items.get("id") or lots_items.get("lotId") or lot_id or "")
        initial_sum = float(lots_items.get("startingPrice") or lots_items.get("price") or 0.0)

    # Шаг 3: заявки по лоту
    raw_apps: List[Dict[str, Any]] = []
    if lot_id:
        apps_res, a_status = await rb_call(jwt, f"{base}/applications/lot/{lot_id}", method="GET")
        if rb_ok(apps_res, a_status):
            apps_payload = apps_res.get("items") or apps_res.get("data") or []
            if isinstance(apps_payload, dict) and "items" in apps_payload:
                raw_apps = apps_payload["items"]
            elif isinstance(apps_payload, list):
                raw_apps = apps_payload

    # Шаг 4: слияние с существующим results_data
    existing_data: Dict[str, Any] = {}
    if pub.results_data:
        try:
            existing_data = json.loads(pub.results_data) if isinstance(pub.results_data, str) else pub.results_data
        except Exception:
            existing_data = {}

    existing_apps_map: Dict[str, Dict[str, Any]] = {}
    for a in existing_data.get("applications", []):
        k1 = str(a.get("application_number") or "").strip()
        k2 = str(a.get("inn") or "").strip()
        if k1:
            existing_apps_map[k1] = a
        if k2:
            existing_apps_map[k2] = a

    parsed_apps: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_apps):
        app_num = str(item.get("applicationNumber") or item.get("id") or (idx + 1)).strip()
        inn = str(item.get("inn") or "").strip()
        supplier_name = str(
            item.get("supplier") or item.get("supplierShortName") or item.get("organizationName") or ""
        ).strip()
        price_with_vat = float(item.get("FinalPriceWithVAT") or item.get("priceWithVAT") or item.get("price") or 0.0)
        price_without_vat = float(item.get("FinalPriceWithoutVAT") or item.get("priceWithoutVAT") or 0.0)
        vat_raw = str(item.get("VAT") or item.get("vat") or "").strip()
        vat_label = format_vat_label(vat_raw)

        platform_rejected = bool(item.get("rejected") or item.get("isRejected"))
        state_str = str(item.get("state") or "").lower()
        if "decline" in state_str or "reject" in state_str:
            platform_rejected = True
        platform_decline_reason = str(item.get("declineInfo") or item.get("declineReason") or "").strip()

        lookup = existing_apps_map.get(app_num) or (existing_apps_map.get(inn) if inn else None)
        if lookup and "admitted" in lookup:
            admitted = bool(lookup["admitted"])
            rejection_reason = lookup.get("rejection_reason", "")
            decision_text = lookup.get("decision_text", "")
        else:
            admitted = not platform_rejected
            rejection_reason = platform_decline_reason
            if admitted:
                decision_text = "Признать соответствующей требованиям закупочной документации."
            else:
                reason_part = f" {platform_decline_reason}" if platform_decline_reason else ""
                decision_text = f"Признать не соответствующей требованиям закупочной документации.{reason_part}"

        # Неблокирующий запрос ответов анкеты участника
        app_id_val = str(item.get("id") or item.get("applicationId") or "").strip()
        q_answers: List[Dict[str, Any]] = []
        if app_id_val:
            try:
                q_res, q_status = await rb_call(
                    jwt, f"{base}/applications/{app_id_val}/purchase-questions/list", method="GET"
                )
                if rb_ok(q_res, q_status):
                    items_q = q_res.get("items") or q_res.get("data") or []
                    if isinstance(items_q, list):
                        q_answers = items_q
                    elif isinstance(items_q, dict) and "items" in items_q:
                        q_answers = items_q["items"]
            except Exception as q_err:
                logger.debug("Failed to fetch questions for app %s: %s", app_id_val, q_err)

        parsed_apps.append({
            "app_id": str(item.get("id") or app_num),
            "application_number": app_num,
            "supplier_name": supplier_name,
            "supplier_short_name": str(item.get("supplierShortName") or ""),
            "inn": inn,
            "kpp": str(item.get("kpp") or ""),
            "ogrn": str(item.get("ogrn") or ""),
            "address": str(item.get("legalAddress") or item.get("postalAddress") or ""),
            "phone": str(item.get("organizationPhone") or item.get("phone") or ""),
            "email": str(item.get("organizationEmail") or item.get("email") or ""),
            "submitted_at": str(item.get("signedAt") or item.get("offerCreateDate") or item.get("createdAt") or ""),
            "price_with_vat": price_with_vat,
            "price_without_vat": price_without_vat,
            "vat_raw": vat_raw,
            "vat_label": vat_label,
            "positions": [
                {
                    **p,
                    "vat_rate": normalize_item_vat_rate(
                        p.get("vat_rate") or p.get("vatRate") or vat_label,
                        default_vat_label=vat_label,
                    ),
                }
                for p in (item.get("PricePerLotPosition") or item.get("positions") or [])
            ],
            "documents": item.get("DocumentsList") or item.get("ThirdPart") or item.get("documents") or [],
            "questionnaire_answers": q_answers,
            "platform_rejected": platform_rejected,
            "platform_decline_reason": platform_decline_reason,
            "admitted": admitted,
            "rejection_reason": rejection_reason,
            "decision_text": decision_text,
        })

    recalculated = recalculate_places(parsed_apps)

    results = {
        "procedure_id": str(procedure_id),
        "lot_id": str(lot_id or ""),
        "registration_number": registration_number,
        "published_at": published_at,
        "submission_deadline": submission_deadline,
        "summing_up_date": summing_up_date,
        "procedure_state": procedure_state,
        "initial_sum": initial_sum,
        "applications": recalculated,
        "total_applications": len(recalculated),
        "admitted_count": sum(1 for a in recalculated if a.get("admitted")),
        "rejected_count": sum(1 for a in recalculated if not a.get("admitted")),
        "protocol_number": existing_data.get("protocol_number") or (f"№{registration_number}-1" if registration_number else ""),
        "protocol_date": existing_data.get("protocol_date") or date.today().isoformat(),
        "meeting_time": existing_data.get("meeting_time") or "16:30",
        "meeting_address": existing_data.get("meeting_address") or "",
        "commission_order_number": existing_data.get("commission_order_number") or "",
        "commission_order_date": existing_data.get("commission_order_date") or "",
        "commission_members": existing_data.get("commission_members") or [],
    }
    return results
