"""Self-service эндпоинты текущего пользователя: карточка «я» (permissions),
подпись, фото, скан водительского удостоверения, диагностика видимости.

ПЕРЕНЕСЕНО (не изменено) из app/routers/users.py при разрезании монолитного
роутера (Правило №5, сессия 2026-09-08). Тот же префикс /api/users. GET /me —
ровно один сегмент, поэтому ОБЯЗАН регистрироваться в app/routes.py ДО
users.router — иначе Starlette матчит его на литерал маршрута GET /{user_id}
раньше, чем на этот, и FastAPI падает 422 при попытке привести "me" к int.
Остальные пути здесь двухсегментные (/me/signature, /me/photo, /me/license-scan,
/me/visibility-debug) — конфликта по форме с GET /{user_id} нет, но
регистрируются рядом для единообразия.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from app.schemas.schemas import UserOut, PermissionsOut
from app.auth.permissions import get_effective_tabs
from typing import Optional

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(
    org_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Текущий пользователь. С org_id возвращает effective tabs+actions для этой орг (D-08).

    Superadmin (D-05.3) всегда получает полный набор tabs+actions, даже если у него
    нет org_id — иначе фронтенд гейтит все вкладки через authStore.hasTab() = false.
    """
    out = UserOut.model_validate(current_user)
    out.has_license_scan = bool(current_user.license_scan)
    # Rule #6: единственный резолвер должности — org_id из запроса (активная
    # орг), иначе единственное/первое членство, иначе legacy User.position.
    from app.services.user_position import resolve_user_position, bulk_load_memberships
    _memberships_map = await bulk_load_memberships(db, [current_user.id])
    out.position = resolve_user_position(
        current_user, org_id=org_id, memberships=_memberships_map.get(current_user.id)
    )
    from app.models.permission import PermissionTab, PermissionAction

    if current_user.role == "superadmin":
        # D-05.3: superadmin sees all tabs + actions, независимо от org_id
        tabs_rows = await db.execute(select(PermissionTab.tab_key))
        actions_rows = await db.execute(select(PermissionAction.action_key))
        tabs = sorted(r for r, in tabs_rows)
        actions = sorted(r for r, in actions_rows)
        out.permissions = PermissionsOut(tabs=tabs, actions=actions)
        return out

    # D-08: resolve permissions for the given org_id (or active org from JWT)
    effective_org_id = org_id or getattr(current_user, "_active_org_id", None) or current_user.org_id

    tabs_rows = await db.execute(select(PermissionTab.tab_key))
    all_tab_keys = {r for r, in tabs_rows}
    actions_rows = await db.execute(select(PermissionAction.action_key))
    all_action_keys = {r for r, in actions_rows}

    async def _resolve_for_org(target_org_id: int) -> tuple[list[str], list[str]]:
        eff = await get_effective_tabs(current_user, db, target_org_id)
        return sorted(eff & all_tab_keys), sorted(eff & all_action_keys)

    chosen_tabs: list[str] = []
    chosen_actions: list[str] = []
    chosen_org_id = effective_org_id

    if effective_org_id is not None:
        chosen_tabs, chosen_actions = await _resolve_for_org(effective_org_id)

    # Phase 30.6 fix: если НЕТ активной орг вообще (effective_org_id is None) и
    # tabs пуст — попробовать другие доступные орг и выбрать где tabs больше всего.
    # ВАЖНО (Filippov fix 2026-06): эскалация НЕ должна срабатывать при явно
    # выбранной активной орг. Иначе employee в ЦЕНТРПОИСК получает org_admin-листы
    # из ВСКС, т.к. там прав больше. Явная активная орг = строгие права этой орг.
    if not chosen_tabs and effective_org_id is None:
        from app.models.user_organization import UserOrganization
        candidate_org_ids: set[int] = set()
        try:
            res = await db.execute(
                select(UserOrganization.org_id).where(
                    UserOrganization.user_id == current_user.id
                )
            )
            candidate_org_ids.update(r[0] for r in res.all() if r[0])
        except Exception:
            pass
        # 24.06-fix: кандидаты — ТОЛЬКО орг с реальным членством. Осиротевшие UOA-орг
        # (org_admin без членства) иначе подсовывали employee admin-набор вкладок
        # (Филиппов получал admin.billing). Скоуп прав = членство, как в jwt.py.
        if current_user.org_id:
            candidate_org_ids.add(current_user.org_id)
        candidate_org_ids.discard(effective_org_id)  # уже пробовали

        best_tabs: list[str] = []
        best_actions: list[str] = []
        best_org_id: Optional[int] = None
        for cand in candidate_org_ids:
            t, a = await _resolve_for_org(cand)
            if len(t) > len(best_tabs):
                best_tabs, best_actions, best_org_id = t, a, cand
        if best_tabs:
            chosen_tabs = best_tabs
            chosen_actions = best_actions
            chosen_org_id = best_org_id

    out.permissions = PermissionsOut(tabs=chosen_tabs, actions=chosen_actions)
    # Подсказка фронту: какой org_id реально использовали (для записи в active_org_id)
    if chosen_org_id is not None and chosen_org_id != effective_org_id:
        # Дополнительное поле в response — фронт может его прочитать после json()
        out.__dict__['effective_org_id'] = chosen_org_id
    return out


# ---------------------------------------------------------------------------
# Signature (подпись пользователя)
# ---------------------------------------------------------------------------

@router.get("/me/signature")
async def get_my_signature(current_user: User = Depends(get_current_user)):
    return {"signature": current_user.signature_image}


