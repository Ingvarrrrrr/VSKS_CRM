#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бэкфилл «подписант из ЕГРЮЛ → сотрудник без входа» для УЖЕ существующих
организаций (ПРАВИЛО владельца, 28.10.2026).

ПОВОД. Субсидия «ЗО_актуальная» (организация «ЗРО ВСКС», id=69 на проде):
руководитель по ЕГРЮЛ (Юрченкова А.Е., «Председатель совета», хранится в
contractors.signatory_* привязанного contractor_id) не попадал в штат
организации — выбрать её ответственным исполнителем/подписантом было
некем. С сегодняшнего дня это заводится автоматически при материализации/
обновлении связи организация↔контрагент (app/services/org_dedup.py::
_materialize_org_from_contractor → app/services/signatory_staff.py::
ensure_signatory_staff_for_org), но для организаций, созданных ДО этой
правки, нужен разовый бэкфилл — он и есть этот скрипт.

ОДИН ИСТОЧНИК ИСТИНЫ (ПРАВИЛО №6): скрипт зовёт ТУ ЖЕ функцию
ensure_signatory_staff_for_org (→ get_or_create_signatory_staff_user), что
и автовызов из org_dedup.py и кнопка «Добавить подписанта сотрудником»
(routers/organizations.py::materialize_signatory_as_staff) — второй
механизм материализации не заводится.

ОТБОР. Все Organization с contractor_id IS NOT NULL. Идемпотентность —
внутри get_or_create_signatory_staff_user (точное совпадение ФИО среди
уже числящегося штата org_staff_user_ids, без fuzzy — feedback_dedup_
exact_only): повторный запуск не создаёт дублей.

⚠️ ТОЛЬКО ЛОКАЛЬНО. На прод-БД не запускать (правило задачи 28.10.2026) —
только локальный стек (docker compose -p vsks_crm).

Запуск (backend-код смонтирован, перезапуск контейнера не нужен):
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_signatory_staff.py
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_signatory_staff.py --apply
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_signatory_staff.py --apply --org-ids 69,70

Без --apply — только печать (dry-run), ничего не пишет и не коммитит.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.services.org_requisites import org_requisites  # noqa: E402
from app.services.signatory_staff import ensure_signatory_staff_for_org  # noqa: E402


async def _candidates(db, org_ids=None):
    stmt = select(Organization).where(Organization.contractor_id.isnot(None)).order_by(Organization.id)
    if org_ids:
        stmt = stmt.where(Organization.id.in_(org_ids))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def run_backfill(db, org_ids=None, apply: bool = False):
    """Ядро скрипта — отдельная функция для юнит-теста без subprocess."""
    from app.models.contractor import Contractor

    orgs = await _candidates(db, org_ids)
    created = 0
    already = 0
    skipped_no_signatory = 0
    rows = []

    for org in orgs:
        contractor = await db.get(Contractor, org.contractor_id) if org.contractor_id else None
        req = org_requisites(org, contractor)
        last, first, middle = req.get("signatory_last_name"), req.get("signatory_first_name"), req.get("signatory_middle_name")
        if not (last or first):
            skipped_no_signatory += 1
            continue
        from app.services.service_note_initiators import org_staff_user_ids
        from app.models.user import User
        from app.services.fio import compose_fio

        full_name = compose_fio(last, first, middle)
        staff_ids = await org_staff_user_ids(db, org.id)
        existed = False
        if staff_ids:
            existing = (await db.execute(
                select(User.id).where(User.id.in_(staff_ids), User.full_name == full_name)
            )).scalar_one_or_none()
            existed = existing is not None

        if apply:
            user = await ensure_signatory_staff_for_org(db, org)
            if user is None:
                skipped_no_signatory += 1
                continue
        if existed:
            already += 1
        else:
            created += 1
            rows.append((org.id, full_name, req.get("signatory_position")))

    if apply:
        await db.commit()

    return {
        "orgs_checked": len(orgs),
        "created": created,
        "already_staff": already,
        "skipped_no_signatory": skipped_no_signatory,
        "created_rows": rows,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Записать изменения (без флага — только dry-run)")
    parser.add_argument("--org-ids", type=str, default=None, help="Список id организаций через запятую (по умолчанию — все)")
    args = parser.parse_args()

    org_ids = None
    if args.org_ids:
        org_ids = [int(x) for x in args.org_ids.split(",") if x.strip()]

    async with async_session() as db:
        result = await run_backfill(db, org_ids=org_ids, apply=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] организаций проверено: {result['orgs_checked']}")
    print(f"  создано карточек подписанта: {result['created']}")
    print(f"  уже были в штате:            {result['already_staff']}")
    print(f"  без подписанта в карточке:   {result['skipped_no_signatory']}")
    for org_id, full_name, position in result["created_rows"]:
        print(f"    org={org_id}: {full_name} ({position or '—'})")
    if not args.apply:
        print("\nЭто dry-run — для записи добавьте --apply")


if __name__ == "__main__":
    asyncio.run(main())
