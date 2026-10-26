"""SQL-сторона правила «устарела ли цена» — ОДИН источник правды вместе с
app/services/price_freshness.py::evaluate (Правило №6: не второй механизм).

evaluate() — чистая Python-функция по одному товару, используется там, где
товар уже загружен в память (карточка, старый список). stale_condition()
здесь строит ТУ ЖЕ формулу как SQL boolean-выражение — нужна продукт-поиску
(app/services/product_search.py), чтобы отфильтровать/посчитать «требует
актуализации» ОДНИМ запросом по 250+ тыс. строк, не вычитывая их в Python.

Обе формулы читают ОДНУ и ТУ ЖЕ FreshnessContext (правила + история курса
USD, грузится один раз на запрос в price_freshness.load_context) — здесь
только транслируем её в SQL, правило ttl/fx не переопределяем заново.
Эквивалентность проверена тестом backend/tests/test_product_search.py
(множество id, где is_stale по SQL == множеству id, где evaluate()
отдаёт is_stale=True, на разношёрстном наборе товаров).

ПРОИЗВОДИТЕЛЬНОСТЬ (владелец, 2026-10-26, замер на 263 тыс. товаров):
исходная версия ссылалась на коррелированный подзапрос к fx_rates
(«курс USD на дату price_updated_at или раньше») ЧЕТЫРЕ раза ТЕКСТУАЛЬНО
внутри одного CASE (IS NOT NULL / != 0 / числитель / знаменатель), а сам
этот CASE — ещё ДВАЖДЫ внутри stale_condition (IS NOT NULL / abs(...) >=
порог) — итого 8 выполнений подзапроса НА КАЖДУЮ строку products (Postgres
не кэширует повторные текстуально идентичные скалярные подзапросы сам).
GET /api/products/page раньше безусловно считал stale_total по ВСЕМУ
каталогу на каждый запрос — на 263 тыс. строк это была единственная причина
~50 секунд на запрос (при пустом результате поиска — то есть к фильтрам/
поиску это не имело отношения вообще). С 26.10.2026 этот счётчик — отдельный
GET /api/products/stale-count с TTL-кэшем (product_stale_count_cache.py), но
сам SQL здесь остаётся источником правды для НЕГО и для фильтра stale_only.
Фикс LATERAL —
`fx_base_lateral()` ниже: ОДИН LATERAL-join к fx_rates на запрос вместо
восьми подзапросов на строку (fx_rates — всего ~300 строк, сам join по
индексу (code, rate_date) дешёвый); вызывающая сторона обязана вызвать его
и добавить к своему Select ПЕРЕД тем, как звать stale_condition()/
stale_condition_for_query() — см. docstring функций ниже.
"""
from sqlalchemy import case, func, literal, cast, select, true
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import Date, Numeric

from app.models.fx_rate import FxRate
from app.models.product import Product
from app.services.price_freshness import (
    FX_SHRUNK_TTL_DAYS,
    FX_TRIGGER_PCT,
    USD_CODE,
    FreshnessContext,
)


def _base_ttl_expr(ctx: FreshnessContext) -> ColumnElement:
    """SQL-аналог price_freshness._resolve_base_ttl: приоритет
    price_ttl_days (колонка) -> category -> product_type -> item_kind ->
    default (все правила — из уже загруженного ctx.rules_by_scope, те же
    данные, что видит evaluate())."""
    def _rule_case(scope_kind: str, column):
        whens = [
            (column == key, literal(ttl))
            for (kind, key), ttl in ctx.rules_by_scope.items()
            if kind == scope_kind
        ]
        if not whens:
            return literal(None)
        return case(*whens, else_=literal(None))

    category_ttl = _rule_case("category", Product.category)
    product_type_ttl = _rule_case("product_type", Product.product_type)
    item_kind_ttl = _rule_case("item_kind", Product.item_kind)

    return func.coalesce(
        Product.price_ttl_days,
        category_ttl,
        product_type_ttl,
        item_kind_ttl,
        literal(ctx.default_ttl_days),
    )


