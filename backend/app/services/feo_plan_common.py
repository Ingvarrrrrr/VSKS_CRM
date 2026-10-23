"""feo_plan_common.py — приватные хелперы, общие для 2+ модулей семейства feo_plan.

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). `_leaf_plan_manual` нужен и feo_plan_excess.py
(find_excess_culprit), и feo_plan_tz_checks.py (assert_tz_not_over_plan) —
единственная точка формулы плана листа при plan_source='manual_sum', чтобы
она не разошлась при разъезде по разным файлам (ПРАВИЛО №6).

`_order_substituted_plan` — вторая единая точка (задача владельца, Волна 1 п.13,
2026-09-13, «сумма запланированного неправильно считается»): find_excess_culprit
ДО этой задачи считал вклад узла в план ТОЛЬКО как Σ FeoPlannedItem/manual_plan_amount
(_leaf_plan_manual), полностью игнорируя замещение «заказ вместо плана»
(compute_feo_plan_tree._own_plan_and_forecast, задача владельца 2026-08-05) — из-за
этого сумма контрибьюторов find_excess_culprit могла НЕ совпадать с
compute_feo_plan_tree.plan (и, соответственно, с display/excess_amount, на которые
реально смотрит блокировка и плашка «требуется согласование»). Теперь обе функции
зовут именно эту точку.
"""
from typing import Optional


def _order_substituted_plan(
    qty: float, ordered: float, ordered_qty: float, plan_manual: float, is_payroll: bool = False,
) -> float:
    """Общая точка формулы «заказ замещает план, когда количество набрано
    целиком» (compute_feo_plan_tree._own_plan_and_forecast, задача владельца
    2026-08-05, ФОРМУЛА v2 — см. подробный docstring compute_feo_plan_tree) —
    используется И деревом (для листа и «собственной» части группы), И
    find_excess_culprit (feo_plan_excess.py), И committed_amounts.
    planned_item_contributions (построчно, по одной плановой позиции), И
    historical_fact_import/economy_preview.py — ПРАВИЛО №6: узел/позиция
    заказан(а) ПОЛНОСТЬЮ (qty > 0 and ordered_qty >= qty) → её вклад в план
    становится фактической суммой заказа (`ordered`) — экономия/переплата
    высвобождается; иначе (заказано частично или количество не задано) — план
    резервируется целиком (`plan_manual`), даже если что-то уже заказано
    дешевле/дороже.

    `is_payroll` (владелец, 22.10.2026, план humble-stirring-emerson.md, шаг
    1, «ФОТ не даёт экономии») — ОТКЛЮЧАЕТ замещение целиком: по статьям ФОТ
    (app.services.feo_payroll.payroll_category_ids, с наследованием) план
    НИКОГДА не заменяется суммой выплаты/заказа, даже если количество/сумма
    совпали — иначе невыплаченная часть зарплаты молча становится «экономией»
    и утекает в «Свободно» (прод, ХРО_2026: 1 шт плана × 13 277 966,84,
    выплачено 1 шт × 8 235 337,78 — количество «набралось» целиком, хотя
    деньги не выплачены). Невыплаченный остаток продолжает входить в
    «Запланировано» и показывается строкой «ФОТ» карточки «Можно
    перераспределить» (см. app.services.redistributable_raw — kind=='payroll'
    уже существующей разбивки, та же точка, ПРАВИЛО №6: вторая формула для
    ФОТ не вводится, просто эта замена отключается). Снять защиту на ОДНОЙ
    статье можно только явной кнопкой «Закрыть ФОТ по статье»
    (app.routers.feo_payroll_close — создаёт запись FeoCategory.payroll_closed,
    читаемую вызывающим кодом ДО передачи is_payroll сюда)."""
    if is_payroll:
        return plan_manual
    return ordered if (qty > 0 and ordered_qty >= qty) else plan_manual


