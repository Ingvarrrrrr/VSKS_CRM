"""Дедуп/материализация организаций-грантополучателей по данным контрагента.

Вынесено из app/routers/subsidies.py (Правило №5, рефакторинг 2026-09):
- `_materialize_org_from_contractor` — find-or-create Organization, зеркалящую
  контрагента субсидии (см. её докстринг про контур/Иерархию и root_org_id).
- `_merge_duplicate_orgs_by_inn` — идемпотентный мерж дублей organizations по ИНН.
  Раньше вызывался фоновым бэкафиллом app/startup/backfills.py на КАЖДОМ
  старте; перенесено в scripts/merge_duplicates_by_inn.py (D8/D9, волна 4b,
  Правило №6) — это разовый data-fix, не часть старта приложения.

Re-export обеих функций сохранён в app/routers/subsidies.py — тесты
(test_organization_root_org_id.py) импортируют `_materialize_org_from_contractor`
оттуда.
"""
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


async def _materialize_org_from_contractor(db: AsyncSession, contractor, account_org_id: Optional[int] = None):
    """Find-or-create Organization, зеркалящую контрагента (получатель субсидии),
    чтобы он попадал в контур (Персонал/Иерархия). Матч по contractor_id, затем по ИНН.
    Идемпотентно. Возвращает Organization (или None) — вызывающие используют её как
    org_id субсидии: субсидия принадлежит организации-грантополучателю, а не активной
    орг из свитчера (кейс ДНР_2026: владелец был ЦЕНТРПОИСК вместо Донецкого).

    2026-09-01: новая org, созданная тут, тоже не должна остаться без аккаунта —
    root_org_id берём из `account_org_id` (см. resolve_new_org_root_id), так же
    как в organizations.py::create_organization. `account_org_id` — обычно
    current_user.org_id вызывающего HTTP-эндпоинта; фоновый бэкафилл в
    app/__init__.py передаёт org_id уже существующей субсидии этого контрагента."""
    if contractor is None:
        return None
    from app.models.organization import Organization
    from app.services.org_account_resolution import resolve_new_org_root_id
    org = (await db.execute(
        select(Organization).where(Organization.contractor_id == contractor.id)
    )).scalars().first()
    if org is None and contractor.inn:
        # Organization.inn — вычисляемое поле контрагента (column_property),
        # этот where корректно разворачивается в подзапрос к contractors.
        org = (await db.execute(
            select(Organization).where(Organization.inn == contractor.inn)
        )).scalars().first()
    if org is None:
        _root_org_id = await resolve_new_org_root_id(db, account_org_id, None)
        # Правило №6: Organization НЕ хранит имя/реквизиты — только ссылку
        # на контрагента, который их уже содержит (если что-то у контрагента
        # пусто — значит пусто и у org, column_property читает contractor_id).
        org = Organization(
            contractor_id=contractor.id,
            root_org_id=_root_org_id,
            is_active=True,
        )
        db.add(org)
        await db.flush()
    elif org.contractor_id is None:
        org.contractor_id = contractor.id
    # Жалоба владельца (28.10.2026): организация-грантополучатель (эта функция)
    # зеркалит ЕГРЮЛ-данные контрагента, но без штата — выбрать подписанта
    # (руководителя из ЕГРЮЛ, Contractor.signatory_*) исполнителем/подписантом
    # закупки/заявки было некем, карточки сотрудника для него не было. Тот же
    # единственный механизм, что у кнопки «Добавить подписанта сотрудником»
    # (app/services/signatory_staff.py::get_or_create_signatory_staff_user) —
    # здесь только автовызов при материализации/обновлении связи орг-контрагент,
    # второй механизм не заводим. Идемпотентно — повторный вызов не дублирует.
    from app.services.signatory_staff import ensure_signatory_staff_for_org
    await ensure_signatory_staff_for_org(db, org)
    await db.commit()
    return org


