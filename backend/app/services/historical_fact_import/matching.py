"""Строка файла → существующая плановая позиция (FeoPlannedItem/лист ФЭО).

Каскад из плана (нормализованное имя → сумма плана → путь предков → порядок
вхождения): сначала точное совпадение имени (без нечёткого сопоставления —
lesson feedback_dedup_exact_only), затем среди одноимённых — та, чья плановая
сумма ближе к сумме плана строки файла, затем — чей путь предков ближе к
пути строки, и наконец первая по id (детерминированный порядок — та же
кандидатская позиция при повторном предпросмотре того же файла).

Переиспользует services.plan_catalog.load_plan_catalog (ПРАВИЛО №6 — тот же
каталог плановых позиций, что и ручной матчинг /feo-planned-items/match).
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.plan_catalog import load_plan_catalog

_WS_RE = re.compile(r"\s+")


def normalize_item_name(raw: Optional[str]) -> str:
    if not raw:
        return ""
    s = str(raw).strip().lower()
    s = s.replace("ё", "е")
    s = _WS_RE.sub(" ", s)
    s = s.strip(" .,;:-")
    return s


async def build_matching_context(db: AsyncSession, subsidy_id: int) -> dict:
    """Один набор запросов на весь предпросмотр: каталог плановых позиций +
    множество planned_item_id, уже привязанных к существующей PurchaseItem
    (нужно для match.state='already_purchased' — решение владельца «по
    умолчанию пропуск с предупреждением»)."""
    catalog = await load_plan_catalog(db, subsidy_id)
    by_name: dict[str, list] = {}
    for entry in catalog:
        if entry.get("kind") != "planned_item":
            continue  # закупка привязывается к FeoPlannedItem, не к узлу дерева целиком
        key = normalize_item_name(entry["name"])
        by_name.setdefault(key, []).append(entry)

    # Выровнено с feo_plan_fact.planned_item_consumption (ПРАВИЛО №6, план
    # breezy-mixing-lovelace.md, Часть А): раньше это был голый запрос без
    # фильтра по субсидии/статусу/stopped_at — остановленная закупка в ЧУЖОЙ
    # субсидии «занимала» плановую позицию ЭТОЙ субсидии навечно. Теперь —
    # та же субсидия, PLANNED_STATUSES, не остановлена.
    from app.routers.purchase_budget import PLANNED_STATUSES  # local: avoid router import cycle
    # Задача B (план breezy-mixing-lovelace.md, «Оплачено, но уже в закупке»):
    # тот же запрос, что раньше отдавал только множество связанных
    # planned_item_id — теперь ещё и id/номер/статус закупки, которой
    # принадлежит привязка (ПРАВИЛО №6: existing_update.py читает отсюда, не
    # заводит второй запрос «какая закупка держит эту плановую позицию»).
    bound_rows = (await db.execute(
        select(
            PurchaseItem.feo_planned_item_id,
            Purchase.id, Purchase.registry_number, Purchase.status,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(
            PurchaseItem.feo_planned_item_id.isnot(None),
            Purchase.subsidy_id == subsidy_id,
            Purchase.status.in_(list(PLANNED_STATUSES)),
            Purchase.stopped_at.is_(None),
        )
    )).all()
    already_bound = {r[0] for r in bound_rows}
    bound_purchases: dict[int, list[dict]] = {}
    for fpi_id, pid, registry_number, status in bound_rows:
        bound_purchases.setdefault(fpi_id, []).append(
            {"id": pid, "registry_number": registry_number, "status": status}
        )

    # Баг РЕЕ-2026-08630 (владелец/соседняя сессия, 02.10): 4 строки файла по
    # 50 шт. все схлопнулись на ОДНУ плановую позицию (план 50 шт.) — каждый
    # вызов match_row брал «первую по id» заново, не глядя, что её уже отдали
    # предыдущей строке ЭТОГО ЖЕ прогона. used_ids — множество id, уже
    # выданных строкам текущего предпросмотра/коммита (мутируется match_row,
    # живёт на время одного build_preview()); одна плановая позиция не может
    # получить больше одной строки файла В ОДНОМ прогоне.
    return {
        "catalog": catalog, "by_name": by_name, "already_bound": already_bound,
        "bound_purchases": bound_purchases, "used_ids": set(),
        # Задание 07.10.2026 (чек-лист, п.2): used_ids сам по себе хранит
        # только id позиции — чтобы предупреждение ambiguous у строки N
        # называло ПО НОМЕРУ строку, которая заняла позицию раньше,
        # used_by[planned_item_id] = row["row"] того прогона, что её забрал
        # (ПРАВИЛО №6 — одно место, где used_ids.add(...), там же и used_by[...] = ...).
        "used_by": {},
    }


def match_row(ctx: dict, row: dict) -> dict:
    """{state: found|ambiguous|not_found|already_purchased, planned_item_id,
    candidates: [{id, name, path, amount}]}.

    found — свободная (не привязанная к прежней закупке И не отданная более
    ранней строке этого же прогона) позиция однозначно выбрана по каскаду
    имя→сумма→путь→порядок. ambiguous — каскад не смог сузить пул до одной
    свободной позиции (либо осталось несколько после сужения, либо все
    одноимённые уже разобраны более ранними строками файла — РЕЕ-2026-08630);
    planned_item_id=None, candidates показывает, из чего выбирать вручную, а
    competing_rows/competing_item_name (задание 07.10.2026, п.2) называют,
    какая строка файла уже заняла эту позицию и как она называется — иначе
    предупреждение «несколько строк претендуют» не говорит, на какую строку
    смотреть.
    """
    key = normalize_item_name(row["name"])
    candidates = ctx["by_name"].get(key, [])
    if not candidates:
        return {"state": "not_found", "planned_item_id": None, "candidates": []}

    cand_out = [
        {
            "id": c["id"], "name": c["name"], "path": c["path"], "amount": c.get("amount"),
            "category_id": c.get("category_id"),
        }
        for c in candidates
    ]

    used_ids: set = ctx["used_ids"]
    already_bound: set = ctx["already_bound"]
    available = [c for c in candidates if c["id"] not in used_ids and c["id"] not in already_bound]

    if not available:
        # Все одноимённые уже разобраны: либо старыми закупками
        # (already_purchased — ровно один вариант и он привязан), либо
        # более ранними строками ЭТОГО прогона (РЕЕ-2026-08630 — пул
        # исчерпан, лишняя строка не должна молча задвоить привязку).
        unbound_but_used = [c for c in candidates if c["id"] in used_ids]
        if unbound_but_used and not any(c["id"] in already_bound for c in candidates):
            used_by: dict = ctx["used_by"]
            competing_rows = sorted({
                used_by[c["id"]] for c in unbound_but_used if c["id"] in used_by
            })
            competing_item_name = unbound_but_used[0]["name"]
            return {
                "state": "ambiguous", "planned_item_id": None, "candidates": cand_out,
                "competing_rows": competing_rows, "competing_item_name": competing_item_name,
            }
        chosen = sorted(candidates, key=lambda c: c["id"])[0]
        return {"state": "already_purchased", "planned_item_id": chosen["id"], "candidates": cand_out}

    pool = list(available)
    plan_amount = row["plan"].get("amount")
    if len(pool) > 1 and plan_amount is not None:
        def _amt_dist(c):
            a = c.get("amount")
            if a is None:
                return Decimal("9" * 15)
            return abs(Decimal(str(a)) - Decimal(str(plan_amount)))
        min_dist = min(_amt_dist(c) for c in pool)
        narrowed = [c for c in pool if _amt_dist(c) == min_dist]
        if len(narrowed) < len(pool):
            pool = narrowed

    if len(pool) > 1 and row.get("path"):
        row_path_set = set(row["path"])
        def _path_overlap(c):
            return len(row_path_set & set(c.get("path", "").split(" › ") if isinstance(c.get("path"), str) else (c.get("path") or [])))
        max_overlap = max(_path_overlap(c) for c in pool)
        if max_overlap > 0:
            narrowed = [c for c in pool if _path_overlap(c) == max_overlap]
            if len(narrowed) < len(pool):
                pool = narrowed

    # Финальный шаг каскада — порядок вхождения (первая по id среди того,
    # что осталось после сужения по сумме/пути): ВСЕГДА детерминированно
    # выбирает одну позицию, даже если несколько неотличимы друг от друга
    # (одинаковое имя+сумма+путь) — иначе первая строка файла с таким
    # именем сама получала бы 'ambiguous' без всякой пользы. 'ambiguous'
    # зарезервирован ровно за случаем «пул уже исчерпан более ранними
    # строками этого же прогона» (см. ветку `if not available` выше,
    # РЕЕ-2026-08630).
    pool = sorted(pool, key=lambda c: c["id"])
    chosen = pool[0]
    used_ids.add(chosen["id"])
    # .get("row") — не KeyError на старых вызовах/тестах без номера строки
    # (row всегда несёт "row" из rows.py в реальном предпросмотре).
    ctx["used_by"][chosen["id"]] = row.get("row")
    return {"state": "found", "planned_item_id": chosen["id"], "candidates": cand_out}