def _leaf_plan_manual(
    plan_source: Optional[str], manual_plan_amount, items_total: float, excess_approved: bool,
) -> tuple:
    """Общая точка с compute_feo_plan_tree._manual_plan_for (тот же переключатель
    FeoCategory.plan_source, ОДИН узел) — задача 2, отчёт сессии 2026-09-03.

    _manual_plan_for — приватный closure ВНУТРИ compute_feo_plan_tree (завязан на
    батчевые словари всей субсидии: leaf_item_amt/own_manual_excess/
    latest_approval_by_cat), поэтому find_excess_culprit не может вызвать его
    напрямую — вместо этого воспроизводит ЕЁ ЖЕ формулу здесь, как отдельную
    независимо тестируемую точку (без доступа к closure-словарям, только на
    переданных аргументах). compute_feo_plan_tree._manual_plan_for сознательно
    НЕ трогалась при этом рефакторинге (следующая задача правит
    assert_no_unapproved_excess/эту область отдельно) — идентичность формул
    доказывается тестом test_find_excess_culprit_uses_same_plan_source_formula
    в test_feo_plan_tree_scenarios.py, сравнивающим числа обеих функций на одних
    данных, а не совместным вызовом кода.

    ДО задачи 2 find_excess_culprit вообще не знал о plan_source — использовал
    REMOVED-формулу «оба поля planned_quantity и planned_amount не пустые →
    qty×amt, иначе Σ FeoPlannedItem» (угадывание по пустым полям), удалённую из
    compute_feo_plan_tree коммитом f8d68bc (2026-08-13, «способ расчёта плана
    задаётся переключателем, а не угадывается по пустым полям»). Из-за этого
    расхождения find_excess_culprit мог назвать пользователю цифру плана, НЕ
    совпадающую с той, из-за которой реально сработала блокировка.

    Формула (см. FeoCategory.plan_source, docstring compute_feo_plan_tree):
      'planned_items' (умолчание) — план узла = items_total (Σ активных
        FeoPlannedItem, считает вызывающий код), excess_plan_over_manual = 0.
      'manual_sum' — план узла = manual_plan_amount, ПОКА накопленное
        превышение (items_total − manual_plan_amount) не согласовано; когда
        excess_approved=True (последний PlanExcessApproval ИМЕННО этого узла
        approved) — план узла становится items_total.

    Возвращает (manual_plan_entered, plan_manual, excess_plan_over_manual) — те
    же три величины, что и первые три элемента кортежа _manual_plan_for."""
    items_total = float(items_total)
    if (plan_source or "planned_items") != "manual_sum":
        return 0.0, items_total, 0.0
    manual_amt = float(manual_plan_amount) if manual_plan_amount is not None else 0.0
    excess = items_total - manual_amt
    if excess <= 0.005:
        excess = 0.0
    plan_manual = manual_amt
    if excess > 0.005 and excess_approved:
        plan_manual = items_total
    return manual_amt, plan_manual, excess


