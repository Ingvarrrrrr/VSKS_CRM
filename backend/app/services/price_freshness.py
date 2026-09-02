"""Единственный источник правды: устарела ли цена товара — владелец, 2026-08-29.

Владелец: «цена может быть уже неактуальна... срок актуальности РАЗНЫЙ для
разных видов товаров: бытовые — до 2 месяцев, продукты питания — около
2 недель... доп. критерий — курс доллара: если USD/RUB изменился более
чем на 10%, срок актуальности сокращается до месяца, и пользователю надо
явно сказать, что цену надо пересмотреть с поправкой на изменение курса».

load_context() грузит правила + ВСЮ историю курса USD (fx_rates) ОДИН раз на
запрос (не в цикле по товарам — см. вызовы в app/routers/products.py).
evaluate() — чистая синхронная функция без I/O: расчёт «курс на дату ≤ X»
идёт через bisect по уже загруженному в память отсортированному списку дат
(ревью 2026-08-29: раньше evaluate() была async и каждый уникальный
price_updated_at стоил 2 SELECT — на каталоге ~950 товаров это до ~1900
запросов на один GET /api/products/).

Контракт evaluate() (JSON-форма — см. PriceFreshnessOut в
app/schemas/schemas.py) менять нельзя без согласования с фронтом:
    {
      "is_stale": bool,
      "age_days": int | None,
      "ttl_days": int,
      "base_ttl_days": int,
      "reason": "ok" | "never" | "expired" | "fx",
      "fx_change_pct": float | None,
      "label": str,
    }

Владелец, 2026-08-29: "дата неизвесна" — оставить серым. reason="never"
(дата актуализации не указана вообще) — нейтральное состояние, is_stale
ВСЕГДА False для него и подсветкой/оранжевым не считается. is_stale=True
означает именно «просрочено по сроку (expired) или по курсу (fx)» — только
эти два reason должны красить UI оранжевым.

Владелец, 2026-08-30: жалоба на текст label для reason="fx" — старая
формулировка не называла базовый срок (60 дн.) и период, за который двигался
курс, и писала «требуется» там, где порог 10% — лишь умолчание (значит
«может потребоваться»). Процент изменения курса всегда считается ровно от
даты актуализации цены до последнего известного курса — то есть период
сдвига курса равен возрасту цены (age_days), это явно проговаривается в
тексте. Актуальные формы label по reason:
  - "ok" без курсового сдвига: "Цена актуальна"
  - "ok" с курсовым сдвигом ≥10% (срок ещё не истёк даже сжатый):
    "Цена актуальна, но за {age_days} дн. курс доллара изменился на {±X.X}% —
    стоит перепроверить."
  - "never": "Дата актуализации цены не указана"
  - "expired": "Цена от {ДД.ММ.ГГГГ} — ей уже {age_days} дн., а актуальной
    для этого товара считается {ttl_days} дн. Пора обновить."
  - "fx": "Цена от {ДД.ММ.ГГГГ} — ей {age_days} дн., по сроку ещё годится
    (актуальной считается {base_ttl_days} дн.). Но за эти {age_days} дн.
    курс доллара изменился на {±X.X}% — цену стоит перепроверить."

Владелец, 2026-08-30 (2): текст label для "expired"/"fx" был канцеляритом
(«при сроке N дн.» не объясняет пользователю, что за число N). Переписано
живым языком без слов «срок актуальности», «при сроке», «требуется
актуализация» — используются «пора обновить» / «стоит перепроверить».
"""
import bisect
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fx_rate import FxRate
from app.models.price_freshness_rule import PriceFreshnessRule

DEFAULT_TTL_DAYS = 60
FX_TRIGGER_PCT = 10.0      # порог изменения курса USD/RUB
FX_SHRUNK_TTL_DAYS = 30    # срок при сработавшем курсовом триггере
USD_CODE = "USD"


@dataclass
class FreshnessContext:
    """Загружается один раз на запрос — правила орги и вся история курса USD
    не гоняются по одному запросу на каждый товар."""
    rules_by_scope: dict  # (scope_kind, scope_key) -> ttl_days ; org-override побеждает global
    default_ttl_days: int
    # История курса USD, отсортированная по дате по возрастанию — параллельные
    # списки для bisect (см. _usd_change_pct). Пустые списки, если fx_rates
    # ещё не наполнена (backfill/refresh не отработали — см. app/__init__.py).
    fx_dates: list = field(default_factory=list)
    fx_values: list = field(default_factory=list)


async def load_context(db: AsyncSession, org_id: Optional[int]) -> FreshnessContext:
    """Грузит применимые правила (глобальные org_id IS NULL + org_id текущей орги)
    И всю историю курса USD — каждое ОДИН раз. org-override побеждает global
    при совпадении (scope_kind, scope_key)."""
    q = select(PriceFreshnessRule)
    if org_id is not None:
        q = q.where(
            (PriceFreshnessRule.org_id.is_(None)) | (PriceFreshnessRule.org_id == org_id)
        )
    else:
        q = q.where(PriceFreshnessRule.org_id.is_(None))
    rows = (await db.execute(q)).scalars().all()

    rules_by_scope: dict = {}
    # Сначала глобальные, затем org — org перезаписывает global для того же ключа.
    for r in sorted(rows, key=lambda r: r.org_id is not None):
        rules_by_scope[(r.scope_kind, r.scope_key)] = r.ttl_days

    default_ttl = rules_by_scope.get(("default", "*"), DEFAULT_TTL_DAYS)

    fx_rows = (await db.execute(
        select(FxRate.rate_date, FxRate.value)
        .where(FxRate.code == USD_CODE)
        .order_by(FxRate.rate_date.asc())
    )).all()
    fx_dates = [r[0] for r in fx_rows]
    fx_values = [Decimal(r[1]) for r in fx_rows]

    return FreshnessContext(
        rules_by_scope=rules_by_scope,
        default_ttl_days=default_ttl,
        fx_dates=fx_dates,
        fx_values=fx_values,
    )


