"""display_contractor_name — единый источник истины (ПРАВИЛО №6) для «кого
показывать контрагентом у закупки» — и в реестре закупок (PurchaseOutFull.
contractor_name, см. app.services.purchase_serializers._purchase_to_full),
и в Excel-экспорте реестра (колонка "contractor", см.
app.routers.purchase_export._get_cell_value). Второй копии этой развилки
нигде не заводить.

Владелец, 30.09: «Если это авансовый отчёт, то в столбце "Контрагент" должны
выводиться данные, кому его возмещать, а не у кого куплено». Продавцы из
чеков (позиций) остаются видны в карточке закупки и в разворотах позиций
(PurchaseItemOut.contractor_name на каждой строке) — эта функция их не трогает,
она только решает, что подставить в ШАПОЧНОЕ поле contractor_name закупки.

Порядок для purchase_method='advance':
  1) Purchase.reimbursement_user_id — «кому возмещать» (задаётся вручную,
     PATCHABLE_FIELDS в app/routers/purchases.py);
  2) Purchase.service_note_by — автор/инициатор авансового. Заполняется
     ВСЕГДА при создании закупки: либо wish.created_by (заявка →
     app.services.wish_distribution._distribute_wish_to_purchases), либо
     current_user.id (прямое «Новый авансовый отчёт» — см.
     app/routers/purchases.py::create_purchase, `dump["service_note_by"] =
     current_user.id`). Тем же значением на момент создания заполняется и
     created_by заявки-компаньона source='advance_report' — второй поход за
     Wish.created_by не нужен, service_note_by уже несёт то же имя.

Для остальных способов закупки — как и раньше: контрагент шапки закупки
(contractor_id, при наличии contract_id — из Contract, см.
app.services.purchase_contract_header).
"""
from app.models.purchase import Purchase


def display_contractor_name(
    p: Purchase,
    *,
    contractor_name: str | None = None,
    reimbursement_user_name: str | None = None,
    service_note_by_name: str | None = None,
) -> str | None:
    if getattr(p, "purchase_method", None) == "advance":
        return reimbursement_user_name or service_note_by_name or None
    return contractor_name
