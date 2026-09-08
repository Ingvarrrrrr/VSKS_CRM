"""Поиск контрагента по ИНН во внешних реестрах (ЕГРЮЛ/ЕГРИП, ФНС) и bulk-FNS-обогащение.

ПЕРЕНЕСЕНО (не изменено) из app/routers/contractors.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Тот же префикс
/api/contractors, регистрируется РЯДОМ с contractors.router и ДО него —
GET /lookup-inn/{inn} имеет 2 сегмента и не конфликтует с GET /{cid} core-
роутера независимо от порядка, но для единообразия со всеми siblings
регистрируется до него (см. app/routes.py).

enrich-from-fns/{contractor_id} и enrich-all-fns вызывают lookup_inn
напрямую (тот же паттерн переиспользования, что и раньше в монолите) —
второго механизма ЕГРЮЛ/ФНС-поиска не заводим.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contractor import Contractor
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.schemas.schemas import ContractorOut
from app.services.contractor_lookup import _split_signatory, _check_npd_status
from app.services.fio import split_position_and_fio

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


@router.get("/lookup-inn/{inn}")
async def lookup_inn(
    inn: str,
    force_egrul: bool = Query(False),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lookup company data by INN: first local DB (unless force_egrul=1), then FNS EGRUL/EGRIP API."""
    import httpx
    import logging
    import re as _re_lookup
    logger = logging.getLogger(__name__)

    inn = inn.strip()
    if not inn or len(inn) not in (10, 12):
        raise HTTPException(400, "ИНН должен быть 10 (юр.лицо) или 12 (ИП) цифр")

    # Step 0: check local DB first (skip if force_egrul requested)
    if not force_egrul:
        local = await db.execute(
            select(Contractor).where(Contractor.inn == inn).limit(1)
        )
        local_contractor = local.scalar_one_or_none()
    else:
        local_contractor = None
    if local_contractor:
        # Defensive filter: if phone field contains the INN (data entry error) — suppress it
        raw_phone = local_contractor.phone
        _lc_phone = (raw_phone or '').lower().strip()
        if raw_phone and (
            _lc_phone == inn
            or _lc_phone.startswith('инн')
            or _re_lookup.sub(r'\D', '', raw_phone) == inn
        ):
            raw_phone = None
            logger.warning("lookup_inn: phone field contained INN for contractor %s, suppressed", inn)
        _lc_sig, _lc_pos = _split_signatory(
            local_contractor.signatory, getattr(local_contractor, "signatory_position", None)
        )
        return {
            "id": local_contractor.id,
            "name": local_contractor.name,
            "inn": local_contractor.inn,
            "kpp": local_contractor.kpp,
            "ogrn": local_contractor.ogrn,
            "address": local_contractor.address,
            "postal_address": local_contractor.postal_address,
            "org_type": local_contractor.org_type,
            "signatory": _lc_sig,
            "signatory_position": _lc_pos,
            "signatory_last_name": local_contractor.signatory_last_name,
            "signatory_first_name": local_contractor.signatory_first_name,
            "signatory_middle_name": local_contractor.signatory_middle_name,
            "signatory_basis": local_contractor.signatory_basis,
            "contact_person": local_contractor.contact_person,
            "phone": raw_phone,
            "email": local_contractor.email,
            "org_phone": local_contractor.org_phone,
            "org_email": local_contractor.org_email,
            "settlement_account": local_contractor.settlement_account,
            "bank_name": local_contractor.bank_name,
            "bik": local_contractor.bik,
            "correspondent_account": local_contractor.correspondent_account,
            "bank_details": local_contractor.bank_details,
            "_source": "local",
        }

    # FNS public API (no auth required)
    url = f"https://egrul.nalog.ru/search-result/{inn}"
    search_url = "https://egrul.nalog.ru/"

    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            # Step 1: initiate search
            resp1 = await client.post(search_url, json={"query": inn, "region": "", "page": ""})
            token = resp1.json().get("t")
            if not token:
                raise HTTPException(502, "ФНС не вернула токен поиска")

            # Step 2: get results (may need retry)
            import asyncio
            for attempt in range(5):
                await asyncio.sleep(1)
                resp2 = await client.get(f"https://egrul.nalog.ru/search-result/{token}")
                data = resp2.json()
                rows = data.get("rows", [])
                if rows:
                    break

            if not rows:
                # Самозанятых (плательщиков НПД) в ЕГРЮЛ/ЕГРИП нет вообще —
                # прежде чем сказать «не найден», спрашиваем реестр НПД.
                npd = await _check_npd_status(inn) if len(inn) == 12 else {"state": "no", "message": ""}
                if npd["state"] == "yes":
                    return {
                        "inn": inn,
                        "org_type": "Самозанятый",
                        "status": npd["message"],
                        "_source": "npd",
                        "_notice": (
                            f"ИНН {inn} — самозанятый (плательщик налога на профессиональный доход). "
                            "В ЕГРЮЛ/ЕГРИП таких записей нет, поэтому ФИО, адрес и банковские "
                            "реквизиты придётся заполнить вручную."
                        ),
                    }
                if npd["state"] == "invalid":
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "INN_NOT_FOUND",
                            "message": (
                                f"ИНН {inn} некорректен — не проходит проверку контрольной цифры ФНС. "
                                "Скорее всего, в номере опечатка."
                            ),
                            "hint": "Сверьте ИНН с документом контрагента.",
                        },
                    )
                if npd["state"] == "unknown":
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "INN_NOT_FOUND",
                            "message": (
                                f"ИНН {inn} не найден в ЕГРЮЛ/ЕГРИП. Проверить, не самозанятый ли это, "
                                f"сейчас не получилось: {npd['message']}."
                            ),
                            "hint": "Повторите попытку через минуту либо заполните карточку вручную.",
                        },
                    )
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "INN_NOT_FOUND",
                        "message": (
                            f"ИНН {inn} не найден: его нет ни в ЕГРЮЛ/ЕГРИП, ни в реестре самозанятых. "
                            "Проверьте правильность ввода."
                        ),
                        "hint": "Если организация существует, попробуйте найти её по названию или КПП.",
                    },
                )

            row = rows[0]  # first match
            # ЕГРЮЛ возвращает руководителя как "ДОЛЖНОСТЬ: ФИО"
            # (например "ПРЕДСЕДАТЕЛЬ: Девлишева Максим Махмович").
            _signatory, _signatory_position = _split_signatory(row.get("g"))
            _eg_last, _eg_first, _eg_middle, _ = split_position_and_fio(
                row.get("g"), _signatory_position
            )
            result = {
                "name": row.get("c") or row.get("n"),  # c=short name, n=full name
                "full_name": row.get("n"),              # n=full legal name
                "inn": row.get("i"),
                "ogrn": row.get("o"),
                "kpp": row.get("p"),
                "address": row.get("a"),
                # Доработка 5 мая: НЕ выставляем "Юр.лицо" по умолчанию.
                # ФНС возвращает запись и для ИП (12 цифр ИНН) и для ЮЛ (10 цифр).
                # Для 10-значного ИНН однозначно подразумевается ЮЛ → "Юр.лицо";
                # для 12-значного определяем по статусу/типу выгрузки. Если в выгрузке
                # FNS поля o/p отсутствуют (для физлиц) → не выставляем тип, пусть
                # пользователь сам выберет «Самозанятый/Физ.лицо/ИП».
                "org_type": (
                    "ИП" if len(inn) == 12 else (
                        "Юр.лицо" if row.get("o") else None
                    )
                ),
                "signatory": _signatory,  # director/head ФИО (без должности)
                "signatory_position": _signatory_position,  # должность подписанта
                "signatory_last_name": _eg_last,
                "signatory_first_name": _eg_first,
                "signatory_middle_name": _eg_middle,
                "status": row.get("s"),  # status text
                "registration_date": row.get("r"),
            }
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("FNS lookup error for INN %s: %s", inn, e)
        raise HTTPException(502, f"Ошибка запроса к ФНС: {str(e)[:200]}")


