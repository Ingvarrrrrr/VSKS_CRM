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


def _row_category_key(row: dict) -> str:
    """Категория строки файла для матчинга. Чек-лист 13.10.2026 (прод «ДНР
    3», «Проезд, проживание, питание»): читаем `row['category_name']` —
    самый глубокий ЗАПОЛНЕННЫЙ уровень строки СЕБЯ (rows.py), НЕ `row['path']`
    — path строит _build_path, который выбрасывает уровень, совпавший с
    именем позиции (чтобы не дублировать его при отображении); когда сам
    Ур.4 файла текстуально равен имени позиции (как у строк 151/152), path
    обрывался на Ур.3 — категория «уезжала» на уровень выше настоящей,
    фильтр по категории отсекал верного кандидата (151 забирала позицию,
    152 уходила в ambiguous, хотя их сумма 700 000 = план позиции).
    `category_name` отсутствует (старые вызовы/тесты без него) → откат на
    path[-1] (прежнее поведение). Пусто → "" — НЕ «нет категории у позиции»,
    а «категория строки неизвестна», "" ниже всегда означает «не
    фильтровать по категории», а не «фильтровать на пустую категорию»."""
    category_name = row.get("category_name")
    if category_name:
        return normalize_item_name(category_name)
    path = row.get("path")
    if not path:
        return ""
    return normalize_item_name(path[-1])


def _candidate_category_key(candidate: dict) -> str:
    """Категория кандидата каталога — последний сегмент его `path`
    («Направление › Подкатегория › Лист», services.feo_plan_totals.
    build_category_path) — конечная категория ФЭО, к которой привязан сам
    кандидат (FeoCategory для kind='plan_position'/'feo_article', родительская
    категория листа для kind='planned_item'). Сравнивается нормализованно,
    тем же normalize_item_name, что и имена позиций (ПРАВИЛО №6 — одна
    функция нормализации везде)."""
    path = candidate.get("path")
    if not path:
        return ""
    parts = path.split(" › ") if isinstance(path, str) else list(path)
    if not parts:
        return ""
    return normalize_item_name(parts[-1])


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
            PurchaseItem.feo_plan_part_key,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(
            PurchaseItem.feo_planned_item_id.isnot(None),
            Purchase.subsidy_id == subsidy_id,
            Purchase.status.in_(list(PLANNED_STATUSES)),
            Purchase.stopped_at.is_(None),
        )
    )).all()
    bound_purchases: dict[int, list[dict]] = {}
    # Состав объединённой позиции (владелец, 12.10.2026, merged-item-parts.md,
    # п.2 чек-листа 13.10): «уже закуплено» у позиции С parts решается ПО
    # ЧАСТИ (bound_parts[fpi_id][part_key]), не по всей позиции — иначе
    # закупка на одну часть («Gaz», часть 20) молча занимает ВСЮ позицию и
    # блокирует её свободные части (27/28/31). bound_rows_no_part — строки
    # PurchaseItem без feo_plan_part_key (старые привязки до parts/обычная
    # позиция без parts) — для них часть не определена, безопаснее считать
    # позицию занятой целиком (прежнее поведение).
    bound_parts: dict[int, dict[str, dict]] = {}
    bound_rows_no_part: set[int] = set()
    for fpi_id, pid, registry_number, status, part_key in bound_rows:
        bound_purchases.setdefault(fpi_id, []).append(
            {"id": pid, "registry_number": registry_number, "status": status, "part_key": part_key}
        )
        if part_key:
            bound_parts.setdefault(fpi_id, {})[part_key] = {
                "id": pid, "registry_number": registry_number, "status": status,
            }
        else:
            bound_rows_no_part.add(fpi_id)

    # parts_by_id — состав КАЖДОЙ позиции каталога (пусто у обычных позиций).
    parts_by_id: dict[int, list] = {
        entry["id"]: (entry.get("parts") or [])
        for entry in catalog if entry.get("kind") == "planned_item"
    }
    already_bound: set = set()
    for fpi_id in bound_purchases:
        item_parts = parts_by_id.get(fpi_id)
        if not item_parts:
            # Обычная позиция (нет parts) — любая привязка занимает её
            # целиком, как и раньше.
            already_bound.add(fpi_id)
            continue
        if fpi_id in bound_rows_no_part:
            # Привязка без part_key у составной позиции — неоднозначно, чья
            # это часть; безопаснее считать позицию занятой целиком (не
            # отдавать её часть другой строке молча).
            already_bound.add(fpi_id)
            continue
        part_keys = {p.get("key") for p in item_parts if p.get("key")}
        bound_keys = set(bound_parts.get(fpi_id, {}).keys())
        if part_keys and part_keys <= bound_keys:
            # Все части уже закуплены — позиция занята целиком.
            already_bound.add(fpi_id)
        # иначе — есть свободные части, позиция остаётся «доступной» для
        # обычного каскада match_row/_assign_shared_groups; какая КОНКРЕТНО
        # часть свободна для данной строки файла решает preview.py
        # (resolve_row_plan_part, предзаполненный bound_parts — ПРАВИЛО №6,
        # второй выбор части не заводим).

    # Баг РЕЕ-2026-08630 (владелец/соседняя сессия, 02.10): 4 строки файла по
    # 50 шт. все схлопнулись на ОДНУ плановую позицию (план 50 шт.) — каждый
    # вызов match_row брал «первую по id» заново, не глядя, что её уже отдали
    # предыдущей строке ЭТОГО ЖЕ прогона. used_ids — множество id, уже
    # выданных строкам текущего предпросмотра/коммита (мутируется match_row,
    # живёт на время одного build_preview()); одна плановая позиция не может
    # получить больше одной строки файла В ОДНОМ прогоне.
    return {
        "catalog": catalog, "by_name": by_name, "already_bound": already_bound,
        "bound_purchases": bound_purchases, "bound_parts": bound_parts, "used_ids": set(),
        # Задание 07.10.2026 (чек-лист, п.2): used_ids сам по себе хранит
        # только id позиции — чтобы предупреждение ambiguous у строки N
        # называло ПО НОМЕРУ строку, которая заняла позицию раньше,
        # used_by[planned_item_id] = row["row"] того прогона, что её забрал
        # (ПРАВИЛО №6 — одно место, где used_ids.add(...), там же и used_by[...] = ...).
        "used_by": {},
        # Задача Б (12.10.2026) — заполняется _assign_shared_groups
        # (order_rows_for_matching), читается match_row (ПРАВИЛО №6, одно
        # место решения «строка → позиция» для группы «общая позиция на
        # несколько отдельных закупок»).
        "forced": {}, "forced_groups": {},
    }


