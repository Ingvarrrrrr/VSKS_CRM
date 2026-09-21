"""Правило А (план ancient-prancing-music.md, раздел A) — единственный источник
правила «тип позиции → товары/услуги» и общих формул деления сумм по типу
(Правило №6 проекта: одна формула — один источник, никаких вторых копий).

Решение владельца (21.09): работы считаются услугами; пустой/непонятный тип —
отдельная корзина «без типа», её НЕЛЬЗЯ молча приписывать к товарам.

Нормализация свободного текста типа ("Товар", " услуга ", "работы" и т.п.) не
дублируется — берётся из normalize_item_type() (app/routers/feo_planned_items.py,
уже единственный источник нормализации для FeoPlannedItem/импорта ФЭО, см.
services/feo_import_apply.py:34, тот же импорт без цикла). kind_of() здесь лишь
переводит её результат («товар»/«услуга»/«работа»/None) в одну из трёх
канонических корзин, которыми пользуются деньги: payment_target.py,
payment_lookup.py, дашборд (B), дерево ФЭО и контроли превышения по типам (E).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, Optional, Tuple

from app.routers.feo_planned_items import normalize_item_type

KIND_GOODS = "goods"
KIND_SERVICES = "services"
KIND_UNSPECIFIED = "unspecified"

_CENT = Decimal("0.01")


def kind_of(item_type: Optional[str]) -> str:
    """«товар» → goods; «услуга»/«работа» → services; пусто/непонятное → unspecified.

    Единственное место в проекте, где этот выбор делается — все контроли/суммы
    по типу обязаны звать эту функцию, а не заново разбирать item_type."""
    normalized = normalize_item_type(item_type)
    if normalized == "товар":
        return KIND_GOODS
    if normalized in ("услуга", "работа"):
        return KIND_SERVICES
    return KIND_UNSPECIFIED


@dataclass
class TypeShares:
    """Доли (0..1), goods + services + unspecified == 1 РОВНО (unspecified —
    остаток, а не отдельное деление, иначе Decimal-деление на 3 части могло бы
    не досчитаться до 1 из-за конечной точности)."""
    goods: Decimal
    services: Decimal
    unspecified: Decimal


def purchase_type_shares(items: Iterable) -> TypeShares:
    """Доли по Σ total_price позиций закупки (или любых объектов с полями
    item_type/total_price — плановых позиций и т.п.). Позиция без total_price
    считается 0. Нет позиций или Σ == 0 → всё «без типа» (закупку без позиций
    или с нулевыми суммами нельзя молча приписать к товарам)."""
    totals: Dict[str, Decimal] = {KIND_GOODS: Decimal(0), KIND_SERVICES: Decimal(0), KIND_UNSPECIFIED: Decimal(0)}
    for it in items:
        raw_amount = getattr(it, "total_price", None)
        amt = Decimal(str(raw_amount)) if raw_amount is not None else Decimal(0)
        totals[kind_of(getattr(it, "item_type", None))] += amt

    total = totals[KIND_GOODS] + totals[KIND_SERVICES] + totals[KIND_UNSPECIFIED]
    if total == 0:
        return TypeShares(goods=Decimal(0), services=Decimal(0), unspecified=Decimal(1))

    goods_share = totals[KIND_GOODS] / total
    services_share = totals[KIND_SERVICES] / total
    # unspecified — остаток, чтобы сумма долей была ровно 1 (см. докстринг TypeShares).
    unspecified_share = Decimal(1) - goods_share - services_share
    return TypeShares(goods=goods_share, services=services_share, unspecified=unspecified_share)


def split_amount_by_shares(amount, shares: TypeShares) -> Tuple[Decimal, Decimal, Decimal]:
    """Делит amount на (goods, services, unspecified) по долям, с округлением до
    копеек так, чтобы сумма трёх частей была РОВНО amount. Остаток округления
    уходит в самую большую из трёх частей (а не в фиксированный порядок) —
    иначе на маленьких суммах остаток может достаться доле, которая должна
    была быть нулевой."""
    amt = Decimal(str(amount)) if amount is not None else Decimal(0)
    raw = {
        KIND_GOODS: amt * shares.goods,
        KIND_SERVICES: amt * shares.services,
        KIND_UNSPECIFIED: amt * shares.unspecified,
    }
    rounded = {k: v.quantize(_CENT, rounding=ROUND_HALF_UP) for k, v in raw.items()}
    target = amt.quantize(_CENT, rounding=ROUND_HALF_UP)
    diff = target - sum(rounded.values())
    if diff != 0:
        biggest = max(rounded, key=lambda k: rounded[k])
        rounded[biggest] += diff
    return rounded[KIND_GOODS], rounded[KIND_SERVICES], rounded[KIND_UNSPECIFIED]


def sum_by_kind(rows: Iterable[Tuple[Optional[str], Optional[Decimal]]]) -> Dict[str, Decimal]:
    """{'goods': Σ, 'services': Σ, 'unspecified': Σ} по парам (item_type, amount) —
    для плановых позиций/строк ФЭО (используется расчётом контролей превышения
    по типам, раздел E плана)."""
    totals: Dict[str, Decimal] = {KIND_GOODS: Decimal(0), KIND_SERVICES: Decimal(0), KIND_UNSPECIFIED: Decimal(0)}
    for item_type, amount in rows:
        amt = Decimal(str(amount)) if amount is not None else Decimal(0)
        totals[kind_of(item_type)] += amt
    return totals