def plan_floor_addition(own_plan_before_floor: float, own_over: float, own_committed_all: float) -> float:
    """Третья единая точка (владелец, решение 02.10.2026, «договор входит в
    план» — план .planning/quick/2026-10-02-money-redistribution/PLAN.md,
    шаг 3): «пол» на СОБСТВЕННОЙ (без рекурсии по детям) части узла —
    own_committed_all не может быть больше «Запланировано» этой же собственной
    части (own_plan_before_floor — own-часть ДО пола, та же величина, что
    возвращает _order_substituted_plan/_own_plan_and_forecast own-веткой;
    own_over — собственный over_plan=true расход узла, plan_consumption_by_
    category.over).

    ⚠️ own_committed_all — committed ТОЛЬКО НЕпривязанных к FeoPlannedItem
    позиций (committed_amounts.committed_consumption_by_category с
    exclude_planned_item_linked=True), НО включая over_plan
    (include_over_plan=True) — НЕ node['committed'] целиком (который включает
    ещё и ПРИВЯЗАННЫЕ/над-плановые позиции): те уже учтены own-планом
    (leaf_item_committed_amt/committed_by_planned_item, своим путём, ЕСЛИ
    привязаны и не over_plan) и own_over (over_consumption, тоже
    exclude_planned_item_linked=True) своим — подставлять сюда ВСЕ позиции
    задвоило бы привязанную над-плановую сумму и ложно поднимало бы план
    (боевой регрессионный тест test_8_over_plan_included_in_committed_total_
    and_economy в test_money_committed.py — привязанная над-плановая позиция
    НЕ должна расширять plan узла). Вызывающий код (compute_feo_plan_tree.
    _own_plan_floor, find_excess_culprit) обязан передавать именно эту
    «НЕпривязанную+over» сумму, а не committed_consumption_all/node['committed'].

    Повод (владелец, 02.10.2026): категории без единой плановой позиции
    (0 позиций — импорт их никогда не заводил) или с суммой плановых позиций
    меньше факта договора — реальные законтрактованные деньги «терялись» из
    «Запланировано» (МИНПРОС_2026 — категория «Услуги по изготовлению
    брендированного комбинезона…», 0 плановых позиций, договор РЕЕ-2026-00850
    на 1 935 000 ₽ — «Свободно» считало их свободными, хотя они заняты).

    ОБЩАЯ точка для compute_feo_plan_tree (feo_plan_tree.py, scalar `plan` и
    типовой `_plan_by_kind` own-часть — через `_own_plan_floor`) И
    find_excess_culprit (feo_plan_excess.py, контрибьютор «пол: договор без
    плановой позиции») — ПРАВИЛО №6: дерево и контроль превышения обязаны
    читать ОДНУ И ТУ ЖЕ добавку, иначе Σ контрибьюторов разойдётся с
    node['display'] узла (test_feo_excess_culprit_matches_control.py), точно
    как раньше для _order_substituted_plan (см. докстринг модуля выше).

    Возвращает ТОЛЬКО добавку (≥0) — вызывающий код сам прибавляет её к своей
    own-плановой сумме и публикует отдельно (node['plan_floor_added']) для
    объяснения на экране «включено N ₽ договоров без плановой позиции»."""
    return max(0.0, own_committed_all - (own_plan_before_floor + own_over))


def manual_plan_gap(manual_plan_entered: float, items_total_raw: float) -> float:
    """Четвёртая единая точка (владелец, 23.10.2026, план humble-stirring-
    emerson.md, 🔵 «ваш пример по строкам» — карточка «Можно перераспределить»,
    строка «задано на категорию, но не расписано позициями»).

    Повод: статья «Задано на категорию» (plan_source='manual_sum', см.
    FeoCategory.plan_source) без плановых позиций ВООБЩЕ (ЦентрПоиск_2026:
    «Аренда автотранспортных средств…» план 372 000, позиций 0) или с суммой
    позиций МЕНЬШЕ заданной — не теряет свою долю ФЭО из «Можно
    перераспределить»: node['plan_manual'] УЖЕ считает эту статью полностью
    запланированной (manual_plan_entered, пока превышение не согласовано —
    см. _leaf_plan_manual выше), но app.services.redistributable_raw.
    not_committed_raw_rows видит ТОЛЬКО реальные FeoPlannedItem и для такой
    статьи возвращает 0 строк — разница (сама заданная сумма) «терялась»
    из подстрок карточки, хотя в её ИТОГЕ (budget_basis − committed) эти
    деньги уже сидели (находка владельца — ЦентрПоиск_2026 подстроки меньше
    итога на 6 703 025,12, ЦП_2026_2 — на 10 650 000,00).

    gap = max(0, заданная сумма узла СВОЯ (БЕЗ рекурсии по детям) − Σ
    активных FeoPlannedItem СВОИХ (БЕЗ рекурсии), ТА ЖЕ пара, что
    compute_feo_plan_tree передаёт в _manual_plan_for/own_items_raw) — когда
    позиций больше, чем заданная сумма (превышение, другая ветка, см.
    excess_plan_over_manual) gap=0 (max зажимает отрицательное), когда режим
    узла 'planned_items' (manual_plan_entered всегда 0 по построению
    _manual_plan_for) gap тривиально 0 — формула не требует отдельной
    проверки режима. Вызывающий код (compute_feo_plan_tree, node
    ['manual_plan_gap']) суммирует gap рекурсивно по поддереву, как и прочие
    аддитивные поля узла (ПРАВИЛО №6 — одна формула, не per-режимный if в
    каждом месте, где нужна эта строка карточки)."""
    return max(0.0, float(manual_plan_entered) - float(items_total_raw))


