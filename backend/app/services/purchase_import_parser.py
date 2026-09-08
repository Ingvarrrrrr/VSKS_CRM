"""Purchase import parsing/grouping — facade module.

Split out of the former backend/app/routers/purchase_export.py (refactor,
2026-09), and further split (refactor, 2026-09) into:
  - `purchase_import_parser_maps.py`      — column maps & label→code lookup tables
  - `purchase_import_parser_helpers.py`   — per-cell/date helpers & ФЭО-path resolution
  - `purchase_import_parser_group.py`     — `_parse_and_group` (one large function
    with no internal def-scoped stages to cut along, kept whole per ПРАВИЛО №5 —
    same treatment as `feo_plan_tree.py::compute_feo_plan_tree`) plus `load_workbook`

This module re-exports every public and private name from all three so that
existing imports (`from app.services.purchase_import_parser import
_parse_and_group, load_workbook` in `app.routers.purchase_import`) and any
test monkeypatch targets keep working unchanged — nothing else in the
codebase references these names directly (see module docstrings below for
the full grep evidence).

The imports below that are not otherwise used in this file (re, defaultdict,
datetime, Decimal, BytesIO, Any/Dict/List/Optional, HTTPException, select,
AsyncSession, the ORM models, normalize_event_name, recompute_purchase_payments,
set_item_contractor, to_decimal, normalize_feo_name, _acc_docs) are kept only
so `dir()` of this facade stays a superset of the pre-split module's — the
same re-export-everything treatment `feo_plan.py` got in the sibling ФЭО
refactor (git d0bb409).
"""
import re as _re  # noqa: F401
from collections import defaultdict  # noqa: F401
from datetime import datetime  # noqa: F401
from decimal import Decimal  # noqa: F401
from io import BytesIO  # noqa: F401
from typing import Any, Dict, List, Optional  # noqa: F401

from fastapi import HTTPException  # noqa: F401
from sqlalchemy import select  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from app.models.contractor import Contractor  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.feo_category import FeoCategory  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.purchase import Purchase  # noqa: F401
from app.models.purchase_item import PurchaseItem  # noqa: F401
from app.services.item_contractor import set_item_contractor  # noqa: F401
from app.models.subsidy import Subsidy  # noqa: F401
from app.routers.events import normalize_event_name  # noqa: F401
from app.services.purchase_payments import recompute_purchase_payments  # noqa: F401
from app.services import acceptance_docs as _acc_docs  # noqa: F401
from app.utils.numbers import to_decimal  # noqa: F401
from app.utils.text import normalize_feo_name  # noqa: F401

from app.services.purchase_import_parser_maps import (  # noqa: F401
    _COLUMN_MAP,
    _CONTRACT_TYPE_MAP,
    _ITEM_TYPE_MAP,
    _METHOD_MAP,
    _NEW_TEMPLATE_MARKER_FIELDS,
    _OLD_TEMPLATE_MARKER_FIELDS,
    _PAYMENT_BASIS_MAP,
    _PAYMENTS_COLUMN_MAP,
    _REQUIRED_FIELDS,
    _STATUS_MAP,
    _SUBSTATUS_MAP,
)
from app.services.purchase_import_parser_helpers import (  # noqa: F401
    _build_feo_index,
    _find_payments_sheet,
    _make_cell_helper,
    _norm_feo,
    _resolve_feo_levels,
    _resolve_feo_path,
    _to_dec,
    _to_date_val,
)
from app.services.purchase_import_parser_group import (  # noqa: F401
    _parse_and_group,
    load_workbook,
)
