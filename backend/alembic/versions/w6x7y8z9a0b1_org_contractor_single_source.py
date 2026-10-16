"""Организация без своих реквизитов — единственный источник Contractor.

Переделка предыдущей попытки (y5z6a7b8c9d0, зеркало organizations.name ↔
contractors.name — ДВА места хранения, владелец отклонил как нарушение
Правило №6). Эта миграция НЕ копирует и НЕ синхронизирует — она один раз
привязывает каждую организацию к контрагенту и дозаполняет в контрагенте
то, что уже было известно только организации, а дальше организация читает
имя и реквизиты из контрагента через column_property
(app/models/organization.py) — хранения больше нет, кроме как у контрагента.

1) Для организаций без contractor_id:
   - если есть ИНН и контрагент с таким ИНН уже существует → привязать к нему;
   - если есть ИНН, но контрагента с ним нет → создать контрагента из полей
     организации (name/full_name/inn/kpp/ogrn/address/signatory*) и привязать;
   - если ИНН нет совсем (напр. тестовые/черновые организации) → создать
     минимального контрагента из org.name и привязать, чтобы НИ ОДНА
     организация не осталась без источника имени/реквизитов.
2) Для уже привязанных контрагентов — пополейно дозаполнить ТОЛЬКО пустые
   поля контрагента (name/full_name/inn/kpp/ogrn/address/signatory*) из
   соответствующих колонок организации. Непустые поля контрагента НЕ
   трогаются (контрагент побеждает) — только страхуемся от потери данных,
   которые раньше были видны лишь в organizations.*.

Идемпотентно: повторный прогон ничего не меняет (все organizations уже с
contractor_id, все контрагентские поля уже не пусты либо у org тоже пусто).

Revision ID: w6x7y8z9a0b1
Revises: v2w3x4y5z6a7
Create Date: 2026-10-16 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "w6x7y8z9a0b1"
down_revision = "v2w3x4y5z6a7"
branch_labels = None
depends_on = None

_REQ_FIELDS = (
    "name", "full_name", "inn", "kpp", "ogrn", "address",
    "signatory", "signatory_position", "signatory_last_name",
    "signatory_first_name", "signatory_middle_name",
)


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Организации без contractor_id -----------------------------------
    orgs = bind.execute(sa.text(
        "SELECT id, name, full_name, inn, kpp, ogrn, address, signatory, "
        "signatory_position, signatory_last_name, signatory_first_name, "
        "signatory_middle_name FROM organizations WHERE contractor_id IS NULL"
    )).mappings().all()

    for o in orgs:
        inn = (o["inn"] or "").strip() or None
        contractor_id = None
        if inn:
            row = bind.execute(
                sa.text("SELECT id FROM contractors WHERE inn = :inn LIMIT 1"),
                {"inn": inn},
            ).first()
            if row:
                contractor_id = row[0]
        if contractor_id is None:
            # Контрагента с таким ИНН нет (или ИНН не указан вовсе) — создаём
            # минимального контрагента из того, что знает организация.
            name = (o["name"] or "").strip() or f"Организация #{o['id']}"
            res = bind.execute(
                sa.text(
                    "INSERT INTO contractors "
                    "(name, full_name, inn, kpp, ogrn, address, signatory, "
                    "signatory_position, signatory_last_name, signatory_first_name, "
                    "signatory_middle_name, org_id) "
                    "VALUES (:name, :full_name, :inn, :kpp, :ogrn, :address, :signatory, "
                    ":signatory_position, :signatory_last_name, :signatory_first_name, "
                    ":signatory_middle_name, :org_id) RETURNING id"
                ),
                {
                    "name": name,
                    "full_name": o["full_name"],
                    "inn": inn,
                    "kpp": o["kpp"],
                    "ogrn": o["ogrn"],
                    "address": o["address"],
                    "signatory": o["signatory"],
                    "signatory_position": o["signatory_position"],
                    "signatory_last_name": o["signatory_last_name"],
                    "signatory_first_name": o["signatory_first_name"],
                    "signatory_middle_name": o["signatory_middle_name"],
                    "org_id": o["id"],
                },
            )
            contractor_id = res.scalar_one()
        bind.execute(
            sa.text("UPDATE organizations SET contractor_id = :cid WHERE id = :oid"),
            {"cid": contractor_id, "oid": o["id"]},
        )

    # --- 2. Пополейный дозаполнение пустых полей контрагента ----------------
    # (не трогаем непустые — контрагент побеждает).
    set_clauses = []
    for f in _REQ_FIELDS:
        set_clauses.append(
            f"{f} = CASE WHEN c.{f} IS NULL OR btrim(c.{f}) = '' "
            f"THEN o.{f} ELSE c.{f} END"
        )
    sql = (
        "UPDATE contractors c SET " + ", ".join(set_clauses) + " "
        "FROM organizations o WHERE o.contractor_id = c.id"
    )
    bind.execute(sa.text(sql))

    # --- 3. organizations.name больше не источник истины ---------------------
    # Organization.name — теперь column_property, читающая Contractor.name
    # (app/models/organization.py); новый код НЕ пишет в физическую колонку
    # organizations.name (ни `Organization(name=...)`, ни `org.name = ...`
    # — последнее и не персистировалось бы). NOT NULL на мёртвой колонке
    # валил бы INSERT у любого нового Organization(contractor_id=...) без
    # явного name= (org_dedup.py::_materialize_org_from_contractor,
    # app/routers/organizations.py::create_organization) — известный баг,
    # снимаем ограничение. Колонка остаётся (исторические данные, сама
    # backfill-миграция выше), просто не NOT NULL.
    op.alter_column("organizations", "name", nullable=True)


def downgrade() -> None:
    # Контрагенты, созданные здесь для организаций без ИНН, и дозаполненные
    # поля — необратимо объединены с уже существующими данными (как и у
    # аналогичных backfill-миграций в проекте, см. merge_duplicates_by_inn).
    pass
