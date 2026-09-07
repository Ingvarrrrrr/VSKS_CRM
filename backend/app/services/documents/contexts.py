"""Построение docxtpl-контекста: позиции, суммы, ФЭО-пути, роль/отдел.

Зависит от formatting.py (форматирование) и doc_types.py (константы) —
вниз по иерархии модулей."""


from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from fastapi import HTTPException

from app.routers.purchases import is_framework_head
from app.services.fio import compose_fio as _compose_fio
from app.services.acceptance_docs import (
    derived_scalars as _acceptance_derived_scalars,
    total_amount as _acceptance_total_amount,
)

from .doc_types import CONTRACT_FAMILY_DOC_TYPES, FEO_PATH_UNRESOLVED_LABEL
from .formatting import (
    _fmt_date,
    _fmt_money,
    _merge_identical_items,
    _fio_to_genitive,
    _fio_to_initials,
)


# Phase 23: split "Президент Козеев Евгений Викторович" into structured parts
def _signatory_split(
    signatory: str,
    last: str | None = None,
    first: str | None = None,
    middle: str | None = None,
    position: str | None = None,
) -> dict:
    """Split signatory string into structured dict.

    If structured parts (last/first/middle) are provided — use them directly
    instead of applying heuristics to *signatory*.  *position* is taken from
    the argument when provided.

    Returns:
        position      — должность подписанта
        name_full     — ФИО (Фамилия Имя Отчество)
        name_genitive — rough genitive form
        name_initials — "Козеев Е.В."
    """
    if last:
        # Structured path — no heuristics needed
        name_full = _compose_fio(last, first, middle) or signatory or ""
        return {
            "position": position or "",
            "name_full": name_full,
            "name_genitive": _fio_to_genitive(name_full),
            "name_initials": _fio_to_initials(name_full),
        }

    # Legacy heuristic path (no structured parts available)
    if not signatory:
        return {"position": "", "name_full": "", "name_genitive": "", "name_initials": ""}
    parts = signatory.strip().split()
    if len(parts) <= 1:
        return {"position": "", "name_full": signatory, "name_genitive": signatory, "name_initials": signatory}
    # Heuristic: ФИО = last 3 words if ≥4 words total, else last 2
    if len(parts) >= 4:
        pos_words = parts[:-3]
        fio_words = parts[-3:]  # Фамилия Имя Отчество
    elif len(parts) == 3:
        # Could be "Иванов Иван Иванович" (no position) or "Директор Иванов Иван"
        # Heuristic: first word starts with uppercase → probably all ФИО or pos+2
        pos_words = []
        fio_words = parts
    else:
        pos_words = parts[:1]
        fio_words = parts[1:]

    resolved_position = position or " ".join(pos_words)
    name_full = " ".join(fio_words)

    return {
        "position": resolved_position,
        "name_full": name_full,
        "name_genitive": _fio_to_genitive(name_full),
        "name_initials": _fio_to_initials(name_full),
    }


def _sum_items_price(p) -> float:
    """Fallback: manually sum item.total_price when p.total_nmck is NULL."""
    items = getattr(p, "items", None) or []
    total = 0.0
    for it in items:
        try:
            total += float(getattr(it, "total_price", 0) or 0)
        except Exception:
            pass
    return total


