from fastapi import APIRouter, Depends, HTTPException, Body, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.jwt import get_current_user
from app.database import get_db
from app.services.field_registry import FIELDS, list_groups
from app.services.pivot_engine import execute_query, execute_drill
from app.services.calc_columns import apply_calc_columns
from app.services import report_excel
from app.services import report_pdf
from app.models.user import User
from datetime import datetime

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


@router.post('/export.xlsx')
async def post_export_xlsx(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Универсальный Excel-экспорт.

    body: {config: {kind, ...}, name?: str}
    """
    config = body.get('config', {})
    report_name = body.get('name', 'Отчёт')
    kind = config.get('kind', 'list')

    # Execute query
    result = await execute_query(config, user, db)
    # Apply calc/composite
    calc_specs = config.get('calc_columns', [])
    if calc_specs and result.get('rows'):
        apply_calc_columns(result['rows'], calc_specs)

    meta = {
        'org_name': 'Организация',
        'report_name': report_name,
        'kind': kind,
        'author': getattr(user, 'full_name', None) or getattr(user, 'username', None) or str(user.id),
        'generated_at': datetime.utcnow().strftime('%d.%m.%Y %H:%M'),
    }

    if kind == 'list':
        data = report_excel.export_list(result.get('rows', []), config, meta)
    elif kind == 'pivot':
        data = report_excel.export_pivot(result, config, meta)
    elif kind == 'dashboard':
        from sqlalchemy import select
        from app.models.report_config import ReportConfig
        widget_results = []
        for w in config.get('widgets', []):
            sid = w.get('source_config_id')
            if not sid:
                continue
            rc = (await db.execute(select(ReportConfig).where(ReportConfig.id == sid))).scalar_one_or_none()
            if not rc:
                continue
            sub_result = await execute_query(rc.config_json or {}, user, db)
            widget_results.append({'widget': w, 'result': sub_result})
        data = await report_excel.export_dashboard(widget_results, config, meta)
    else:
        raise HTTPException(400, 'Unknown kind')

    filename = f'{report_name}_{datetime.utcnow().strftime("%Y%m%d_%H%M")}.xlsx'
    return Response(
        content=data,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('/export.pdf')
async def post_export_pdf(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Универсальный PDF-экспорт.

    body: {config: {kind, ...}, name?: str}
    """
    config = body.get('config', {})
    report_name = body.get('name', 'Отчёт')
    kind = config.get('kind', 'list')

    # Execute query
    result = await execute_query(config, user, db)
    # Apply calc/composite
    calc_specs = config.get('calc_columns', [])
    if calc_specs and result.get('rows'):
        apply_calc_columns(result['rows'], calc_specs)

    meta = {
        'org_name': 'Организация',
        'report_name': report_name,
        'kind': kind,
        'author': getattr(user, 'full_name', None) or getattr(user, 'username', None) or str(user.id),
        'generated_at': datetime.utcnow().strftime('%d.%m.%Y %H:%M'),
    }

    if kind == 'list':
        data = report_pdf.export_list(result.get('rows', []), config, meta)
    elif kind == 'pivot':
        data = report_pdf.export_pivot(result, config, meta)
    elif kind == 'dashboard':
        from sqlalchemy import select
        from app.models.report_config import ReportConfig
        widget_results = []
        for w in config.get('widgets', []):
            sid = w.get('source_config_id')
            if not sid:
                continue
            rc = (await db.execute(select(ReportConfig).where(ReportConfig.id == sid))).scalar_one_or_none()
            if not rc:
                continue
            sub_result = await execute_query(rc.config_json or {}, user, db)
            widget_results.append({'widget': w, 'result': sub_result})
        data = await report_pdf.export_dashboard(widget_results, config, meta)
    else:
        raise HTTPException(400, 'Unknown kind')

    filename = f'{report_name}_{datetime.utcnow().strftime("%Y%m%d_%H%M")}.pdf'
    return Response(
        content=data,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