def order_rows_for_matching(ctx: dict, rows: list) -> list:
    """Задача A (владелец, боевой файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист
    ДНРР, 11.10.2026): план GALA содержит ОДНУ позицию «Проезд, проживание,
    питание» на 292 815,90 ₽. Строка 151 файла (план 407 184,10) идёт раньше
    строки 152 (план 292 815,90) — но именно 152 точно совпадает по сумме
    плана с позицией GALA. match_row вызывался по строкам сверху вниз, 151
    забирала позицию первой (ложное «превышение» 407 184,10 > 292 815,90), а
    152 получала «позиции нет в плане».

    Возвращает `rows` в ДВА прохода: сначала строки, у которых среди
    СВОБОДНЫХ (не привязанных к чужой закупке — already_bound; used_ids на
    момент сортировки пуст, сортировка идёт ДО единого прохода match_row)
    одноимённых позиций каталога есть позиция с суммой плана, равной
    (±0,01) сумме плана строки файла, — точное совпадение однозначно решает,
    кому принадлежит позиция; затем все остальные строки, в исходном
    порядке. Сам каскад выбора внутри match_row (имя→сумма→путь→порядок) НЕ
    меняется ни для одной строки — меняется только ОЧЕРЁДНОСТЬ вызова.
    by_name/already_bound — тот же словарь/множество, что строит и читает
    match_row (ПРАВИЛО №6), второй индекс не заводится."""
    by_name: dict = ctx["by_name"]
    already_bound: set = ctx["already_bound"]

    def _has_exact_free_amount_match(row: dict) -> bool:
        plan_amount = (row.get("plan") or {}).get("amount")
        if plan_amount is None:
            return False
        target = Decimal(str(plan_amount))
        key = normalize_item_name(row.get("name"))
        for c in by_name.get(key, []):
            if c["id"] in already_bound:
                continue
            c_amount = c.get("amount")
            if c_amount is None:
                continue
            if abs(Decimal(str(c_amount)) - target) <= Decimal("0.01"):
                return True
        return False

    exact: list = []
    rest: list = []
    for row in rows:
        (exact if _has_exact_free_amount_match(row) else rest).append(row)

    # Задача Б (владелец, боевой файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист
    # ДНРР, 12.10.2026): «Gaz A22R35 Х920АЕ 180» — план GALA содержит ОДНУ
    # позицию на 352 400 ₽ (ремонт этой машины), а в файле факта — 4 СТРОКИ
    # с этим же именем на 317 400 / 20 000 / 10 000 / 5 000 — четыре ОТДЕЛЬНЫЕ
    # закупки в рамках одной плановой позиции, не «3 строки без места в
    # плане». Решение «какая строка какую позицию получает» принимается
    # ЗДЕСЬ, один раз, ДО основного прохода match_row (ПРАВИЛО №6 — второй
    # механизм распределения строка→позиция не заводим, match_row ниже
    # только читает ctx['forced']/ctx['forced_groups']).
    _assign_shared_groups(ctx, rows)

    return exact + rest