def _build_acceptance_doc_context(p, doc_type: str, doc_indices_csv: str | None) -> dict:
    """Phase 27.2-01: build acceptance_doc_* context entries.

    For service_note_payment / service_note_advance:
      - читаем acceptance_docs JSONB (source of truth после Phase 26-H);
      - если doc_indices задан — фильтруем по индексам;
      - first doc → name/number/date; сумма всех selected → amount.
    Для остальных doc_type и при отсутствии JSONB-данных — legacy fallback.
    """
    SZ_TYPES = ("service_note_payment", "service_note_advance")

    def _legacy_amount():
        return _fmt_money(
            _acceptance_total_amount(p)
            or p.contract_price
            or p.planned_total_price
            or p.total_nmck
            or _sum_items_price(p)
            or 0
        )

    if doc_type in SZ_TYPES:
        raw_docs: list = p.acceptance_docs or []
        if raw_docs:
            # Filter by doc_indices if provided
            if doc_indices_csv:
                try:
                    indices = [int(i.strip()) for i in doc_indices_csv.split(",") if i.strip().isdigit()]
                    selected = [raw_docs[i] for i in indices if 0 <= i < len(raw_docs)]
                except Exception:
                    selected = raw_docs
            else:
                selected = raw_docs

            if selected:
                def _fmt_doc_date(raw_date) -> str:
                    if isinstance(raw_date, str) and raw_date:
                        try:
                            from datetime import date as _date
                            return _date.fromisoformat(raw_date).strftime("%d.%m.%Y")
                        except ValueError:
                            return raw_date
                    return _fmt_date(raw_date)

                total_amount = sum(float(d.get("amount") or 0) for d in selected)
                return {
                    "acceptance_doc_name":   "; ".join(d.get("name") or "" for d in selected),
                    "acceptance_doc_number": "; ".join(d.get("number") or "" for d in selected),
                    "acceptance_doc_date":   "; ".join(_fmt_doc_date(d.get("date") or "") for d in selected),
                    "acceptance_doc_amount": _fmt_money(total_amount) if total_amount else _legacy_amount(),
                }

    # Legacy fallback (all other doc_types OR no JSONB data)
    # ПРАВИЛО №6 (2026-09-07, группа D4): «одиночный» документ — из
    # app.services.acceptance_docs.derived_scalars (первый JSONB-документ, с
    # фолбэком на legacy-скаляры для немигрированных закупок), не напрямую
    # из скаляров.
    _acc = _acceptance_derived_scalars(p)
    return {
        "acceptance_doc_name":   _acc["name"] or "",
        "acceptance_doc_number": _acc["number"] or "",
        "acceptance_doc_date":   _fmt_date(_acc["date"]) or "",
        "acceptance_doc_amount": (
            _fmt_money(_acc["amount"])
            if _acc["amount"]
            else _legacy_amount()
        ),
    }


async def _build_contract_items_context(p, db) -> dict:
    """Phase 27.1 CD-5: build docxtpl context entries for {{contract_items}} loop.

    Returns dict with keys:
      - contract_items: list[dict] for loop in template (fields num/name/quantity/unit/unit_price/total)
      - contract_items_total: formatted string like "150 000,00 ₽"
      - contract_items_total_numeric: float for arithmetic in template
      - contract_item_count: int, len of contract_items list

    Fallback (D-08 deprecated alias): if purchase has no contract_items —
    populate from purchase_items so legacy templates keep working.
    """
    from app.models.contract_item import ContractItem as _ContractItem
    ci_query = await db.execute(
        select(_ContractItem)
        .where(_ContractItem.purchase_id == p.id)
        .order_by(_ContractItem.id)
    )
    contract_items_db = ci_query.scalars().all()

    result_list = []
    total_numeric = 0.0
    if contract_items_db:
        # Primary path: contract_items exist — use them
        for idx, ci in enumerate(contract_items_db, start=1):
            tot = float(ci.total) if ci.total else 0.0
            result_list.append({
                "num": idx,
                "name": ci.name or "",
                "quantity": float(ci.quantity) if ci.quantity else "",
                "unit": ci.unit or "",
                "unit_price": _fmt_money(ci.unit_price),
                "total": _fmt_money(ci.total),
                "total_numeric": tot,
            })
            total_numeric += tot
    else:
        # D-08 fallback: contract_items empty — use purchase_items as deprecated alias
        for idx, (item, qty, total) in enumerate(_merge_identical_items(getattr(p, "items", None) or []), start=1):
            tot = float(total) if total else 0.0
            result_list.append({
                "num": idx,
                "name": item.item_name or "",
                "quantity": float(qty) if qty else "",
                "unit": item.unit or "",
                "unit_price": _fmt_money(item.unit_price),
                "total": _fmt_money(total),
                "total_numeric": tot,
            })
            total_numeric += tot

    return {
        "contract_items": result_list,
        "contract_items_total": _fmt_money(total_numeric),
        "contract_items_total_numeric": total_numeric,
        "contract_item_count": len(result_list),
    }


