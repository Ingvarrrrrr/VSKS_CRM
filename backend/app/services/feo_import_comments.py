"""Колонка «Комментарий» шаблона импорта ФЭО (владелец, 22.09): текст строки
файла уходит в ЛЕНТУ комментариев (таблица feo_comments, та же, что показывает
frontend/src/components/subsidies/FeoCommentThread.vue) — а НЕ в поле notes.
Правило №5 (модульность): отдельный файл, а не дописывание в
feo_import_apply.py (1565 строк) или feo_import_duplicates.py.

Правило №6 (один источник истины): запись FeoComment здесь — ЕДИНСТВЕННОЕ
место, где импорт ФЭО создаёт комментарии; создание/поиск самой позиции или
категории по-прежнему делают feo_import_apply.py/feo_import_duplicates.py —
этот модуль только читает уже присвоенные id, второй механизм апсерта
категории/позиции не заводит.

Два канала намерений, наполняемых `feo_import_apply.py` по ходу ОСНОВНОГО
цикла (регистратор — пара строк на месте вызова):

    register_item_comment_intent(state, row_num, text)
        Строка задала «Плановую позицию» (обычную ИЛИ без-уровневую/orphan —
        обе идут через `feo_import_duplicates.register_pending_item`, оба
        случая учтены одинаково). Итоговый id позиции известен только ПОСЛЕ
        `finalize_lvl5_items` (группировка дублей меняет кардинальность
        строка↔позиция — merge сливает несколько строк в одну позицию) —
        см. `record_item_id` ниже.

    register_category_comment_intent(state, leaf, row_num, text)
        Строка НЕ задала «Плановую позицию» — комментарий относится к
        КАТЕГОРИИ этой строки (самый глубокий заполненный уровень). `leaf`
        уже имеет реальный id: `find_or_create_category`
        (feo_import_common.py) всегда делает `db.flush()`.

record_item_id(state, row_num, item_id) — вызывается `feo_import_duplicates.py`
(`_upsert_one` и его вызывающие `_upsert_merge`/`_upsert_keep_separate`/
`finalize_lvl5_items` для одиночной строки) сразу после того, как
FeoPlannedItem получила реальный id — единственное место, знающее итоговую
привязку row_num → id позиции; второй раз группировку дублей здесь не
пересчитываем.

apply_feo_comments(state) — вызывается ОДИН раз из `feo_import_core.py`,
ПОСЛЕ `finalize_lvl5_items` (позиции уже имеют id). dry_run: комментарии НЕ
пишутся (транзакция и так откатится), но `state.comments_created` считается —
предпросмотр мастера показывает, сколько будет создано. Повторный импорт
того же файла не плодит дубли: ОДИН batch-запрос существующих комментариев
затронутых позиций/категорий (не по одному на строку), сравнение текста
после `strip()` (регистр — как есть, задача не просила нормализовывать
регистр). Пустая ячейка — `register_*` вызывать не нужно (см. `get_cell`,
возвращает None для пустых/«none»/«null»)."""
from sqlalchemy import select

from app.models.feo_comment import FeoComment


def register_item_comment_intent(state, row_num: int, text: str | None) -> None:
    """Комментарий строки, задавшей «Плановую позицию» (см. докстринг модуля)."""
    if not text:
        return
    state.comment_item_texts[row_num] = text


def register_category_comment_intent(state, leaf, row_num: int, text: str | None) -> None:
    """Комментарий строки БЕЗ «Плановой позиции» — относится к категории
    (`leaf`) этой строки. `leaf.id` уже реальный (см. докстринг модуля)."""
    if not text or leaf is None or leaf.id is None:
        return
    state.comment_category_intents.append((leaf.id, row_num, text))


def record_item_id(state, row_num: int, item_id: int) -> None:
    """Итоговый id FeoPlannedItem, в которую превратилась строка `row_num`
    (см. докстринг модуля — вызывается feo_import_duplicates.py)."""
    state.comment_item_ids[row_num] = item_id


async def apply_feo_comments(state) -> None:
    db = state.db
    user = state.user
    author_name = None
    if user is not None:
        author_name = getattr(user, "full_name", None) or getattr(user, "username", None)
    user_id = getattr(user, "id", None) if user is not None else None

    # (kind, target_id, text) — item/category в одном списке, порядок
    # появления в файле не важен (существующие тексты вычитываются batch'ем
    # ниже, а не по одной строке).
    intents: list[tuple[str, int, str]] = []
    for row_num, text in state.comment_item_texts.items():
        item_id = state.comment_item_ids.get(row_num)
        if item_id is None:
            # Строка была отменена пост-проходом (group_total_row) или её
            # позиция не создалась по иной причине — комментарий вешать не на что.
            continue
        stripped = text.strip()
        if stripped:
            intents.append(("item", item_id, stripped))
    for cat_id, _row_num, text in state.comment_category_intents:
        stripped = text.strip()
        if stripped:
            intents.append(("category", cat_id, stripped))

    if not intents:
        return

    item_ids = {t for k, t, _ in intents if k == "item"}
    cat_ids = {t for k, t, _ in intents if k == "category"}

    # Один batch-запрос на каждую сущность (не по одному на строку) — задача
    # владельца: повторный импорт того же файла не должен плодить дубли.
    existing_item_texts: dict[int, set[str]] = {}
    if item_ids:
        rows = (await db.execute(
            select(FeoComment.feo_planned_item_id, FeoComment.text)
            .where(FeoComment.feo_planned_item_id.in_(item_ids))
        )).all()
        for iid, txt in rows:
            existing_item_texts.setdefault(iid, set()).add((txt or "").strip())

    existing_cat_texts: dict[int, set[str]] = {}
    if cat_ids:
        rows = (await db.execute(
            select(FeoComment.feo_category_id, FeoComment.text)
            .where(FeoComment.feo_category_id.in_(cat_ids))
        )).all()
        for cid, txt in rows:
            existing_cat_texts.setdefault(cid, set()).add((txt or "").strip())

    seen_in_batch: set[tuple[str, int, str]] = set()
    created = 0
    for kind, target_id, text in intents:
        dedup_key = (kind, target_id, text)
        if dedup_key in seen_in_batch:
            # Тот же текст на ту же цель встретился дважды в ЭТОМ файле
            # (например, две строки-дубли Ур.5, разобранные «оставить как
            # есть», обе с одинаковым текстом комментария) — не плодим и
            # внутри одного импорта, не только между повторными импортами.
            continue
        seen_in_batch.add(dedup_key)
        existing = existing_item_texts.get(target_id, set()) if kind == "item" else existing_cat_texts.get(target_id, set())
        if text in existing:
            continue
        created += 1
        if state.dry_run:
            continue
        kwargs = dict(text=text, user_id=user_id, author_name=author_name)
        if kind == "item":
            kwargs["feo_planned_item_id"] = target_id
        else:
            kwargs["feo_category_id"] = target_id
        db.add(FeoComment(**kwargs))

    state.comments_created = created
