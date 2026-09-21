"""contract_excess_approval.py — согласование превышения ДОГОВОРНОЙ позиции
(ContractItem) над её позицией из заявки/закупки (PurchaseItem).

Волна 4, п.18 (владелец, дословно): «если цена в договоре и количество, либо
цена, либо количество в договоре больше, чем того, что было в первоначальной
заявке, потом в закупке... не должны пропускать большую цену без
дополнительного согласования, иначе будут проблемы». Решение владельца — НЕ
жёсткий запрет, а СОГЛАСОВАНИЕ, как у превышения плана ФЭО.

── Почему это ЧЕТВЁРТЫЙ, независимый вид превышения ─────────────────────────
До этой правки в contract_items.py не было НИ ОДНОГО сравнения с
purchase_items — только пересчёт денег договора (см.
app.routers.purchases._recalc_contract_price_from_contract_items). Два
существующих контроля сравнивают ДРУГИЕ пары величин:
  - app.services.feo_plan.assert_no_unapproved_excess — план узла ФЭО против
    его финансирования (бюджета), и факт (по договору/КП) против ПЛАНА узла —
    это агрегат по КАТЕГОРИИ целиком, не построчное сравнение с конкретной
    закупочной позицией;
  - app.services.tz_excess_approval — ТЗ позиции (PurchaseItem/WishItem)
    против её ПЛАНОВОЙ позиции (FeoPlannedItem) — сравнение на этапе «заявка →
    план закупок», ещё до всякого договора.
Ни один из них не видит рассинхрон КОНКРЕТНОЙ договорной строки с КОНКРЕТНОЙ
позицией закупки/ТЗ — сравнение здесь ТРЕТЬЕЙ парой величин (Договор vs
ТЗ/закупка), поэтому заводится отдельно, по образцу tz_excess_approval.py.

── Как это согласуется (ПРАВИЛО №6 — переиспользовать, не плодить второй
   механизм) ──────────────────────────────────────────────────────────────
Используется СУЩЕСТВУЮЩАЯ модель app.models.plan_excess_approval.
PlanExcessApproval — ТА ЖЕ таблица, ТЕ ЖЕ уполномоченные (право
'plan_excess.decide', см. app.routers.plan_excess._authorized_plan_excess_approvers,
переиспользуется КАК ЕСТЬ, копии логики нет), тот же список «Согласование
превышения плана ФЭО» на фронте. Одобрение по категории снимает блокировку
для ВСЕХ видов сразу — та же семантика «последний запрос решает», что и у
feo_plan.compute_feo_plan_tree/tz_excess_approval.

Сопоставление договорной строки с её строкой закупки/ТЗ — ИСКЛЮЧИТЕЛЬНО через
ContractItem.source_item_id (см. app.models.contract_item и
app.services.contract_item_link.relink_contract_items — тот же канонический
канал, которым уже пользуется весь проект для «какой закупочной позиции
принадлежит эта договорная строка», в т.ч. пересчёт факта ФЭО и печать
документов). Вторая эвристика сопоставления здесь НЕ заводится: перед вызовом
проверки роутер обязан вызвать relink_contract_items, чтобы связь была
максимально актуальна.

── Ограничение (сознательное, задокументировано, а не тихий пробел) ────────
Как и tz_excess_approval/feo_plan, вся инфраструктура согласования держится
на FeoCategory + Subsidy: если у закупки нет subsidy_id, либо у позиции нет
ни своей feo_category_id, ни фолбэка на Purchase.feo_category_id — сравнивать
можно (числа есть), но СОГЛАСОВЫВАТЬ через этот механизм некому и негде
(нет категории/субсидии, к которой привязать запрос). В этом случае гейт —
no-op: превышение не блокируется. У большинства закупок с реальными
договорами subsidy_id и feo_category_id заполнены (см. вкладку «Категории
ФЭО»), но это не гарантировано абсолютно всеми — то же ограничение уже
принято в tz_excess_approval.py (`if not violations or not subsidy_id`).
"""
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import plan_excess_kinds as PEK