def _build_contract_item_feo_paths(contract_items, plan_items, feo_path_nodes) -> list:
    """Путь ФЭО по ДОГОВОРНЫМ позициям для листа согласования.

    Требование владельца (2026-08-30): «В "Путь ФЭО" должны прописываться
    договорные категории, они должны совпадать с Плановыми». У ContractItem
    своего поля ФЭО нет — категория берётся у плановой PurchaseItem, из
    которой договорная позиция скопирована (``source_item_id``). Этим
    совпадение договорных категорий с плановыми гарантировано по построению:
    это буквально та же запись категории, а не пересчёт/эвристика.

    Договорная позиция без ``source_item_id`` (заведена вручную, а не
    копированием из плана) не может унаследовать чужую категорию — попадает
    в отдельную группу с меткой :data:`FEO_PATH_UNRESOLVED_LABEL`, чтобы в
    документе было видно, что категория не определена, вместо того чтобы
    либо промолчать, либо подставить произвольную.

    Args:
        contract_items: iterable ContractItem (source_item_id, total).
        plan_items: iterable PurchaseItem (id, feo_category_id) — используется
            только как справочник id → feo_category_id, суммы отсюда не берутся.
        feo_path_nodes: callable(category_id) -> list[FeoCategory] (root → leaf),
            та же функция, что строит feo_path/feo_level_* выше по контексту.

    Returns:
        [(path_str, Decimal total), ...] — по одной строке на категорию, в
        порядке первого появления среди contract_items; группа «не
        определена» (если есть) — последней.
    """
    plan_feo_by_id = {
        it.id: it.feo_category_id for it in (plan_items or []) if getattr(it, "feo_category_id", None)
    }
    cat_sums: dict = {}
    order: list = []
    unresolved_sum = Decimal("0")
    has_unresolved = False
    for ci in (contract_items or []):
        amt = Decimal(str(ci.total)) if ci.total is not None else Decimal("0")
        source_id = getattr(ci, "source_item_id", None)
        cid = plan_feo_by_id.get(source_id) if source_id else None
        if cid:
            if cid not in cat_sums:
                cat_sums[cid] = Decimal("0")
                order.append(cid)
            cat_sums[cid] += amt
        else:
            has_unresolved = True
            unresolved_sum += amt

    item_feo_paths: list = []
    for cid in order:
        cat_path = " → ".join(n.name.strip() for n in feo_path_nodes(cid))
        if cat_path:
            item_feo_paths.append((cat_path, cat_sums[cid]))
    if has_unresolved:
        item_feo_paths.append((FEO_PATH_UNRESOLVED_LABEL, unresolved_sum))
    return item_feo_paths


def _build_items_list_from_contract_items(p, resolve_photo=None) -> list[dict]:
    """items_list для договорных документов — ТОЛЬКО из ContractItem.

    Поля те же, что у items_list из purchase_items (num/name/description/
    type/item_kind/quantity/unit/unit_price/total_price/total/photo/code/
    norm_hours), чтобы существующие шаблоны (contract_tz.docx,
    contract_repair_framework.docx и др.), перебирающие {{items}}, работали
    без правки .docx. Никакого отката на purchase_items здесь нет —
    «Плановые не равно Договор» (требование владельца).
    """
    items_list: list[dict] = []
    for idx, ci in enumerate(getattr(p, "contract_items", None) or [], start=1):
        product = getattr(ci, "product", None)
        photo_url = getattr(product, "photo_url", None) if product else None
        items_list.append({
            "num": idx,
            "name": ci.name or "",
            "description": ((getattr(product, "description", None) if product else "") or ""),
            "type": "",
            "item_kind": (getattr(product, "item_kind", None) if product else None) or "товар",
            "quantity": float(ci.quantity) if ci.quantity else "",
            "unit": ci.unit or "",
            "unit_price": _fmt_money(ci.unit_price),
            "total_price": _fmt_money(ci.total),
            "total": _fmt_money(ci.total),
            "photo": resolve_photo(photo_url) if resolve_photo else "",
            # Поля для repair_framework (появятся позже, пока заглушки)
            "code": "",
            "norm_hours": "",
        })
    return items_list