def fx_base_lateral():
    """ОДИН LATERAL-join к fx_rates на запрос — курс USD на дату (или раньше)
    products.price_updated_at. Вызывающая сторона обязана добавить его к
    своему Select через `.outerjoin(fx_base, true())` (одна строка в
    fx_base на товар — LIMIT 1 внутри — поэтому это не умножает число строк
    результата, outerjoin на случай price_updated_at без подходящей даты
    курса), ПЕРЕД вызовом stale_condition()/_fx_change_pct_expr() —
    см. докстринг модуля, почему это важно для производительности на
    250+ тыс. товаров."""
    updated_date = cast(Product.price_updated_at, Date)
    return (
        select(FxRate.value.label("value"))
        .where(FxRate.code == USD_CODE, FxRate.rate_date <= updated_date)
        .order_by(FxRate.rate_date.desc())
        .limit(1)
        .correlate(Product)
        .lateral("fx_base")
    )


def _fx_change_pct_expr(ctx: FreshnessContext, fx_base) -> ColumnElement:
    """SQL-аналог price_freshness._usd_change_pct: latest_value — последний
    известный курс USD (ctx.fx_values[-1], тот же bisect-результат, что видит
    evaluate() — читаем из УЖЕ загруженного ctx, не из второго SELECT к
    fx_rates, иначе Python и SQL могли бы увидеть разные «последние» курсы
    при курсе, обновившемся между двумя запросами). base_value — fx_base.value,
    колонка ОДНОГО общего LATERAL-join'а (fx_base_lateral(), добавлен
    вызывающей стороной в FROM), а не повторный коррелированный подзапрос на
    каждое упоминание (было — см. докстринг модуля)."""
    if not ctx.fx_values:
        return literal(None, type_=Numeric)

    latest_value = literal(ctx.fx_values[-1], type_=Numeric)
    base_value = fx_base.c.value

    return case(
        (
            (base_value.is_not(None)) & (base_value != 0),
            (latest_value - base_value) / base_value * literal(100, type_=Numeric),
        ),
        else_=literal(None, type_=Numeric),
    )


def stale_condition(ctx: FreshnessContext, fx_base) -> ColumnElement:
    """Единое SQL boolean-выражение «товар требует актуализации» — та же
    формула, что evaluate()['is_stale']. Безопасно использовать и в WHERE
    (stale_only), и в count()/case() для stale_total. `fx_base` — alias
    LATERAL-join'а из fx_base_lateral(), ОБЯЗАН уже быть в FROM вызывающего
    Select (см. докстринги выше и модуля)."""
    base_ttl = _base_ttl_expr(ctx)
    fx_change_pct = _fx_change_pct_expr(ctx, fx_base)

    fx_triggered = fx_change_pct.is_not(None) & (func.abs(fx_change_pct) >= literal(FX_TRIGGER_PCT, type_=Numeric))
    effective_ttl = case((fx_triggered, func.least(base_ttl, literal(FX_SHRUNK_TTL_DAYS))), else_=base_ttl)

    updated_date = cast(Product.price_updated_at, Date)
    age_days = func.current_date() - updated_date  # date - date => integer days

    return (
        Product.price.is_not(None)
        & Product.price_updated_at.is_not(None)
        & (age_days > effective_ttl)
    )


def apply_stale_join(q, ctx: FreshnessContext):
    """Хелпер для вызывающей стороны (ПРАВИЛО №6 — один способ подключения
    fx_base везде, где нужен stale_condition): добавляет LATERAL-join к `q`
    и возвращает (q_с_join, stale_bool_expr). Если ctx.fx_values пуст —
    fx_base всё равно добавляется (безвредный outerjoin), чтобы сигнатура
    не менялась от наличия истории курса."""
    fx_base = fx_base_lateral()
    q = q.outerjoin(fx_base, true())
    return q, stale_condition(ctx, fx_base)
