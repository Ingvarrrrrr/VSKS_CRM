"""Единый источник юридических реквизитов организации (Правило №6).

Начиная с миграции `w6x7y8z9a0b1` (16.10.2026) у организации больше НЕТ
собственных реквизитов: `Organization.name/full_name/inn/kpp/ogrn/address/
signatory*` — вычисляемые `column_property` (см. `app/models/
organization.py`), читающие значение из привязанного `Contractor` по
`contractor_id`. Эта функция больше не мержит "org или contractor" —
Contractor — ЕДИНСТВЕННЫЙ источник, пусто у контрагента значит пусто,
никакого фолбэка на `_legacy_*` колонки организации.

Один хелпер — везде, где нужен набор реквизитов организации (сериализатор
`/api/organizations`, генерация документов, публикации), обязаны вызывать
`org_requisites()`, а не читать поля Organization по отдельности и не
изобретать свой merge-паттерн "org или contractor" — второго источника
того же показателя не должно быть (Правило №6).
"""
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.services.documents.org_name_case import doc_case_org_name, org_name_exceptions

# Поля-реквизиты: при наличии привязанного контрагента читаются ИСКЛЮЧИТЕЛЬНО
# из него (не смешиваются "бери непустое" — иначе ровно та же болезнь
# расхождения, которую эта волна чинит). `name` (короткое отображаемое имя)
# сюда сознательно не входит — это рабочее поле organizations, а не
# юридический реквизит (см. _merge_org_with_contractor до этой правки).
REQUISITE_FIELDS: tuple[str, ...] = (
    "full_name",
    "inn",
    "kpp",
    "ogrn",
    "address",
    "signatory",
    "signatory_position",
    "signatory_last_name",
    "signatory_first_name",
    "signatory_middle_name",
)


def org_requisites(org: Organization, contractor: Optional[Contractor] = None) -> dict:
    """Вернуть словарь реквизитов организации `org`.

    Читает поля НАПРЯМУЮ из `contractor` (обычные mapped-колонки Contractor),
    а не через `org.<field>` (column_property со скалярным подзапросом).

    Это не «второй источник» (Правило №6 не нарушено: при наличии contractor
    значение — то же самое число, что вернул бы `org.<field>`, читается из
    того же Contractor.<field>, только напрямую, а не через подзапрос) — это
    защита от реальной ловушки async SQLAlchemy: если организация в текущей
    сессии была где-то закоммичена (даже правкой НЕ-реквизитного поля, напр.
    `org.region`/`org.director_last_name`), ORM молча «expire»-ит её
    column_property-атрибуты; следующий синхронный `getattr(org, 'inn')` вне
    `await` пытается тихо перезагрузить их и падает
    `sqlalchemy.exc.MissingGreenlet` (воспроизведено на этой волне:
    app/routers/organization_director.py — GET/POST .../director). Поля
    Contractor такой проблеме не подвержены (обычные колонки, не подзапрос).

    `contractor=None` (org без contractor_id — не должно происходить после
    миграции w6x7y8z9a0b1, но на случай гонки/битых данных) → все поля None,
    без обращения к `org.<field>` (та же причина — не трогаем
    column_property вовсе, если неоткуда ждать осмысленного значения).
    """
    if contractor is None:
        return {field: None for field in REQUISITE_FIELDS}
    return {field: getattr(contractor, field, None) for field in REQUISITE_FIELDS}


def resolve_org_display_name(
    org: Optional[Organization], contractor: Optional[Contractor]
) -> Optional[str]:
    """ЕДИНАЯ функция отображаемого имени организации (Правило №6) — дефект
    org id=69 на проде, 27.10.2026: `organizations.name`/`Organization.name`
    column_property читает ТОЛЬКО `contractor.name`, и если это поле у
    контрагента пусто (историческая запись, или форма создания org не
    заполнила его — см. create_organization), API отдавал None/"" — пустая
    строка в дропдауне выбора организации (DeptCreateDialog.vue) и 500
    ResponseValidationError на /api/hierarchy/graph (OrgOut.name: str).

    Приоритет, без второго хранимого источника — это именно ОТОБРАЖЕНИЕ, а
    не запись (ничего не персистируется здесь, в отличие от create_organization,
    который дозаполняет пустые поля контрагента при создании):
    1) `contractor.name` — короткое наименование, как ввёл пользователь;
    2) `contractor.full_name`, приведённое к обычному регистру через
       `doc_case_org_name` (app/services/documents/org_name_case.py) — ЕГРЮЛ
       отдаёт полное наименование КАПСОМ (владелец, 27.10.2026), та же
       функция и то же правило, что уже применяется при подстановке в
       документы; `org.doc_name_exceptions` (если `org` передан) учитывается
       так же, как и там;
    3) None — у контрагента вовсе нет названия (не должно происходить после
       фикса create_organization + бэкфилл-миграции; вызывающий сам решает,
       чем заменить None — не здесь, чтобы не плодить второй текст фолбэка).
    """
    if contractor is None:
        return None
    if contractor.name:
        return contractor.name
    if contractor.full_name:
        exceptions = org_name_exceptions(org) if org is not None else []
        return doc_case_org_name(contractor.full_name, exceptions) or None
    return None


async def bulk_org_requisites(db: AsyncSession, orgs: Iterable[Organization]) -> dict[int, dict]:
    """Реквизиты для набора организаций без N+1 запросов к contractors.

    Собирает все `contractor_id` разом в один SELECT. Полезно там, где
    Organization выбрана без eager-load связи `contractor` (в отличие от
    большинства запросов в app/routers/organizations.py, которые уже делают
    `selectinload(Organization.contractor)` — там N+1 и так не возникает,
    достаточно звать `org_requisites(org, org.contractor)`).
    """
    orgs = list(orgs)
    contractor_ids = {o.contractor_id for o in orgs if o.contractor_id}
    contractors_by_id: dict[int, Contractor] = {}
    if contractor_ids:
        rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors_by_id = {c.id: c for c in rows}
    return {
        o.id: org_requisites(o, contractors_by_id.get(o.contractor_id) if o.contractor_id else None)
        for o in orgs
    }