def _build_items_list_from_purchase_items(p, tz_override_mode=None, resolve_photo=None) -> list[dict]:
    """items_list для плановых документов — из purchase_items (как раньше).

    Извлечено без изменения поведения из тела generate_document(), чтобы
    логика выбора источника (план vs договор) была тестируемой чистой
    функцией и переиспользовалась в обоих местах построения контекста.
    """
    description_mode = tz_override_mode or getattr(p, "description_mode", None) or "exact"
    items_list: list[dict] = []
    for idx, (item, qty, total) in enumerate(_merge_identical_items(getattr(p, "items", None) or []), start=1):
        photo_url = item.product.photo_url if item.product else None
        items_list.append({
            "num": idx,
            "name": item.item_name or "",
            "description": (
                (item.product.description_44fz if description_mode == "44fz" else item.product.description)
                if item.product else ""
            ) or "",
            "type": item.item_type or "",
            "item_kind": (item.product.item_kind if item.product else None) or "товар",
            "quantity": float(qty) if qty else "",
            "unit": item.unit or "",
            "unit_price": _fmt_money(item.unit_price),
            "total_price": _fmt_money(total),
            "total": _fmt_money(total),
            "photo": resolve_photo(photo_url) if resolve_photo else "",
            # Поля для repair_framework (появятся позже, пока заглушки)
            "code": "",
            "norm_hours": "",
        })
    return items_list


def _resolve_doc_amount(p, doc_type: str) -> tuple[float, bool]:
    """Вернуть (doc_amount_val, amount_is_planned) — сумму документа.

    Для CONTRACT_FAMILY_DOC_TYPES сумма берётся ТОЛЬКО из p.contract_price
    или суммы ContractItem, БЕЗ отката на НМЦК/план/сумму плановых позиций
    (требование владельца: «Плановые не равно Договор»). total_nmck/nmck
    сюда не входят — они остаются плановыми полями в контексте документа.
    ПРАВИЛО №6 (2026-09-05): эта формула — app.services.purchase_amounts.
    contract_amount(), не вторая копия («цена договора» — сознательно другой
    показатель, чем effective, см. её докстринг).

    Для остальных типов — ПРАВИЛО №6: единый расчёт эффективной суммы
    закупки по стадии, app.services.purchase_amounts.purchase_amounts()
    (раньше здесь была третья по счёту копия цепочки COALESCE/`or`).
    """
    from app.services.purchase_amounts import contract_amount as _contract_amount, purchase_amounts as _purchase_amounts_fn

    if doc_type in CONTRACT_FAMILY_DOC_TYPES:
        _ci = getattr(p, "contract_items", None) or []
        _ci_total = Decimal(str(sum((ci.total or 0) for ci in _ci))) if _ci else None
        amount = _contract_amount(p, contract_items_total=_ci_total)
        return float(amount) if amount is not None else 0.0, False
    _items = getattr(p, "items", None) or []
    _items_total = Decimal(str(sum((it.total_price or 0) for it in _items))) if _items else None
    _ci2 = getattr(p, "contract_items", None) or []
    _ci2_total = Decimal(str(sum((ci.total or 0) for ci in _ci2))) if _ci2 else None
    _amounts = _purchase_amounts_fn(p, contract_items_total=_ci2_total, items_total=_items_total)
    amount_is_planned = _amounts.effective_source in ("planned_total_price", "sum(purchase_items.total_price)")
    return float(_amounts.effective) if _amounts.effective is not None else 0.0, amount_is_planned


def _require_contract_items_for_doc(p, doc_type: str) -> None:
    """422, если запрошен договорной документ, а позиции договора не заполнены.

    Молчаливый откат на purchase_items здесь недопустим — «Плановые не равно
    Договор» (требование владельца). Код ошибки CONTRACT_ITEMS_REQUIRED тот
    же, что и в purchase_transitions.py (переход в «Заключён договор»), для
    единообразия обработки на фронте.

    Рамочная ГОЛОВА договора (is_framework_head — framework_cumulative/
    framework_with_amount, parent_purchase_id IS NULL) исключена: владелец
    (2026-08-31), «рамочные договора без закупок внутри должны согласовываться
    и печататься» — у головы может ещё не быть закупок внутри, а вместо
    позиций договора у неё общая сумма (Purchase.contract_price, см.
    _resolve_doc_amount). Дочерние закупки рамочного (parent_purchase_id
    заполнен) под это исключение НЕ подпадают — для них позиции обязательны
    как обычно.
    """
    if doc_type not in CONTRACT_FAMILY_DOC_TYPES:
        return
    if is_framework_head(p):
        return
    if getattr(p, "contract_items", None):
        return
    raise HTTPException(
        422,
        detail={
            "code": "CONTRACT_ITEMS_REQUIRED",
            "message": "В закупке пока не заполнены позиции договора",
            "hint": (
                "Договор печатается по списку «Как в договоре». Это отдельный список: "
                "в нём стоят наименования, количество и цены, о которых вы договорились "
                "с поставщиком, — они могут отличаться от того, что заявляли изначально. "
                "Сейчас этот список пуст, поэтому подставить в договор нечего.\n\n"
                "Что сделать: в блоке позиций нажмите «Скопировать из заявки» — плановые "
                "строки перенесутся в договорные. Затем поправьте наименования и цены так, "
                "как в подписываемом договоре, и сформируйте документ заново."
            ),
            "missing_fields": ["contract_items"],
            "doc_type": doc_type,
        },
    )


