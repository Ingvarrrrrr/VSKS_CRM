"""CRUD-ядро контрагентов: список/карточка/создание/правка/удаление.

РАЗРЕЗАНО (Правило №5, сессия 2026-09-08) из монолитного contractors.py
(1939 строк) на:
  - app/services/contractor_file_parsing.py — разбор файлов карточек
    (xlsx/xls/docx/doc/pdf) в строки, без HTTP.
  - app/services/contractor_lookup.py — _split_signatory, _check_npd_status
    (используется здесь и в contractors_lookup.py).
  - app/routers/contractors_lookup.py — GET /lookup-inn/{inn},
    POST /enrich-from-fns/{id}, POST /enrich-all-fns.
  - app/routers/contractors_enrich.py — POST /enrich-all-from-egrul,
    /enrich-from-receipts, /sync-denormalized-names.
  - app/routers/contractors_directory.py — GET /product-categories,
    /with-stats, /duplicates-by-inn (односегментные — регистрируются ДО
    этого роутера в app/routes.py, см. комментарий там).
  - app/routers/contractors_import.py — /parse-file, /import/template,
    /import/excel, /import/preview, /import/mapped.

apply_requisite_fields остаётся здесь: единственный внешний потребитель,
app/routers/organizations.py, импортирует его по прежнему пути
`from app.routers.contractors import apply_requisite_fields` — путь не
менялся, потребитель не переписывался.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy import select, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.contractor import Contractor
from app.schemas.schemas import ContractorCreate, ContractorOut
from app.auth.jwt import get_current_user, get_single_org_id
from app.auth.permissions import require_tab
from app.models.user import User
from app.services.fio import compose_fio
from app.services.contractor_lookup import _check_npd_status
from typing import List


def apply_requisite_fields(contractor: Contractor, updates: dict) -> None:
    """Задать поля контрагента из `updates` + пересобрать `signatory` из
    ФИО-частей, если они переданы.

    Правило №6: единственное место, которое одновременно проставляет поля
    контрагента и пересобирает `signatory` — используется PUT /contractors/{id}
    (update_contractor, ниже) И записью реквизитов организации при заданном
    `Organization.contractor_id` (app/routers/organizations.py::update_organization).
    Не дублировать эту логику там ещё раз — при разводе оргов/контрагентов
    именно рассинхрон таких копий и стал причиной волны Правило №6.

    `updates` — только те поля, что нужно проставить (ключи, отсутствующие в
    словаре, не трогаются — вызывающий сам решает, полная это замена или
    частичное обновление).
    """
    for k, v in updates.items():
        setattr(contractor, k, v)
    if any(updates.get(f) for f in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name')):
        contractor.signatory = compose_fio(
            updates.get('signatory_last_name', contractor.signatory_last_name),
            updates.get('signatory_first_name', contractor.signatory_first_name),
            updates.get('signatory_middle_name', contractor.signatory_middle_name),
        )


router = APIRouter(prefix="/api/contractors", tags=["contractors"])


@router.get("/", response_model=List[ContractorOut])
async def list_contractors(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    search: str = Query(None),
    limit: int = Query(200, ge=1, le=5000),
):
    q = select(Contractor)
    # Контрагенты — общий справочник юрлиц (не sensitive data). Org-фильтр
    # убран: при создании закупки/договора любой пользователь должен видеть
    # любого контрагента в autocomplete (фидбек Филиппов 01.06).
    # Раньше: org_id IN user_orgs OR org_id IS NULL → не-админы не видели
    # контрагентов привязанных к другим орг (КРАФТВЭЙ, ЛИНИЯ ГРАФИК и т.п.).
    # Приоритет: фирмы с российским ИНН (ровно 10 или 12 цифр) — выше остальных.
    # Фидбек пользователя: искать приоритетно по российским ИНН, а не все подряд.
    ru_inn_priority = case(
        (Contractor.inn.op('~')(r'^[0-9]{10}$'), 0),
        (Contractor.inn.op('~')(r'^[0-9]{12}$'), 0),
        else_=1,
    )
    if search:
        term = f"%{search}%"
        prefix = f"{search}%"
        relevance = case(
            (Contractor.name.ilike(prefix), 0),
            (Contractor.inn.ilike(prefix), 1),
            (Contractor.name.ilike(term), 2),
            else_=3,
        )
        q = q.where(or_(Contractor.name.ilike(term), Contractor.inn.ilike(term)))
        q = q.order_by(ru_inn_priority, relevance, Contractor.name)
    else:
        q = q.order_by(ru_inn_priority, Contractor.name)
    result = await db.execute(q.limit(limit))
    return result.scalars().all()


@router.get("/{cid}", response_model=ContractorOut)
async def get_contractor(
    cid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    c = await db.get(Contractor, cid)
    if not c:
        raise HTTPException(404, "Контрагент не найден")
    return c


@router.post("/{cid}/check-npd-status")
async def check_contractor_npd_status(
    cid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Точечная проверка ОДНОГО контрагента в реестре самозанятых (НПД, ФНС).

    Владелец (2026-09-04, «вторая половина правила про НДС»): «самозанятые
    не облагаются НДС» — для печати документов основание освобождения
    подставляется автоматически по Contractor.org_type == 'Самозанятый'
    (см. documents.py::_resolve_vat_exemption_basis). На боевой базе этот
    признак не проставлен НИ РАЗУ ни одному из 9229 контрагентов с
    12-значным ИНН — фактическая причина: единственное место, где вообще
    вызывается _check_npd_status, — GET /contractors/lookup-inn/{inn}, и
    только как fallback, когда ЕГРЮЛ/ЕГРИП по этому ИНН вернул ПУСТОЙ
    результат при интерактивном добавлении НОВОГО контрагента через форму
    «Добавить контрагента». Ни прямое создание (POST /), ни массовый
    импорт из Excel (import/excel, import/mapped — там org_type берётся
    как есть из файла), ни фоновые enrich-эндпоинты (enrich-all-from-egrul,
    enrich-from-fns, enrich-all-fns — они тянут данные из ЕГРЮЛ/ФНС, а не
    из реестра НПД) этот путь не вызывают. Подавляющее большинство
    контрагентов на проде заведены импортом/из чеков, а не через ту форму
    — отсюда 0 совпадений при 9229 контрагентах с 12-значным ИНН.

    Эта ручка НЕ проставляет org_type массово и не привязана к другим
    проверкам — точечно, по явному клику пользователя, для ОДНОГО
    контрагента. Владелец прямо запретил массовый UPDATE: 12-значный ИНН —
    это ещё и ИП, который может быть плательщиком НДС, автоматически
    считать всех самозанятыми нельзя.

    Переиспользует уже существующий _check_npd_status (тот же запрос к
    statusnpd.nalog.ru, что и в lookup_inn) — второго механизма проверки
    не заводим.
    """
    c = await db.get(Contractor, cid)
    if not c:
        raise HTTPException(404, "Контрагент не найден")
    inn = (c.inn or "").strip()
    if len(inn) != 12:
        raise HTTPException(
            400,
            detail={
                "code": "NPD_CHECK_REQUIRES_INN12",
                "message": "Проверка в реестре самозанятых доступна только для ИНН из 12 цифр",
                "hint": (
                    "12-значный ИНН — признак физлица (ИП или самозанятого); "
                    "у этого контрагента ИНН другой длины, реестр НПД по нему "
                    "не ищет."
                ),
            },
        )
    npd = await _check_npd_status(inn)
    if npd["state"] == "yes":
        c.org_type = "Самозанятый"
        await db.commit()
        return {
            "ok": True,
            "found": True,
            "org_type": c.org_type,
            "message": (
                "Подтверждено реестром ФНС: контрагент — самозанятый "
                "(плательщик налога на профессиональный доход). Тип "
                "организации обновлён на «Самозанятый»."
            ),
        }
    if npd["state"] == "no":
        return {
            "ok": True,
            "found": False,
            "org_type": c.org_type,
            "message": (
                "В реестре самозанятых этот ИНН не найден — статус НПД не "
                "подтверждён. Если это индивидуальный предприниматель, "
                "выберите тип «ИП» вручную; ИП плательщиком НДС может быть."
            ),
        }
    if npd["state"] == "invalid":
        raise HTTPException(
            400,
            detail={
                "code": "NPD_CHECK_INVALID_INN",
                "message": f"ИНН {inn} не проходит проверку контрольной цифры реестра ФНС",
                "hint": "Сверьте ИНН с документом контрагента — похоже, в номере опечатка.",
            },
        )
    # 'unknown' — сервис недоступен ИЛИ упёрлись в лимит запросов с одного IP
    # (см. docstring _check_npd_status). Внятный отказ, не generic-ошибка.
    raise HTTPException(
        503,
        detail={
            "code": "NPD_REGISTRY_UNAVAILABLE",
            "message": "Реестр самозанятых не ответил",
            "hint": (
                f"Сервис ФНС временно недоступен или превышен лимит запросов "
                f"с одного IP ({npd['message']}). Попробуйте повторить проверку "
                "позже."
            ),
        },
    )


