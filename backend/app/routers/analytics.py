from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.jwt import get_current_user
from app.database import get_db
from app.services.field_registry import FIELDS, list_groups
from app.services.pivot_engine import execute_query, execute_drill
from app.services.calc_columns import apply_calc_columns
from app.models.user import User

router = APIRouter(prefix='/api/analytics', tags=['analytics'])


@router.get('/fields')
async def get_fields(user: User = Depends(get_current_user)):
    """Каталог всех доступных полей для UI-конфигуратора отчётов."""
    return {
        'groups': list_groups(),
        'fields': [
            {
                'key': f.key,
                'label': f.label,
                'type': f.type,
                'source': f.source,
                'group': f.group,
                'format': f.format,
                'agg_default': f.agg_default,
                'is_dimension': f.is_dimension,
                'is_measure': f.is_measure,
                'drillable': f.drillable,
                'enum_values': f.enum_values,
                'description': f.description,
            }
            for f in FIELDS.values()
        ],
    }


@router.post('/query')
async def post_query(
    config: dict = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Universal query endpoint для list и pivot."""
    try:
        result = await execute_query(config, user, db)
        calc_specs = config.get('calc_columns', [])
        if calc_specs and result.get('rows'):
            apply_calc_columns(result['rows'], calc_specs)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail={'code': 'INVALID_CONFIG', 'message': str(e)})
    except Exception as e:
        import logging
        logging.exception('analytics/query failed')
        raise HTTPException(status_code=500, detail={'code': 'QUERY_FAILED', 'message': str(e)})


@router.post('/drill')
async def post_drill(
    payload: dict = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Drill-down: получает {config, dimension_values} → плоский список Purchase для пересечения."""
    config = payload.get('config', {})
    dim_vals = payload.get('dimension_values', {})
    try:
        return await execute_drill(config, dim_vals, user, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={'code': 'INVALID_CONFIG', 'message': str(e)})
    except Exception as e:
        import logging
        logging.exception('analytics/drill failed')
        raise HTTPException(status_code=500, detail={'code': 'DRILL_FAILED', 'message': str(e)})