@router.post("/enrich-from-fns/{contractor_id}")
async def enrich_contractor_from_fns(
    contractor_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors')),
):
    """Fetch data from FNS by contractor's INN and fill empty fields."""
    res = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    c = res.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Контрагент не найден")
    if not c.inn:
        raise HTTPException(400, "У контрагента не заполнен ИНН")

    # Reuse lookup. Дефект (сессия 2026-09-08): `_` — результат require_tab
    # (усечённый current_user-подобный объект), позиционно попадал на
    # force_egrul: bool. Смысл эндпоинта — «дотянуться до ЕГРЮЛ/ФНС», а не
    # найти совпадение по ИНН в локальной таблице (совпало бы с самим `c` и
    # ничего не обновило бы) — поэтому force_egrul=True, db передан явно
    # (при прямом вызове функции Depends(get_db) не резолвится). current_user
    # внутри lookup_inn не используется — не прокидываем чужой объект туда,
    # где ждут bool.
    fns_data = await lookup_inn(c.inn, force_egrul=True, db=db)

    updated_fields = []
    field_map = {
        'name': 'name', 'kpp': 'kpp', 'ogrn': 'ogrn',
        'address': 'address', 'org_type': 'org_type', 'signatory': 'signatory',
    }
    for fns_field, model_field in field_map.items():
        fns_val = fns_data.get(fns_field)
        if fns_val and not getattr(c, model_field, None):
            setattr(c, model_field, fns_val)
            updated_fields.append(model_field)

    await db.commit()
    await db.refresh(c)
    return {"updated_fields": updated_fields, "contractor": ContractorOut.model_validate(c)}


@router.post("/enrich-all-fns")
async def enrich_all_contractors_from_fns(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('contractors')),
):
    """Bulk-enrich all contractors that have a Russian INN (10 or 12 digits) from FNS."""
    import asyncio
    import re
    import logging
    logger = logging.getLogger(__name__)

    result = await db.execute(select(Contractor).where(Contractor.inn.isnot(None), Contractor.inn != ""))
    contractors = result.scalars().all()

    russian_inn_re = re.compile(r"^\d{10}(\d{2})?$")
    candidates = [c for c in contractors if russian_inn_re.match((c.inn or "").strip())]

    updated_count = 0
    skipped_count = 0
    errors = []

    field_map = {
        'name': 'name', 'kpp': 'kpp', 'ogrn': 'ogrn',
        'address': 'address', 'org_type': 'org_type', 'signatory': 'signatory',
    }

    for c in candidates:
        try:
            # Тот же дефект и то же исправление, что в enrich_contractor_from_fns
            # выше: current_user попадал на force_egrul: bool.
            fns_data = await lookup_inn(c.inn.strip(), force_egrul=True, db=db)
            changed = False
            for fns_field, model_field in field_map.items():
                fns_val = fns_data.get(fns_field)
                if fns_val and not getattr(c, model_field, None):
                    setattr(c, model_field, fns_val)
                    changed = True
            if changed:
                updated_count += 1
            else:
                skipped_count += 1
        except HTTPException:
            skipped_count += 1
        except Exception as e:
            errors.append({"inn": c.inn, "error": str(e)[:100]})
            logger.warning("FNS enrich error for INN %s: %s", c.inn, e)

    await db.commit()
    return {
        "total": len(candidates),
        "updated": updated_count,
        "skipped": skipped_count,
        "errors": errors,
    }
