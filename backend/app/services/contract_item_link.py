"""Восстановление связи ContractItem.source_item_id → PurchaseItem.

Диагноз прод-инцидента (сессия 2026-09-01, 26 позиций без ФЭО-категории в
закупках 767, 785, 802, 807, 808, 841, 886, 902):

1. ``update_purchase`` (app/routers/purchases.py) на КАЖДОМ PUT закупки
   удаляет ВСЕ её PurchaseItem (``DELETE ... WHERE purchase_id = pid``) и
   вставляет их заново — новые строки получают НОВЫЕ id. У ContractItem
   FK ``source_item_id`` объявлен ``ON DELETE SET NULL`` — Postgres обнуляет
   его сразу же, в рамках того же DELETE, для каждой договорной позиции,
   ссылавшейся на удалённую плановую.
2. Следом фронт (CreateOrderView.vue) отдельным запросом
   ``PUT /api/purchases/{id}/contract-items`` присылает договорные позиции
   СО СТАРЫМИ ``source_item_id`` (он их не знает — не видел пересоздания).
   ``replace_all_contract_items`` не находит такие id среди PurchaseItem
   этой закупки и молча выбрасывает поле из payload — связь теряется
   окончательно.

Итог: ``documents.py::_build_contract_item_feo_paths`` не может определить
ФЭО-категорию договорной позиции (она берётся ИСКЛЮЧИТЕЛЬНО через
``source_item_id`` — намеренно, чтобы не унаследовать чужую категорию, см.
docstring там же) → в лист согласования печатается
``FEO_PATH_UNRESOLVED_LABEL``. ``feo_plan.py`` тоже теряет приоритетный
расчёт факта по ``source_item_id``.

Этот модуль — общий матчер «договорная позиция → плановая позиция ТОЙ ЖЕ
закупки», вызываемый и из ``update_purchase`` (с ``id_map`` — точным
сопоставлением старых/новых id), и из ``replace_all_contract_items``
(без ``id_map`` — по имени/цене/позиции), и из миграции backfill (там —
чистым SQL, без этого модуля, т.к. для уже осевших на проде NULL старый id
физически нигде не сохранён).

Принцип, продиктованный владельцем (см. documents.py:920-924): при
неоднозначности НИЧЕГО не связывать. Честное «категория не определена»
лучше подставленной чужой категории.

РАЗБИЕНИЕ ДОГОВОРНОЙ ПОЗИЦИИ (D-05, см. splitContractRow в
PurchaseItemsEditor.vue) — легальный случай, который этот модуль обязан
поддерживать, а не путать с неоднозначностью: пользователь делит одну
договорную позицию на две строки с ОДНИМ И ТЕМ ЖЕ source_item_id (обычно
разными quantity/unit_price — в этом смысл разбиения).
``_build_contract_item_feo_paths`` (documents.py) с этим работает корректно,
суммируя обе строки в одну ФЭО-категорию плановой позиции — родитель у них
объективно один, никакого гадания тут нет. Поэтому:

- Pass 0 (точная карта id_map) не гейтится через ``occupied`` вовсе — карта
  точна по построению, и если она указывает двум разным договорным строкам
  на один и тот же новый id плановой позиции, это и есть разбиение.
- Pass 1/2 (совпадение по имени) разрешают повторно использовать уже занятую
  плановую позицию, если та занята договорной позицией С ТЕМ ЖЕ
  нормализованным именем — это ровно сигнатура разбиения (были две
  договорные строки с одинаковым именем, но только одна плановая позиция
  с этим именем — значит, разбиение, а не неоднозначность плана).
- Pass 3/4 (quantity+unit_price, позиционный) остаются строгими: у разбитых
  строк количества/суммы как раз РАЗНЫЕ, повтор там означал бы реальную
  ошибку матчинга, а не легальное разбиение.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.purchase_item import PurchaseItem


def _norm_name(value: Optional[str]) -> str:
    """trim + lowercase, устойчиво к None."""
    return (value or "").strip().lower()


# Снимок старой плановой позиции для build_purchase_item_id_map:
# (id, item_name, quantity, unit_price).
OldItemSnapshot = Tuple[int, Optional[str], object, object]


def build_purchase_item_id_map(
    old_snapshot: Sequence[OldItemSnapshot],
    new_items: Sequence[PurchaseItem],
) -> Dict[int, int]:
    """Строит карту «старый PurchaseItem.id → новый PurchaseItem.id».

    Нужна вызывающему коду (``update_purchase``), который снимает снимок
    старых позиций ДО их удаления, а после delete+insert получает те же
    (по смыслу) позиции под новыми id — карта восстанавливает соответствие,
    чтобы затем прогнать Pass 0 в :func:`relink_contract_items`.

    Правила (в порядке применения, тот же принцип «неоднозначно — пропуск»,
    что и в relink_contract_items):

    - Точное совпадение ``item_name`` среди ещё не сопоставленных новых
      позиций с этим именем, только если кандидат ровно один.
    - Позиционно 1↔1 (``ORDER BY id``) для того, что осталось несопоставленным
      по имени — но только если количество оставшихся старых позиций РАВНО
      количеству оставшихся новых. Иначе оставляем их вне карты (relink
      попробует найти их через Pass 1-4 по актуальным данным).

    ``quantity``/``unit_price`` из снимка не используются здесь напрямую —
    они переданы вызывающему для возможного будущего расширения, но точное
    совпадение по цене уже покрывается Pass 3 внутри relink_contract_items
    (которое сработает следующим шагом, если id_map позицию не покрыл).
    """
    id_map: Dict[int, int] = {}
    new_sorted = sorted(new_items, key=lambda ni: ni.id)

    new_by_name: Dict[str, List[PurchaseItem]] = {}
    for ni in new_sorted:
        new_by_name.setdefault(ni.item_name, []).append(ni)

    used_new_ids: set[int] = set()
    remaining_old: List[OldItemSnapshot] = []
    for old_id, name, quantity, unit_price in sorted(old_snapshot, key=lambda s: s[0]):
        candidates = [ni for ni in new_by_name.get(name, []) if ni.id not in used_new_ids]
        if len(candidates) == 1:
            match = candidates[0]
            id_map[old_id] = match.id
            used_new_ids.add(match.id)
        else:
            remaining_old.append((old_id, name, quantity, unit_price))

    unused_new = [ni for ni in new_sorted if ni.id not in used_new_ids]
    if remaining_old and len(remaining_old) == len(unused_new):
        for (old_id, _name, _qty, _price), ni in zip(remaining_old, unused_new):
            id_map[old_id] = ni.id

    return id_map


async def relink_contract_items(
    db: AsyncSession,
    purchase_id: int,
    id_map: Optional[Dict[int, int]] = None,
) -> int:
    """Восстанавливает ContractItem.source_item_id для закупки purchase_id.

    Обрабатывает только договорные позиции, у которых текущий
    ``source_item_id`` отсутствует (NULL) либо указывает на PurchaseItem,
    которой больше нет (обнулено каскадом или относится к чужой закупке —
    последнее в норме не должно происходить, но проверяется явно как
    защита от порчи данных).

    Проходы применяются по порядку, ПЕРВЫЙ сработавший для конкретной
    договорной позиции побеждает — дальше эта позиция не трогается:

    - **Pass 0** (только если передан ``id_map``): если старый
      ``source_item_id`` есть в ``id_map`` (старый id плановой позиции →
      новый), проставляем новый id напрямую. Это точное восстановление —
      единственный проход без эвристики, вызывающий код должен передавать
      ``id_map`` только когда действительно знает, что это ТА ЖЕ позиция
      под новым id (см. update_purchase). Гейт ``occupied`` тут НЕ
      применяется: карта точна по построению, и если она уводит две разные
      договорные позиции на один и тот же новый id — это разбитая позиция
      (D-05), у которой ОБЕ половины обязаны получить общего родителя.
    - **Pass 1**: точное совпадение ``PurchaseItem.item_name ==
      ContractItem.name`` среди позиций ЭТОЙ закупки — только если кандидат
      ровно один. Плановая позиция, уже занятая договорной с ТЕМ ЖЕ именем
      (в т.ч. с прошлых проходов/вызовов), не блокирует — это сигнатура
      разбиения, не неоднозначность.
    - **Pass 2**: то же по нормализованному имени (trim + lower) — только
      при единственном кандидате, с тем же послаблением для позиций,
      занятых договорной с тем же нормализованным именем.
    - **Pass 3**: совпадение по ``quantity`` И ``unit_price`` одновременно
      (оба должны быть заданы) — только при единственном кандидате.
    - **Pass 4**: позиционный 1↔1 (``ORDER BY id``) — включается ТОЛЬКО если
      ни одна плановая позиция закупки ещё не занята НИ ОДНОЙ договорной (ни
      исходно, ни через Pass 0-3 этого же прогона) И число плановых позиций
      закупки равно числу договорных. Это самый рискованный проход — по
      построению он либо связывает ВСЕ позиции закупки разом (полностью
      "чистое" состояние), либо не срабатывает вовсе.

    Жёсткие инварианты:

    - Никогда не связывает с PurchaseItem другой закупки (запрос заранее
      ограничен ``purchase_id``).
    - Одна плановая позиция не достаётся двум договорным СЛУЧАЙНО в рамках
      одного вызова — используется карта ``claimed_by_name``, растущая по
      ходу проходов. Единственное намеренное исключение — разбитые позиции
      (см. docstring модуля): им общий родитель полагается по построению,
      а не по случайному совпадению эвристики.
    - Неоднозначность → NULL остаётся NULL. Это прямое требование владельца
      (см. docstring ``_build_contract_item_feo_paths`` в documents.py) —
      честная "категория не определена" лучше подмены.
    - Идемпотентна: повторный вызов на уже связанных позициях — no-op
      (``_is_broken`` для них — False).
    - Коммит НЕ делает — это ответственность вызывающего кода.

    Returns:
        Количество договорных позиций, для которых источник был восстановлен.
    """
    ci_result = await db.execute(
        select(ContractItem).where(ContractItem.purchase_id == purchase_id)
    )
    contract_items = list(ci_result.scalars().all())
    if not contract_items:
        return 0

    pi_result = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )
    purchase_items = list(pi_result.scalars().all())
    pi_by_id = {pi.id: pi for pi in purchase_items}

    def _is_broken(ci: ContractItem) -> bool:
        return ci.source_item_id is None or ci.source_item_id not in pi_by_id

    # Позиции, уже корректно связанные (в т.ч. с прошлых вызовов), держат
    # свою плановую позицию занятой — на неё нельзя переставить другую
    # договорную ни в одном из проходов ниже, КРОМЕ Pass 1/2 по имени, где
    # повторное использование разрешено, если занявшая её договорная
    # позиция имеет ТОТ ЖЕ нормализованный name (сигнатура разбиения,
    # см. docstring модуля).
    #
    # claimed_by_name: plan_item_id → нормализованное имя договорной
    # позиции, которая его заняла. occupied — плоское множество тех же id,
    # используется проходами 3/4, где послабление недопустимо.
    claimed_by_name: Dict[int, str] = {
        ci.source_item_id: _norm_name(ci.name)
        for ci in contract_items if not _is_broken(ci)
    }
    occupied: set[int] = set(claimed_by_name.keys())

    broken = sorted((ci for ci in contract_items if _is_broken(ci)), key=lambda ci: ci.id)
    if not broken:
        return 0

    relinked = 0

    # Pass 0 — точная карта старый id → новый id. Без гейта occupied: карта
    # точна по построению, две договорные позиции, уводящие на один новый
    # id, — это разбитая позиция (D-05), обеим полагается общий родитель.
    if id_map:
        for ci in broken:
            if not _is_broken(ci):
                continue
            old_id = ci.source_item_id
            new_id = id_map.get(old_id) if old_id is not None else None
            if new_id is not None and new_id in pi_by_id:
                ci.source_item_id = new_id
                occupied.add(new_id)
                claimed_by_name[new_id] = _norm_name(ci.name)
                relinked += 1

    # Pass 1 — точное имя, единственный кандидат. Плановая позиция доступна,
    # если свободна ИЛИ занята договорной позицией с тем же именем.
    for ci in broken:
        if not _is_broken(ci):
            continue
        candidates = [
            pi for pi in purchase_items
            if pi.item_name == ci.name
            and (pi.id not in claimed_by_name or claimed_by_name[pi.id] == _norm_name(ci.name))
        ]
        if len(candidates) == 1:
            pi = candidates[0]
            ci.source_item_id = pi.id
            occupied.add(pi.id)
            claimed_by_name[pi.id] = _norm_name(ci.name)
            relinked += 1

    # Pass 2 — нормализованное имя (trim + lower), единственный кандидат.
    # То же послабление для повторного использования разбитой позиции.
    for ci in broken:
        if not _is_broken(ci):
            continue
        norm_name = _norm_name(ci.name)
        candidates = [
            pi for pi in purchase_items
            if _norm_name(pi.item_name) == norm_name
            and (pi.id not in claimed_by_name or claimed_by_name[pi.id] == norm_name)
        ]
        if len(candidates) == 1:
            pi = candidates[0]
            ci.source_item_id = pi.id
            occupied.add(pi.id)
            claimed_by_name[pi.id] = norm_name
            relinked += 1

    # Pass 3 — quantity И unit_price одновременно, единственный кандидат.
    # Строгий occupied: у разбитых строк количества/суммы как раз РАЗНЫЕ,
    # повтор здесь означал бы реальную ошибку матчинга.
    for ci in broken:
        if not _is_broken(ci):
            continue
        if ci.quantity is None or ci.unit_price is None:
            continue
        candidates = [
            pi for pi in purchase_items
            if pi.id not in occupied
            and pi.quantity is not None and pi.unit_price is not None
            and pi.quantity == ci.quantity and pi.unit_price == ci.unit_price
        ]
        if len(candidates) == 1:
            pi = candidates[0]
            ci.source_item_id = pi.id
            occupied.add(pi.id)
            claimed_by_name[pi.id] = _norm_name(ci.name)
            relinked += 1

    # Pass 4 — позиционный 1↔1. Только если СОВСЕМ ничего не занято (ни
    # исходно, ни проходами 0-3 выше) и число плановых позиций закупки
    # равно числу договорных — иначе порядок id ничего не гарантирует.
    if not occupied and len(purchase_items) == len(contract_items):
        pi_sorted = sorted(purchase_items, key=lambda pi: pi.id)
        ci_sorted = sorted(contract_items, key=lambda ci: ci.id)
        for pi, ci in zip(pi_sorted, ci_sorted):
            if _is_broken(ci):
                ci.source_item_id = pi.id
                occupied.add(pi.id)
                claimed_by_name[pi.id] = _norm_name(ci.name)
                relinked += 1

    return relinked
