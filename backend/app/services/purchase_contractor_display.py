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

---

seller_display_for_advance — ВТОРАЯ, НО ЯВНО ОТДЕЛЬНАЯ развилка (владелец,
02.10): в реестре АВАНСОВЫХ (frontend/src/views/AdvanceReportsView.vue)
колонка "Контрагент" обязана показывать не то же самое, что
display_contractor_name — там показан продавец из чеков/позиций закупки, а
не «кому возмещать». Общий реестр закупок и его Excel-экспорт (purchase_export.
_get_cell_value) продолжают звать display_contractor_name — эта функция НЕ
подменяет её и не вызывается из тех путей, только из сборки реестра
авансовых (app.services.purchase_serializers._purchase_to_full →
multi_contractor_label — тот же единственный расчёт, второй копии формулы
«один продавец → имя, несколько разных → ярлык» не заводится: раньше это
дублировалось инлайном в _purchase_to_full, теперь вынесено сюда).

Правило: продавцы = различные контрагенты по позициям/чекам закупки
(PurchaseItem.contractor, см. app.services.item_contractor.item_contractor —
FK на Contractor либо текст). Если ни у одной позиции продавец не задан —
фолбэк на Purchase.contractor_id (шапка закупки). Один продавец → его
название; несколько различных → "Множественный контрагент" (полный список —
на вызывающей стороне, из тех же item_contractor_names, без второго расчёта).
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


def seller_display_for_advance(
    p: Purchase,
    *,
    item_contractor_names: list | None = None,
    header_contractor_name: str | None = None,
) -> str | None:
    """Продавец(ы) авансового отчёта — для колонки "Контрагент" РЕЕСТРА
    АВАНСОВЫХ (не общего реестра закупок, см. докстринг модуля выше).

    item_contractor_names — имена продавцов по позициям/чекам закупки (может
    содержать None/дубли — вызывающий не обязан дедуплицировать заранее).
    header_contractor_name — Contractor шапки закупки (Purchase.contractor_id),
    фолбэк, когда ни у одной позиции продавец не задан.
    """
    if getattr(p, "purchase_method", None) != "advance":
        return None
    unique_names = {n for n in (item_contractor_names or []) if n}
    if not unique_names:
        return header_contractor_name
    if len(unique_names) > 1:
        return "Множественный контрагент"
    return next(iter(unique_names))
