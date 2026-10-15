"""Штатный прогон автосопоставления платежей по субсидии — вынесено из
app/routers/purchase_payment_matching.py::match_payments_endpoint (Правило
№6: один прогон, не дублировать). Нужен как ОБЫЧНАЯ функция (не HTTP) для
двух вызывающих:
  - POST /api/purchases/match-payments (сам роутер, как раньше);
  - app/routers/bank_statements.py — план .planning/quick/
    2026-10-06-statement-control/PLAN.md, п.5: автоматически после КАЖДОЙ
    загрузки выписки, по субсидиям, затронутым вставленными/обновлёнными
    строками.

Поведение НЕ меняется относительно прежнего router-кода — то же построение
групп (payment_target.build_groups), тот же простой пасс (find_candidates/
attach), тот же добор помесячным/рамочным/авансовым поиском
(payment_lookup_multi). Коммитит сам, когда dry_run=False — вызывающий код
(роутер или импорт выписки) не должен коммитить это отдельно.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase


def _suspicious_group_to_dict(s) -> dict:
    return {
        "registry_number": s.registry_number,
        "purchase_ids": s.purchase_ids,
        "row_count": s.row_count,
        "shared_amount": float(s.shared_amount) if s.shared_amount is not None else None,
        "reason": s.reason,
    }


async def run_match_payments(db: AsyncSession, subsidy_id: int, dry_run: bool = True) -> dict:
    from app.services.payment_target import build_groups, suspicious_groups
    from app.services.payment_lookup import find_candidates, attach, PaymentAttachError

    groups = await build_groups(db, subsidy_id)
    susp = await suspicious_groups(db, subsidy_id=subsidy_id)

    report = {
        "subsidy_id": subsidy_id,
        "dry_run": dry_run,
        "groups_total": len(groups),
        "attached": [],
        "ambiguous": [],
        "not_found": [],
        "suspicious": [_suspicious_group_to_dict(s) for s in susp],
    }

    # Строки выписки, выбранные в этом прогоне: в пробном Payment не пишется,
    # и без этого множества одинаковые суммы у одного ИНН (5 закупок по 51 000)
    # получали один и тот же платёж — пробный отчёт расходился с записью.
    used_bp_ids: set[int] = set()

    for g in groups:
        cands = await find_candidates(db, g, exclude_ids=used_bp_ids)
        whole_amount = False
        if (g.goods_amount and g.services_amount
                and not any(c.auto for kc in cands.values() for c in kc)):
            # Закупка разбита на товары и услуги, а оплачена одним платежом
            # (ЦЕНТРАВТО 89 360,02 = 28 652,50 + 60 707,52).
            whole = await find_candidates(db, g, exclude_ids=used_bp_ids, whole_amount=True)
            if any(c.auto for c in whole["goods"]):
                cands, whole_amount = whole, True
        group_attached: list[dict] = []
        group_ambiguous: list[dict] = []
        group_had_target = False

        for kind in ("goods", "services"):
            if whole_amount:
                if kind == "services":
                    continue
                kind_amount = g.goods_amount + g.services_amount
            else:
                kind_amount = g.goods_amount if kind == "goods" else g.services_amount
            if not kind_amount:
                continue
            group_had_target = True
            kind_cands = cands.get(kind, [])
            auto_cand = next((c for c in kind_cands if c.auto), None)

            if auto_cand:
                used_bp_ids.add(auto_cand.bank_payment_id)
                if dry_run:
                    group_attached.append({
                        "kind": kind, "bank_payment_id": auto_cand.bank_payment_id,
                        "amount": float(auto_cand.amount), "basis_label": auto_cand.basis_label,
                    })
                else:
                    try:
                        created = await attach(db, g, [auto_cand.bank_payment_id])
                        group_attached.append({
                            "kind": kind, "bank_payment_id": auto_cand.bank_payment_id,
                            "amount": float(auto_cand.amount), "basis_label": auto_cand.basis_label,
                            "payment_ids": [p.id for p in created],
                        })
                    except PaymentAttachError as exc:
                        await db.rollback()
                        group_ambiguous.append({"kind": kind, "reason": str(exc)})
            elif kind_cands:
                reasons = sorted({c.reason for c in kind_cands if c.reason} or {"нет свободного кандидата"})
                group_ambiguous.append({"kind": kind, "reason": "; ".join(reasons)})

        if group_attached:
            report["attached"].append({
                "group_key": g.group_key, "registry_number": g.registry_number, "items": group_attached,
            })
        if group_ambiguous:
            report["ambiguous"].append({
                "group_key": g.group_key, "registry_number": g.registry_number, "items": group_ambiguous,
            })
        if group_had_target and not group_attached and not group_ambiguous:
            report["not_found"].append({"group_key": g.group_key, "registry_number": g.registry_number})

    from app.services.payment_lookup_multi import match_monthly, match_framework, match_advance

    handled_keys = {a["group_key"] for a in report["attached"]}
    pending_groups = [g for g in groups if g.group_key not in handled_keys]

    purchase_ids_all = [pid for g in pending_groups for pid in g.purchase_ids]
    purchases_by_id = {}
    if purchase_ids_all:
        purchase_rows = (await db.execute(
            select(Purchase).where(Purchase.id.in_(purchase_ids_all))
        )).scalars().all()
        purchases_by_id = {p.id: p for p in purchase_rows}

    multi_report = {
        "monthly": {"attached": [], "ambiguous": []},
        "framework": {"attached": [], "ambiguous": []},
        "advance": {"attached": [], "ambiguous": []},
    }

    for g in pending_groups:
        monthly_purchase = next(
            (purchases_by_id[pid] for pid in g.purchase_ids if purchases_by_id.get(pid) and purchases_by_id[pid].is_monthly_payment),
            None,
        )
        if monthly_purchase is not None:
            r = await match_monthly(db, g, monthly_purchase, dry_run=dry_run)
            multi_report["monthly"]["attached"].extend(
                {**item, "group_key": g.group_key} for item in r["attached"]
            )
            multi_report["monthly"]["ambiguous"].extend(
                {**item, "group_key": g.group_key} for item in r["ambiguous"]
            )

    framework_groups = [g for g in pending_groups if g.is_framework]
    if framework_groups:
        r = await match_framework(db, framework_groups, dry_run=dry_run)
        multi_report["framework"]["attached"].extend(r["attached"])
        multi_report["framework"]["ambiguous"].extend(r["ambiguous"])

    advance_pairs = []
    for g in pending_groups:
        adv_purchase = next(
            (
                purchases_by_id[pid] for pid in g.purchase_ids
                if purchases_by_id.get(pid)
                and purchases_by_id[pid].purchase_method == "advance"
                and purchases_by_id[pid].reimbursement_user_id
            ),
            None,
        )
        if adv_purchase is not None:
            advance_pairs.append((g, adv_purchase))
    if advance_pairs:
        r = await match_advance(db, advance_pairs, dry_run=dry_run)
        multi_report["advance"]["attached"].extend(r["attached"])
        multi_report["advance"]["ambiguous"].extend(r["ambiguous"])

    if dry_run:
        # При записи добор не видит строк, уже разнесённых простым проходом
        # (они в БД); в пробном их в БД нет — убираем из отчёта так же, иначе
        # заказы рамочного договора показаны дважды (по заказу и по договору).
        for part in multi_report.values():
            kept = []
            for item in part["attached"]:
                ids = set(item.get("bank_payment_ids") or [item.get("bank_payment_id")])
                if not ids & used_bp_ids:
                    used_bp_ids.update(ids)
                    kept.append(item)
            part["attached"] = kept

    report["multi"] = multi_report

    if not dry_run:
        await db.commit()

    return report