async def _resolve_user_dept(user, db, org_id: Optional[int] = None) -> str:
    """Возвращает название отдела пользователя для шаблона СЗ.

    Бизнес-правило: должность/отдел берутся per-org, по той организации,
    к которой привязана субсидия закупки. Если юзер в этой org в нескольких
    отделах — берём первый (по user_organizations.id).

    Приоритет:
      1) Department.name через user_organizations где org_id == org_id (если задан)
      2) Department.name через user_organizations первая запись (любая org)
      3) User.department (legacy строковое поле)
      4) "" если ничего нет
    """
    if user is None:
        return ""
    try:
        from app.models.user_organization import UserOrganization
        from app.models.department import Department
        from sqlalchemy import select as _sel
        # 1. В пределах org закупки
        if org_id is not None:
            res = await db.execute(
                _sel(Department.name)
                .join(UserOrganization, UserOrganization.dept_id == Department.id)
                .where(
                    UserOrganization.user_id == user.id,
                    UserOrganization.org_id == org_id,
                )
                .order_by(UserOrganization.id)
                .limit(1)
            )
            name = res.scalar_one_or_none()
            if name:
                return name
        # 2. Любая первая
        res = await db.execute(
            _sel(Department.name)
            .join(UserOrganization, UserOrganization.dept_id == Department.id)
            .where(UserOrganization.user_id == user.id)
            .order_by(UserOrganization.id)
            .limit(1)
        )
        name = res.scalar_one_or_none()
        if name:
            return name
    except Exception:
        pass
    # 3. Legacy строковое поле
    return getattr(user, "department", None) or ""


async def _resolve_user_position(user, db, org_id: Optional[int] = None) -> str:
    """Возвращает должность пользователя для шаблона СЗ.

    Тонкая обёртка над app.services.user_position.resolve_user_position —
    единственном источнике правил резолюции (Правило №6: не считать должность
    заново в каждом месте). Приоритет см. в докстринге resolve_user_position:
    UO.position по org_id → единственное/первое членство → User.position (legacy,
    только когда членств нет вовсе).
    """
    if user is None:
        return ""
    from app.services.user_position import resolve_user_position
    try:
        from app.models.user_organization import UserOrganization
        from sqlalchemy import select as _sel
        rows = (
            await db.execute(
                _sel(UserOrganization)
                .where(UserOrganization.user_id == user.id)
                .order_by(UserOrganization.id)
            )
        ).scalars().all()
    except Exception:
        rows = []
    return resolve_user_position(user, org_id=org_id, memberships=rows) or ""


def _format_service_term(p) -> str:
    """Build the human-readable service-term string for docx templates.

    Phase 19 — three modes:
      - range:    "с 01.05.2026 по 31.05.2026"
      - duration: "в течение 30 календарных дней после заключения договора"
      - deadline: "до 30.06.2026 включительно"
    """
    mode = getattr(p, "service_term_mode", None)
    if mode == "range" and p.service_start_date and p.service_end_date:
        return (
            f"с {p.service_start_date.strftime('%d.%m.%Y')} "
            f"по {p.service_end_date.strftime('%d.%m.%Y')}"
        )
    if mode == "duration" and getattr(p, "service_term_days", None):
        type_name = {
            "calendar": "календарных",
            "working":  "рабочих",
        }.get(getattr(p, "service_term_type", None) or "calendar", "календарных")
        return f"в течение {p.service_term_days} {type_name} дней после заключения договора"
    if mode == "deadline" and getattr(p, "service_deadline_date", None):
        return f"до {p.service_deadline_date.strftime('%d.%m.%Y')} включительно"
    return ""