async def _merge_duplicate_orgs_by_inn(db: AsyncSession, *, dry_run: bool = False) -> Optional[dict]:
    """Идемпотентный мерж дублей organizations по ИНН контрагента.

    ПРАВИЛО №6 (миграция w6x7y8z9a0b1, 16.10.2026): organizations.inn и
    organizations.name/full_name/kpp/ogrn/address/signatory — мёртвые
    legacy-колонки, новый код их больше не пишет (см. app/models/
    organization.py). Группировать дубли по ним означало бы сравнивать
    замороженные на момент миграции значения. Дубли теперь ищутся по
    `contractors.inn` привязанного контрагента (contractor_id организации),
    а «свежие данные» для реквизитных полей брать неоткуда и не из чего
    мержить — они не хранятся в organizations вовсе, поэтому мержатся
    только НЕ-реквизитные поля самой organizations (color/is_active/
    contractor_id).

    Алгоритм:
    - survivor = MIN(id) в группе (стабильный якорь).
    - Победа «свежих данных» для color/is_active/contractor_id: непустое
      значение из строки с MAX(id).
    - Все FK перепривязываются через information_schema (generic), SAVEPOINT
      защищает от конфликтов уникальных индексов (junction-таблицы).
    - losers удаляются, commit выполняется после всех групп.
    - Функция НЕ падает фатально — ошибка группы логируется и пропускается.

    dry_run=True (добавлено для CLI backend/scripts/merge_duplicates_by_inn.py,
    D8/D9) — только находит группы дублей и возвращает их размер, НИЧЕГО не
    пишет (ни rewire FK, ни merge полей, ни DELETE). Поведение по умолчанию
    (dry_run=False) не менялось; единственный вызывающий теперь —
    scripts/merge_duplicates_by_inn.py (раньше был app/startup/backfills.py —
    вызов оттуда убран, D8/D9, это разовый data-fix, а не часть старта).
    """
    _log = logging.getLogger(__name__)

    # 1. Найти группы дублей по ИНН контрагента (через contractor_id, НЕ по
    #    мёртвой organizations.inn — ПРАВИЛО №6).
    dup_result = await db.execute(text(
        "SELECT c.inn, array_agg(o.id ORDER BY o.id) AS ids "
        "FROM organizations o "
        "JOIN contractors c ON c.id = o.contractor_id "
        "WHERE c.inn IS NOT NULL AND btrim(c.inn) <> '' "
        "GROUP BY c.inn HAVING count(*) > 1"
    ))
    groups = dup_result.fetchall()

    if not groups:
        _log.info("org-merge по ИНН: дублей не найдено")
        return {"groups": 0, "merged": 0}

    if dry_run:
        return {"groups": len(groups), "merged": sum(len(row[1]) - 1 for row in groups)}

    # 2. Собрать FK-ссылки на organizations.id через information_schema (один раз)
    fk_result = await db.execute(text(
        "SELECT tc.table_name, kcu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "  AND tc.table_schema = kcu.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name "
        "  AND tc.table_schema = ccu.table_schema "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND ccu.table_name = 'organizations' "
        "  AND ccu.column_name = 'id'"
    ))
    fk_refs = fk_result.fetchall()  # список (table_name, column_name)

    # Поля для «свежих данных» — только НЕ-реквизитные (реквизиты теперь
    # только у контрагента, ПРАВИЛО №6; contractor_id у всей группы и так
    # совпадает, т.к. группа собрана по c.inn — но берём явно, на случай
    # если организации привязаны к РАЗНЫМ контрагентам с одним ИНН).
    _merge_fields = ["color", "contractor_id", "is_active"]

    total_deleted = 0
    n_groups = len(groups)

    for row in groups:
        inn_val = row[0]
        ids = row[1]  # уже упорядочены по возрастанию
        survivor_id = ids[0]
        loser_ids = ids[1:]

        try:
            # 3. Загрузить все строки группы и выбрать «свежие» непустые поля
            all_rows_result = await db.execute(
                text("SELECT id, color, contractor_id, is_active "
                     "FROM organizations WHERE id = ANY(:ids) ORDER BY id DESC"),
                {"ids": ids}
            )
            all_rows = all_rows_result.fetchall()

            # Для каждого поля: берём первое непустое значение при обходе от MAX к MIN id
            updates = {}
            for field_idx, field in enumerate(_merge_fields):
                for r in all_rows:
                    val = r[field_idx + 1]  # +1 т.к. id в col 0
                    if val is None:
                        continue
                    if isinstance(val, str) and val.strip() == "":
                        continue
                    updates[field] = val
                    break

            # Получить текущие значения survivor для сравнения
            surv_row_result = await db.execute(
                text("SELECT color, contractor_id, is_active "
                     "FROM organizations WHERE id = :sid"),
                {"sid": survivor_id}
            )
            surv_row = surv_row_result.fetchone()
            surv_dict = dict(zip(_merge_fields, surv_row)) if surv_row else {}

            # Применить только изменившиеся поля
            changed = {k: v for k, v in updates.items() if surv_dict.get(k) != v}
            if changed:
                set_clause = ", ".join(f"{k} = :{k}" for k in changed)
                changed["_sid"] = survivor_id
                await db.execute(
                    text(f"UPDATE organizations SET {set_clause} WHERE id = :_sid"),
                    changed
                )

            # 4. Перепривязать все FK (generic)
            for fk_table, fk_col in fk_refs:
                # Пропускаем self-reference organizations.id на organizations.id
                # (т.е. если таблица=organizations и колонка=id — это PK, не FK)
                # Но root_org_id — это FK и должен перепривязаться, он пройдёт как обычно
                try:
                    async with db.begin_nested():
                        await db.execute(
                            text(f'UPDATE "{fk_table}" SET "{fk_col}" = :surv '
                                 f'WHERE "{fk_col}" = ANY(:losers)'),
                            {"surv": survivor_id, "losers": loser_ids}
                        )
                except Exception as upd_err:
                    # Конфликт уникального индекса — fallback: удалить loser-строки
                    _log.warning(
                        f"org-merge: UPDATE {fk_table}.{fk_col} конфликт ({upd_err!r}), "
                        f"fallback DELETE loser-строк"
                    )
                    try:
                        async with db.begin_nested():
                            await db.execute(
                                text(f'DELETE FROM "{fk_table}" '
                                     f'WHERE "{fk_col}" = ANY(:losers)'),
                                {"losers": loser_ids}
                            )
                    except Exception as del_err:
                        _log.warning(
                            f"org-merge: DELETE fallback {fk_table}.{fk_col} тоже провалился: {del_err!r}"
                        )

            # 5. Удалить losers
            await db.execute(
                text("DELETE FROM organizations WHERE id = ANY(:losers)"),
                {"losers": loser_ids}
            )
            total_deleted += len(loser_ids)

        except Exception as group_err:
            _log.warning(
                f"org-merge: группа ИНН={inn_val!r} пропущена из-за ошибки: {group_err!r}"
            )
            continue

    await db.commit()
    _log.info(
        f"org-merge по ИНН: групп {n_groups}, удалено дублей {total_deleted}"
    )
    return {"groups": n_groups, "merged": total_deleted}