def manual_plan_gap_by_kind(gap: float, is_payroll: bool) -> dict:
    """Разбивка manual_plan_gap (см. функцию выше) по виду — владелец,
    23.10.2026 (правка после живой проверки): «строки «Можно
    перераспределить» по видам обязаны давать итог до копейки» — без этой
    разбивки Σ redistributable_by_kind была короче итога карточки ровно на
    manual_plan_gap (находка на синтетической субсидии 100/80/70/54: «юнит»
    46 = 20+16+10, но redistributable_by_kind.unspecified показывал только 36).

    Сама сумма — НЕ РАСПИСАНА позициями по определению (это и есть повод
    строки «задано на категорию, но не расписано позициями»), поэтому типа
    «товар»/«услуга» у неё взять неоткуда — ТА ЖЕ трактовка, что уже
    применяется ко ВСЕЙ declared-сумме узла, пока превышение над ней не
    согласовано (_manual_plan_for.plan_manual_by_kind, feo_plan_tree.py:
    «одно число manual_plan_amount, БЕЗ разбивки по позициям... целиком в
    KIND_UNSPECIFIED» — ПРАВИЛО №6, та же договорённость, не новая):
    payroll-категория (своя или по предку, feo_payroll.payroll_category_ids)
    — вся сумма идёт в payroll (как и бюджет/факт такой категории, см.
    _feo_by_kind/kind_of_by_category_id); иначе — целиком в unspecified."""
    from app.services.item_type_split import KIND_GOODS, KIND_PAYROLL, KIND_SERVICES, KIND_UNSPECIFIED
    g = float(gap)
    return {
        KIND_GOODS: 0.0,
        KIND_SERVICES: 0.0,
        KIND_PAYROLL: g if is_payroll else 0.0,
        KIND_UNSPECIFIED: 0.0 if is_payroll else g,
    }


def composite_group_metrics(quantities: list, unit_prices: list) -> tuple:
    """Единая формула агрегации ГРУППЫ строк закупки, привязанных к ОДНОЙ
    плановой позиции (FeoPlannedItem.is_composite=True) — задача «Составная
    плановая позиция» (сессия 2026-10-01). Используется И контролем «ТЗ не
    выше плана» (assert_tz_batch_not_over_plan/patch-гейт одной строки,
    app/services/feo_plan_tz_checks.py, app/routers/purchase_items_edit.py), И
    расходом плановой позиции (planned_item_consumption,
    app/services/feo_plan_fact.py) — ПРАВИЛО №6, формула не дублируется.

    Пример владельца: плановая «Проживание и питание участников» на 133 чел.,
    закупка — ДВЕ строки: «проживание» 133×1265 и «питание» 133×735, обе
    привязаны к одной плановой позиции. Без составного режима количество
    строк сложилось бы (266 > 133 план) и цена за единицу взялась бы
    максимумом (1265 < план OK, хотя по факту на человека уходит 2000 ₽
    совокупно). is_composite переключает ОБЕ формулы:
      - quantities (количества строк группы, включая саму строку) → берётся
        MAX, а не сумма: 133 и 133 → 133, совпадает с планом;
      - unit_prices (цены за единицу строк группы) → берётся СУММА, а не
        максимум: 1265 + 735 = 2000, сравнивается с unit_price плана.
    Сумма группы (total_price) этой функцией НЕ считается — она остаётся
    суммой сумм строк, как и в обычном (не составном) режиме, формула не
    меняется.

    Пустые списки → (Decimal('0'), Decimal('0')) — вызывающий код не должен
    звать эту функцию для группы без строк, но ноль безопаснее исключения.
    """
    from decimal import Decimal

    qtys = [Decimal(str(q)) if q is not None else Decimal("0") for q in quantities]
    prices = [Decimal(str(p)) if p is not None else Decimal("0") for p in unit_prices]
    qty = max(qtys) if qtys else Decimal("0")
    price = sum(prices, Decimal("0"))
    return qty, price
