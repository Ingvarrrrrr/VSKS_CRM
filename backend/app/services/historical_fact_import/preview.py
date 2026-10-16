"""POST /preview — собирает контракт-ответ БЕЗ записи в БД.

Склеивает columns.py → rows.py → statuses.py → matching.py → grouping.py и
добавляет сигналы для UI мастера (needs_contract_decision, is_payroll, skip,
warnings) — ровно то, что commit.py потом читает из decisions, чтобы решить,
что писать.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.historical_fact_import import columns as columns_mod
from app.services.historical_fact_import import rows as rows_mod
from app.services.historical_fact_import import statuses as statuses_mod
from app.services.historical_fact_import import matching as matching_mod
from app.services.historical_fact_import import grouping as grouping_mod
from app.services.historical_fact_import import existing_update as existing_update_mod
# ПРАВИЛО №6: подпись статуса — тот же источник, что statuses.py/
# purchase_transitions.py используют для STATUS_CHOICES, не вторая копия.
from app.routers.purchase_transitions import STATUS_LABELS
# ЕДИНСТВЕННЫЙ резолвер «категория ФЭО — ФОТ» (себя или предка) — задача A
# (владелец, 07.10.2026): «ФОТ определяется по категории, а не по названиям».
from app.services.feo_payroll import payroll_category_ids
# ПРАВИЛО №6: формат суммы в ₽ для текста предупреждений строки — тот же
# _fmt_money, что уже используется в commit.py (_format_rub) и шаблонах
# документов, не второй форматтер.
from app.services.documents.formatting import _fmt_money
# ПРАВИЛО №6: список номеров строк диапазонами («99–101, 103») — тот же
# хелпер, что собирает сводные предупреждения импорта ФЭО (feo_import_apply.py/
# feo_import_plan.py), не вторая копия схлопывания диапазонов.
from app.services.feo_import_common import format_rows as _format_rows
# Задача B (11.10.2026): _rub переехал в plan_diff_warnings.py (ПРАВИЛО №6 —
# единственный форматтер суммы для этого модуля, второй копии не держим);
# build_file_plan_vs_gala_warning/build_tz_excess_message — тексты двух
# предупреждений про расхождение плана/факта файла с планом GALA.
from app.services.historical_fact_import.plan_diff_warnings import (
    _rub, build_file_plan_vs_gala_warning, build_tz_excess_message,
)
# Задача 1 владельца (16.10.2026, продолжение GoodsService) — ОДНО место
# формата ключа «это и есть моя же закупка» (ПРАВИЛО №6), см. docstring
# build_source_key в contract_groups.py.
from app.services.historical_fact_import.contract_groups import build_source_key, valid_inn
# Часть объединённой плановой позиции (план merged-item-parts.md) —
# ПРАВИЛО №6, единственное место решения строка→часть (см. docstring модуля).
from app.services.historical_fact_import.plan_parts import (
    resolve_row_plan_part, resolve_bound_row_part, part_by_key, build_part_excess_warning,
)
# Правка 12.10.2026 (план lazy-swimming-hollerith.md, п.4б): «экономия видна»
# при импорте факта — та же формула замещения плана заказом, что у дерева
# ФЭО (ПРАВИЛО №6, см. docstring economy_preview.py).
from app.services.historical_fact_import.economy_preview import (
    build_order_substitution_economy,
    build_order_substitution_overspend,
)
from app.services.feo_plan_fact import planned_item_consumption


def _row_ranges_only(rows: list) -> str:
    """Номера строк диапазонами БЕЗ слова «строка/строки» впереди (нужно для
    текста ambiguous ниже, где слово уже стоит в своём месте по-русски:
    «строке 99» / «строкам 99–101, 103») — переиспользует feo_import_common.
    format_rows (ПРАВИЛО №6), просто отрезает его собственный префикс."""
    text = _format_rows(rows)
    return text.split(" ", 1)[1] if " " in text else text


def _ru_plural_position(n: int) -> str:
    """«1 позиция» / «2 позиции» / «5 позиций» — стандартные русские
    окончания (11-14 — всегда «позиций», как и любое число, кончающееся на
    11-14, напр. 111)."""
    if n % 100 in (11, 12, 13, 14):
        return "позиций"
    last = n % 10
    if last == 1:
        return "позиция"
    if 2 <= last <= 4:
        return "позиции"
    return "позиций"


# Задание 07.10.2026 (чек-лист п.4): короткие подписи причин пропуска для
# totals.breakdown.skipped_by_reason — ЕДИНСТВЕННОЕ место, где заводится
# подпись кода skip_reason (сам текст предупреждения строки длиннее и
# формулируется там, где решается skip, см. цикл build_preview ниже;
# ПРАВИЛО №6 — коды те же, вторых не заводим).
SKIP_REASON_LABELS: dict[str, str] = {
    "manual": "Пропущена вручную",
    "no_status": "Нет статуса / план закупок",
    "needs_status": "Статус не распознан",
    "payroll": "ФОТ",
    # 🔵 правка (план lazy-swimming-hollerith.md): раньше это означало «N
    # строк одноимённой позиции при одной свободной в плане GALA» — теперь,
    # когда позицию из названия категории автоматически не заводят, это
    # всегда «в плане GALA такой позиции нет совсем» (владелец).
    "ambiguous": "Позиции нет в плане GALA",
    "already_purchased_multi": "Позиция уже в нескольких закупках",
    "already_purchased_unknown": "Позиция уже в закупке",
    "over_plan_skip": "Пропущено по решению о превышении",
    # 🔵 правка (план lazy-swimming-hollerith.md): строка-категория («Плановая
    # позиция» пуста) с данными — не пропуск молча, а уведомление владельцу.
    "no_item_name": "Нет названия позиции",
}


def paid_not_delivered_predicate(paid, target_status: Optional[str], is_advance: bool) -> bool:
    """Единственный предикат «оплата есть, а статус строки ниже «Поставлено»/
    «Оплачено»» (owner, 07.10.2026, прод id=74 «ЛНР»: РЕЕ-2026-03421). Один
    источник ПРАВИЛО №6 — используется и для текста предупреждения строки
    (ниже), и для totals.paid_not_delivered (владелец, доп. задача: «при
    импорте об этом должно идти уведомление» — на шаге итогов мастера, не
    только у самой строки). Аванс (is_advance) — оплата до поставки сама по
    себе законна и уже объяснена отдельным предупреждением «аванс», здесь не
    считается."""
    return bool(paid and target_status and target_status not in ("delivered", "paid") and not is_advance)


def paid_status_without_paid_predicate(target_status: Optional[str], paid) -> bool:
    """Единственный предикат «статус «Оплачено», но колонка «Оплачено» в
    файле пуста» (владелец, файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, строки
    141/142/151: статус «Оплачено», колонка оплаты пуста, платёж не
    создаётся — владелец посчитал их «оплатой» по своей таблице, в GALA они
    не попадут в «Оплачено»). ПРАВИЛО №6 — один источник и для
    предупреждения строки (ниже), и для totals.paid_status_without_paid
    (задача C, видно уже на шаге итогов мастера, не только у самой строки).
    target_status — уже ПОСЛЕ подмены is_advance (ордер вместо paid для
    авансов) — авансовые строки сюда не попадают, у них своё предупреждение."""
    return bool(target_status == "paid" and not paid)


async def build_preview(
    db: AsyncSession,
    subsidy_id: int,
    content: bytes,
    filename: str,
    sheet: Optional[str],
    mapping: Optional[dict],
    decisions: Optional[dict],
) -> dict:
    decisions = decisions or {}
    row_overrides = decisions.get("row_overrides") or {}
    over_plan_decisions = decisions.get("over_plan") or {}
    include_payroll = bool(decisions.get("include_payroll", False))

    detected = columns_mod.detect_format_and_header(content, filename, sheet)
    cols = columns_mod.build_columns(detected)
    cols = columns_mod.apply_mapping_override(cols, mapping)
    parsed_rows = rows_mod.parse_rows(detected, cols, detected["header_row"])

    ctx = await matching_mod.build_matching_context(db, subsidy_id)

    # Задача A (владелец, 07.10.2026): ФОТ — по категории ФЭО плановой
    # позиции строки (себя или предка, feo_payroll.payroll_category_ids),
    # НЕ по словам в названии/пути. Один набор категорий на весь
    # предпросмотр. planned_item_category — та же карта id→category_id, что
    # уже лежит в каталоге плановых позиций (matching_mod.build_matching_
    # context → ctx['catalog']), повторного похода в БД не делаем.
    payroll_cat_ids = await payroll_category_ids(db, [subsidy_id])
    # ПРАВИЛО №6: один словарь id→каталожная запись — источник и для
    # категории (ФОТ), и для имени/пути/суммы найденной плановой позиции в
    # match (показывается владельцу в колонке «Сопоставление», задание
    # 07.10.2026), второй поход в БД/второй словарь не заводим.
    catalog_by_id: dict[int, dict] = {
        entry["id"]: entry
        for entry in ctx["catalog"] if entry.get("kind") == "planned_item"
    }
    planned_item_category: dict[int, Optional[int]] = {
        pid: entry.get("category_id") for pid, entry in catalog_by_id.items()
    }

    # Превышение плана (owner: «договор больше плана» — предупреждение с
    # выбором). Переиспользуем tz_excess_approval.collect_tz_over_plan_violations
    # (ПРАВИЛО №6) — read-only здесь, ничего не пишет.
    from app.services.tz_excess_approval import collect_tz_over_plan_violations

    row_to_match: dict = {}
    for row in parsed_rows:
        if not row.get("no_item_name"):
            continue
        # 🔵 правка (план lazy-swimming-hollerith.md): строка-категория
        # без своей «Плановой позиции» НЕ привязывается автоматически,
        # даже если в плане GALA есть позиция с именем, совпадающим с
        # именем категории (owner: «категорию с позицией импорт не
        # склеивает, один клик делает владелец») — match_row() не
        # вызывается (он бы занял свободную позицию и пометил её
        # used_ids). Кандидаты — тот же каталог по тому же нормализован-
        # ному имени (matching_mod.normalize_item_name, ctx['by_name'],
        # ПРАВИЛО №6 — тот же индекс, что строит match_row, второй не
        # заводим), просто без потребления/привязки.
        _key = matching_mod.normalize_item_name(row["name"])
        _candidates = ctx["by_name"].get(_key, [])
        row_to_match[row["row"]] = {
            "state": "no_item_name",
            "planned_item_id": None,
            "candidates": [
                {
                    "id": c["id"], "name": c["name"], "path": c["path"], "amount": c.get("amount"),
                    "category_id": c.get("category_id"),
                }
                for c in _candidates
            ],
        }

    # Задача A (владелец, боевой файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист
    # ДНРР, 11.10.2026): строки с точным совпадением суммы плана сопоставляются
    # ПЕРВЫМИ (matching_mod.order_rows_for_matching, ПРАВИЛО №6 — порядок
    # решает тот же каскад match_row, здесь меняется только очерёдность
    # вызова) — иначе более РАННЯЯ по номеру строка той же одноимённой
    # позиции забирает её себе, даже когда сумма плана точно совпадает у
    # ДРУГОЙ строки. row_to_match заполняется по номеру строки — итоговый
    # порядок строк предпросмотра (цикл ниже проходит parsed_rows как раньше)
    # не меняется.
    matchable_rows = [r for r in parsed_rows if not r.get("no_item_name")]
    for row in matching_mod.order_rows_for_matching(ctx, matchable_rows):
        row_to_match[row["row"]] = matching_mod.match_row(ctx, row)

    tz_units = []
    for row in parsed_rows:
        match = row_to_match[row["row"]]
        if match["planned_item_id"]:
            amount = row["fact"]["amount"] if row["fact"]["amount"] is not None else row["contracted"]
            tz_units.append(SimpleNamespace(
                over_plan=False,
                feo_planned_item_id=match["planned_item_id"],
                feo_category_id=None,
                quantity=row["fact"]["qty"],
                unit_price=row["fact"]["price"],
                total_price=amount,
                item_name=row["name"],
            ))
    violations = await collect_tz_over_plan_violations(db, tz_units, fallback_category_id=None)
    violations_by_fpi: dict = {}
    for v in violations:
        if v.get("feo_planned_item_id"):
            violations_by_fpi.setdefault(v["feo_planned_item_id"], []).append(v)

    # Правка 12.10.2026 (п.4б): «уже заказано» по каждой плановой позиции,
    # на которую может сматчиться строка файла — ОДИН батчевый запрос
    # (planned_item_consumption, ПРАВИЛО №6, тот же источник used/used_qty,
    # что residuals/plan-positions), а не поход в БД на каждую строку.
    consumption_by_item = await planned_item_consumption(db, list(catalog_by_id.keys()))

    out_rows = []
    totals_contract = Decimal(0)
    totals_paid = Decimal(0)
    skipped_count = 0
    top_warnings: list[str] = []
    # Задание 07.10.2026 (п.4): разбивка итогов — считается В ЭТОМ ЖЕ цикле
    # (ПРАВИЛО №6, не второй расчёт totals): по статусу GALA × {включены в
    # итог / пропущены}, плюс отдельно строки, обновляющие существующую
    # закупку (included_existing — paid считается, contract нет, см. ниже),
    # плюс пропущенные — ещё и по коду причины.
    breakdown_by_status: dict[str, dict] = {}
    breakdown_existing = {"rows": 0, "paid": Decimal(0)}
    breakdown_skip_by_reason: dict[str, dict] = {}
    # Правка 12.10.2026 (п.4б): «экономия видна» — строки, экономия (не
    # Decimal float) собирается в этом же цикле (ПРАВИЛО №6, не второй расчёт).
    economy_rows: list[dict] = []
    economy_total = Decimal(0)
    # Задача владельца (13.10.2026) — зеркало economy_rows/economy_total выше,
    # для «перерасхода по заказам» (build_order_substitution_overspend,
    # economy_preview.py, ПРАВИЛО №6 — та же единая точка, тот же цикл).
    overspend_rows: list[dict] = []
    overspend_total = Decimal(0)
    # Часть объединённой позиции (план merged-item-parts.md) — какие key уже
    # отданы более ранним строкам ЭТОГО прогона (на позицию), чтобы 4 строки
    # «Gaz A22R35» получили 4 РАЗНЫЕ части, а не одну и ту же дважды.
    assigned_plan_parts: dict[int, set] = {}

    for row in parsed_rows:
        match = row_to_match[row["row"]]
        override = row_overrides.get(str(row["row"])) or {}

        status_info = statuses_mod.resolve_status(row["status_raw"])
        needs_status = False
        if override.get("status"):
            # Явный выбор пользователя (decisions.row_overrides[row].status,
            # код из statuses_mod.STATUS_CHOICES) — побеждает автоопределение,
            # «приведением» не считается (пользователь уже выбрал код).
            status_info = statuses_mod.resolve_status_by_code(override["status"])
        elif not status_info["recognized"] and row["status_raw"]:
            # 🔵 Неизвестное значение — строка ждёт выбора статуса из
            # выпадающего списка (6 кодов), не создаётся молча.
            needs_status = True

        # Задача 2 (владелец, 05.10.2026) — «Аванс (да/нет)»: строка со
        # статусом «Оплачено» и Аванс=да означает оплату ДО поставки — закупка
        # обязана встать в статус «Заказано» (ordered), не «Оплачено»
        # (committed_amounts.py — «Заключён договор» уже включает её, но
        # «Поставлено»/статус «Оплачено» нет, пока поставка не отмечена
        # отдельно). commit.py прочитает is_advance ниже и выставит
        # Purchase.is_prepayment=True на созданной закупке.
        is_advance = bool(row.get("advance")) and status_info["target_status"] == "paid"
        if is_advance:
            status_info = {**status_info, "target_status": "ordered"}

        warnings: list[str] = []
        fact_amount = row["fact"]["amount"]
        if fact_amount and not row["status_raw"]:
            warnings.append("Есть факт, но статус не указан")
        if status_info["target_status"] is None and row["status_raw"] and status_info["recognized"] and fact_amount:
            warnings.append('Статус «План закупок», но в строке уже есть факт')
        if needs_status:
            warnings.append(f'Нераспознанный статус: «{row["status_raw"]}» — выберите статус из списка')
        if status_info.get("correction"):
            warnings.append(status_info["correction"])
        if status_info["target_status"] == "contracted" and status_info["needs_payment"] and not row["paid"]:
            warnings.append('Статус «Заключён договор» (из «Оплачено частично»), но «Оплачено» не заполнено')
        if is_advance:
            warnings.append("аванс: оплачено до поставки")
        if paid_status_without_paid_predicate(status_info["target_status"], row["paid"]):
            # Повод: файл ЛНР МАО 07.10.2026 — колонка «Оплата» не
            # распозналась как paid, 35 строк «Оплачено» ушли с суммой 0 ₽ и
            # без единого платежа, молча (columns.py теперь ловит «Оплата»
            # через _is_paid_header, но на случай ручного mapping/override
            # оставляем предупреждение).
            warnings.append(
                'Статус «Оплачено», но сумма оплаты пуста — платёж не будет создан '
                '(проверьте, что колонка оплаты сопоставлена)'
            )

        # Задача (владелец, 07.10.2026, прод id=74 «ЛНР», РЕЕ-2026-03421) —
        # «Оплачено больше, чем поставлено» должно быть видно уже на импорте,
        # не только постфактум на дашборде (см. paid_over_delivered.py —
        # зеркало той же идеи «оплата раньше поставки» на уровне закупки,
        # не вторая формула: здесь просьба предупредить СТРОКУ импорта, там —
        # посчитать уже созданные закупки). Аванс (is_advance) уже объяснён
        # отдельным предупреждением выше — не дублируем.
        if paid_not_delivered_predicate(row["paid"], status_info["target_status"], is_advance):
            status_label = STATUS_LABELS.get(status_info["target_status"], status_info["target_status"])
            warnings.append(
                f'Оплата {_rub(row["paid"])} при статусе «{status_label}» — '
                'оплачено, но не поставлено; проверьте статус'
            )

        plan_amount = row["plan"]["amount"]
        contract_amount_for_row = fact_amount if fact_amount is not None else row["contracted"]
        over_plan_choice = over_plan_decisions.get(str(row["row"]))
        # Жалоба владельца (чек-лист 07.10.2026, п.4): суммы — с разрядами и
        # копейками, словами владельца («выберите решение в колонке
        # «Превышение»», не внутреннее «оставить с пометкой / урезать /
        # пропустить» вперемешку с координатами UI).
        is_over_plan = bool(
            plan_amount is not None and contract_amount_for_row is not None
            and contract_amount_for_row > plan_amount
        )
        if is_over_plan:
            warnings.append(
                f"Договор больше плана ({_rub(contract_amount_for_row)} > {_rub(plan_amount)}) — "
                "выберите решение в колонке «Превышение»"
            )
        # Если превышение уже показано строкой выше — текст нарушения ТЗ
        # (collect_tz_over_plan_violations) про то же самое превышение не
        # дублируется: это тот же сигнал второй раз, да ещё с советом
        # «измените плановую позицию в Плане закупок или уменьшите ТЗ»,
        # который в импорте факта неприменим (решение здесь — колонка
        # «Превышение», не правка ТЗ/плана). Сам факт превышения (is_over_plan)
        # остаётся сигналом независимо от этого дедупа.
        if match["planned_item_id"] in violations_by_fpi and not over_plan_choice and not is_over_plan:
            # Задача B: текст словами владельца («Факт больше плана GALA:
            # количество — в плане 1, в строке 4…»), НЕ v["message"]
            # (tz_excess_approval.collect_tz_over_plan_violations — тот текст
            # написан для карточки заявки/закупки, «уменьшите ТЗ» здесь
            # неприменимо: владелец сравнивает со своим файлом, не с ТЗ).
            # violation_details — структурные поля того же нарушения
            # (ПРАВИЛО №6, добавлены в feo_plan_tz_checks.tz_over_plan_
            # violations, не вторая формула сравнения).
            for v in violations_by_fpi[match["planned_item_id"]]:
                warnings.append(build_tz_excess_message(v.get("violation_details") or []))

        # «Законтрактовано» без факта при статусе «В работе» (правка 2, план) —
        # решается ПОЧЕЛОВЕЧНО через decisions.contract_confirmed_rows в commit.
        needs_contract_decision = bool(
            status_info["target_status"] == "work_in_progress"
            and not fact_amount
            and row["contracted"]
        )

        if override.get("planned_item_id"):
            # Пользователь уже разрешил привязку вручную (в т.ч. ambiguous —
            # РЕЕ-2026-08630: несколько строк файла на одно имя плановой
            # позиции) — применяем ДО решения про skip, иначе состояние
            # «до override» (already_purchased/ambiguous) продолжало бы
            # пропускать строку даже после явного выбора.
            match = {**match, "planned_item_id": override["planned_item_id"], "state": "found"}

        # Задание 07.10.2026 (чек-лист, п.3): для found/already_purchased
        # показать владельцу, С КАКОЙ плановой позицией сопоставлено —
        # имя/путь/сумма из ТОГО ЖЕ catalog_by_id, что уже строит категорию
        # ФОТ выше (ПРАВИЛО №6, второй запрос/словарь не заводим). После
        # override (если пользователь выбрал другую позицию) — имя уже новой.
        if match.get("planned_item_id") is not None:
            _entry = catalog_by_id.get(match["planned_item_id"])
            match = {
                **match,
                "planned_item_name": _entry.get("name") if _entry else None,
                "planned_item_path": _entry.get("path") if _entry else None,
                "planned_item_amount": _entry.get("amount") if _entry else None,
            }
            # Задача B (владелец, строка 89 «Бочка металлическая…»): план
            # строки файла (кол-во/цена/сумма) отличается от плана
            # сопоставленной позиции GALA, даже когда сумма совпала случайно
            # (4 × 5 500 = 1 × 22 000 = 22 000 — количество и цена разные).
            if _entry is not None:
                _plan_diff_warning = build_file_plan_vs_gala_warning(row["plan"], _entry)
                if _plan_diff_warning:
                    warnings.append(_plan_diff_warning)

            # Часть объединённой позиции (план merged-item-parts.md) — только
            # когда у позиции есть parts (объединённая загрузкой плана);
            # обычная позиция (parts=[]) не несёт plan_part_key вовсе.
            _parts = (_entry or {}).get("parts") or []
            if _parts:
                _fpi_id = match["planned_item_id"]
                # Правка (чек-лист 13.10.2026, п.2): части, уже занятые
                # СУЩЕСТВУЮЩЕЙ закупкой (ctx['bound_parts'], см. matching.py),
                # предзаполняют assigned ДО каскада — чтобы resolve_row_plan_
                # part (ПРАВИЛО №6, единственное место выбора части) никогда
                # не отдал занятую часть новой строке файла молча.
                _bound_parts_for_item: dict = ctx.get("bound_parts", {}).get(_fpi_id, {})
                if _fpi_id not in assigned_plan_parts:
                    assigned_plan_parts[_fpi_id] = set(_bound_parts_for_item.keys())
                _assigned = assigned_plan_parts[_fpi_id]
                _override_part_key = override.get("plan_part_key")
                _plan_part_key = resolve_row_plan_part(_parts, _override_part_key, plan_amount, _assigned)
                if _plan_part_key is None and not _override_part_key:
                    # resolve_row_plan_part ищет только СВОБОДНЫЕ части —
                    # строка файла может быть «попаданием» в часть, которая
                    # уже закуплена (bound_parts), а не «часть не выбрана».
                    _plan_part_key = resolve_bound_row_part(_parts, set(_bound_parts_for_item.keys()), plan_amount)
                _bound_info = _bound_parts_for_item.get(_plan_part_key) if _plan_part_key else None
                if _plan_part_key and _bound_info:
                    # Эта часть уже закуплена существующей закупкой —
                    # строка не создаёт новую, а обновляет существующую по
                    # ЭТОЙ части (текст/решение — ниже, та же ветка
                    # «already_purchased», что и у обычных позиций).
                    _assigned.add(_plan_part_key)
                    match = {**match, "plan_part_key": _plan_part_key, "plan_parts": _parts, "state": "already_purchased"}
                elif _plan_part_key:
                    _assigned.add(_plan_part_key)
                    match = {**match, "plan_part_key": _plan_part_key, "plan_parts": _parts}
                    _part = part_by_key(_parts, _plan_part_key)
                    _part_excess_warning = build_part_excess_warning(_part, contract_amount_for_row) if _part else None
                    if _part_excess_warning:
                        warnings.append(_part_excess_warning)
                else:
                    match = {**match, "plan_part_key": None, "plan_parts": _parts}
                    warnings.append(
                        f'Выберите часть позиции «{match.get("planned_item_name") or row["name"]}» '
                        'в колонке «Сопоставление»'
                    )

            # Задача Б (12.10.2026, «Gaz A22R35 Х920АЕ 180») — позиция GALA
            # объединяет несколько строк файла (matching_mod._assign_shared_
            # groups) — каждая строка станет ОТДЕЛЬНОЙ закупкой в рамках этой
            # одной позиции; владелец должен видеть это явно, не только по
            # совпавшим суммам строк.
            if match.get("shared_item") and match.get("shared_rows"):
                _shared_name = match.get("planned_item_name") or row["name"]
                _shared_rows_text = _row_ranges_only(match["shared_rows"])
                _shared_amount_text = _rub(match.get("shared_amount"))
                warnings.append(
                    f'Позиция GALA «{_shared_name}» ({_shared_amount_text}) объединяет строки '
                    f'{_shared_rows_text} файла — каждая строка будет отдельной закупкой в этой позиции'
                )

        # Задача A — ФОТ по категории плановой позиции (после override, т.к.
        # override.planned_item_id может сменить, какая категория у строки).
        _cat_id = planned_item_category.get(match.get("planned_item_id"))
        is_payroll = bool(_cat_id) and _cat_id in payroll_cat_ids

        # Задание 07.10.2026 (чек-лист п.2-3): skip и его причина решаются
        # ЗДЕСЬ и только здесь (ПРАВИЛО №6) — skip_reason.text идёт и в
        # warnings строки, и в контракт row.skip_reason (FactImportRowSkipCell.
        # vue / FactImportStepConfirm.vue читают оттуда, не формулируют текст
        # заново). skip_forced=True — причина не устранена, галочку снять
        # нельзя (no_status/needs_status/payroll/ambiguous); иначе — manual/
        # over_plan_skip/already_purchased_*, где override.skip уже работает.
        manual_skip = bool(override.get("skip", False)) and "skip" in override
        skip = manual_skip
        skip_forced = False
        skip_reason: Optional[dict] = (
            {"code": "manual", "text": "пропущена вами"} if manual_skip else None
        )
        existing_purchase: Optional[dict] = None

        # 🟢 Правка (владелец, 16.10.2026, продолжение GoodsService): позиция
        # каталога «Услуги связи» (ежемесячная услуга) — ОДНА, но реальных
        # закупок на неё за разные месяцы МНОГО. matching.match_row видит
        # «позиция уже привязана» и ставит already_purchased для КАЖДОЙ
        # строки с этим именем, указывая на ОДНУ (первую попавшуюся)
        # привязанную закупку — даже когда эта строка на самом деле про
        # СВОЙ, другой, месяц/заказ (другой № закупки/заказа). Раньше все
        # такие строки молча копились в один бакет «обновить статус/оплату»
        # (existing_update.py) — 7 месяцев схлопывались в один платёж задним
        # числом поверх первой закупки (боевая находка: +78 203 к закупке на
        # 11 870). Если у строки есть СВОЯ опознаваемая личность (ИНН+№
        # закупки, build_source_key) и у найденной привязанной закупки тоже
        # есть source_key, но они РАЗНЫЕ — это НЕ та же закупка, просто то же
        # имя позиции: откатываем match на not_found, строка пойдёт обычным
        # путём (создаст СВОЮ закупку, см. ветку ambiguous/not_found ниже,
        # которая теперь тоже не пропускается молча). Если source_key нет
        # (старые файлы без ИНН/№ закупки) — поведение не меняется.
        if match["state"] == "already_purchased":
            _bound_single = ctx.get("bound_purchases", {}).get(match["planned_item_id"]) or []
            if len(_bound_single) == 1:
                _row_source_key = build_source_key(valid_inn(row.get("inn")), row.get("purchase_no"))
                _cand_source_key = _bound_single[0].get("source_key")
                if _row_source_key and _cand_source_key and _row_source_key != _cand_source_key:
                    match = {**match, "state": "not_found", "planned_item_id": None}

        if match["state"] == "already_purchased" and "skip" not in override:
            # Задача B (владелец, 07.10.2026): «он должен статусы смотреть» —
            # не пропускать строку молча, а обновить закупку, которой уже
            # принадлежит эта плановая позиция, по статусу/оплате из файла
            # (см. existing_update.py). ctx['bound_purchases'] — тот же запрос,
            # что и already_bound (matching.py), просто с данными о закупке.
            #
            # Часть объединённой позиции (чек-лист 13.10.2026, п.2): если
            # already_purchased решён по КОНКРЕТНОЙ части (match['plan_part_
            # key'], см. блок выше) — закупка, которую обновляем, тоже РОВНО
            # одна — закупка ЭТОЙ части (ctx['bound_parts']), а не список
            # закупок всей позиции (у позиции может быть несколько частей,
            # закупленных разными закупками — это не «несколько закупок на
            # одну и ту же часть», ambiguous здесь не к месту).
            _part_key_bound = match.get("plan_part_key")
            if _part_key_bound:
                _bp = ctx.get("bound_parts", {}).get(match["planned_item_id"], {}).get(_part_key_bound)
                bound = [_bp] if _bp else []
            else:
                bound = ctx.get("bound_purchases", {}).get(match["planned_item_id"]) or []
            status_ok = status_info["target_status"] is not None and not needs_status
            if len(bound) == 1 and status_ok:
                bp = bound[0]
                existing_purchase = {"id": bp["id"], "registry_number": bp["registry_number"], "status": bp["status"]}
                if _part_key_bound:
                    _part_row_label = (part_by_key(match.get("plan_parts") or [], _part_key_bound) or {}).get("row")
                    warnings.append(
                        f'Часть «строка {_part_row_label if _part_row_label is not None else _part_key_bound}» '
                        f'позиции «{match.get("planned_item_name") or row["name"]}» уже в закупке '
                        f'{bp["registry_number"] or bp["id"]} — она будет обновлена по файлу '
                        f'(статус «{STATUS_LABELS.get(status_info["target_status"], status_info["target_status"])}», '
                        'оплата по отметке)'
                    )
                else:
                    warnings.append(
                        f'Плановая позиция уже в закупке {bp["registry_number"] or bp["id"]} — она будет '
                        f'обновлена по файлу (статус «{STATUS_LABELS.get(status_info["target_status"], status_info["target_status"])}», '
                        'оплата по отметке)'
                    )
            elif len(bound) > 1:
                regs = ", ".join(str(b["registry_number"] or b["id"]) for b in bound)
                text = f"у плановой позиции уже есть закупки: {regs} — строка пропущена по умолчанию"
                skip = True
                skip_reason = {"code": "already_purchased_multi", "text": text}
                warnings.append(f"У плановой позиции уже есть закупки: {regs} — строка пропущена по умолчанию")
            else:
                skip = True
                skip_reason = {
                    "code": "already_purchased_unknown",
                    "text": "у плановой позиции уже есть закупка — строка пропущена по умолчанию",
                }
                warnings.append("У плановой позиции уже есть закупка — строка пропущена по умолчанию")

        if match["state"] == "ambiguous" and "skip" not in override:
            # 🟢 Правка (владелец, 16.10.2026, продолжение задачи GoodsService):
            # «каждая строка со стадией должна стать закупкой/заказом
            # независимо от того, нашлась ли плановая позиция; строка без
            # позиции — с пометкой «плановая позиция не найдена», не пропуск».
            # Раньше ambiguous принудительно пропускался (skip_forced) — на
            # листе GoodsService 14 строк со стадией и реальной суммой молча
            # не становились закупками (952 950 ₽ «терялись»). Теперь строка
            # создаёт закупку БЕЗ привязки к плану (как и `not_found` — та
            # ветка никогда не была force-skip), предупреждение остаётся
            # информационным (видно в предпросмотре), привязку человек может
            # донастроить вручную позже через override.planned_item_id —
            # ПРЯМОЕ ручное «Пропустить» (override.skip) продолжает работать
            # (проверка `"skip" not in override` выше не изменилась).
            competing_rows = match.get("competing_rows") or []
            competing_name = match.get("competing_item_name") or row["name"]
            n_candidates = len(match["candidates"])
            word = _ru_plural_position(n_candidates)
            if competing_rows:
                rows_label = "строке" if len(competing_rows) == 1 else "строкам"
                rows_text = _row_ranges_only(competing_rows)
                linked = (
                    "она уже сопоставлена" if n_candidates == 1 else "все уже сопоставлены"
                )
                linked_part = f"{linked} {rows_label} {rows_text}"
            else:
                linked_part = (
                    "она уже сопоставлена другой строке файла"
                    if n_candidates == 1 else "все уже сопоставлены другим строкам файла"
                )
            reason_text = (
                f'Плановая позиция не найдена: в плане GALA {n_candidates} {word} «{competing_name}», '
                f'{linked_part} — для этой строки позиции в плане нет. Закупка будет создана БЕЗ привязки '
                'к плану; привязать вручную можно в колонке «Сопоставление», либо нажать «Пропустить»'
            )
            skip_reason = {"code": "ambiguous", "text": reason_text}
            warnings.append(reason_text)

        if match["state"] == "no_item_name" and "skip" not in override:
            # 🔵 Правка (план lazy-swimming-hollerith.md, п.2): «Плановая
            # позиция» пуста у строки-категории, но в строке есть данные —
            # строка не загружается молча, владелец выбирает позицию вручную
            # в колонке «Сопоставление» (override.planned_item_id выше уже
            # превратил бы match.state в «found» ДО этой проверки). skip_
            # forced=False — владелец может и просто снять пропуск галочкой
            # (как у not_found), это его решение.
            skip = True
            skip_forced = False
            if row["status_raw"]:
                hint = f'статус «{STATUS_LABELS.get(status_info["target_status"], row["status_raw"])}»'
            elif fact_amount:
                hint = f'факт {_rub(fact_amount)}'
            elif row["paid"]:
                hint = f'оплата {_rub(row["paid"])}'
            else:
                hint = "есть данные"
            reason_text = (
                f'«Плановая позиция» пуста, а в строке {hint} — похоже, название позиции забыли. '
                'Строка не загружена: впишите позицию в файл или выберите её в колонке «Сопоставление»'
            )
            skip_reason = {"code": "no_item_name", "text": reason_text}
            warnings.append(reason_text)

        if status_info["target_status"] is None and not needs_status and match["state"] != "no_item_name":
            # match.state == "no_item_name" исключён (координатор, повторная
            # правка 10.10): у такой строки «План закупок» — ОДНА из причин
            # самого уведомления no_item_name (ДНРР 152), не отдельная общая
            # причина «нет статуса» — без исключения этот блок перетирал бы
            # skip_reason/текст, выставленные выше, причём безусловно.
            skip = True
            skip_forced = True
            skip_reason = {
                "code": "no_status",
                "text": 'статус «План закупок» / пуст — закупки нет, выберите статус',
            }
        if needs_status:
            # 🔵 Статус не распознан и пользователь ещё не выбрал его явно —
            # строка не создаётся молча (владелец, правка 3).
            skip = True
            skip_forced = True
            skip_reason = {"code": "needs_status", "text": "статус не распознан — выберите статус из списка"}
        if is_payroll and not include_payroll:
            skip = True
            skip_forced = True
            skip_reason = {"code": "payroll", "text": 'ФОТ — включите «Включить ФОТ», чтобы учесть строку'}

        if over_plan_choice == "skip" and not skip_forced:
            # Пункт 3 (чек-лист): решение «Пропустить» в колонке «Превышение»
            # становится пропуском УЖЕ в предпросмотре, не только при коммите
            # (раньше — только commit.py:271, итог предпросмотра не совпадал
            # с тем, что реально запишется).
            skip = True
            skip_reason = {"code": "over_plan_skip", "text": 'решение «Пропустить» в колонке «Превышение»'}

        if skip:
            # Строка полностью пропущена — не одновременно «обновит
            # существующую» (иначе она бы вошла и в skipped_count, и в
            # existing_updates — состояния взаимоисключающие).
            existing_purchase = None

        # Правка 12.10.2026 (план lazy-swimming-hollerith.md, п.4б): «экономия
        # видна» — ТОЛЬКО для строк, что реально создадут закупку (не skip) и
        # только для ОБЫЧНОЙ (не объединённой — match["plan_parts"]) позиции:
        # у объединённой план замещается по составу parts, не этой формулой
        # одного узла (отдельная задача). Формула — build_order_substitution_
        # economy (economy_preview.py, ПРАВИЛО №6, та же _order_substituted_
        # plan, что и дерево ФЭО).
        if not skip and match.get("planned_item_id") is not None and not match.get("plan_parts"):
            _econ_entry = catalog_by_id.get(match["planned_item_id"])
            if _econ_entry is not None:
                _cons = consumption_by_item.get(match["planned_item_id"]) or {"used": 0.0, "used_qty": 0.0}
                _row_qty = row["fact"]["qty"] if row["fact"]["qty"] is not None else row["plan"]["qty"]
                economy_info = build_order_substitution_economy(
                    planned_qty=_econ_entry.get("quantity"),
                    planned_amount=_econ_entry.get("amount"),
                    already_ordered_qty=_cons.get("used_qty", 0.0),
                    already_ordered_sum=_cons.get("used", 0.0),
                    row_qty=_row_qty,
                    row_amount=contract_amount_for_row,
                    planned_item_name=_econ_entry.get("name") or row["name"],
                )
                if economy_info:
                    warnings.append(economy_info["message"])
                    economy_total += economy_info["amount"]
                    economy_rows.append({
                        "row": row["row"],
                        "name": _econ_entry.get("name") or row["name"],
                        "amount": float(economy_info["amount"]),
                    })
                # Задача владельца (13.10.2026) — зеркало экономии выше: та же
                # строка/позиция, та же единая точка _order_substituted_plan,
                # просто ищем перерасход (build_order_substitution_overspend,
                # economy_preview.py, ПРАВИЛО №6).
                overspend_info = build_order_substitution_overspend(
                    planned_qty=_econ_entry.get("quantity"),
                    planned_amount=_econ_entry.get("amount"),
                    already_ordered_qty=_cons.get("used_qty", 0.0),
                    already_ordered_sum=_cons.get("used", 0.0),
                    row_qty=_row_qty,
                    row_amount=contract_amount_for_row,
                    planned_item_name=_econ_entry.get("name") or row["name"],
                )
                if overspend_info:
                    warnings.append(overspend_info["message"])
                    overspend_total += overspend_info["amount"]
                    overspend_rows.append({
                        "row": row["row"],
                        "name": _econ_entry.get("name") or row["name"],
                        "amount": float(overspend_info["amount"]),
                    })

        status_key = status_info["target_status"] or "none"
        status_bucket = breakdown_by_status.setdefault(status_key, {
            "included": {"rows": 0, "contract_amount": Decimal(0), "contract_amount_raw": Decimal(0), "paid": Decimal(0)},
            "skipped": {"rows": 0, "contract_amount": Decimal(0), "contract_amount_raw": Decimal(0), "paid": Decimal(0)},
        })
        raw_amt = Decimal(str(contract_amount_for_row)) if contract_amount_for_row is not None else Decimal(0)
        paid_amt = Decimal(str(row["paid"])) if row["paid"] else Decimal(0)

        if skip:
            skipped_count += 1
            sb = status_bucket["skipped"]
            sb["rows"] += 1
            sb["contract_amount_raw"] += raw_amt
            sb["paid"] += paid_amt
            reason_code = skip_reason["code"] if skip_reason else "manual"
            reason_bucket = breakdown_skip_by_reason.setdefault(reason_code, {
                "label": SKIP_REASON_LABELS.get(reason_code, reason_code),
                "rows": [], "contract_amount_raw": Decimal(0), "paid": Decimal(0),
            })
            reason_bucket["rows"].append(row["row"])
            reason_bucket["contract_amount_raw"] += raw_amt
            reason_bucket["paid"] += paid_amt
        elif existing_purchase:
            # Задача B: эта строка НЕ создаёт новую закупку (см. grouping.py/
            # commit.py — существующая закупка обновляется отдельно, не через
            # обычную группировку) — в totals.contract_amount/«Договоров на
            # сумму» не попадает, но её «Оплачено» всё равно реальная оплата
            # по субсидии. Отдельная корзина included_existing (п.4) — иначе
            # разбивка по статусам «не сходилась» бы с плитками ровно.
            breakdown_existing["rows"] += 1
            breakdown_existing["paid"] += paid_amt
            if row["paid"]:
                totals_paid += Decimal(str(row["paid"]))
        else:
            amt = contract_amount_for_row or Decimal(0)
            if over_plan_choice == "trim" and plan_amount is not None:
                amt = min(amt, plan_amount)
            amt = Decimal(str(amt))
            totals_contract += amt
            if row["paid"]:
                totals_paid += Decimal(str(row["paid"]))
            ib = status_bucket["included"]
            ib["rows"] += 1
            ib["contract_amount"] += amt
            ib["contract_amount_raw"] += raw_amt
            ib["paid"] += paid_amt

        out_rows.append({
            "row": row["row"],
            "name": row["name"],
            "path": row["path"],
            "status": status_info["target_status"],
            "status_raw": row["status_raw"],
            "plan": {
                "qty": float(row["plan"]["qty"]) if row["plan"]["qty"] is not None else None,
                "price": float(row["plan"]["price"]) if row["plan"]["price"] is not None else None,
                "amount": float(row["plan"]["amount"]) if row["plan"]["amount"] is not None else None,
            },
            "fact": {
                "qty": float(row["fact"]["qty"]) if row["fact"]["qty"] is not None else None,
                "price": float(row["fact"]["price"]) if row["fact"]["price"] is not None else None,
                "amount": float(row["fact"]["amount"]) if row["fact"]["amount"] is not None else None,
            },
            "paid": float(row["paid"]) if row["paid"] is not None else None,
            "advance": bool(row.get("advance")),
            "is_advance": is_advance,
            "contracted": float(row["contracted"]) if row["contracted"] is not None else None,
            "supplier": row["supplier"],
            "purchase_no": row["purchase_no"],
            "unit": row["unit"],
            "item_type": row["item_type"],
            "match": match,
            "needs_contract_decision": needs_contract_decision,
            "needs_status": needs_status,
            "is_payroll": is_payroll,
            "skip": skip,
            "skip_reason": skip_reason,
            "skip_forced": skip_forced,
            "existing_purchase": existing_purchase,
            "warnings": warnings,
            "_status_info": status_info,
            # Группировка по договору (владелец, 16.10.2026, шаг 2) —
            # grouping.py (ключ группы) и contract_groups.py (разбор группы
            # на заказы/лимит) читают их отсюда, не второй источник.
            "inn": row.get("inn"),
            "contract_kind": row.get("contract_kind"),
            "order_no": row.get("order_no"),
            "contract_number": row.get("contract_number"),
            "contract_date": row.get("contract_date"),
        })
        if warnings:
            top_warnings.extend(f"Строка {row['row']}: {w}" for w in warnings)

    rows_with_match = [{"row": r, "match": r["match"], "status_info": r["_status_info"]} for r in out_rows]
    groups = grouping_mod.build_groups(rows_with_match, decisions)

    # Группировка по договору (владелец, 16.10.2026, шаг 2) — «внутри
    # договора — по номерам заказов, делай как GoodsService»: каждая группа
    # (уже собранная grouping.py по ИНН/поставщик + № закупки) разбирается
    # contract_groups.build_contract_group() на вид договора/реальный номер
    # и дату/заказы (для рамочных) — ОДНО определение (ПРАВИЛО №6), то же,
    # что потом использует commit.py при создании закупок.
    from app.services.historical_fact_import import contract_groups as contract_groups_mod
    from app.services.historical_fact_import.existing_update import RANK as _CONTRACT_RANK
    _rows_by_num_for_contract = {r["row"]: r for r in out_rows}
    for group in groups:
        group_rows_full = [_rows_by_num_for_contract[rn] for rn in group["rows"] if rn in _rows_by_num_for_contract]
        has_contract_columns = any(gr.get("contract_kind") or gr.get("order_no") for gr in group_rows_full)
        if not has_contract_columns:
            continue
        info = contract_groups_mod.build_contract_group(
            group_rows_full, status_of=lambda r: r.get("status"), status_rank=_CONTRACT_RANK,
        )
        group["contract_kind"] = info.kind
        group["contract_number"] = info.contract_number
        group["contract_date"] = info.contract_date.isoformat() if info.contract_date else None
        group["contract_orders"] = [
            {
                "order_no": o.order_no,
                "amount": float(o.amount),
                "status": o.status,
                "rows": [r["row"] for r in o.rows],
            }
            for o in info.orders
        ]
        group["contract_limit_amount"] = float(info.limit_amount) if info.limit_amount is not None else None

    for r in out_rows:
        r.pop("_status_info", None)

    # 🔵 правка 3 (план breezy-mixing-lovelace.md, Часть А «Похожие закупки в
    # импорте факта»): для каждой будущей закупки (группы) — поиск уже
    # существующей закупки того же поставщика/суммы (historical_fact_import.
    # existing_link). Владелец (16.10.2026): поиск поставщика там теперь
    # ТОЛЬКО по ИНН (см. докстринг existing_link.py) — имя больше не
    # используется вовсе, совпадение по имени давало ложные «сопоставлено»
    # у разных организаций с похожими названиями. Группа без ни одной
    # незапропущенной строки (всё skip) — искать нечего, она всё равно не
    # станет закупкой (commit.py её пропускает).
    from app.services.historical_fact_import import existing_link as existing_link_mod
    from app.services.tz_excess_approval import collect_tz_over_plan_violations as _collect_violations
    from types import SimpleNamespace as _SimpleNamespace
    from app.services.vehicle_org_matching import normalize_inn as _normalize_inn
    from app.services.contractor_resolve import find_contractor_ids_by_inns

    rows_by_num = {r["row"]: r for r in out_rows}
    existing_decisions = decisions.get("existing_match") or {}
    purchases_count = 0

    # Замер скорости (владелец 16.10.2026): раньше find_existing_matches_
    # for_group на КАЖДУЮ группу (113 на листе GoodsService владельца) сама
    # заново запрашивала и нормализовала ВСЕХ контрагентов (4,8 млн вызовов
    # normalize_org_name, ~107 с) — теперь ОДИН запрос `inn IN (...)` по
    # ВСЕМ уникальным валидным ИНН файла разом, здесь, один раз на весь
    # прогон preview (ПРАВИЛО №6 — contractor_resolve.find_contractor_ids_
    # by_inns, тот же normalize_inn, что и везде).
    all_group_inns = [g.get("inn") for g in groups]
    contractor_ids_by_inn = await find_contractor_ids_by_inns(db, all_group_inns)

    missing_inn_groups: list = []

    for group in groups:
        group_rows = [
            rows_by_num[rn] for rn in group["rows"]
            if not rows_by_num[rn]["skip"] and not rows_by_num[rn].get("existing_purchase")
        ]
        if group_rows:
            purchases_count += 1

        # Владелец (16.10.2026): группа БЕЗ валидного ИНН поставщика (10/12
        # цифр, normalize_inn) — не ищем существующую закупку вовсе (ниже),
        # ПОМЕЧАЕМ предупреждением (видно на шаге групп мастера,
        # FactImportStepGroups.vue уже рисует group.warnings — ПРАВИЛО №6,
        # не второе поле) и считаем в totals.missing_supplier_inn. ИНН есть,
        # но контрагента с таким ИНН в базе нет — это НЕ предупреждение
        # (обычный новый поставщик, которого ещё не было в базе), просто нет
        # совпадения с существующей закупкой.
        norm_group_inn = _normalize_inn(group.get("inn"))
        group["supplier_inn_missing"] = not norm_group_inn
        if not norm_group_inn and group_rows:
            group["warnings"].append(
                "Не хватает ИНН поставщика — поставщик может быть указан неверно."
            )
            missing_inn_groups.append(group)

        if not group_rows:
            group["existing_matches"] = []
            group["needs_existing_decision"] = False
            continue

        group_amount = Decimal(str(group["contract_amount"])) if group["contract_amount"] else None
        matches = await existing_link_mod.find_existing_matches_for_group(
            db, subsidy_id, group_amount,
            group_inn=group.get("inn"), contractor_ids_by_inn=contractor_ids_by_inn,
            source_key=group.get("source_key"),
        )
        # Задача 4 владельца (16.10.2026): ИНН+№закупки[+№заказа] совпали
        # точно (source_key_match) — это та же закупка, НО если сумма файла
        # разошлась с суммой закупки — пометка в предупреждениях группы
        # (владелец: «обновлять сумму только если пользователь отметил,
        # иначе не трогать» — сама пометка ничего не меняет, решение по
        # сумме человек принимает отдельно, здесь только видимость).
        _sk_match = next((m for m in matches if m["kind"] == "source_key_match"), None)
        if _sk_match is not None and group_amount is not None and _sk_match.get("amount") is not None:
            _old_amt = Decimal(str(_sk_match["amount"]))
            if _old_amt != group_amount:
                group["warnings"].append(
                    f"Сумма изменилась: было {_rub(_old_amt)} → в файле {_rub(group_amount)} "
                    "(сумма закупки не обновлена — это пометка для проверки)"
                )
        if matches:
            file_row_planned_item_id = group_rows[0]["match"].get("planned_item_id")
            excess_units: list = []
            for m in matches:
                m["items"] = await existing_link_mod.build_existing_match_items(
                    db, m["id"], ctx, file_row_planned_item_id,
                )
                for it in m["items"]:
                    if it.get("suggested") and it["suggested"].get("planned_item_id"):
                        excess_units.append(_SimpleNamespace(
                            over_plan=False,
                            feo_planned_item_id=it["suggested"]["planned_item_id"],
                            feo_category_id=None,
                            quantity=it.get("qty"),
                            unit_price=it.get("price"),
                            total_price=it.get("total"),
                            item_name=it.get("name"),
                        ))
            if excess_units:
                excess_violations = await _collect_violations(db, excess_units, fallback_category_id=None)
                excess_by_fpi: dict = {}
                for v in excess_violations:
                    if v.get("feo_planned_item_id"):
                        excess_by_fpi.setdefault(v["feo_planned_item_id"], []).append(v["message"])
                for m in matches:
                    for it in m["items"]:
                        sug = it.get("suggested")
                        if sug and sug.get("planned_item_id") in excess_by_fpi:
                            it["warnings"] = excess_by_fpi[sug["planned_item_id"]]

        group["existing_matches"] = matches
        decided = group["key"] in existing_decisions
        # Задача 4 (16.10.2026): source_key_match — точное опознание той же
        # закупки (ИНН+№закупки[+№заказа]) — автоприменяется как same_amount,
        # НЕ требует решения человека (см. docstring resolve_group_decision).
        has_auto_same = any(m["kind"] in ("same_amount", "source_key_match") for m in matches)
        has_same_supplier_only = bool(matches) and not has_auto_same
        # «Скорее всего та же» (same_amount/source_key_match) — предвыбрано,
        # коммит может идти без явного решения. «Возможно» (same_supplier,
        # сумма другая) — решение обязательно (владелец: «импорт не идёт,
        # пока по каждому „возможно“ не выбрано»).
        group["needs_existing_decision"] = has_same_supplier_only and not decided

    # Задача B: агрегируем строки с существующей закупкой (row['existing_
    # purchase']) по id закупки — несколько строк файла могут указывать на
    # одну и ту же существующую закупку (разные плановые позиции одной
    # РЕЕ-...). build_preview_entries (existing_update.py) считает paid_add/
    # status_to; commit.py применит РОВНО этот же список (ПРАВИЛО №6).
    existing_update_buckets: dict[int, dict] = {}
    for r in out_rows:
        ep = r.get("existing_purchase")
        if not ep or r["skip"]:
            continue
        bucket = existing_update_buckets.setdefault(ep["id"], {
            "registry_number": ep["registry_number"],
            "status_from": ep["status"],
            "rows": [],
            "paid_sum": Decimal(0),
            "target_status": None,
            "is_advance": False,
        })
        bucket["rows"].append(r["row"])
        if r["paid"]:
            bucket["paid_sum"] += Decimal(str(r["paid"]))
        if r.get("is_advance"):
            bucket["is_advance"] = True
        rs = r["status"]
        if rs and (bucket["target_status"] is None or existing_update_mod.rank_of(rs) > existing_update_mod.rank_of(bucket["target_status"])):
            bucket["target_status"] = rs

    existing_updates_list = await existing_update_mod.build_preview_entries(db, existing_update_buckets)

    # Доп. задача (владелец, 07.10.2026): «при импорте об этом должно идти
    # уведомление» — предупреждение у строки уже есть (paid_not_delivered_
    # predicate выше), но на шаге итогов мастера (FactImportStepConfirm.vue)
    # его не видно среди плиток. Тот же предикат, тот же источник подписи
    # статуса (STATUS_LABELS) — не вторая формула (ПРАВИЛО №6). НЕ пропущенные
    # строки (skip=False) — это покрывает и обычные строки, и existing_purchase
    # (та же проверка read.status/.paid/.is_advance на уровне строки файла,
    # existing_purchase не меняет её «итоговый статус ниже delivered»).
    paid_not_delivered_rows: list[dict] = []
    paid_not_delivered_amount = Decimal(0)
    # Задача C (владелец, файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx): строки
    # 141/142/151 — статус «Оплачено», колонка «Оплачено» пуста; у строки
    # уже есть предупреждение (paid_status_without_paid_predicate выше), но
    # на шаге итогов мастера их не видно, и владелец принимает их за «Факт:
    # Сумма» строк со статусом «Оплачено» = «Оплачено» (расхождение
    # 438 376,10 ₽ с его подсчётом по Excel). Тот же предикат, не вторая
    # формула (ПРАВИЛО №6). Только НЕ пропущенные строки — ПОЛНОСТЬЮ
    # пропущенная строка не создаёт закупку/платёж вообще, в totals она уже
    # учтена отдельно (skipped_by_reason).
    paid_status_without_paid_rows: list[dict] = []
    paid_status_without_paid_amount = Decimal(0)
    for r in out_rows:
        if r["skip"]:
            continue
        if paid_not_delivered_predicate(r["paid"], r["status"], r["is_advance"]):
            paid_not_delivered_rows.append({
                "row": r["row"],
                "name": r["name"],
                "status_label": STATUS_LABELS.get(r["status"], r["status"]),
                "paid": r["paid"],
            })
            paid_not_delivered_amount += Decimal(str(r["paid"]))
        if paid_status_without_paid_predicate(r["status"], r["paid"]):
            fact_val = r["fact"]["amount"] if r["fact"]["amount"] is not None else 0
            paid_status_without_paid_rows.append({"row": r["row"], "name": r["name"], "fact": fact_val})
            paid_status_without_paid_amount += Decimal(str(fact_val))

    # Задание 07.10.2026 (п.4): собрать breakdown в контракт — коды статуса
    # в порядке GALA-стадий ("none" = «Без статуса / план закупок» первым,
    # дальше — statuses_mod.STATUS_CODES), подписи те же STATUS_LABELS, что и
    # у строк (ПРАВИЛО №6). Decimal → float только тут, на выходе.
    def _money(d: Decimal) -> float:
        return float(d)

    breakdown_statuses: list[dict] = []
    for code in ["none", *statuses_mod.STATUS_CODES]:
        bucket = breakdown_by_status.get(code)
        if bucket is None:
            continue
        label = "Без статуса / план закупок" if code == "none" else STATUS_LABELS.get(code, code)
        breakdown_statuses.append({
            "code": code,
            "label": label,
            "included": {
                "rows": bucket["included"]["rows"],
                "contract_amount": _money(bucket["included"]["contract_amount"]),
                "contract_amount_raw": _money(bucket["included"]["contract_amount_raw"]),
                "paid": _money(bucket["included"]["paid"]),
            },
            "skipped": {
                "rows": bucket["skipped"]["rows"],
                "contract_amount": _money(bucket["skipped"]["contract_amount"]),
                "contract_amount_raw": _money(bucket["skipped"]["contract_amount_raw"]),
                "paid": _money(bucket["skipped"]["paid"]),
            },
        })

    breakdown_skipped_by_reason = [
        {
            "code": code,
            "label": data["label"],
            "rows": sorted(data["rows"]),
            "contract_amount_raw": _money(data["contract_amount_raw"]),
            "paid": _money(data["paid"]),
        }
        for code, data in breakdown_skip_by_reason.items()
    ]

    breakdown = {
        "by_status": breakdown_statuses,
        "included_existing": {
            "rows": breakdown_existing["rows"],
            "paid": _money(breakdown_existing["paid"]),
        },
        "skipped_by_reason": breakdown_skipped_by_reason,
    }

    return {
        "format": detected["format"],
        "sheet": sheet,
        "header_row": detected["header_row"],
        "columns": cols,
        "rows": out_rows,
        "groups": groups,
        "statuses": statuses_mod.STATUS_CHOICES,
        "existing_updates": existing_updates_list,
        "totals": {
            "rows": len(out_rows),
            "purchases": purchases_count,
            "contract_amount": float(totals_contract),
            "paid_amount": float(totals_paid),
            "skipped": skipped_count,
            "existing_updates": len(existing_updates_list),
            "breakdown": breakdown,
            "paid_not_delivered": {
                "count": len(paid_not_delivered_rows),
                "amount": float(paid_not_delivered_amount),
                "rows": paid_not_delivered_rows,
            },
            # Задача C: rows_text — те же диапазоны строк, что и в
            # skipped_by_reason выше (_row_ranges_only, ПРАВИЛО №6).
            "paid_status_without_paid": {
                "count": len(paid_status_without_paid_rows),
                "fact_amount": float(paid_status_without_paid_amount),
                "rows": paid_status_without_paid_rows,
                "rows_text": _row_ranges_only(sorted(r["row"] for r in paid_status_without_paid_rows)),
            },
            # Правка 12.10.2026 (п.4б): «Экономия по позициям: N поз., сумма»
            # на шаге итогов мастера (FactImportStepConfirm.vue, по образцу
            # paid_status_without_paid выше, ПРАВИЛО №6 — те же данные, что и
            # у предупреждения строки, не вторая формула).
            "economy": {
                "count": len(economy_rows),
                "amount": float(economy_total),
                "rows": economy_rows,
            },
            # Задача владельца (13.10.2026) — «Перерасход по позициям: N поз.,
            # сумма» на шаге итогов (FactImportStepConfirm.vue), зеркало economy
            # выше (ПРАВИЛО №6 — те же данные цикла, не вторая формула).
            "overspend": {
                "count": len(overspend_rows),
                "amount": float(overspend_total),
                "rows": overspend_rows,
            },
            # Владелец (16.10.2026) — счётчик групп без валидного ИНН
            # поставщика (существующая закупка для них не ищется вовсе, см.
            # выше), чтобы видеть масштаб на шаге итогов мастера, не только
            # на карточке каждой группы.
            "missing_supplier_inn": {
                "count": len(missing_inn_groups),
                "groups": [g["key"] for g in missing_inn_groups],
            },
        },
        "warnings": top_warnings,
    }
