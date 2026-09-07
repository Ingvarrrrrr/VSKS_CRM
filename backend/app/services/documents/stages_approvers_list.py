"""generate_document: approval_map load + item_categories + approvers_list rows
(with electronic-signature InlineImage lookup).

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.services.documents.morphology import _to_gen_fio, _to_gen_phrase
from app.services.documents.formatting import _fmt_money, _format_initials_safe
from app.services.responsible_role import is_responsible_role, is_blank_person_name, RESPONSIBLE_PLACEHOLDER


async def load_approval_map(db: AsyncSession, pid: int) -> dict:
    # Load existing PurchaseApproval records (electronic signatures)
    from app.models.purchase_approval import PurchaseApproval
    pa_res = await db.execute(
        select(PurchaseApproval)
        .where(PurchaseApproval.purchase_id == pid, PurchaseApproval.status == "approved")
        .order_by(PurchaseApproval.order_num)
    )
    # Map subsidy_approver_id → PurchaseApproval (for signature lookup)
    approval_map: dict = {}
    for pa in pa_res.scalars().all():
        if pa.subsidy_approver_id:
            approval_map[pa.subsidy_approver_id] = pa
    return approval_map


def build_item_categories_str(p: Purchase) -> str:
    # Collect unique product categories from items
    item_categories = list(dict.fromkeys(
        item.product.category
        for item in (p.items or [])
        if item.product and item.product.category
    ))
    return ", ".join(item_categories)


def build_approvers_list(selected_approvers, item_feo_paths, feo_path, p: Purchase,
                          resolved_responsible_full, approval_map: dict, fh_pa_by_synth_id: dict,
                          tpl, base64_to_inline) -> list:
    approvers_list = []
    for i, a in enumerate(selected_approvers):
        raw_full = a.full_name or ""
        # «Ответственный исполнитель» — роль-слот (app/services/responsible_role.py):
        # хранимое в subsidy_approvers ФИО для неё ИГНОРИРУЕТСЯ ВСЕГДА, даже если там
        # почему-то оказалось живое имя — источник истины только резолв по закупке.
        # Для остальных ролей подставляем резолв только если сохранённое ФИО пустое/плейсхолдер.
        if is_responsible_role(a.role_name) or is_blank_person_name(raw_full):
            raw_full = resolved_responsible_full or RESPONSIBLE_PLACEHOLDER
        if getattr(a, "show_feo_path", False) and item_feo_paths:
            note = "; ".join(f"{path} — {_fmt_money(total)} ₽" for path, total in item_feo_paths)
        elif getattr(a, "show_feo_path", False) and feo_path:
            item_type_label = {"товар": "Товары", "услуга": "Услуги"}.get(p.item_type or "", "")
            note = feo_path + (f" ({item_type_label})" if item_type_label else "")
        else:
            note = ""

        # Electronic signature — approval_map keyed by SubsidyApprover.id (денежное
        # согласование); fh_pa_by_synth_id — своя карта для цепочки необходимости
        # рамочной головы (см. блок выше, у тех строк subsidy_approver_id всегда NULL).
        pa = approval_map.get(a.id) or fh_pa_by_synth_id.get(a.id)
        signature_img = ""
        decided_date = ""
        if pa and pa.signature_data and pa.signature_algorithm == "visual":
            signature_img = base64_to_inline(tpl, pa.signature_data)
            if pa.decided_at:
                decided_date = pa.decided_at.strftime("%d.%m.%Y")

        approvers_list.append({
            "num": i + 1,
            "role_name": a.role_name,
            # Владелец: «в листе согласования ФИО целиком, а фамилия должна быть
            # целиком, имя-отчество инициалами» — печатаем сокращённую форму,
            # полное ФИО остаётся под отдельным ключом для шаблонов, которым
            # оно реально нужно (напр. текст договора).
            "full_name": _format_initials_safe(raw_full),
            "full_name_full": raw_full,
            "signature_img": signature_img,
            "decided_date": decided_date,
            "note": note,
            # Phase 26-V: родительный падеж — ОБЯЗАТЕЛЬНО от полного ФИО:
            # _to_gen_fio определяет пол по окончанию отчества
            # (parts[2].endswith(('вна','чна'))), от сокращённого «А.О.»
            # род не определится и склонение сломается.
            "full_name_gen": _to_gen_fio(raw_full),
            "role_name_gen": _to_gen_phrase(a.role_name or ""),
        })
    return approvers_list