@router.post("/", response_model=ContractorOut)
async def create_contractor(
    data: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('contractors')),
):
    d = data.model_dump()
    d['org_id'] = get_single_org_id(current_user) or current_user.org_id

    # phase26-oo: дедуп по ИНН — фронт-quick-add часто вызывает POST даже когда
    # контрагент уже есть в БД (race condition или забытый lookup). Возвращаем
    # существующего вместо создания дубля.
    inn = (d.get('inn') or '').strip()
    if inn:
        existing_q = await db.execute(
            select(Contractor).where(Contractor.inn == inn)
        )
        existing = existing_q.scalars().first()
        if existing:
            # Обновим пустые поля если в новом запросе они заполнены (best-effort merge)
            updated = False
            for field in ('name', 'kpp', 'ogrn', 'address', 'phone', 'email', 'signatory'):
                new_val = d.get(field)
                old_val = getattr(existing, field, None)
                if new_val and not old_val:
                    setattr(existing, field, new_val)
                    updated = True
            if updated:
                await db.commit()
                await db.refresh(existing)
            return existing

    c = Contractor(**d)
    # Пересобираем signatory из структурированных частей (только ФИО, без должности)
    if any(d.get(f) for f in ('signatory_last_name', 'signatory_first_name', 'signatory_middle_name')):
        c.signatory = compose_fio(
            d.get('signatory_last_name'),
            d.get('signatory_first_name'),
            d.get('signatory_middle_name'),
        )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.patch("/{cid}/email", response_model=ContractorOut)