def _fmt_qty(d: Decimal) -> str:
    """Количество без хвостовых нулей (2, не 2.0000)."""
    s = f"{d:,.4f}".rstrip("0").rstrip(".")
    return s or "0"


def _fmt_money(d: Decimal) -> str:
    return f"{d:,.2f} ₽"


def _d(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def _contract_vs_purchase_violation(
    ci, pi, fallback_category_id: Optional[int],
) -> Optional[dict]:
    """Сравнивает ОДНУ договорную позицию `ci` с её позицией закупки/ТЗ `pi`
    по количеству, цене за единицу и сумме ОТДЕЛЬНО (владелец: «либо цена,
    либо количество... не должны пропускать без согласования» — три
    независимых сравнения, как в feo_plan_tz_checks.assert_tz_not_over_plan).

    `ci`/`pi` — любой объект с атрибутами .quantity/.unit_price и
    .total(ci)/.total_price(pi) — принимает как персистентные ORM-объекты,
    так и ещё не сохранённые Pydantic/SimpleNamespace-обёртки (см. вызовы в
    contract_items.py, где PUT проверяет ЕЩЁ НЕ вставленные строки).

    Возвращает None, если нарушений нет (в т.ч. когда ci дешевле/меньше —
    «ТЗ может быть НИЖЕ, но не ВЫШЕ», тот же принцип, что и в
    feo_plan_tz_checks). Сравнение строго `>` в Decimal, без допуска — тот же
    принцип, что и в feo_plan_tz_checks.assert_tz_not_over_plan (ПРАВИЛО №6:
    формула сравнения одна на весь проект, эпсилон нигде не заводится).
    """
    ci_qty = _d(getattr(ci, "quantity", None))
    ci_price = _d(getattr(ci, "unit_price", None))
    ci_total_raw = getattr(ci, "total", None)
    ci_total = _d(ci_total_raw) if ci_total_raw is not None else (ci_qty * ci_price)

    pi_qty = _d(getattr(pi, "quantity", None))
    pi_price = _d(getattr(pi, "unit_price", None))
    pi_total_raw = getattr(pi, "total_price", None)
    pi_total = _d(pi_total_raw) if pi_total_raw is not None else (pi_qty * pi_price)

    diffs: list[str] = []
    if ci_qty > pi_qty:
        diffs.append(
            f"количество: в закупке {_fmt_qty(pi_qty)}, в договоре {_fmt_qty(ci_qty)} "
            f"(больше на {_fmt_qty(ci_qty - pi_qty)})"
        )
    if ci_price > pi_price:
        diffs.append(
            f"цена за единицу: в закупке {_fmt_money(pi_price)}, в договоре {_fmt_money(ci_price)} "
            f"(больше на {_fmt_money(ci_price - pi_price)})"
        )
    if ci_total > pi_total:
        diffs.append(
            f"сумма: в закупке {_fmt_money(pi_total)}, в договоре {_fmt_money(ci_total)} "
            f"(больше на {_fmt_money(ci_total - pi_total)})"
        )

    if not diffs:
        return None

    name = (getattr(ci, "name", None) or getattr(pi, "item_name", None) or "позиция").strip()
    cat_id = getattr(pi, "feo_category_id", None) or fallback_category_id
    excess_total = ci_total - pi_total
    # excess_amount заполняет NOT NULL поле PlanExcessApproval.excess_amount —
    # нужно ЧИСЛО даже когда превышение по количеству/цене не увеличило
    # сумму (напр. кол-во больше, цена меньше, сумма совпала) — фолбэк на 0,
    # honest «есть нарушение, но сумма не выросла», а не выдуманная цифра.
    amount = excess_total if excess_total > 0 else Decimal("0")

    return {
        "feo_category_id": cat_id,
        "item_name": name,
        "amount": float(amount),
        "message": (
            f"Позиция договора «{name}» превышает соответствующую позицию закупки/ТЗ: "
            + "; ".join(diffs) + "."
        ),
    }


def collect_contract_over_purchase_violations(
    contract_items: Iterable,
    purchase_items_by_id: dict,
    fallback_category_id: Optional[int] = None,
) -> list[dict]:
    """Строит список нарушений «договорная строка дороже/больше своей позиции
    закупки/ТЗ» — БЕЗ обращения к БД (чистая функция, синхронная), удобно
    вызывать и до, и после мутаций в роутере.

    Договорные строки без `source_item_id` (не привязаны к конкретной позиции
    закупки — например, добавлены вручную сверх ТЗ) пропускаются — сравнивать
    не с чем, это ОСОЗНАННЫЙ пробел (см. docstring модуля), не тихая порча
    данных: такая строка просто не участвует в этом контроле.
    """
    violations: list[dict] = []
    for ci in contract_items:
        src_id = getattr(ci, "source_item_id", None)
        if not src_id:
            continue
        pi = purchase_items_by_id.get(src_id)
        if pi is None:
            continue
        v = _contract_vs_purchase_violation(ci, pi, fallback_category_id)
        if v:
            violations.append(v)
    return violations


async def register_contract_excess_approvals(
    db: AsyncSession,
    violations: list[dict],
    *,
    subsidy_id: Optional[int],
    current_user,
    context_label: str,
) -> list[dict]:
    """Регистрирует нарушения из collect_contract_over_purchase_violations как
    запросы PlanExcessApproval — ТОЧНАЯ копия структуры
    app.services.tz_excess_approval.register_tz_excess_approvals (та же
    таблица/уполномоченные/идемпотентность), адаптированная под текст
    «договор vs закупка» вместо «ТЗ vs плановая позиция». Логика подбора
    уполномоченных (_authorized_plan_excess_approvers) и уведомлений
    НЕ дублируется — импортируется из app.routers.plan_excess как есть.

    Если по категории уже есть pending-запрос — переиспользуется (без дублей
    при повторных попытках сохранить одни и те же превышающие позиции).
    Если согласовывать некому (ни у одного пользователя нет
    'plan_excess.decide') — БРОСАЕТ 409 (не пропускает молча).
    commit НЕ делает — ответственность вызывающего кода.
    """
    if not violations or not subsidy_id:
        return []

    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
    from app.auth.jwt import get_single_org_id
    from app.routers.plan_excess import (
        _authorized_plan_excess_approvers,
        _notify_pending_plan_excess_approvers,
        _load_approval,
        _approval_dict,
    )

    subsidy = await db.get(Subsidy, subsidy_id)
    if subsidy is None:
        return []
    org_id = subsidy.org_id or get_single_org_id(current_user)
    if not org_id:
        raise HTTPException(
            409,
            "Не удалось определить организацию субсидии — согласование превышения "
            "договора над закупкой невозможно настроить.",
        )

    by_cat: dict[int, list[dict]] = {}
    for v in violations:
        cid = v.get("feo_category_id")
        if cid:
            by_cat.setdefault(cid, []).append(v)

    results: list[dict] = []
    requester_name = current_user.full_name or current_user.username

    for cid, cat_violations in by_cat.items():
        cat = await db.get(FeoCategory, cid)
        cat_name = cat.name if cat else f"#{cid}"

        # ⚠️ Смотрим на ПОСЛЕДНИЙ запрос СВОЕГО вида (kind=contract_over_tz) по
        # категории НЕЗАВИСИМО от статуса — не только 'pending' (правка,
        # поймана живой проверкой на стенде 2026-09-13): если латест уже
        # 'approved', НЕЛЬЗЯ заводить второй pending-запрос —
        # assert_no_pending_contract_excess смотрит на ПОСЛЕДНИЙ по created_at,
        # и свежесозданный pending заслонил бы собой уже одобренное решение на
        # КАЖДОЙ следующей попытке сохранить те же позиции (вечный 409 даже
        # после одобрения — баг, а не гейт). Если записи своего вида ещё нет —
        # legacy-фолбэк (задача владельца 2026-09-21, независимые согласования
        # по видам, см. app.services.plan_excess_kinds.LEGACY_FALLBACK_KINDS и
        # app.services.feo_plan_tree._latest_approval — та же семантика).
        latest = (await db.execute(
            select(PlanExcessApproval).where(
                PlanExcessApproval.feo_category_id == cid,
                PlanExcessApproval.kind == PEK.CONTRACT_OVER_TZ,
            ).order_by(PlanExcessApproval.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if latest is None:
            latest = (await db.execute(
                select(PlanExcessApproval).where(
                    PlanExcessApproval.feo_category_id == cid,
                    PlanExcessApproval.kind == PEK.LEGACY,
                ).order_by(PlanExcessApproval.created_at.desc()).limit(1)
            )).scalar_one_or_none()
        if latest is not None and latest.status in ("approved", "pending"):
            full = await _load_approval(latest.id, db)
            results.append(_approval_dict(full))
            continue

        approvers = await _authorized_plan_excess_approvers(
            db, org_id, subsidy_id, exclude_user_id=current_user.id,
        )
        if not approvers:
            names = "; ".join(f"«{it['item_name']}»" for it in cat_violations[:5])
            raise HTTPException(
                409,
                f"Договор по категории ФЭО «{cat_name}» превышает закупку/ТЗ ({names}), а "
                f"согласовать это превышение некому: ни у одного пользователя организации нет "
                f"права «Согласование превышения плана ФЭО» (plan_excess.decide). Выдайте это "
                f"право нужному кругу лиц (например, финансисту или владельцу организации) и "
                f"повторите {context_label}.",
            )

        total_excess = sum(Decimal(str(it["amount"])) for it in cat_violations)
        items_desc = "; ".join(
            f"«{it['item_name']}»: {it['message']}" for it in cat_violations
        )
        approval = PlanExcessApproval(
            feo_category_id=cid,
            subsidy_id=subsidy_id,
            kind=PEK.CONTRACT_OVER_TZ,
            excess_amount=total_excess,
            plan_amount=None,
            budget_amount=None,
            status="pending",
            mode="sequential",
            requested_by_id=current_user.id,
            comment=(
                f"Позиция договора превышает свою позицию закупки/ТЗ — {context_label}. "
                f"{items_desc}"
            ),
        )
        db.add(approval)
        await db.flush()

        for i, u in enumerate(approvers):
            db.add(PlanExcessApprovalStep(
                approval_id=approval.id,
                user_id=u.id,
                order_num=i,
                role_name="Уполномочен на согласование превышения",
                approver_full_name=u.full_name or u.username,
                status="pending",
            ))
        await db.flush()

        full = await _load_approval(approval.id, db)
        results.append(_approval_dict(full))
        try:
            await _notify_pending_plan_excess_approvers(full, db, requester_name, cat_name)
        except Exception:
            import logging as _log
            _log.getLogger(__name__).warning(
                "notify contract-excess approvers failed for cat %s", cid,
            )

    return results


CONTRACT_EXCESS_PENDING_CODE = "CONTRACT_EXCESS_OVER_PURCHASE_PENDING"


async def assert_no_pending_contract_excess(
    db: AsyncSession,
    contract_items: Iterable,
    purchase_items_by_id: dict,
    fallback_category_id: Optional[int] = None,
) -> None:
    """Блокирует сохранение договорных позиций (409), пока по КАЖДОЙ
    затронутой категории ФЭО не найден ПОСЛЕДНИЙ (по created_at)
    PlanExcessApproval со статусом 'approved'. Пересчитывает нарушения ПРЯМО
    СЕЙЧАС по переданным `contract_items` — не полагается на снимок на момент
    регистрации (состав мог измениться). Ничего не пишет в БД, не коммитит.

    Единственный источник текста отказа (ПРАВИЛО проекта — отказ с понятной
    причиной, не generic «ошибка», без копий по роутерам) — конкретные числа
    берутся из collect_contract_over_purchase_violations выше.
    """
    from app.models.plan_excess_approval import PlanExcessApproval
    from app.models.feo_category import FeoCategory

    violations = collect_contract_over_purchase_violations(
        contract_items, purchase_items_by_id, fallback_category_id,
    )
    if not violations:
        return

    by_cat: dict[int, list[dict]] = {}
    for v in violations:
        cid = v.get("feo_category_id")
        if cid:
            by_cat.setdefault(cid, []).append(v)

    for cid, cat_violations in by_cat.items():
        # СВОЙ вид (kind=contract_over_tz), а если записи ещё нет — legacy-
        # фолбэк (см. комментарий у аналогичного лукапа в
        # register_contract_excess_approvals выше).
        appr = (await db.execute(
            select(PlanExcessApproval)
            .where(
                PlanExcessApproval.feo_category_id == cid,
                PlanExcessApproval.kind == PEK.CONTRACT_OVER_TZ,
            )
            .order_by(PlanExcessApproval.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if appr is None:
            appr = (await db.execute(
                select(PlanExcessApproval)
                .where(
                    PlanExcessApproval.feo_category_id == cid,
                    PlanExcessApproval.kind == PEK.LEGACY,
                )
                .order_by(PlanExcessApproval.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
        if appr is not None and appr.status == "approved":
            continue

        cat = await db.get(FeoCategory, cid)
        cat_name = cat.name if cat else f"#{cid}"
        details = " ".join(v["message"] for v in cat_violations)
        status_txt = {
            "pending": "запрос на согласование ещё не решён",
            "rejected": "запрос на согласование отклонён",
        }.get(appr.status if appr else None, "запрос на согласование ещё не создан")
        raise HTTPException(
            409,
            {
                "code": CONTRACT_EXCESS_PENDING_CODE,
                "message": (
                    f"Договор по категории ФЭО «{cat_name}» превышает закупку/ТЗ — {status_txt}. "
                    f"{details} Сохранение договорных позиций заблокировано, пока уполномоченный "
                    f"(право «Согласование превышения плана ФЭО») не одобрит превышение."
                ),
                "feo_category_id": cid,
                "plan_excess_approval_id": appr.id if appr else None,
            },
        )


async def enforce_contract_excess_approval(
    db: AsyncSession,
    contract_items: Iterable,
    purchase_items_by_id: dict,
    *,
    subsidy_id: Optional[int],
    current_user,
    context_label: str,
    fallback_category_id: Optional[int] = None,
) -> None:
    """Единая точка входа для роутера contract_items.py — вызывать ДО
    фактической мутации БД (delete/insert/setattr+commit), чтобы отказ не
    оставил висящих незакоммиченных изменений.

    Считает нарушения → регистрирует запрос(ы) согласования (переиспользует
    существующий pending, идемпотентно) → бросает 409, если хоть одна
    затронутая категория ещё не имеет 'approved' решения. При отсутствии
    нарушений или отсутствии subsidy_id — no-op (см. docstring модуля про
    сознательное ограничение области действия).

    ⚠️ КОММИТИТ после регистрации, ДО броска 409 — важно: эта функция
    вызывается из contract_items.py ДО мутации ContractItem (до delete/insert
    в PUT, до setattr в PATCH/POST), именно чтобы 409 не оставил висящих
    изменений позиций договора. Но САМ запрос согласования (PlanExcessApproval
    + шаги) обязан ПЕРЕЖИТЬ это же исключение — иначе get_db() закрывает
    сессию без commit при пробросе HTTPException, откатывая только что
    созданный approval вместе с (несостоявшейся) мутацией позиций, и
    уполномоченный никогда не увидит запрос на решение (сохранение будет
    вечно 409-ить, регистрируя и тут же теряя новый approval на каждой
    попытке — живой баг, пойманный проверкой на стенде 2026-09-13). В момент
    вызова enforce_contract_excess_approval в contract_items.py в сессии ещё
    нет других незакоммиченных мутаций ContractItem — commit() здесь фиксирует
    ТОЛЬКО строки approval/steps.
    """
    violations = collect_contract_over_purchase_violations(
        contract_items, purchase_items_by_id, fallback_category_id,
    )
    if not violations or not subsidy_id:
        return
    await register_contract_excess_approvals(
        db, violations, subsidy_id=subsidy_id, current_user=current_user,
        context_label=context_label,
    )
    await db.commit()
    await assert_no_pending_contract_excess(
        db, contract_items, purchase_items_by_id, fallback_category_id,
    )
