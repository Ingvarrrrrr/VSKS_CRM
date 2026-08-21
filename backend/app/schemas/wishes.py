from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal

# wishes.title — VARCHAR(500). Заголовок формируется на фронте из названий
# позиций; при множестве товаров он может превысить лимит → раньше падало
# INTERNAL_ERROR (StringDataRightTruncation). Клампим централизованно.
_TITLE_MAX = 500


def _clamp_title(v: Optional[str]) -> Optional[str]:
    if v and len(v) > _TITLE_MAX:
        return v[:_TITLE_MAX - 1] + "…"
    return v


def _blank_to_none(v):
    """Пустая строка из формы для опционального поля = «не заполнено» = None.
    Иначе pydantic роняет date/Decimal на '' с непонятным VALIDATION_ERROR."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class WishItemPurchaseMatch(BaseModel):
    """W-diff (2026-08-13): сведения о «двойнике» позиции заявки в закупке —
    нужны фронту для двух вещей, которые он сам посчитать не может:
    1) какие позиции остановлены, а какие идут (purchase_stopped_at);
    2) чип «в закупке иначе» — сравнение feo_category_id/quantity/unit_price/
       total_price этой модели с одноимёнными полями WishItemOut.

    Только читает, ничего не чинит: если сопоставить не удалось — все поля
    пустые (match_method=None), кроме, при неоднозначности по имени,
    ambiguous_candidates_count.
    """
    # 'wish_item_id' — надёжная прямая связь purchase_items.wish_item_id;
    # 'item_name' — старые данные без связи, сопоставлено по точному
    #   нормализованному имени (единственный кандидат) среди позиций закупок
    #   ЭТОЙ ЖЕ заявки;
    # 'item_name_qty' — по имени нашлось НЕСКОЛЬКО позиций закупки, но после
    #   сужения точным совпадением quantity остался ровно один кандидат
    #   (напр. одно и то же название дважды в заявке с разным количеством —
    #   человек различает их количеством, не наугад);
    # 'item_name_ambiguous' — по имени (и, если пробовали, по количеству)
    #   всё ещё НЕСКОЛЬКО позиций закупки (см. ambiguous_candidates_count) —
    #   специально не выбираем наугад, остальные поля в этом случае пустые.
    match_method: Optional[str] = None
    ambiguous_candidates_count: Optional[int] = None  # только при match_method='item_name_ambiguous'
    purchase_item_id: Optional[int] = None
    purchase_id: Optional[int] = None
    purchase_number: Optional[int] = None
    purchase_status: Optional[str] = None
    # Не пусто — закупка (или её рамочный договор) остановлена: см. app.routers.wishes.stop_wish.
    # По этому полю фронт красит позицию как «остановлена» vs «идёт».
    purchase_stopped_at: Optional[datetime] = None
    feo_category_id: Optional[int] = None
    feo_category_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class WishPurchaseSync(BaseModel):
    """Ответ повторного согласования заявки, у которой уже есть закупка (план
    crystalline-soaring-heron.md, п.2) — приведение существующей закупки к
    текущему состоянию заявки. См. app.routers.wishes._sync_purchase_from_wish.
    Фронт использует для предпросмотра «что изменилось» (предмет было/стало,
    добавленные/убранные/изменённые позиции). `blocked_reason` непусто, если
    закупка ушла дальше «Плана закупок» — тогда предмет/состав НЕ менялись, и
    остальные списки (items_added/items_removed/items_changed) пустые.

    QA-правки (2026-08-21): items_conflicted — поля (quantity/unit_price/
    total_price), которые правили В ЗАКУПКЕ после переноса (значение разошлось
    со снимком planned_*) — из заявки НЕ перезаписаны, конфликт возвращён на
    показ человеку. items_kept_manual — строки закупки без живой связи с этой
    заявкой (заведены закупщиком прямо в закупке) — НЕ удалены при сверке с
    заявкой, но и не участвуют в её составе; список для «эти позиции остались,
    не потерялись»."""
    purchase_id: int
    registry_number: Optional[str] = None
    subject_before: Optional[str] = None
    subject_after: Optional[str] = None
    items_added: List[dict] = []
    items_removed: List[dict] = []
    items_changed: List[dict] = []
    items_conflicted: List[dict] = []
    items_kept_manual: List[dict] = []
    blocked_reason: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class WishPurchaseSummary(BaseModel):
    """Пункт 4 (владелец, 2026-08-13): «из согласованной заявки нужно перейти
    в закупку(и), которые из неё исполняются; если их несколько — выпадающий
    список». purchase_ids (List[int]) для этого недостаточно — фронту нужны
    номер/статус/сумма для каждой закупки, чтобы список был осмысленным, без
    догадок и доп. запросов на клике. Заполняется батчем (см. _wish_purchase_summaries_map
    в app.routers.wishes) — так же, как purchase_ids/items_total рядом."""
    id: int
    purchase_number: Optional[int] = None
    registry_number: Optional[str] = None
    item_name: Optional[str] = None
    status: Optional[str] = None
    status_label: Optional[str] = None
    amount: Optional[Decimal] = None
    stopped_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class WishItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    item_name: str
    item_type: Optional[str] = "товар"
    quantity: Optional[float] = 1
    unit: Optional[str] = "шт"
    unit_price: Optional[float] = 0
    total_price: Optional[float] = 0
    country_origin: Optional[str] = "РФ"
    target_column_key: Optional[str] = None  # Phase 13 D-04: kanban column override
    feo_category_id: Optional[int] = None  # B9: per-item FEO category
    feo_planned_item_id: Optional[int] = None  # привязка к плановой позиции плана закупок (mirrors PurchaseItem.feo_planned_item_id)
    feo_planned_item_match_confirmed: bool = False  # человек подтвердил похожую-по-имени привязку (см. WishItem model)
    needed_date: Optional[date] = None  # W2: дата потребности per-item
    vat_rate: Optional[str] = None  # per-item НДС ставка (mirrors PurchaseItem.vat_rate)
    over_plan: bool = False  # false — расходует план элемента ФЭО; true — сверх плана (mirrors PurchaseItem.over_plan)
    # W-diff (2026-08-13): «двойник» позиции в закупке — заполняется ТОЛЬКО в карточке
    # заявки (GET /{wish_id}), в списке (GET /) отсутствует (лишний вес). См. WishItemPurchaseMatch.
    purchase_match: Optional[WishItemPurchaseMatch] = None
    model_config = ConfigDict(from_attributes=True)


class WishItemPatch(BaseModel):
    """D-04: Patch payload for drag-drop column reassignment."""
    target_column_key: Optional[str] = None


class WishCreate(BaseModel):
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    subsidy_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    event_id: Optional[int] = None
    assigned_to: Optional[int] = None
    feo_per_item: bool = False  # режим «своя категория ФЭО для каждого товара»
    vat_mode: Optional[str] = None  # 'uniform' | 'per_item'
    # Контрагент — необязательное поле (владелец, 2026-08-17): либо ссылка на
    # справочник (contractor_id), либо просто имя от руки, если контрагента
    # там ещё нет (contractor_name). Ни то, ни другое не обязательно и не
    # блокирует сохранение/согласование/конвертацию заявки.
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    items: Optional[list] = None  # list of dicts with item_name, item_type, quantity, unit, unit_price, total_price, country_origin

    @field_validator('title')
    @classmethod
    def _v_title(cls, v):
        return _clamp_title(v)

    @field_validator('desired_date', 'quantity', 'estimated_price', mode='before')
    @classmethod
    def _v_blank(cls, v):
        return _blank_to_none(v)


class WishUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    subsidy_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    event_id: Optional[int] = None
    assigned_to: Optional[int] = None
    # Optional[...] = None (не bool = False) намеренно: update_wish делает
    # body.model_dump(exclude_none=True) — default False затирал бы существующее
    # значение при каждом частичном PUT, не содержащем это поле.
    feo_per_item: Optional[bool] = None
    vat_mode: Optional[str] = None  # 'uniform' | 'per_item'
    # Контрагент — см. WishCreate.contractor_id/contractor_name. Optional[...] = None,
    # как и у остальных полей формы заявки (feo_category_id/subsidy_id выше) —
    # общий model_dump(exclude_none=True) в update_wish по-прежнему трактует
    # отсутствующий/null ключ как «не менять». НО контрагент — необязательное
    # поле, которое обязано уметь и ОЧИЩАТЬСЯ явным null (иначе поставить его
    # можно, а снять — нельзя ничем). update_wish обрабатывает это точечно,
    # ПОСЛЕ общего exclude_none-дампа: смотрит body.model_fields_set (Pydantic v2
    # помечает поле как «set», если ключ реально присутствовал в теле запроса,
    # даже если значение null) — так отличает «прислали null» (очистить) от
    # «ключ не прислали вовсе» (не трогать, например автосохранение другого
    # поля). См. комментарий в app/routers/wishes.py::update_wish.
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    items: Optional[list] = None  # list of dicts with item_name, item_type, quantity, unit, unit_price, total_price, country_origin

    @field_validator('title')
    @classmethod
    def _v_title(cls, v):
        return _clamp_title(v)

    @field_validator('desired_date', 'quantity', 'estimated_price', mode='before')
    @classmethod
    def _v_blank(cls, v):
        return _blank_to_none(v)


class WishReject(BaseModel):
    rejection_reason: str


class WishStop(BaseModel):
    """POST /{wish_id}/stop — необязательная причина остановки."""
    reason: Optional[str] = None


class WishItemFeoPatch(BaseModel):
    """Владелец (2026-08-19): согласующий из цепочки может перераспределять
    позиции заявки по категориям/плановым позициям ФЭО, НЕ трогая состав
    (название/кол-во/цену/ед./страну) — тот заблокирован для него на фронте
    (PurchaseItemsEditor readonly + feoAttrsEditable). Только эти два поля
    и попадают в патч построчно, см. patch_wish_execution."""
    id: int
    feo_category_id: Optional[int] = None
    feo_planned_item_id: Optional[int] = None


class WishExecutionPatch(BaseModel):
    """B-exec: approver sets executor + execution deadline + event + assigned_to."""
    executor_id: Optional[int] = None
    execution_deadline: Optional[date] = None
    event_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    assigned_to: Optional[int] = None
    # Построчные ФЭО-правки согласующего (см. WishItemFeoPatch) — отдельно от
    # WishUpdate.items (тот меняет состав, доступен только автору/участнику).
    items: Optional[List[WishItemFeoPatch]] = None


class WishStatusForce(BaseModel):
    """Superadmin: force-set wish status (bypass workflow guards)."""
    status: str  # draft / submitted / approved / rejected / converted


class WishConvert(BaseModel):
    approved_quantity: Optional[Decimal] = None
    approved_price: Optional[Decimal] = None
    subsidy_id: Optional[int] = None


class WishOut(BaseModel):
    id: int
    org_id: int
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    # Владелец (2026-08-19): «нужно, чтобы было видно, кто отклонил» — переживает
    # сброс WishApproval-цепочки (см. Wish.rejected_by докстринг в models/wish.py).
    rejected_by: Optional[int] = None
    rejected_at: Optional[datetime] = None
    rejected_by_name: Optional[str] = None
    created_by: int
    creator_name: Optional[str] = None
    approved_by: Optional[int] = None
    approver_name: Optional[str] = None
    purchase_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    subsidy_id: Optional[int] = None
    subsidy_name: Optional[str] = None
    feo_category_id: Optional[int] = None
    feo_per_item: bool = False  # режим «своя категория ФЭО для каждого товара»
    vat_mode: Optional[str] = None  # 'uniform' | 'per_item'
    # Контрагент заявки — необязательный (владелец, 2026-08-17). contractor_id —
    # ссылка на справочник, contractor_name — свободный ввод, когда контрагента
    # там ещё нет. contractor_display_name — готовое имя для показа: из
    # справочника, если contractor_id задан, иначе contractor_name — фронту не
    # нужно резолвить самому (см. _enrich в app.routers.wishes).
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    contractor_display_name: Optional[str] = None
    event_id: Optional[int] = None
    event_name: Optional[str] = None
    assigned_to: Optional[int] = None
    assignee_name: Optional[str] = None
    assigned_to_name: Optional[str] = None  # alias for legacy frontend
    executor_id: Optional[int] = None
    executor_name: Optional[str] = None
    execution_deadline: Optional[date] = None
    approval_mode: Optional[str] = None
    # «От кого»: имена участников заявки (WishMember), помимо автора
    member_names: List[str] = []
    # «Кому»: цепочка согласующих (WishApproval, по order_num)
    approver_names: List[str] = []
    # Все закупки, созданные из заявки (конвертация разбивает по категориям)
    purchase_ids: List[int] = []
    # Пункт 4 (владелец, 2026-08-13): то же самое, но с номером/статусом/суммой —
    # для меню «Перейти в закупку». purchase_ids НЕ убираем (используется как есть).
    purchases: List[WishPurchaseSummary] = []
    items: List[WishItemOut] = []
    # Phase 31: diff-tracking — unseen changes from other users
    unseen_fields: List[str] = []
    unseen_changes_count: int = 0
    # Предупреждение конвертации (например, удалённая категория ФЭО обнулена)
    convert_warning: Optional[str] = None
    # Владелец (2026-08-12): согласование больше не блокируется несогласованным
    # превышением плана ФЭО — вместо отказа список предупреждений по категориям,
    # где план после создания закупок превышает финансирование (см.
    # _collect_excess_warnings в app.routers.wishes). Пустой список — превышения нет.
    excess_warnings: List[dict] = []
    # Плановые позиции следуют за сменой категории (владелец, 2026-08-17):
    # непусто, когда PUT сменил категорию ФЭО у позиции заявки, чья плановая
    # позиция была общей с другими закупками/заявками — переехать она не
    # смогла (испортила бы план для остальных), привязка снята явно, а не
    # молча. См. app/services/plan_autoassign.py::move_or_detach_planned_item.
    plan_transfer_warnings: List[str] = []
    # Повторное согласование, приведение существующей закупки к заявке (план
    # crystalline-soaring-heron.md, п.2) — см. WishPurchaseSync. None — либо
    # закупка ещё не создавалась, либо этот вызов её не создавал/не проверял.
    purchase_sync: Optional[WishPurchaseSync] = None
    # 'advance_report' = авто-заявка из авансового отчёта; NULL = обычная
    source: Optional[str] = None
    # W1: True если привязанная закупка перешла в Договор+ (редактирование запрещено)
    contracted_locked: bool = False
    # Правка владельца (2026-08-18): человекочитаемое описание блокирующих закупок
    # («№890 «...» — стадия «Заказано»») для баннера на фронте — раньше текст был
    # захардкожен «на этапе «Договор»» независимо от реальной стадии. None, если
    # заявка не заблокирована. См. _wish_locked_descr в app/routers/wishes.py.
    contracted_locked_reason: Optional[str] = None
    # Остановка заявки (владелец, 2026-08-13) — см. POST /{wish_id}/stop
    stopped_at: Optional[datetime] = None
    stopped_by: Optional[int] = None
    stopped_by_name: Optional[str] = None
    stopped_reason: Optional[str] = None
    stopped_partial: bool = False
    # Владелец: столбец «сумма заявки» на листе /wishes — Σ total_price её
    # позиций (WishItem), НЕ то же самое, что estimated_price (единая ручная
    # оценка на уровне заявки, не сумма по позициям). Список считает батчем
    # одним агрегирующим запросом (см. list_wishes); карточка — из уже
    # загруженных items, без доп. запроса.
    items_total: Optional[Decimal] = None

    class Config:
        from_attributes = True
