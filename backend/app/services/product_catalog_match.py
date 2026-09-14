"""Единая точка входа для ТОЧНОГО сопоставления товара по названию (Правило №6,
владелец 2026-09-14).

Повод: импорт позиций закупки заводил ВТОРОЙ товар в каталоге вместо того,
чтобы найти уже существующий — нормализация имени перед сравнением была
неполной (обрезка пробелов по краям + lower(), без схлопывания повторяющихся
пробелов внутри строки), так что «Бензорез Champion  3.5 кВт» (двойной
пробел) и «Бензорез Champion 3.5 кВт» считались разными товарами. По базе
набралось 41 группа дублей (82 товара), у части — один экземпляр с описанием
(из ТЗ), другой пустой.

Владелец, дословно: «При точном совпадении названия загрузка ДОПОЛНЯЕТ
существующий товар, а не заводит новый. ...сопоставление предпочитает запись
с ТЗ.»

Нормализация ОДНА на весь проект (используется везде ниже): обрезка пробелов
по краям, схлопывание повторяющихся пробелов, регистр не важен. Здесь и
только здесь — точное совпадение; НИКАКОГО fuzzy (владелец уже один раз
запрещал нечёткое сравнение для дедупа каталога — оно слепляло разные товары,
д600 ≠ д500, ZenBook 14 ≠ 13, см. app/services/product_matcher.py и
text_match.py — те остаются для ИНТЕРАКТИВНОГО набора/предпросмотра с
ранжированием кандидатов, не для решения «это тот же товар или другой»).

Если каталог уже содержит несколько товаров с одинаковым нормализованным
именем (дубли, до слияния скриптом слияния дублей) — `pick_preferred`
выбирает того, у кого заполнено описание («предпочитает запись с ТЗ»);
если ни у кого описания нет — первый попавшийся (порядок не важен, они
неразличимы по этому критерию).

Используется:
  - app/services/items_import_catalog.py (_upsert_product_to_catalog,
    _save_smart_preview_to_purchase) — импорт позиций закупки;
  - app/routers/purchase_items_import.py, purchase_items_import_mapped.py —
    те же импорты, отдельные роутеры (Правило №5);
  - app/product_matcher.py (find_matching_product) — общий exact-match для
    contract_items.py/purchases.py/receipts_creation.py/products.py;
  - app/services/wish_distribution.py, app/routers/wish_convert.py — тихий
    бэкфилл product_id у легаси wish_items по точному имени.
"""
import re
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

_WS_RE = re.compile(r"\s+")


def normalize_product_name(name: Optional[str]) -> str:
    """Единая нормализация имени товара для точного сравнения: обрезка
    пробелов по краям + схлопывание повторяющихся пробелов + lower()."""
    if not name:
        return ""
    return _WS_RE.sub(" ", name.strip()).lower()


def pick_preferred(candidates: Sequence[Product]) -> Optional[Product]:
    """Из нескольких товаров с одинаковым нормализованным именем выбрать один:
    приоритет — заполненное описание («сопоставление предпочитает запись с
    ТЗ», владелец 2026-09-14); иначе — первый попавшийся."""
    if not candidates:
        return None
    for c in candidates:
        if (getattr(c, "description", None) or "").strip():
            return c
    return candidates[0]


def index_products_by_name(products: Iterable[Product]) -> dict:
    """Строит словарь normalize_product_name(name) → предпочтительный Product,
    схлопывая дубли по правилу pick_preferred. Единая точка построения
    "product_by_name"-словарей для импортов позиций закупки и бэкфилла — не
    плодить пятую копию (Правило №6)."""
    groups: dict[str, list] = {}
    for p in products:
        key = normalize_product_name(getattr(p, "name", None))
        if not key:
            continue
        groups.setdefault(key, []).append(p)
    return {key: pick_preferred(items) for key, items in groups.items()}


async def find_exact_product(
    db: AsyncSession,
    name: str,
    *,
    org_id: Optional[int] = None,
    include_org_null: bool = False,
) -> Optional[Product]:
    """Точный (НЕ fuzzy) поиск товара в каталоге по нормализованному имени.

    org_id=None (по умолчанию) — без ограничения по организации (каталог
    общий, см. project_products_catalog_shared в памяти проекта).
    org_id задан + include_org_null=False — строго эта организация (как
    раньше вело себя app/product_matcher.py::find_matching_product).
    org_id задан + include_org_null=True — эта организация ИЛИ глобальные
    записи org_id IS NULL (как строят свои product_by_name импорты позиций
    закупки).

    При нескольких дублях с одинаковым именем — pick_preferred.
    """
    norm = normalize_product_name(name)
    if not norm:
        return None
    norm_expr = func.lower(func.regexp_replace(func.trim(Product.name), r"\s+", " ", "g"))
    q = select(Product).where(norm_expr == norm)
    if org_id is not None:
        if include_org_null:
            q = q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
        else:
            q = q.where(Product.org_id == org_id)
    candidates = (await db.execute(q)).scalars().all()
    return pick_preferred(candidates)
