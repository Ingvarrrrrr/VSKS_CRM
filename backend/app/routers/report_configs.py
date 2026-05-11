from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.database import get_db
from app.auth.jwt import get_current_user, get_single_org_id
from app.auth.permissions import require_action
from app.models.report_config import ReportConfig
from app.models.user import User
from app.schemas.schemas import ReportConfigCreate, ReportConfigUpdate, ReportConfigOut
from app.services.pivot_engine import execute_query
from app.services.calc_columns import apply_calc_columns

router = APIRouter(prefix='/api/report-configs', tags=['report-configs'])


def _get_user_active_org_id(user: User) -> Optional[int]:
    """Возвращает текущую active org для сохранения шаблона.

    Использует get_single_org_id-паттерн из jwt.py:
    - superadmin → первая выбранная org из _active_org_ids
    - все остальные → _active_org_id или org_id (primary)
    """
    return get_single_org_id(user)


@router.get('/', response_model=List[ReportConfigOut])
async def list_configs(
    kind: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список сохранённых шаблонов в активной организации пользователя.

    Возвращает все is_shared=true + свои is_shared=false."""
    org_id = _get_user_active_org_id(user)
    if not org_id:
        return []

    q = select(ReportConfig).where(ReportConfig.org_id == org_id)
    if kind:
        q = q.where(ReportConfig.kind == kind)
    # Фильтр: shared OR own
    q = q.where(
        (ReportConfig.is_shared == True) | (ReportConfig.created_by_id == user.id)
    ).order_by(ReportConfig.kind, ReportConfig.is_default.desc(), ReportConfig.name)

    rows = (await db.execute(q)).scalars().all()
    return list(rows)


@router.get('/{config_id}', response_model=ReportConfigOut)
async def get_config(
    config_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = _get_user_active_org_id(user)
    rc = (await db.execute(select(ReportConfig).where(ReportConfig.id == config_id))).scalar_one_or_none()
    if not rc or rc.org_id != org_id:
        raise HTTPException(404, 'Шаблон не найден')
    if not rc.is_shared and rc.created_by_id != user.id:
        raise HTTPException(403, 'Шаблон не публичный')
    return rc


@router.post('/', response_model=ReportConfigOut)
async def create_config(
    payload: ReportConfigCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_action('report_config.edit')),
):
    org_id = _get_user_active_org_id(user)
    if not org_id:
        raise HTTPException(400, 'Нет активной организации')
    rc = ReportConfig(
        org_id=org_id,
        kind=payload.kind,
        name=payload.name,
        description=payload.description,
        config_json=payload.config_json,
        parameters_json=payload.parameters_json,
        created_by_id=user.id,
        is_default=payload.is_default,
        is_shared=payload.is_shared,
    )
    db.add(rc)
    try:
        await db.commit()
        await db.refresh(rc)
    except Exception as e:
        await db.rollback()
        msg = str(e).lower()
        if 'unique' in msg or 'duplicate' in msg:
            raise HTTPException(409, f'Шаблон "{payload.name}" уже существует')
        raise HTTPException(500, str(e))
    return rc


@router.put('/{config_id}', response_model=ReportConfigOut)
async def update_config(
    config_id: int,
    payload: ReportConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_action('report_config.edit')),
):
    org_id = _get_user_active_org_id(user)
    rc = (await db.execute(select(ReportConfig).where(ReportConfig.id == config_id))).scalar_one_or_none()
    if not rc or rc.org_id != org_id:
        raise HTTPException(404, 'Шаблон не найден')
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rc, field, value)
    await db.commit()
    await db.refresh(rc)
    return rc


@router.delete('/{config_id}')
async def delete_config(
    config_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_action('report_config.edit')),
):
    org_id = _get_user_active_org_id(user)
    rc = (await db.execute(select(ReportConfig).where(ReportConfig.id == config_id))).scalar_one_or_none()
    if not rc or rc.org_id != org_id:
        raise HTTPException(404, 'Шаблон не найден')
    await db.execute(delete(ReportConfig).where(ReportConfig.id == config_id))
    await db.commit()
    return {'deleted': config_id}


@router.post('/{config_id}/run')
async def run_config(
    config_id: int,
    params: Optional[dict] = Body(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Запуск сохранённого шаблона с параметрами. Возвращает результат query.

    params: {param_key: value} — подставляется в config_json.filters перед вызовом execute_query."""
    org_id = _get_user_active_org_id(user)
    rc = (await db.execute(select(ReportConfig).where(ReportConfig.id == config_id))).scalar_one_or_none()
    if not rc or rc.org_id != org_id:
        raise HTTPException(404, 'Шаблон не найден')

    config = dict(rc.config_json or {})
    # Подстановка параметров в filters
    filters = dict(config.get('filters', {}))
    if params:
        for pdef in (rc.parameters_json or []):
            pkey = pdef.get('key')
            if pkey and pkey in params:
                filters[pkey] = params[pkey]
    config['filters'] = filters

    result = await execute_query(config, user, db)
    calc_specs = config.get('calc_columns', [])
    if calc_specs and result.get('rows'):
        apply_calc_columns(result['rows'], calc_specs)

    return result
