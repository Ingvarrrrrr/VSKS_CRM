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
# ФОТ и иные выплаты персоналу (решение владельца 07.10.2026, план .planning/
# quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2) — четвёртая корзина, см.
# kind_of_for_category ниже.
KIND_PAYROLL = "payroll"

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


# Четыре корзины вида позиции статьи ФЭО (решение владельца 07.10.2026,
# план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2) — порядок
# фиксирован, используется везде, где нужно пройти по всем корзинам сразу
# (ПРАВИЛО №6 — единственный список, не переписывать литералом в other
# модулях).
ALL_KINDS: Tuple[str, str, str, str] = (KIND_GOODS, KIND_SERVICES, KIND_PAYROLL, KIND_UNSPECIFIED)


def empty_kind_dict() -> Dict[str, float]:
    """{goods:0.0, services:0.0, payroll:0.0, unspecified:0.0} — заготовка
    аккумулятора по всем 4 корзинам (ПРАВИЛО №6, см. ALL_KINDS)."""
    return {k: 0.0 for k in ALL_KINDS}


def collapse_kind_dict_to_payroll(values: Dict[str, float], is_payroll: bool) -> Dict[str, float]:
    """Статья ФЭО с признаком `is_payroll` (своим или ЛЮБОГО предка) — ВСЕ её
    позиции вида `payroll`, НЕЗАВИСИМО от item_type самой позиции (решение
    владельца 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-cards/
    PLAN.md шаг 2). `values` — уже посчитанный по товар/услуга/без типа
    словарь (goods/services/unspecified, payroll обычно 0 — классификатор
    item-уровня payroll не ставит); при `is_payroll=True` вся сумма трёх
    корзин переносится в payroll, goods/services/unspecified становятся 0 —
    единственное место, где категория ПЕРЕБИВАЕТ вид позиции (ПРАВИЛО №6:
    используется и для own_plan_by_kind/own_feo_by_kind этого модуля, и для
    rollup'ов over/ordered/fact/committed по категории в feo_plan_tree.py —
    второй такой свёртки не заводить)."""
    if not is_payroll:
        return {
            KIND_GOODS: values.get(KIND_GOODS, 0.0),
            KIND_SERVICES: values.get(KIND_SERVICES, 0.0),
            KIND_PAYROLL: values.get(KIND_PAYROLL, 0.0),
            KIND_UNSPECIFIED: values.get(KIND_UNSPECIFIED, 0.0),
        }
    total = sum(values.get(k, 0.0) for k in (KIND_GOODS, KIND_SERVICES, KIND_PAYROLL, KIND_UNSPECIFIED))
    return {KIND_GOODS: 0.0, KIND_SERVICES: 0.0, KIND_PAYROLL: total, KIND_UNSPECIFIED: 0.0}


def kind_of_by_category_id(item_type: Optional[str], feo_category_id, payroll_category_ids) -> str:
    """Удобная обёртка над kind_of_for_category для вызывающего кода, у
    которого есть feo_category_id позиции и ГОТОВЫЙ набор payroll-категорий
    субсидии (app.services.feo_payroll.payroll_category_ids — ЕДИНСТВЕННЫЙ
    резолвер «себя или предка», ПРАВИЛО №6). `payroll_category_ids` — любой
    контейнер, поддерживающий `in` (set/frozenset)."""
    is_payroll = feo_category_id is not None and feo_category_id in payroll_category_ids
    return kind_of_for_category(item_type, is_payroll)


def kind_of_for_category(item_type: Optional[str], category_is_payroll: bool) -> str:
    """Классификатор вида позиции статьи ФЭО (решение владельца 07.10.2026,
    план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2) — ОДИН
    классификатор для всех разбивок дерева/карточек: позиция статьи с
    `is_payroll` (у самой статьи или у ЛЮБОГО предка — вызывающий код обязан
    передать уже разрешённый inherited-флаг, см. app.services.feo_plan_tree)
    получает вид `payroll` НЕЗАВИСИМО от item_type. Второй классификатор не
    заводить — везде, где раньше звался kind_of() для позиции статьи ФЭО (не
    для «голой» закупки без категории), теперь звать эту функцию."""
    if category_is_payroll:
        return KIND_PAYROLL
    return kind_of(item_type)


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


def split_amount_by_kind_pool(amount, pool: Dict[str, float]) -> Dict[str, Decimal]:
    """Делит amount по ДОЛЯМ пула pool ({kind: вес}, напр. Σ плановых позиций
    этого типа) — обобщение split_amount_by_shares на 4 корзины, включая
    payroll (используется при распределении явного FeoCategory.budget по
    типам его плановых позиций без собственной typed-разбивки ФЭО, план
    .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2, см.
    feo_plan_tree.py::_feo_by_kind). unspecified получает 0, если хоть одна
    типизированная (goods/services/payroll) доля не нулевая — остаток
    округления уходит в самую большую типизированную часть; если все
    типизированные доли нулевые — вся сумма целиком в unspecified (как и
    раньше, старое поведение split_amount_by_shares на 2 типа)."""
    amt = Decimal(str(amount)) if amount is not None else Decimal(0)
    target = amt.quantize(_CENT, rounding=ROUND_HALF_UP)
    typed_keys = (KIND_GOODS, KIND_SERVICES, KIND_PAYROLL)
    typed_total = sum(Decimal(str(pool.get(k, 0.0) or 0.0)) for k in typed_keys)
    if typed_total <= Decimal("0.005"):
        return {KIND_GOODS: Decimal(0), KIND_SERVICES: Decimal(0), KIND_PAYROLL: Decimal(0), KIND_UNSPECIFIED: target}
    raw = {k: amt * (Decimal(str(pool.get(k, 0.0) or 0.0)) / typed_total) for k in typed_keys}
    rounded = {k: v.quantize(_CENT, rounding=ROUND_HALF_UP) for k, v in raw.items()}
    rounded[KIND_UNSPECIFIED] = Decimal(0)
    diff = target - sum(rounded.values())
    if diff != 0:
        biggest = max(typed_keys, key=lambda k: rounded[k])
        rounded[biggest] += diff
    return rounded


def sum_by_kind(rows: Iterable[Tuple[Optional[str], Optional[Decimal]]]) -> Dict[str, Decimal]:
    """{'goods': Σ, 'services': Σ, 'unspecified': Σ} по парам (item_type, amount) —
    для плановых позиций/строк ФЭО (используется расчётом контролей превышения
    по типам, раздел E плана)."""
    totals: Dict[str, Decimal] = {KIND_GOODS: Decimal(0), KIND_SERVICES: Decimal(0), KIND_UNSPECIFIED: Decimal(0)}
    for item_type, amount in rows:
        amt = Decimal(str(amount)) if amount is not None else Decimal(0)
        totals[kind_of(item_type)] += amt
    return totals