@router.put("/me/signature")
async def save_my_signature(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sig = body.get("signature", "")
    if not sig or not sig.startswith("data:image/"):
        raise HTTPException(422, "Подпись должна быть в формате data:image/png;base64,...")
    if len(sig) > 500_000:
        raise HTTPException(422, "Подпись слишком большая (макс 500 КБ)")
    current_user.signature_image = sig
    await db.commit()
    return {"ok": True}


@router.delete("/me/signature")
async def delete_my_signature(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.signature_image = None
    await db.commit()
    return {"ok": True}


@router.get("/me/visibility-debug")
async def visibility_debug(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """27.4-11: диагностика «почему вижу X / могу Y» для current_user.

    Возвращает: JWT-источники org_id, user_organizations memberships,
    resolved org_ids фильтра, метаданные всех орг (name+inn+root+owner),
    список всех видимых субсидий с org meta, effective tabs+actions.

    Для диагностики чужих видимых субсидий — смотреть visible_subsidies[].org_id
    vs legacy_users_org_id: если совпадает → data issue (Subsidy.org_id ошибочно
    указывает на чужую org).
    """
    from app.models.organization import Organization
    from app.models.subsidy import Subsidy
    from app.models.user_organization import UserOrganization
    from app.auth.permissions import get_effective_actions, get_effective_tabs, _active_org

    jwt_org_id = getattr(current_user, '_active_org_id', None)
    jwt_org_ids = getattr(current_user, '_active_org_ids', None)
    legacy_org_id = current_user.org_id

    uo_rows = (await db.execute(
        select(UserOrganization.org_id, UserOrganization.position, UserOrganization.dept_id)
        .where(UserOrganization.user_id == current_user.id)
    )).all()

    resolved_org_ids = get_org_filter(current_user)

    all_org_ids = set()
    for v in (jwt_org_id, legacy_org_id):
        if v:
            all_org_ids.add(v)
    if jwt_org_ids:
        all_org_ids.update(jwt_org_ids)
    if resolved_org_ids:
        all_org_ids.update(resolved_org_ids)
    all_org_ids.update(r[0] for r in uo_rows if r[0])

    orgs_meta = {}
    if all_org_ids:
        rows = (await db.execute(
            select(
                Organization.id, Organization.name, Organization.inn,
                Organization.root_org_id, Organization.owner_user_id,
            ).where(Organization.id.in_(all_org_ids))
        )).all()
        orgs_meta = {
            r[0]: {"name": r[1], "inn": r[2], "root_org_id": r[3], "owner_user_id": r[4]}
            for r in rows
        }

    q = select(Subsidy.id, Subsidy.name, Subsidy.org_id).order_by(Subsidy.id)
    if resolved_org_ids is not None:
        q = q.where(Subsidy.org_id.in_(resolved_org_ids))
    visible_subs_raw = (await db.execute(q)).all()

    sub_org_ids = {s[2] for s in visible_subs_raw if s[2]}
    sub_org_meta = {}
    if sub_org_ids:
        rows = (await db.execute(
            select(Organization.id, Organization.name, Organization.inn)
            .where(Organization.id.in_(sub_org_ids))
        )).all()
        sub_org_meta = {r[0]: {"name": r[1], "inn": r[2]} for r in rows}

    visible_subsidies = [
        {
            "id": s[0],
            "name": s[1],
            "org_id": s[2],
            "org_name": sub_org_meta.get(s[2], {}).get("name") if s[2] else None,
            "org_inn": sub_org_meta.get(s[2], {}).get("inn") if s[2] else None,
        }
        for s in visible_subs_raw
    ]

    active_org = _active_org(current_user)
    tabs = await get_effective_tabs(current_user, db, active_org)
    actions = await get_effective_actions(current_user, db, active_org)

    return {
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "legacy_users_org_id": legacy_org_id,
        },
        "jwt": {
            "_active_org_id": jwt_org_id,
            "_active_org_ids": jwt_org_ids,
        },
        "user_organizations": [
            {"org_id": r[0], "position": r[1], "dept_id": r[2]} for r in uo_rows
        ],
        "resolved_org_ids_for_filter": resolved_org_ids,
        "organizations_meta": orgs_meta,
        "visible_subsidies": visible_subsidies,
        "visible_subsidies_count": len(visible_subsidies),
        "effective": {
            "tabs": sorted(tabs),
            "actions": sorted(actions),
            "purchase_status_change_granted": "purchase.status_change" in actions,
        },
    }


@router.get("/me/photo")
async def get_my_photo(current_user: User = Depends(get_current_user)):
    return {"photo_url": current_user.profile_photo}


@router.put("/me/photo")
async def save_my_photo(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = body.get("photo_url", "")
    if not photo or not photo.startswith("data:image/"):
        raise HTTPException(422, "Фото должно быть в формате data:image/...;base64,...")
    if len(photo) > 2_000_000:
        raise HTTPException(422, "Фото слишком большое (макс 2 МБ)")
    current_user.profile_photo = photo
    await db.commit()
    return {"ok": True}


@router.delete("/me/photo")
async def delete_my_photo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.profile_photo = None
    await db.commit()
    return {"ok": True}


# ── Phase 30.3: скан водительского удостоверения ──────────────────────────────
@router.get("/me/license-scan")
async def get_my_license_scan(
    current_user: User = Depends(get_current_user),
):
    return {"license_scan": current_user.license_scan}


@router.put("/me/license-scan")
async def save_my_license_scan(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scan = body.get("license_scan", "")
    if not scan or not scan.startswith("data:image/"):
        raise HTTPException(422, "Скан должен быть data:image/...;base64,...")
    if len(scan) > 3_000_000:
        raise HTTPException(422, "Скан слишком большой (макс 3 МБ)")
    current_user.license_scan = scan
    await db.commit()
    return {"ok": True}


@router.delete("/me/license-scan")
async def delete_my_license_scan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.license_scan = None
    await db.commit()
    return {"ok": True}
