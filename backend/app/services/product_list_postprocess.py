"""Постобработка СПИСКА товаров — общий хелпер для всех мест, отдающих
несколько Product целиком (GET /api/products/, GET /api/products/page), не
для карточки одного товара. Правило №6 — вынесено из app/routers/products.py,
который раньше делал это инлайном только в list_products(); /page дублировал
бы тот же код без переноса сюда.

Четыре шага, в этом порядке:
  1. скрыть контрактные цены чужих организаций (price_shared/contour);
  2. price_freshness (app/services/price_freshness.py::evaluate, контекст
     правил+курса грузится один раз на запрос);
  3. characteristics — обнулить (JSONB может быть тяжёлым, список его не
     показывает, см. app/routers/products.py docstring);
  4. средняя цена (_attach_price_stats) — по региону ТЕКУЩЕЙ организации
     пользователя, партия 1-9 (план clever-bouncing-lantern.md п.7).
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.auth.jwt import get_single_org_id
from app.models.organization import Organization
from app.models.user import User
from app.services.price_freshness import load_context as load_freshness_context, evaluate as evaluate_freshness
from app.services.product_price_stats import compute_price_stats_bulk


async def attach_price_stats(
    db: AsyncSession, products: list,
    *, target_region: Optional[str] = None, quantity=None,
) -> None:
    """Проставляет avg_price/avg_price_basis/avg_price_stale (+avg_price_level/
    avg_price_region/avg_price_batch) ОДНИМ запросом на весь список
    (app.services.product_price_stats.compute_price_stats_bulk) — не N+1.
    Используется и списком (с target_region/quantity — средняя по региону и
    партии 1-9 текущей организации), и карточкой товара (список из одного,
    без фильтра)."""
    ids = [p.id for p in products]
    stats_by_id = await compute_price_stats_bulk(
        db, ids, target_region=target_region, quantity=quantity,
    )
    for p in products:
        stats = stats_by_id.get(p.id)
        if stats is not None:
            p.avg_price = stats.avg_price
            p.avg_price_basis = stats.basis_count
            p.avg_price_stale = stats.stale
            p.avg_price_level = stats.level
            p.avg_price_region = stats.region_used
            p.avg_price_batch = stats.batch


async def _hide_foreign_contract_prices(db: AsyncSession, products: list, current_user: User) -> None:
    # Хозяин аккаунта = суперадмин в своём аккаунте (владелец, 16.10.2026) —
    # контрактная цена своей же орги для него не «чужая». ИСПРАВЛЕНИЕ К1
    # (QA-итерация 2, 19.10.2026): account_owner раньше обходил скрытие
    # БЕЗУСЛОВНО (каталог товаров общий — project_products_catalog_shared) —
    # теперь только для орг своего аккаунта (та же проверка, что у
    # app.routers.external_drivers.py::_check_visibility — is_org_in_owner_account).
    if current_user.role == "superadmin":
        return
    contour_org_ids = None
    if current_user.role == "account_owner":
        from app.auth.visibility import get_account_contour_org_ids
        contour_org_ids = await get_account_contour_org_ids(current_user, db)
    user_org_id = current_user.org_id
    for p in products:
        if not p.contract_org_id or p.price_shared:
            continue
        if p.contract_org_id == user_org_id:
            continue
        if contour_org_ids is not None and p.contract_org_id in contour_org_ids:
            continue
        p.contract_price = None
        p.contract_number = None
        p.contract_date = None
        p.contract_org_id = None


async def postprocess_catalog_list(db: AsyncSession, products: list, current_user: User) -> None:
    """Единая постобработка результата списка каталога — см. докстринг
    модуля. Вызывается ПОСЛЕ того, как products выбраны из БД (с
    defer(Product.characteristics), иначе шаг 3 ниже не нужен бы)."""
    await _hide_foreign_contract_prices(db, products, current_user)

    # Актуализация цены (владелец, 2026-08-29): контекст правил + курс USD
    # грузится ОДИН раз на весь список, не в цикле по товарам.
    org_id = get_single_org_id(current_user)
    freshness_ctx = await load_freshness_context(db, org_id)
    for p in products:
        p.price_freshness = evaluate_freshness(p, freshness_ctx)
        # characteristics не загружено (defer в запросе) — явно выставляем
        # None, а не читаем атрибут: чтение недогруженной deferred-колонки
        # внутри async ORM без await лезет за ней в БД и роняет сериализацию.
        # set_committed_value (не обычное присваивание!) — иначе объект
        # помечается dirty и autoflush перед следующим запросом (напр.
        # attach_price_stats) шлёт UPDATE products SET characteristics=NULL
        # на каждый товар из списка (53 тыс. на проде).
        set_committed_value(p, "characteristics", None)

    # Список «Товары»: средняя для партии 1-9 по региону ТЕКУЩЕЙ организации
    # пользователя (план clever-bouncing-lantern.md п.7) — тот же порядок
    # поиска уровней, что и везде (compute_price_stats), нет данных по
    # региону → функция сама откатится на более общий уровень/"all".
    org_region = None
    if org_id is not None:
        org_region = (await db.execute(
            select(Organization.region).where(Organization.id == org_id)
        )).scalar_one_or_none()
    await attach_price_stats(db, products, target_region=org_region, quantity=1)
