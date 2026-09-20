"""Обновление ОДНОЙ строки закупки данными связанной позиции заявки —
единственный источник этого набора полей и алгоритма «ручная правка vs
заявка» (ПРАВИЛО №6), вынесенный из app/services/wish_distribution.py
(_sync_purchase_from_wish, одиночная закупка) — сессия 2026-09-20, задача A
(владелец, лист 2 №2 «синхронизация для нескольких закупок»).

Используется:
  - app.services.wish_distribution._sync_purchase_from_wish — заявка на ОДНУ
    закупку (обычное повторное согласование).
  - app.services.wish_multi_sync.sync_multi_purchase_from_wish — заявка,
    распределённая канбаном на НЕСКОЛЬКО закупок (раньше эта ветка вообще не
    обрабатывалась, см. докстринг wish_multi_sync.py).

Оба вызывающих места раньше держали БЫ копию этого блока — теперь ровно одна
реализация, поведение и текст сообщений идентичны для обеих веток.
"""
from app.models.purchase_item import PurchaseItem
from app.models.wish_item import WishItem

# Снимок плана (Шаг 1 «план ≠ факт»): поле с сохранённым «снимком ТЗ на момент
# переноса» — planned_* движется вместе с текущим значением ТОЛЬКО пока его не
# трогали руками в закупке (правило проекта «после согласования правят в
# закупке»). Признак ручной правки — текущее значение отличается от снимка;
# тогда поле НЕ перезаписывается из заявки (ни значение, ни сам снимок), а
# расхождение возвращается в конфликтах, чтобы фронт показал его человеку
# вместо молчаливого отката.
_TRACKED_MONEY_FIELDS = (
    ("quantity", "planned_quantity"),
    ("unit_price", "planned_unit_price"),
    ("total_price", "planned_total"),
)


def _fmt_item_amounts(qty, price, total) -> str:
    return f"{qty or 0} × {price or 0} ₽ = {float(total or 0):.2f} ₽"


def sync_purchase_item_fields_from_wish_item(pi: PurchaseItem, wi: WishItem, wish) -> dict:
    """Мутирует `pi` in-place данными `wi` (та же пара позиций уже сопоставлена
    вызывающим кодом — двухступенчато, по wish_item_id/normalize(item_name)).

    Возвращает {"changed": bool, "changed_entry": {"name","was","now"} | None,
    "conflicts": [{"name","field","in_purchase","in_wish"}, ...]}. Commit/flush
    делает вызывающий код.
    """
    from app.services.wish_access import _eff_date

    _before_qty, _before_price, _before_total = pi.quantity, pi.unit_price, pi.total_price
    _name_changed = (pi.item_name or "") != (wi.item_name or "")

    _any_field_changed = _name_changed
    conflicts: list[dict] = []
    for field, snap_field in _TRACKED_MONEY_FIELDS:
        cur_val = float(getattr(pi, field) or 0)
        snap_val = float(getattr(pi, snap_field) or 0)
        wish_val = float(getattr(wi, field) or 0)
        _manually_edited = abs(cur_val - snap_val) > 0.005
        if _manually_edited:
            if abs(cur_val - wish_val) > 0.005:
                conflicts.append({
                    "name": wi.item_name, "field": field,
                    "in_purchase": cur_val, "in_wish": wish_val,
                })
            # Не трогаем ни значение, ни снимок — ручная правка остаётся как есть.
            continue
        if abs(cur_val - wish_val) > 0.005:
            _any_field_changed = True
        setattr(pi, field, getattr(wi, field))
        setattr(pi, snap_field, getattr(wi, field))

    changed_entry = None
    if _any_field_changed:
        changed_entry = {
            "name": wi.item_name,
            "was": _fmt_item_amounts(_before_qty, _before_price, _before_total),
            "now": _fmt_item_amounts(pi.quantity, pi.unit_price, pi.total_price),
        }

    pi.item_name = wi.item_name
    pi.item_type = wi.item_type or pi.item_type
    pi.unit = wi.unit
    pi.country_origin = wi.country_origin
    pi.feo_category_id = wi.feo_category_id
    pi.feo_planned_item_id = wi.feo_planned_item_id
    pi.over_plan = getattr(wi, 'over_plan', False)
    pi.vat_rate = getattr(wi, 'vat_rate', None)
    pi.needed_date = _eff_date(wish, wi)
    # Ре-линковка (см. докстринг вызывающего кода): правка в 'draft' пересоздаёт
    # WishItem с новым id — восстанавливаем hard link на АКТУАЛЬНЫЙ id.
    pi.wish_item_id = wi.id

    return {"changed": _any_field_changed, "changed_entry": changed_entry, "conflicts": conflicts}