def _assign_shared_groups(ctx: dict, rows: list) -> None:
    """Группа одноимённых строк файла (после нормализации имени), у которых
    Σ плана СТРОК РАВНА (±0,01) плановой сумме ОДНОЙ свободной одноимённой
    позиции GALA, а свободных одноимённых позиций в плане МЕНЬШЕ, чем строк
    в группе, — вся группа получает эту ОДНУ позицию (`ctx['forced']`,
    `row_num -> planned_item_id`); match_row() ниже отдаёт её каждой строке
    группы без обычного состязания за «свободность» (used_ids), помечая
    `shared_item=True` — несколько закупок на одну FeoPlannedItem — ожидаемо
    и легитимно для этого случая (owner: «это разные закупки»).

    Если в group_rows для какой-то строки план неизвестен (amount=None) —
    группа НЕ трогается (нельзя проверить равенство сумм, см. контрольный
    пример владельца: 2 строки 407 184,10/292 815,90 при ОДНОЙ позиции
    292 815,90 — сумма строк НЕ равна сумме позиции, это другой случай,
    решается обычным каскадом match_row/order_rows_for_matching выше, а не
    этой функцией — у него остаётся одна found, одна ambiguous, как раньше)."""
    by_name: dict = ctx["by_name"]
    already_bound: set = ctx["already_bound"]
    forced: dict = ctx.setdefault("forced", {})
    forced_groups: dict = ctx.setdefault("forced_groups", {})

    # Задача В (12.10.2026, баг «ДНР 3»/лист ДНРР): группировка ТОЛЬКО по
    # имени смешивала строки из РАЗНЫХ категорий плана в одну группу — «Gaz
    # A22R35 Х920АЕ 180» в файле встречается в 4 категориях (Ремонт ТС,
    # Мойка, Шиномонтажные работы, Страхование) суммарно 7 строками, план
    # GALA содержит 4 РАЗНЫЕ позиции с этим именем (по одной на категорию);
    # группа «все 7 строк» при 4 кандидатах не проходила проверку len(free)
    # ==1 → shared не применялся вовсе, 2 из 4 строк «Ремонт ТС» уходили в
    # ambiguous. Группа теперь — (имя, категория СТРОКИ) — см. _row_category_
    # key; категория строки "" (путь не передан — старые вызовы/тесты без
    # path) означает «неизвестна», тогда кандидаты не фильтруются по
    # категории (прежнее поведение, см. _candidate_category_key).
    groups: dict[tuple[str, str], list] = {}
    for row in rows:
        key = normalize_item_name(row.get("name"))
        cat_key = _row_category_key(row)
        groups.setdefault((key, cat_key), []).append(row)

    for (key, cat_key), group_rows in groups.items():
        if len(group_rows) < 2:
            continue
        candidates = by_name.get(key, [])
        if cat_key:
            candidates = [c for c in candidates if _candidate_category_key(c) == cat_key]
        free = [c for c in candidates if c["id"] not in already_bound]
        # Ровно ОДНА свободная одноимённая позиция, и строк группы СТРОГО
        # больше — иначе обычный каскад справляется сам (len(free) >= len
        # (group_rows) — всем хватает по одной; len(free) > 1 при нескольких
        # разных суммах — не наш случай, его разбор не запрошен владельцем).
        if len(free) != 1 or len(group_rows) <= len(free):
            continue
        amounts = [(row.get("plan") or {}).get("amount") for row in group_rows]
        if any(a is None for a in amounts):
            continue
        total = sum(Decimal(str(a)) for a in amounts)
        target = free[0]
        c_amount = target.get("amount")
        if c_amount is None or abs(Decimal(str(c_amount)) - total) > Decimal("0.01"):
            continue
        row_nums = sorted(r.get("row") for r in group_rows if r.get("row") is not None)
        for row in group_rows:
            forced[row.get("row")] = target["id"]
        forced_groups[target["id"]] = {"rows": row_nums, "amount": total, "name": target["name"]}


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

    # Задача Б (12.10.2026) — группа строк уже получила ОДНУ общую позицию
    # через _assign_shared_groups (order_rows_for_matching, ПРАВИЛО №6, одно
    # место решения). Эксклюзивность used_ids здесь НЕ применяется намеренно
    # — несколько закупок на одну FeoPlannedItem легитимны ровно для этого
    # случая (каждая строка группы = отдельная закупка внутри одной позиции).
    forced: dict = ctx.get("forced") or {}
    row_num = row.get("row")
    if row_num in forced:
        chosen_id = forced[row_num]
        group_info = (ctx.get("forced_groups") or {}).get(chosen_id) or {}
        return {
            "state": "found", "planned_item_id": chosen_id, "candidates": cand_out,
            "shared_item": True,
            "shared_rows": group_info.get("rows"),
            "shared_amount": group_info.get("amount"),
        }

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
    # Задача В (12.10.2026) — тот же критерий категории, что и в
    # _assign_shared_groups выше (ПРАВИЛО №6 — _row_category_key/
    # _candidate_category_key, одна функция сравнения категорий на оба
    # места), теперь первым шагом обычного каскада: если у строки есть
    # одноимённые кандидаты в ЕЁ категории — выбор идёт только среди них, а
    # не среди одноимённых кандидатов во всех категориях субсидии сразу.
    # Строка без категории (path пуст — старые вызовы/тесты) не сужает пул
    # вовсе (прежнее поведение).
    row_cat_key = _row_category_key(row)
    if len(pool) > 1 and row_cat_key:
        same_cat = [c for c in pool if _candidate_category_key(c) == row_cat_key]
        if same_cat and len(same_cat) < len(pool):
            pool = same_cat

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