async def patch_contractor_email(
    cid: int,
    email: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors')),
):
    c = (await db.execute(select(Contractor).where(Contractor.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    c.email = email
    await db.commit()
    await db.refresh(c)
    return c


@router.put("/{cid}", response_model=ContractorOut)
async def update_contractor(
    cid: int,
    data: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors'))
):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    apply_requisite_fields(c, data.model_dump())
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/bulk")
async def bulk_delete_contractors(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors'))
):
    from app.models.purchase import Purchase
    ids = payload.get("ids", [])
    if not ids:
        return {"deleted": 0, "skipped_linked": 0, "skipped_not_found": 0}

    # IDs referenced in purchases — cannot delete
    linked_result = await db.execute(
        select(Purchase.contractor_id).where(Purchase.contractor_id.in_(ids)).distinct()
    )
    linked_ids = {r[0] for r in linked_result}

    safe_ids = [i for i in ids if i not in linked_ids]

    result = await db.execute(select(Contractor).where(Contractor.id.in_(safe_ids)))
    contractors_found = result.scalars().all()
    for c in contractors_found:
        await db.delete(c)
    await db.commit()

    return {
        "deleted": len(contractors_found),
        "skipped_linked": len(linked_ids),
        "skipped_not_found": len(safe_ids) - len(contractors_found),
    }


@router.delete("/{cid}")
async def delete_contractor(
    cid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contractors'))
):
    result = await db.execute(select(Contractor).where(Contractor.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}
