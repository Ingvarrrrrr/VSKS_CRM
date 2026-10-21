"""POST /commit — одна транзакция на прогон: предпросмотр ещё раз (тот же
код, та же группировка — ПРАВИЛО №6, не второй расчёт) → запись.

Для каждой группы (не skip-строки): insert_purchase_with_items с позициями
по ФАКТУ → если есть договор (contracted/paid): copy_items_to_contract с
теми же числами + временный № + ensure_contract_linked → recalc_purchase_
money → платёж «по отметке» + recompute_purchase_payments → PurchaseEvent.
Без register_*_approvals и notify_* (владелец: «уведомления и согласования
не запускаются»).

db.commit() делает ВЫЗЫВАЮЩИЙ (роутер) — здесь только flush, чтобы вся
операция была одной транзакцией.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.historical_fact_import.preview import build_preview
# ПРАВИЛО №6: формат суммы в ₽ для текста отказа — переиспользуем
# _fmt_money шаблонов документов (единственный существующий money-форматтер
# на бэкенде с нужным видом «19 800,80»), не заводим второй.
from app.services.documents.formatting import _fmt_money
# Дефект (прод, субсидия «ХО (копия)», 2026-10-05): файл импорта факта несёт
# «Товар»/«Услуга» как в оригинале (регистр/форма — произвольные), row["item_type"]
# остаётся СЫРЫМ текстом файла (preview.py его просто копирует для показа
# человеку как есть). normalize_item_type — ЕДИНСТВЕННЫЙ источник нормализации
# (app/services/item_types.py, ПРАВИЛО №6) — применяем его ЗДЕСЬ, в момент
# записи в purchase_items.item_type/fake_item для плановой позиции, чтобы в
# БД попадало каноническое значение ("товар"/"услуга"/"работа"), а не текст
# файла. Разбивка товары/услуги (item_type_split.py::kind_of) уже сама
# нормализует на чтении — этот фикс не про неё, а про то, что должно лежать
# в самой колонке для любого другого потребителя, который сравнивает
# item_type буквально (PurchaseItemsEditor.vue и т.п. ждут "товар"/"услуга").
from app.services.item_types import normalize_item_type
# ПРАВИЛО №6: ранг статуса — ОДИН источник (existing_update.py), и для
# «наивысшая стадия строк группы» здесь, и для «поднимать статус СУЩЕСТВУЮЩЕЙ
# закупки только вверх» там — раньше это была вторая копия того же словаря.
from app.services.historical_fact_import.existing_update import RANK as _RANK
# Группировка по договору (владелец, 16.10.2026, шаг 2) — виды договора +
# разбор на заказы/лимит УЖЕ посчитаны build_preview() (ПРАВИЛО №6, тот же
# расчёт, не второй) — здесь только читаем group["contract_*"] и создаём
# голову+заказы вместо одной плоской закупки.
from app.services.historical_fact_import import contract_groups as contract_groups_mod
# Нумерация заказов внутри рамочного договора — ОДНА функция (ПРАВИЛО №6),
# та же, что уже отладил загрузчик ФАДМ (scripts/fadm_sheet_load/sheet_v2_build.py).
from app.routers.purchase_budget import _assign_framework_seq


def _format_rub(v) -> str:
    formatted = _fmt_money(v)
    return f"{formatted} ₽" if formatted else "0,00 ₽"


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    return Decimal(str(v))


def _parse_iso_date(s):
    if not s:
        return None
    from datetime import date
    return date.fromisoformat(s)


async def commit_import(
    db: AsyncSession,
    subsidy_id: int,
    current_user,
    content: bytes,
    filename: str,
    sheet: Optional[str],
    mapping: Optional[dict],
    decisions: Optional[dict],
) -> dict:
    decisions = decisions or {}
    preview = await build_preview(db, subsidy_id, content, filename, sheet, mapping, decisions)

    # 🔵 правка 3 (план breezy-mixing-lovelace.md, Часть А): «Импорт не идёт,
    # пока по каждому „возможно“ не выбрано „та же / другая“» — needs_
    # existing_decision=True у группы означает kind='same_supplier' без
    # решения (preview.py её не предвыбирает). До записи ЧЕГО-ЛИБО в БД.
    from fastapi import HTTPException
    undecided = [g for g in preview["groups"] if g.get("needs_existing_decision")]
    if undecided:
        # Дефект приёмки (02.10.2026): текст отказа показывал служебный ключ
        # группы («supplier|офисмаг») — заменён на поставщика и сумму группы,
        # понятные человеку без знания внутреннего ключа.
        human = "; ".join(
            f'{g.get("supplier") or "(без поставщика)"} — {_format_rub(g.get("contract_amount"))}'
            for g in undecided
        )
        raise HTTPException(
            400,
            "Нужно решить, та же это закупка или другая: "
            f"{human}",
        )

    from app.models.fact_import_run import FactImportRun
    from app.models.subsidy import Subsidy
    from app.models.contractor import Contractor
    from app.models.payment import Payment
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseEvent
    from app.models.purchase_comment import PurchaseComment
    from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate
    from app.services.contractor_resolve import find_or_create_contractor
    from app.services.vehicle_org_matching import normalize_inn as _normalize_inn_commit
    from app.services.purchase_create_core import insert_purchase_with_items
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.services.purchase_payments import recompute_purchase_payments
    from app.services.historical_fact_import import existing_link as existing_link_mod
    from app.services.historical_fact_import import existing_update as existing_update_mod

    subsidy = await db.get(Subsidy, subsidy_id)

    run = FactImportRun(
        subsidy_id=subsidy_id,
        user_id=getattr(current_user, "id", None),
        filename=filename,
        sheet=preview.get("sheet") or sheet,
        format=preview["format"],
        mapping=mapping or {},
        decisions=decisions,
        status="committed",
    )
    db.add(run)
    await db.flush()

    contract_confirmed = {int(r) for r in (decisions.get("contract_confirmed_rows") or [])}
    over_plan_decisions = decisions.get("over_plan") or {}
    supplier_overrides = decisions.get("supplier_overrides") or {}
    row_overrides = decisions.get("row_overrides") or {}

    rows_by_num = {r["row"]: r for r in preview["rows"]}
    created_refs: dict = {
        "contractor_ids": [], "contract_ids": [], "planned_item_ids": [], "purchase_ids": [],
        # 🟢🔵 «та же закупка» (Часть А) — позиции СУЩЕСТВУЮЩЕЙ закупки,
        # привязанные к плану этим прогоном; rollback.py восстанавливает их
        # прежние значения feo_planned_item_id/feo_category_id.
        "existing_match_item_backups": [],
        # Задача B («Оплачено, но уже в закупке») — закупки, которым этот
        # прогон поднял статус/добавил оплату БЕЗ создания новой закупки;
        # rollback.py восстанавливает поля закупки из backup.
        "existing_update_backups": [],
    }
    purchases_created = 0
    payments_created = 0
    contractors_created = 0

    # Дерево ФЭО относит факт/заказано/законтрактовано к категории через
    # COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id) —
    # найдено соседней сессией на прогоне 02.10 (обе колонки оставались
    # NULL, импортированные закупки «невидимы» в дереве). feo_planned_item_id
    # сам по себе дерево НЕ читает для разнесения по узлам — обязана быть
    # ещё и feo_category_id на каждой позиции, см. FeoPlannedItem.feo_category_id.
    _fpi_cat_cache: dict[int, Optional[int]] = {}

    async def _category_for_planned_item(fpi_id: Optional[int]) -> Optional[int]:
        if not fpi_id:
            return None
        if fpi_id not in _fpi_cat_cache:
            from app.models.feo_planned_item import FeoPlannedItem
            fpi = await db.get(FeoPlannedItem, fpi_id)
            _fpi_cat_cache[fpi_id] = fpi.feo_category_id if fpi else None
        return _fpi_cat_cache[fpi_id]

    existing_decisions = decisions.get("existing_match") or {}
    existing_match_report: list[dict] = []

    for group in preview["groups"]:
        # Задача B: строки, обновляющие СУЩЕСТВУЮЩУЮ закупку (row['existing_
        # purchase']) — применяются ОТДЕЛЬНО (existing_update_mod.apply_
        # existing_updates ниже, после цикла групп), не как позиции новой.
        group_rows = [
            rows_by_num[rn] for rn in group["rows"]
            if not rows_by_num[rn]["skip"] and not rows_by_num[rn].get("existing_purchase")
        ]
        if not group_rows:
            continue

        # 🟢🔵 «Та же закупка» (план breezy-mixing-lovelace.md, Часть А) —
        # новая закупка НЕ создаётся; непривязанные позиции СУЩЕСТВУЮЩЕЙ
        # закупки привязываются к строкам плана из файла (ПРАВИЛО №6 —
        # existing_link.apply_existing_match_decision переиспользует
        # feo_item_linking.link_purchase_item_to_planned, тот же сервис, что
        # и ручной POST /feo-planned-items/map).
        decision_info = existing_link_mod.resolve_group_decision(group, existing_decisions)
        if decision_info["action"] == "same" and decision_info["match"]:
            match = decision_info["match"]
            decision = existing_decisions.get(group["key"]) or {}
            apply_result = await existing_link_mod.apply_existing_match_decision(
                db,
                purchase_id=match["id"],
                items_info=match.get("items") or [],
                item_links=decision.get("item_links") or {},
                current_user=current_user,
            )
            if apply_result["item_backups"]:
                created_refs["existing_match_item_backups"].extend(apply_result["item_backups"])
            for new_fpi_id in apply_result["created_planned_item_ids"]:
                created_refs["planned_item_ids"].append(new_fpi_id)

            existing_purchase = await db.get(Purchase, match["id"])
            if existing_purchase and apply_result["item_backups"]:
                await recalc_purchase_money(db, existing_purchase)

            db.add(PurchaseEvent(
                purchase_id=match["id"],
                user_id=getattr(current_user, "id", None),
                event_type="fact_import_existing_match",
                data={"import_run_id": run.id, "rows": group["rows"]},
            ))
            existing_match_report.append({
                "registry_number": match.get("registry_number"),
                "purchase_id": match["id"],
                "items_linked": len(apply_result["item_backups"]),
                "planned_items_created": len(apply_result["created_planned_item_ids"]),
            })
            continue

        # Группировка по договору (владелец, 16.10.2026, шаг 2) — тело цикла
        # «собрать позиции из набора строк» теперь СВОЯ функция: generic-путь
        # (одна закупка на всю группу) вызывает её один раз на group_rows,
        # рамочный путь (ниже, _create_framework_group) — один раз НА КАЖДЫЙ
        # заказ (своя подвыборка строк) — ПРАВИЛО №6, не вторая копия тела.
        async def _collect_items(rows_subset: list) -> tuple:
            items_data: list = []
            total_amount = Decimal(0)
            paid_total = Decimal(0)
            target_status: Optional[str] = None
            group_category_ids: set = set()
            # Задача 2 (владелец, 05.10.2026) — «Аванс (да/нет)»: хоть одна
            # строка группы с is_advance=True → созданная закупка несёт
            # is_prepayment=True (оплачено ДО поставки, статус уже override-
            # нут preview.py в "ordered" — committed_amounts.py уже признаёт
            # её законтрактованной, но «Поставлено» она не формирует, пока
            # статус не станет delivered+).
            group_is_advance = False

            for row in rows_subset:
                row_key = str(row["row"])
                override = row_overrides.get(row_key) or {}
                planned_item_id = override.get("planned_item_id") or row["match"].get("planned_item_id")

                # Позиция без совпадения — явно велели создать новую плановую
                # (иначе пропускается ещё на этапе предпросмотра/группировки,
                # т.к. ничего привязать не удастся, а план импорт не трогает
                # молча).
                if not planned_item_id and override.get("create_planned_item") and row["match"]["state"] == "not_found":
                    from app.services.plan_autoassign import create_auto_planned_item
                    eff_cat_id = override.get("feo_category_id")
                    if eff_cat_id:
                        fake_item = SimpleNamespace(
                            item_name=row["name"],
                            quantity=_dec(row["fact"]["qty"]) or _dec(row["plan"]["qty"]),
                            unit=row.get("unit"),
                            total_price=_dec(row["plan"]["amount"]) or _dec(row["fact"]["amount"]),
                            item_type=normalize_item_type(row.get("item_type")),
                        )
                        new_fpi = await create_auto_planned_item(db, fake_item, eff_cat_id, note="импортом факта (02.10.2026)")
                        planned_item_id = new_fpi.id
                        created_refs["planned_item_ids"].append(new_fpi.id)

                row_status = row["status"]
                # Правка (владелец, 16.10.2026, сверка карточек субсидии 26121
                # с листом GoodsService — 3 строки [187,207,217], статус
                # «Поставлено», «Итоговая цена за объём» (O) = буквальный 0,
                # а не пусто, при этом нет ни fact.qty, ни fact.price вовсе —
                # «0» в этой колонке тут не настоящая сумма (0 товаров не
                # поставляют со статусом «Поставлено»), а артефакт листа
                # (формула/пустая ячейка, посчитанная как 0). В ОТЛИЧИЕ от
                # случая, когда fact.amount=0 пришёл ВМЕСТЕ со своими qty/
                # price (это настоящий 0, не трогаем) — здесь весь факт-
                # комплект строки пуст, реальные числа есть только в плане
                # (L/K/I), 108 000 ₽ по трём таким строкам «пропадали» из
                # «Заказано»/«Поставлено» на карточке субсидии. Тот же
                # фоллбэк на plan.amount, что и ниже для None — не второй
                # механизм (Правило №6), просто условие None расширено.
                _fact_amount = row["fact"]["amount"]
                if (
                    _fact_amount == Decimal(0)
                    and row["fact"]["qty"] is None
                    and row["fact"]["price"] in (None, Decimal(0))
                ):
                    _fact_amount = None
                amount = _fact_amount if _fact_amount is not None else row["contracted"]
                # ИСПРАВЛЕНО (прод, 05.10.2026, РЕЕ-2026-02795 и др.): «Ведётся
                # работа» БЕЗ факта и БЕЗ договора (needs_contract_decision
                # ниже не взводится — для него нужен row["contracted"], а
                # здесь он пуст) — amount оставался None → _dec(None) or
                # Decimal(0) → total_price=0, хотя qty_dec/price_dec ниже ВСЁ
                # РАВНО берут plan.qty/plan.price (ненулевые) — позиция
                # выходила «50 × 8200 = 0,00». Фоллбэк на plan.amount ТОЙ ЖЕ
                # строки — тот же принцип, что и у обычного создания закупки
                # без факта (план = НМЦД, пока факта нет); planned_item_
                # consumption/recalc_purchase_money считают из total_price
                # позиции, вторая формула здесь не нужна (ПРАВИЛО №6).
                if amount is None:
                    amount = row["plan"]["amount"]

                if row["needs_contract_decision"]:
                    if row["row"] in contract_confirmed:
                        row_status = "contracted"
                        amount = row["contracted"]
                    else:
                        row_status = "work_in_progress"
                        amount = 0

                over_choice = over_plan_decisions.get(row_key)
                plan_amount = row["plan"]["amount"]
                if over_choice == "skip":
                    continue
                if over_choice == "trim" and plan_amount is not None and amount is not None and amount > plan_amount:
                    amount = plan_amount

                amount_dec = _dec(amount) or Decimal(0)
                qty_dec = _dec(row["fact"]["qty"]) or _dec(row["plan"]["qty"])
                price_dec = None
                if qty_dec and qty_dec != 0 and amount_dec:
                    price_dec = (amount_dec / qty_dec)
                else:
                    price_dec = _dec(row["fact"]["price"]) or _dec(row["plan"]["price"])

                item_category_id = await _category_for_planned_item(planned_item_id)
                if item_category_id:
                    group_category_ids.add(item_category_id)

                items_data.append(PurchaseItemCreate(
                    item_name=row["name"],
                    item_type=normalize_item_type(row.get("item_type")),
                    quantity=qty_dec,
                    unit=row.get("unit"),
                    unit_price=price_dec,
                    total_price=amount_dec,
                    feo_planned_item_id=planned_item_id,
                    feo_category_id=item_category_id,
                    match_confirmed=True,
                    # Часть объединённой позиции (план merged-item-parts.md)
                    # — уже решена build_preview() выше, override.plan_part_key
                    # учтён ТАМ (ПРАВИЛО №6 — одно место решения строка→часть,
                    # здесь просто читаем результат). Не найдено/не выбрана —
                    # None, закупка создаётся без части.
                    feo_plan_part_key=row["match"].get("plan_part_key"),
                ))
                total_amount += amount_dec
                if row["paid"]:
                    paid_total += _dec(row["paid"])
                if row.get("is_advance"):
                    group_is_advance = True

                # Задача владельца (21.10.2026, ХРО_2026) — строка ФОТ
                # (row["is_payroll"], решён ТАМ же, где единственный раз
                # решается ФОТ строки — preview.py, см. docstring выше про
                # _cat_id/payroll_cat_ids, ПРАВИЛО №6) с оплатой > 0 выходит
                # сразу «Оплачено»: выплата ЗП исполнена в момент
                # перечисления, промежуточных стадий (договор/заказано/
                # поставлено) у неё не бывает. Поднимаем ранг СТРОКИ до
                # максимального ('paid') перед общей ранжировкой ниже —
                # второй механизм выбора статуса не завели.
                if row.get("is_payroll") and _dec(row.get("paid")):
                    row_status = "paid"

                if row_status and (target_status is None or _RANK.get(row_status, 0) > _RANK.get(target_status, 0)):
                    target_status = row_status

            return items_data, total_amount, paid_total, target_status, group_category_ids, group_is_advance

        async def _create_framework_group(group: dict, group_rows: list, contractor_id: Optional[int],
                                            contract_kind: str, contract_orders: list) -> None:
            """Рамочный договор (владелец, 16.10.2026, шаг 2) — голова
            (Contract, без собственных позиций) + дочерняя закупка на КАЖДЫЙ
            заказ (order_no), parent_purchase_id=голова, нумерация заказов —
            `_assign_framework_seq` (ПРАВИЛО №6, тот же код, что и загрузчик
            ФАДМ). «Рамочный с суммой» — лимит строки «Установка предельной
            суммы договора» идёт в Contract.max_amount/Purchase.contract_price
            головы (сама строка НЕ позиция/заказ, contract_groups.py её уже
            отделил от списка заказов)."""
            nonlocal purchases_created, payments_created
            from app.models.contract import Contract

            contract_type = (contract_groups_mod.CONTRACT_TYPE_FRAMEWORK_WITH_AMOUNT
                              if contract_kind == contract_groups_mod.KIND_FRAMEWORK_WITH_AMOUNT
                              else contract_groups_mod.CONTRACT_TYPE_FRAMEWORK_CUMULATIVE)
            real_number = group.get("contract_number")
            real_date = _parse_iso_date(group.get("contract_date"))

            head_data = PurchaseCreate(
                subsidy_id=subsidy_id,
                status="contracted",
                contractor_id=contractor_id,
                purchase_method="single",
                purchase_contract_type=contract_type,
                subject=f'{group.get("supplier") or "(без поставщика)"} — рамочный договор '
                        f'(закупка {group.get("purchase_no") or ""})',
                items=[],
            )
            head, _ = await insert_purchase_with_items(db, head_data, current_user, items_data=[], total_nmck=None)
            head.import_run_id = run.id
            # Задача 4 владельца (16.10.2026) — тот же group["source_key"]
            # (ИНН+№ закупки, без № заказа — заказы несут свой ключ с ним,
            # см. child.source_key ниже), что и у «разовой» закупки: повторная
            # заливка того же файла опознаёт ГОЛОВУ договора точно и не
            # заводит вторую (find_existing_matches_for_group срабатывает на
            # уровне группы ДО входа в этот рамочный путь, см. commit.py выше).
            head.source_key = group.get("source_key")
            await existing_update_mod.materialize_contract(
                db, head, force_temp_number=True, real_number=real_number, real_date=real_date,
            )

            limit_amount = group.get("contract_limit_amount")
            if limit_amount:
                contract = await db.get(Contract, head.contract_id)
                if contract:
                    contract.max_amount = Decimal(str(limit_amount))
                head.contract_price = Decimal(str(limit_amount))

            db.add(PurchaseEvent(
                purchase_id=head.id,
                user_id=getattr(current_user, "id", None),
                event_type="fact_import",
                data={"import_run_id": run.id, "rows": group["rows"], "role": "framework_head"},
            ))
            purchases_created += 1
            created_refs["purchase_ids"].append(head.id)
            _flag_missing_inn_comment(head.id)

            for order in contract_orders:
                order_row_nums = set(order.get("rows") or [])
                order_rows = [r for r in group_rows if r["row"] in order_row_nums]
                if not order_rows:
                    continue
                (order_items, order_total, order_paid, order_status,
                 order_category_ids, order_is_advance) = await _collect_items(order_rows)
                if not order_items or not order_status:
                    continue
                order_category_id = next(iter(order_category_ids)) if len(order_category_ids) == 1 else None
                # Владелец (16.10.2026) — тот же приём, что и у обычной
                # (не рамочной) закупки ниже: несколько категорий ФЭО среди
                # позиций ЗАКАЗА → feo_per_item=True, feo_category_id=None,
                # у каждой позиции своя feo_category_id (уже пишется выше).
                order_feo_per_item = len(order_category_ids) > 1

                child_data = PurchaseCreate(
                    subsidy_id=subsidy_id,
                    status=order_status,
                    contractor_id=contractor_id,
                    purchase_method="single",
                    purchase_contract_type=contract_type,
                    feo_category_id=order_category_id,
                    feo_per_item=order_feo_per_item,
                    order_number=order.get("order_no") or None,
                    subject=f'Заказ {order.get("order_no")} — {group.get("supplier") or ""}',
                    items=order_items,
                )
                child, _ = await insert_purchase_with_items(
                    db, child_data, current_user, items_data=order_items, total_nmck=order_total,
                )
                child.import_run_id = run.id
                child.parent_purchase_id = head.id
                # Задача 4 владельца (16.10.2026) — у рамочного дочернего
                # заказа ключ несёт И № заказа (E), не только № закупки (D):
                # несколько заказов одного договора иначе слиплись бы в один
                # source_key (см. docstring build_source_key).
                from app.services.vehicle_org_matching import normalize_org_name as _norm_org
                child.source_key = contract_groups_mod.build_source_key(
                    contract_groups_mod.valid_inn(group.get("inn")),
                    group.get("purchase_no"),
                    order.get("order_no"),
                    supplier_fallback=_norm_org(group.get("supplier")) or None,
                )
                if order_is_advance:
                    child.is_prepayment = True
                if child.planned_total_price is None:
                    child.planned_total_price = order_total
                    child.total_nmck = order_total
                    child.nmck = order_total

                if order_status in ("contracted", "ordered", "delivered", "paid"):
                    # Заказ наследует номер/дату договора ГОЛОВЫ (тот же
                    # договор — ensure_contract_linked внутри materialize_
                    # contract сведёт их в ОДИН Contract по (номер,
                    # контрагент, дата), как и голову).
                    await existing_update_mod.materialize_contract(
                        db, child, real_number=head.contract_number, real_date=head.contract_date,
                    )
                else:
                    child.contract_price = None
                await _assign_framework_seq(child, db)

                if order_paid > 0:
                    pay = Payment(
                        purchase_id=child.id, amount=order_paid, payment_source="manual",
                        confirmed_by_statement=False, import_run_id=run.id,
                    )
                    db.add(pay)
                    payments_created += 1
                    await db.flush()
                    await recompute_purchase_payments(db, child.id)

                db.add(PurchaseEvent(
                    purchase_id=child.id,
                    user_id=getattr(current_user, "id", None),
                    event_type="fact_import",
                    data={"import_run_id": run.id, "rows": order.get("rows") or [], "role": "framework_order",
                          "order_no": order.get("order_no")},
                ))
                purchases_created += 1
                created_refs["purchase_ids"].append(child.id)

        async def _resolve_group_contractor() -> Optional[int]:
            # Поставщик группы — explicit override (contractor_id) либо
            # найден/создан по ИНН группы (точная нормализация, без fuzzy —
            # lesson feedback_dedup_exact_only), ПРАВИЛО №6: find_or_create_
            # contractor.
            #
            # Владелец (16.10.2026): раньше сюда всегда передавался inn=None
            # (ИНН группы не использовался вовсе — контрагент искался/
            # создавался ТОЛЬКО по названию, даже когда в файле есть валидный
            # ИНН поставщика). Теперь ИНН группы передаётся, а поиск ПО
            # ИМЕНИ внутри find_or_create_contractor разрешён ТОЛЬКО когда
            # есть валидный ИНН (match_by_name=bool(ИНН)) — без ИНН совпадение
            # одних и тех же слов в названии у разных организаций больше не
            # привязывает новую закупку к чужому контрагенту, всегда
            # создаётся новый (тот же риск ложного совпадения, который
            # existing_link.py теперь тоже не допускает для поиска
            # существующей закупки).
            nonlocal contractors_created
            cid = supplier_overrides.get(group["key"])
            if cid is None and group.get("supplier"):
                max_id_before = (await db.execute(select(func.coalesce(func.max(Contractor.id), 0)))).scalar()
                group_norm_inn = _normalize_inn_commit(group.get("inn"))
                # Дефект (прод, лист GoodsService владельца, 16.10.2026):
                # колонка «ИНН» у части строк несёт текст-заглушку («Не
                # найден» и т.п.), не сам ИНН. Раньше сюда всегда шёл
                # inn=None — заглушка никогда не попадала в Contractor.inn.
                # Передавать «сырое» group.get("inn") напрямую, когда оно НЕ
                # прошло normalize_inn, — ломает contractors.ix_contractors_
                # inn_unique: ВТОРОЙ поставщик с той же заглушкой («Не
                # найден») не может быть создан (unique по TRIM(inn)).
                # Передаём инн только когда он валиден; невалидный —
                # ВСЕГДА None (как и раньше), независимо от match_by_name.
                cid = await find_or_create_contractor(
                    db, group["supplier"], (group.get("inn") if group_norm_inn else None),
                    org_id=getattr(subsidy, "org_id", None),
                    match_by_name=bool(group_norm_inn),
                )
                if cid and cid > max_id_before:
                    contractors_created += 1
                    created_refs["contractor_ids"].append(cid)
            return cid

        _MISSING_INN_COMMENT = "[Импорт факта] Не хватает ИНН поставщика — поставщик может быть указан неверно."

        def _flag_missing_inn_comment(purchase_id: Optional[int]) -> None:
            # Владелец (16.10.2026): предупреждение «нет ИНН поставщика»,
            # которое видно на шаге групп мастера (preview.py — group.
            # warnings), должно остаться видимым и ПОСЛЕ загрузки на
            # карточке созданной закупки — переиспользуем уже существующий
            # механизм комментариев закупки (PurchaseComment, тот же, что и
            # системные авторассылки — routers/purchase_ops.py,
            # ПРАВИЛО №6), не заводим новое поле на Purchase/PurchaseEvent.
            if not purchase_id or not group.get("supplier_inn_missing"):
                return
            db.add(PurchaseComment(
                purchase_id=purchase_id,
                user_id=getattr(current_user, "id", None),
                user_name=getattr(current_user, "full_name", None) or getattr(current_user, "email", None),
                text=_MISSING_INN_COMMENT,
            ))

        # Группировка по договору (владелец, 16.10.2026, шаг 2) — «Рамочный
        # накопительный»/«Рамочный с суммой» (contract_groups.py уже разобрал
        # группу на заказы в preview.py) → голова-договор + дочерняя закупка
        # НА КАЖДЫЙ заказ (order_no), вместо одной плоской закупки на всю
        # группу. «Разовый» (или колонки «Тип договора»/«Номер заказа» в
        # файле вовсе нет — group.get("contract_kind") тогда None) идёт
        # старым путём ниже, без изменений.
        contract_kind = group.get("contract_kind")
        contract_orders = group.get("contract_orders") or []
        if contract_kind in (contract_groups_mod.KIND_FRAMEWORK_CUMULATIVE,
                              contract_groups_mod.KIND_FRAMEWORK_WITH_AMOUNT) and contract_orders:
            contractor_id = await _resolve_group_contractor()
            await _create_framework_group(group, group_rows, contractor_id, contract_kind, contract_orders)
            continue

        items_data, total_amount, paid_total, target_status, group_category_ids, group_is_advance = \
            await _collect_items(group_rows)
        if not items_data or not target_status:
            continue

        contractor_id = await _resolve_group_contractor()

        # Purchase.feo_category_id — заполняем только когда ВСЕ позиции группы
        # из одной категории (как create_purchase для обычной, не per-item,
        # закупки); при нескольких категориях оставляем None и ставим
        # feo_per_item=True (владелец, 16.10.2026 — «у каждого товара своя
        # категория», как ручная форма закупки делает уже сейчас; раньше
        # этот флаг здесь не ставился вовсе, хотя per-item feo_category_id
        # на строках уже писался — карточка закупки без feo_per_item=True не
        # показывает категорию у товаров, см. PurchaseItemsEditor.vue).
        group_category_id = next(iter(group_category_ids)) if len(group_category_ids) == 1 else None
        group_feo_per_item = len(group_category_ids) > 1

        data = PurchaseCreate(
            subsidy_id=subsidy_id,
            status=target_status,
            contractor_id=contractor_id,
            purchase_method="single",
            feo_category_id=group_category_id,
            feo_per_item=group_feo_per_item,
            items=items_data,
        )
        p, _created_items = await insert_purchase_with_items(
            db, data, current_user, items_data=items_data, total_nmck=total_amount,
        )
        p.import_run_id = run.id
        # Задача 4 владельца (16.10.2026) — ключ повторной заливки (см.
        # docstring build_source_key в contract_groups.py); None, когда
        # группа не смогла его построить (нет настоящего ИНН/№ закупки) —
        # закупка просто не находится точно при повторном прогоне, как и
        # раньше коммита этой задачи.
        p.source_key = group.get("source_key")
        if group_is_advance:
            p.is_prepayment = True

        # «План не трогаем, но у ИСТОРИЧЕСКОЙ закупки своего плана не было —
        # план=факт на момент постановки» (см. docstring recalc_purchase_money:
        # для уже «замороженного» статуса planned_total_price не пишется сам —
        # заполняем снимок здесь, один раз, вручную, не заводя второй писатель).
        if p.planned_total_price is None:
            p.planned_total_price = total_amount
            p.total_nmck = total_amount
            p.nmck = total_amount

        if target_status in ("contracted", "ordered", "delivered", "paid"):
            # ПРАВИЛО №6: тот же путь, что и «обновить СУЩЕСТВУЮЩУЮ закупку»
            # (apply_existing_updates ниже) — temp-номер/договорные позиции/
            # привязка/пересчёт вынесены в existing_update.materialize_contract.
            # force_temp_number=True — insert_purchase_with_items уже мог
            # подставить дефолтный contract_number («{год}/{id}»), для новой
            # закупки он ВСЕГДА перезаписывается временным (как раньше), КРОМЕ
            # случая, когда группировка по договору (владелец, 16.10.2026,
            # шаг 2) дала настоящий номер/дату — тогда они побеждают.
            await existing_update_mod.materialize_contract(
                db, p, force_temp_number=True,
                real_number=group.get("contract_number"),
                real_date=_parse_iso_date(group.get("contract_date")),
            )
        else:
            # «В работе» — договора ещё нет (владелец: «не отмечена → закупка
            # в работе БЕЗ суммы договора»). recalc_purchase_money внутри
            # insert_purchase_with_items уже заполнил contract_price снимком
            # позиций (фолбэк «заморожен, договорных позиций нет, поле
            # пусто») — это верно для contracted/paid, но не для work_in_
            # progress без договора: откатываем.
            p.contract_price = None

        if paid_total > 0:
            pay = Payment(
                purchase_id=p.id,
                amount=paid_total,
                payment_source="manual",
                confirmed_by_statement=False,
                import_run_id=run.id,
            )
            db.add(pay)
            payments_created += 1
            await db.flush()
            await recompute_purchase_payments(db, p.id)

        db.add(PurchaseEvent(
            purchase_id=p.id,
            user_id=getattr(current_user, "id", None),
            event_type="fact_import",
            data={"import_run_id": run.id, "rows": group["rows"]},
        ))

        purchases_created += 1
        created_refs["purchase_ids"].append(p.id)
        _flag_missing_inn_comment(p.id)

    # Задача B («Оплачено, но уже в закупке») — preview['existing_updates']
    # уже посчитан build_preview() выше (тот же набор entries, что показывался
    # человеку на шаге итогов, ПРАВИЛО №6 — без повторного расчёта); здесь
    # только применяем: статус ТОЛЬКО вверх + платёж «по отметке».
    existing_update_backups = await existing_update_mod.apply_existing_updates(
        db, run_id=run.id, current_user=current_user, entries=preview.get("existing_updates") or [],
    )
    created_refs["existing_update_backups"] = existing_update_backups
    # apply_existing_updates создаёт Payment РОВНО когда entry['paid_add'] > 0
    # (см. его код) — считаем по тому же условию, второй счётчик не заводим.
    payments_created += sum(1 for e in (preview.get("existing_updates") or []) if (e.get("paid_add") or 0) > 0)

    run.purchases_created = purchases_created
    run.payments_created = payments_created
    run.contractors_created = contractors_created
    run.created_refs = created_refs

    from app.services.historical_fact_import.report import build_report
    run.report = await build_report(db, created_refs["purchase_ids"])
    # 🟢🔵 «оставлена существующая РЕЕ-…» (владелец, Часть А) — строки про
    # закупки, которые НЕ создавались, а были привязаны к плану.
    run.report = (run.report or []) + [
        {
            "purchase_id": r["purchase_id"],
            "registry_number": r["registry_number"],
            "existing_match": True,
            "items_linked": r["items_linked"],
            "planned_items_created": r["planned_items_created"],
            "missing": [],
        }
        for r in existing_match_report
    ] + [
        {
            "purchase_id": b["purchase_id"],
            "registry_number": None,
            "existing_update": True,
            "missing": [],
        }
        for b in existing_update_backups
    ]

    await db.flush()

    return {
        "run_id": run.id,
        "purchases_created": purchases_created,
        "payments_created": payments_created,
        "contractors_created": contractors_created,
        "existing_matches_linked": len(existing_match_report),
        "report_url": f"/api/subsidies/{subsidy_id}/fact-import/runs/{run.id}",
    }
