"""Кто может быть указан инициатором/адресатом/исполнителем служебной
записки и приказа о закупке (Правило владельца, 22.10.2026).

«В служебных записках и приказах могут быть только те, кто устроен в данной
организации» — организация берётся из субсидии закупки (subsidies.org_id, а
НЕ Purchase, у Purchase своего org_id нет). «Устроен» = ШТАТ организации
(primary User.org_id ИЛИ членство user_organizations) — ровно то же понятие
«штата», что уже считает app.services.service_note_initiators.org_staff_user_ids
(ПРАВИЛО №6: формула штата не дублируется, читаем оттуда).

Разведка перед правкой (22.10.2026) показала, что из трёх полей в документ
реально попадает только ИНИЦИАТОР:
  - Purchase.service_note_by → app.services.documents.stages_relations.
    resolve_initiator → контекст {{initiator_name}} — печатается в
    service_note*.docx И order_purchase.docx (общий контекст для всех
    doc_type, см. app.services.documents.contexts_build).
  - Purchase.service_note_to_user_id («адресат») — проверено скан по
    backend/templates/*.docx (распакован .docx, текст document.xml без
    тегов): плейсхолдера под это поле НИ В ОДНОМ шаблоне нет. Поле хранится
    (видно на карточке закупки), но в печатный документ не попадает. Тем не
    менее Правило владельца называет его прямо — ограничиваем независимо от
    того, печатается оно сегодня или нет (на будущее, если шаблон появится).
  - Purchase.assigned_user_id («исполнитель») — тоже проверено сканом той же
    пары шаблонов: ни {{responsible_person}}, ни любой другой плейсхолдер,
    завязанный на assigned_user, в service_note*.docx/order_purchase.docx
    НЕ печатается (resolve_responsible_person в stages_relations.py строит
    "Ответственного исполнителя" для КОНТРАКТНЫХ документов — в контракт
    же "штат" ограничивать не просили). Поэтому assigned_user_id сюда
    СОЗНАТЕЛЬНО не включён — Правило владельца явно разрешает не
    ограничивать его, если он не попадает в документ.

Используется из app/routers/purchases.py (PUT/PATCH) — единственное место
серверной проверки на СОХРАНЕНИИ закупки. Генерация самого документа
(resolve_initiator) проверяет инициатора отдельно, через
initiator_candidate_ids — ТА проверка шире (учитывает роль выбирающего), но
ВКЛЮЧАЕТ требование штата как подмножество (initiator_candidate_ids всегда
⊆ org_staff_user_ids). Здесь — минимальный, не зависящий от роли выбирающего
гейт «штат или 400», применяемый при самом сохранении, а не только при
печати.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.service_note_initiators import org_staff_user_ids

# Поле Purchase → (ключ правила, человекочитаемая роль в сообщении об ошибке).
# Порядок — как в сообщении владельца: инициатор, адресат, исполнитель.
SERVICE_NOTE_PEOPLE_FIELDS: dict[str, str] = {
    "service_note_by": "Инициатор служебной записки",
    "service_note_to_user_id": "Адресат служебной записки",
}


async def assert_service_note_people_in_staff(
    db: AsyncSession,
    purchase,
    changes: dict,
) -> None:
    """changes — {field: новое_значение_user_id}, ТОЛЬКО реально меняющиеся
    поля (вызывающий уже сверил со старым значением p.<field> — см. вызовы в
    purchases.py). Поля без записи в `changes` не проверяются.

    Субсидии нет или у неё нет org_id — штата не существует, проверка
    пропускается (та же логика фолбэка, что в initiator_candidate_ids).
    """
    relevant = {
        field: val
        for field, val in (changes or {}).items()
        if field in SERVICE_NOTE_PEOPLE_FIELDS and val is not None
    }
    if not relevant:
        return

    from app.models.subsidy import Subsidy

    subsidy_id = getattr(purchase, "subsidy_id", None)
    subsidy: Optional[Subsidy] = await db.get(Subsidy, subsidy_id) if subsidy_id else None
    org_id = getattr(subsidy, "org_id", None) if subsidy else None
    if not org_id:
        return

    staff = await org_staff_user_ids(db, org_id)

    from app.models.organization import Organization
    org = await db.get(Organization, org_id)
    org_name = getattr(org, "name", "") if org else ""

    for field, user_id in relevant.items():
        if user_id in staff:
            continue
        role_label = SERVICE_NOTE_PEOPLE_FIELDS[field]
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SERVICE_NOTE_PERSON_NOT_STAFF",
                "message": (
                    f"{role_label} должен быть сотрудником организации"
                    + (f" «{org_name}»" if org_name else "")
                ),
            },
        )