def _usd_change_pct(ctx: FreshnessContext, since_date: date) -> Optional[float]:
    """Процентное изменение последнего известного курса USD относительно
    курса на since_date — bisect по in-memory серии, без I/O. Возвращает
    None если истории нет вообще, либо самая ранняя известная дата курса
    ПОЗЖЕ since_date (нет базы для сравнения)."""
    if not ctx.fx_dates:
        return None
    latest_value = ctx.fx_values[-1]
    idx = bisect.bisect_right(ctx.fx_dates, since_date) - 1
    if idx < 0:
        return None  # самая ранняя известная дата курса позже since_date
    base_value = ctx.fx_values[idx]
    if base_value == 0:
        return None
    pct = (latest_value - base_value) / base_value * Decimal(100)
    return float(pct)


def _resolve_base_ttl(product, ctx: FreshnessContext) -> int:
    """Приоритет: product.price_ttl_days -> category -> product_type -> item_kind -> default."""
    if getattr(product, "price_ttl_days", None):
        return int(product.price_ttl_days)
    category = getattr(product, "category", None)
    if category and ("category", category) in ctx.rules_by_scope:
        return ctx.rules_by_scope[("category", category)]
    product_type = getattr(product, "product_type", None)
    if product_type and ("product_type", product_type) in ctx.rules_by_scope:
        return ctx.rules_by_scope[("product_type", product_type)]
    item_kind = getattr(product, "item_kind", None)
    if item_kind and ("item_kind", item_kind) in ctx.rules_by_scope:
        return ctx.rules_by_scope[("item_kind", item_kind)]
    return ctx.default_ttl_days


def _label(
    reason: str,
    age_days: Optional[int],
    ttl_days: int,
    fx_change_pct: Optional[float],
    base_ttl_days: int,
    updated_date: Optional[date],
) -> str:
    if reason == "ok":
        base = "Цена актуальна"
        # Курс уже сдвинулся ≥ порога, но сжатый срок ещё не истёк — предупреждаем
        # заранее, не дожидаясь reason='fx' (владелец, 2026-08-30).
        if age_days is not None and fx_change_pct is not None and abs(fx_change_pct) >= FX_TRIGGER_PCT:
            fx_txt = f"{fx_change_pct:+.1f}%"
            return (
                f"Цена актуальна, но за {age_days} дн. курс доллара изменился на "
                f"{fx_txt} — стоит перепроверить."
            )
        return base
    if reason == "never":
        return "Дата актуализации цены не указана"
    date_txt = updated_date.strftime("%d.%m.%Y") if updated_date else "неизвестно"
    if reason == "fx":
        fx_txt = f"{fx_change_pct:+.1f}%" if fx_change_pct is not None else "существенно"
        return (
            f"Цена от {date_txt} — ей {age_days} дн., по сроку ещё годится "
            f"(актуальной считается {base_ttl_days} дн.). Но за эти {age_days} дн. "
            f"курс доллара изменился на {fx_txt} — цену стоит перепроверить."
        )
    # expired
    return (
        f"Цена от {date_txt} — ей уже {age_days} дн., а актуальной для этого товара "
        f"считается {ttl_days} дн. Пора обновить."
    )


def evaluate(product, ctx: FreshnessContext) -> dict:
    """Возвращает контракт PriceFreshnessOut (см. докстринг модуля).

    Синхронная и чистая (без I/O) — вся нужная история (правила + курс USD)
    уже загружена в ctx через load_context(). Безопасно звать в цикле по
    списку товаров.
    """
    price = getattr(product, "price", None)
    if price is None:
        return {
            "is_stale": False,
            "age_days": None,
            "ttl_days": ctx.default_ttl_days,
            "base_ttl_days": ctx.default_ttl_days,
            "reason": "ok",
            "fx_change_pct": None,
            "label": "Цена не задана",
        }

    price_updated_at = getattr(product, "price_updated_at", None)
    base_ttl_days = _resolve_base_ttl(product, ctx)

    if price_updated_at is None:
        return {
            "is_stale": False,
            "age_days": None,
            "ttl_days": base_ttl_days,
            "base_ttl_days": base_ttl_days,
            "reason": "never",
            "fx_change_pct": None,
            "label": _label("never", None, base_ttl_days, None, base_ttl_days, None),
        }

    updated_date = price_updated_at.date() if isinstance(price_updated_at, datetime) else price_updated_at
    today = datetime.utcnow().date()
    age_days = (today - updated_date).days

    fx_change_pct = _usd_change_pct(ctx, updated_date)

    fx_triggered = fx_change_pct is not None and abs(fx_change_pct) >= FX_TRIGGER_PCT
    effective_ttl = min(base_ttl_days, FX_SHRUNK_TTL_DAYS) if fx_triggered else base_ttl_days

    is_stale = age_days > effective_ttl
    if is_stale:
        reason = "fx" if fx_triggered else "expired"
    else:
        reason = "ok"

    return {
        "is_stale": is_stale,
        "age_days": age_days,
        "ttl_days": effective_ttl,
        "base_ttl_days": base_ttl_days,
        "reason": reason,
        "fx_change_pct": fx_change_pct,
        "label": _label(reason, age_days, effective_ttl, fx_change_pct, base_ttl_days, updated_date),
    }
