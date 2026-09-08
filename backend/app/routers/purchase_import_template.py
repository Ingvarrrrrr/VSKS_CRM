"""Purchase import-template router.

Handles:
  GET  /api/purchases/import/template  — download blank import template
                                          (single «Закупки» sheet + «Справочники»
                                          + «Справочник колонок», inline payments;
                                          adds cascading ФЭО Ур.1..5 dropdowns
                                          when a subsidy_id is given)

Split out of purchase_export.py (refactor, 2026-09). Keeps the same
`router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])` as
the original module so the OpenAPI schema is unchanged.

Refactor 2026-09 (Правило №5): the column spec / dropdown sets / example
rows / xlsx-building logic that used to live in this file (~1700 lines) now
live in dedicated services:
  - app.services.import_template_spec       (_COL_SPEC)
  - app.services.import_template_dropdowns  (_DD_* lists)
  - app.services.import_template_examples   (_TEMPLATE_EXAMPLE_ROW*)
  - app.services.import_template_builder    (_build_dv_prompt + workbook build)
This router only does auth/visibility checks and streams the result. The
names below are re-exported for backward compatibility with any code that
imported them from this module directly.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import get_current_user
from app.auth.visibility import get_visible_subsidy_ids

# Re-exports for backward compatibility with any code importing these names
# directly from this module (historical location before the 2026-09 split).
from app.services.import_template_builder import (  # noqa: F401
    Workbook,
    DataValidation,
    DefinedName,
    _build_dv_prompt,
    build_purchase_import_template_workbook,
)
from app.services.import_template_spec import _COL_SPEC  # noqa: F401
from app.services.import_template_examples import (  # noqa: F401
    _TEMPLATE_EXAMPLE_ROW,
    _TEMPLATE_EXAMPLE_ROW_2,
)
from app.services.import_template_dropdowns import (  # noqa: F401
    _DD_CONTRACT_TYPE,
    _DD_STATUS,
    _DD_SUBSTATUS,
    _DD_METHOD,
    _DD_BASIS,
    _DD_VAT_APPLICABLE,
    _DD_VAT_RATE,
    _DD_PREPAYMENT,
    _DD_MONTHLY,
    _DD_ITEM_TYPE,
    _DD_PAYMENT_BASIS,
    _DD_UNIT,
    _DD_QUARTER,
    _DD_VAT_MODE,
    _DD_DELIVERY_REGION,
    _DD_EVENT_REGION,
)

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])


@router.get("/import/template")
async def download_import_template(
    subsidy_id: Optional[int] = Query(None, description="ID субсидии для каскадных ФЭО-списков"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скачать шаблон Excel для импорта закупок (лист «Закупки» + «Справочники» + «Справочник колонок»).
    При subsidy_id — добавляет дерево ФЭО субсидии с выпадающими списками на листе «Закупки»."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    # Проверяем доступ к субсидии, если она указана
    if subsidy_id is not None:
        vis = await get_visible_subsidy_ids(current_user, db, "purchases")
        if vis is not None and subsidy_id not in vis:
            raise HTTPException(
                403,
                f"Субсидия #{subsidy_id} вам недоступна или не существует. "
                "Проверьте права доступа к субсидии."
            )

    subsidy_name: Optional[str] = None
    if subsidy_id is not None:
        subsidy_name = (await db.execute(select(Subsidy.name).where(Subsidy.id == subsidy_id))).scalar_one_or_none()

    wb = await build_purchase_import_template_workbook(db, subsidy_id, subsidy_name)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('Шаблон_импорта_закупок.xlsx', safe='-_.~')}"}
    )
