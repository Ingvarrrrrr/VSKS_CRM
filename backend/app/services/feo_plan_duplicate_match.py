"""Правило сопоставления «авто-плановая позиция (дубль) → настоящая позиция
ФЭО той же субсидии» (ПРАВИЛО №6 — единственное место, которое их сравнивает).

Повод (прод, субсидия «Абхазия», id 68, 08.10.2026): заявка №67 при
превращении в закупку создавала позиции БЕЗ собственной feo_category_id →
auto_assign_planned_items (plan_autoassign.py) искала существующую плановую
позицию ТОЛЬКО внутри одной (fallback, «Не определена») категории, не находила
и заводила 186 новых auto_created FeoPlannedItem — хотя в ФЭО уже были строки
с тем же именем/суммой, просто в других категориях. План субсидии задвоился.

Используется:
- app.services.plan_autoassign.auto_assign_planned_items — ПЕРЕД заведением
  новой auto_created FeoPlannedItem пробует это правило по ВСЕЙ субсидии;
  вызывает БЕЗ allow_amount_only (только правило (а) — живой путь, дедуп
  проекта всегда точный, см. ниже);
- backend.scripts.relink_autoplan_to_feo — одноразовый скрипт перепривязки уже
  существующих дублей; вызывает с allow_amount_only=True (разовая проверенная
  владельцем ручная сверка 8 пар на проде, не автоматика).

Правило:
  (а) нормализованное имя (app.services.text_match.normalize) совпадает И
      сумма совпадает (округление до копейки) — если среди НЕ-auto позиций
      ФЭО субсидии, ещё не занятых другим дублём в этом же прогоне, такая
      ровно ОДНА;
  (б) allow_amount_only=True (правка 08.10.2026, по требованию координатора) —
      иначе совпадение ТОЛЬКО по сумме среди ещё не занятых, если ровно ОДНА.
      ОПАСНО на автомате: две разные позиции с одинаковой суммой (напр. две
      разные закупки по 100 000 ₽) склеятся без проверки имени — урок проекта
      «дедуп только точный» (feedback_dedup_exact_only). По умолчанию
      ВЫКЛЮЧЕНО (allow_amount_only=False) — живой путь auto_assign_planned_items
      не должен рисковать; скрипт relink_autoplan_to_feo включает его
      осознанно, под ручной проверкой отчёта перед --apply.
Ноль или 2+ совпадений — неоднозначно, пара не возвращается (вызывающий не
трогает дубль)."""
from typing import Optional, Sequence

from app.services.text_match import normalize


def round_amount(value) -> Optional[float]:
    """Сумма к сравнению — округление до копейки, None остаётся None."""
    if value is None:
        return None
    return round(float(value), 2)


def find_unique_feo_plan_match(
    name: Optional[str],
    amount,
    candidates: Sequence,
    claimed_ids: Optional[set] = None,
    *,
    allow_amount_only: bool = False,
) -> tuple[Optional[int], Optional[str]]:
    """candidates — объекты с атрибутами .id/.name/.amount (обычно
    FeoPlannedItem, is_active=True, auto_created=False — фильтрует вызывающий).

    allow_amount_only (по умолчанию False — см. докстринг модуля): разрешить
    правило (б), совпадение ТОЛЬКО по сумме. Живой путь
    (plan_autoassign.auto_assign_planned_items) не передаёт этот параметр —
    там только точный дедуп (а). Разовый скрипт relink_autoplan_to_feo
    передаёт True.

    Возвращает (id позиции ФЭО, способ 'name_amount'|'amount') либо
    (None, None), если пары нет или совпадение неоднозначно (0 или 2+)."""
    claimed_ids = claimed_ids or set()
    pool = [c for c in candidates if c.id not in claimed_ids]
    if not pool:
        return None, None

    norm_name = normalize(name or "")
    amt = round_amount(amount)

    if norm_name:
        by_name_amount = [
            c for c in pool
            if normalize(c.name or "") == norm_name and round_amount(c.amount) == amt
        ]
        if len(by_name_amount) == 1:
            return by_name_amount[0].id, "name_amount"
        if len(by_name_amount) > 1:
            return None, None  # неоднозначно даже по имени+сумме — не уходим в (б)

    if allow_amount_only and amt is not None:
        by_amount = [c for c in pool if round_amount(c.amount) == amt]
        if len(by_amount) == 1:
            return by_amount[0].id, "amount"

    return None, None
