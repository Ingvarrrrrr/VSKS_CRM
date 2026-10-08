# -*- coding: utf-8 -*-
"""excess_culprit_order.py — ЕДИНОЕ правило «кто перешёл лимит и всё, что
добавлено после» (владелец 08.10.2026, план binary-crunching-island.md,
раздел 1, ПРАВИЛО №6).

Повод: окно «Свободно — товары» (feo_card_drill) называло виновником
«Плакетку МДФ», оплаченную в мае, хотя реальный перебор дал авансовый отчёт
от 22.09 — закупка 975 была создана 01.10 (created_at), но перенесена в
субсидию массовой операцией 05-07.10, а created_at при переносе не меняется.
Второе место с ПОХОЖЕЙ, но другой логикой — feo_plan_excess.find_excess_culprit
(шёл от старых к новым по created_at и искал ПЕРВОЕ пересечение) — правила
были не идентичны, что запрещено ПРАВИЛОМ №6. Эта функция — единственная
точка, которую обязаны звать оба места.

Правило:
  1) строки сортируются от старых к новым по (plan_changed_at, id);
  2) находится первая строка, на которой накопленная сумма ВПЕРВЫЕ превысила
     limit;
  3) виновники — эта строка и ВСЕ, что идут после неё в этом порядке.
  4) «честная оговорка про пачку»: если plan_changed_at первой строки-
     виновницы совпадает (до секунды) с plan_changed_at ещё ≥1 строки(строк),
     лежащей(их) ДО неё в этом же порядке (т.е. превышение произошло ВНУТРИ
     одной одновременной загрузки, разделить которую по времени нельзя) —
     виновниками считается вся эта группа одновременных строк и всё, что
     после неё; возвращается batch_note с датой и количеством строк пачки."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional, Sequence


@dataclass
class CulpritResult:
    culprits: list              # строки-виновники (включая первую пересекшую границу), старые → новые
    total_amount: Decimal        # Σ amount всех строк
    total_excess: Decimal        # total_amount - limit (может быть <= 0, если лимит не превышен)
    crossing_index: Optional[int]  # индекс (в отсортированном списке rows) первой строки-виновницы
    batch_note: Optional[dict]   # {"date": iso-строка, "count": int, "message": str} | None


def plan_changed_at_sort_key(row: Any) -> tuple:
    """(plan_changed_at, id) de rigeur — экспортируемая версия _default_key
    для вызывающего кода (feo_plan_excess.find_excess_culprit), которому
    нужен ТОЛЬКО ключ сортировки одной группы контрибьюторов (FeoPlannedItem),
    а не вся логика нахождения пересечения этого модуля (ПРАВИЛО №6: один
    ключ, не вторая реализация сортировки)."""
    return _default_key(row)


def _default_key(row: Any) -> tuple:
    dt = getattr(row, "plan_changed_at", None) if not isinstance(row, dict) else row.get("plan_changed_at")
    rid = getattr(row, "id", None) if not isinstance(row, dict) else row.get("id")
    # None plan_changed_at сортируется как самое старое (datetime.min) — не
    # должно случаться (колонка NOT NULL), но не падаем на синтетических данных.
    return (dt or datetime.min, rid if rid is not None else 0)


def _amount_of(row: Any) -> Decimal:
    amt = getattr(row, "amount", None) if not isinstance(row, dict) else row.get("amount")
    return Decimal(str(amt or 0))


def _plan_changed_at_of(row: Any) -> Optional[datetime]:
    return getattr(row, "plan_changed_at", None) if not isinstance(row, dict) else row.get("plan_changed_at")


def culprits_after_crossing(
    rows: Sequence[Any],
    limit: Optional[float],
    *,
    key: Optional[Callable[[Any], tuple]] = None,
    amount_of: Optional[Callable[[Any], Decimal]] = None,
    plan_changed_at_of: Optional[Callable[[Any], Optional[datetime]]] = None,
) -> Optional[CulpritResult]:
    """rows — произвольные объекты/dict-ы с полями amount/plan_changed_at/id
    (или см. `key`/`amount_of`/`plan_changed_at_of` для нестандартных полей).
    limit — бюджет/план, который не должен быть превышен. None/rows пусто →
    None (нет данных для виновника).

    Возвращает CulpritResult с виновниками СТАРЫЕ→НОВЫЕ (вызывающий код сам
    разворачивает в «новые→старые» для отображения, если нужно — см.
    feo_card_drill, который явно хочет «от новых к старым»)."""
    if not rows:
        return None
    key_fn = key or _default_key
    amount_fn = amount_of or _amount_of
    pca_fn = plan_changed_at_of or _plan_changed_at_of

    ordered = sorted(rows, key=key_fn)
    amounts = [amount_fn(r) for r in ordered]
    total_amount = sum(amounts, Decimal("0"))

    if limit is None:
        limit_d = Decimal("0")
    else:
        limit_d = Decimal(str(limit))
    total_excess = total_amount - limit_d

    cumulative = Decimal("0")
    crossing_index: Optional[int] = None
    for i, amt in enumerate(amounts):
        cumulative += amt
        if cumulative - limit_d > Decimal("0.005"):
            crossing_index = i
            break

    if crossing_index is None:
        # Лимит не превышен — виновников нет, но результат всё равно
        # возвращается (total_excess <= 0), чтобы вызывающий код мог сверить
        # «виновник не найден ⟺ нет превышения», а не трактовать None как ошибку.
        return CulpritResult(
            culprits=[], total_amount=total_amount, total_excess=total_excess,
            crossing_index=None, batch_note=None,
        )

    # ── «Пачка» — plan_changed_at виновницы совпадает (до секунды) с ≥1
    # строкой(ами) ДО неё в этом же порядке. Расширяем левую границу группы,
    # пока plan_changed_at совпадает с текущей левой границей.
    crossing_dt = pca_fn(ordered[crossing_index])
    batch_start = crossing_index
    if crossing_dt is not None:
        while batch_start > 0:
            prev_dt = pca_fn(ordered[batch_start - 1])
            if prev_dt is not None and _same_second(prev_dt, crossing_dt):
                batch_start -= 1
            else:
                break

    batch_note = None
    if batch_start < crossing_index:
        batch_count = crossing_index - batch_start + 1
        batch_note = {
            "date": crossing_dt.isoformat() if crossing_dt else None,
            "count": batch_count,
            "message": (
                f"Превышение заложено в исходном плане (внесён одной загрузкой "
                f"{crossing_dt.strftime('%d.%m.%Y') if crossing_dt else ''})"
            ),
        }
        culprit_start = batch_start
    else:
        culprit_start = crossing_index

    culprits = list(ordered[culprit_start:])

    return CulpritResult(
        culprits=culprits, total_amount=total_amount, total_excess=total_excess,
        crossing_index=crossing_index, batch_note=batch_note,
    )


def _same_second(a: datetime, b: datetime) -> bool:
    """Совпадение «до секунды» — владелец про пачку (позиции одной загрузки
    могут отличаться на микросекунды/миллисекунды, если писались построчно в
    одной транзакции)."""
    return a.replace(microsecond=0) == b.replace(microsecond=0)
