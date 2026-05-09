from fastapi import APIRouter, Depends
from app.auth.jwt import get_current_user
from app.services.field_registry import FIELDS, list_groups
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
