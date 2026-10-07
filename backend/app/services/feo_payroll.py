"""feo_payroll.py — ОДНА формула «статья ФОТ по имени» (ПРАВИЛО №6).

Повод: субсидия «ДНР» (прод id 76) — статьи «ФОТ ДНР», «НДФЛ 13%»,
«страховой взнос 7,8%», «командировочные» падали в «без типа» на карточках,
хотя у колонки «Товар/услуга/работа» для СТАТЕЙ типа нет вовсе (это ФОТ, не
товар и не услуга и не «без типа» — см. план .planning/quick/2026-10-07-dnr-
feo-cards/PLAN.md шаг 2). Признак `is_payroll` статьи (ручной переключатель
ИЛИ автоматически при импорте/миграции по этому правилу имени) делает её
позиции (и позиции всех подкатегорий) видом `payroll` в разбивках по типу
(app.services.item_type_split.KIND_PAYROLL), независимо от item_type самой
позиции.

Единственная реализация правила «похоже на ФОТ по названию» — миграция
e3f5g7h9i1j3 (разовый backfill) и импорт ФЭО (feo_import_apply.py, при
создании статьи) обязаны звать ЭТУ функцию, а не копировать regex повторно.

ВАЖНО (найдено при проверке на проде, 07.10.2026): «фот» матчить только как
ОТДЕЛЬНОЕ слово — иначе статья «Расходы на приобретение основных средств
(оргтехника, фото-, видеотехники...)» ложно попадает в ФОТ из-за подстроки
«фот» внутри «фото-». Границы слова — `[^а-яёa-z]` по обе стороны (или
начало/конец строки), а не `\b` (между кириллицей и границей слова `\b`
может вести себя непредсказуемо в зависимости от локали движка regex)."""
import re
from typing import Iterable

_PAYROLL_RE = re.compile(
    r"(^|[^а-яёa-z])фот([^а-яёa-z]|$)"       # «ФОТ» отдельным словом (не «фото-»)
    r"|оплат[а-яё]*\s+труда"                   # «оплата труда», «оплату труда»...
    r"|выплат[а-яё]*\s+персонал",              # «выплаты персоналу», «выплата персоналу»...
    re.IGNORECASE,
)


def is_payroll_name(name: str | None) -> bool:
    """True, если название статьи ФЭО похоже на «ФОТ и иные выплаты
    персоналу» (ключевые слова «ФОТ» отдельным словом / «оплата труда» /
    «выплаты персоналу», регистронезависимо). Пустое имя → False."""
    if not name:
        return False
    return bool(_PAYROLL_RE.search(name))


async def payroll_category_ids(db, subsidy_ids: Iterable[int]) -> set:
    """ЕДИНСТВЕННЫЙ резолвер «какие категории ФЭО субсидий считаются ФОТ» —
    статья с FeoCategory.is_payroll=True делает payroll СЕБЯ и ЛЮБУЮ
    подкатегорию (наследование по дереву, план .planning/quick/2026-10-07-
    dnr-feo-cards/PLAN.md шаг 2). Везде, где нужно классифицировать позицию
    закупки/ФЭО как payroll по категории (а не по item_type, см.
    app.services.item_type_split.kind_of_for_category) — звать ЭТУ функцию,
    а не ходить в FeoCategory напрямую (ПРАВИЛО №6).

    Возвращает set id ВСЕХ категорий (себя + потомков) в указанных
    субсидиях, которые эффективно payroll."""
    from sqlalchemy import select
    from app.models.feo_category import FeoCategory

    subsidy_ids = list(subsidy_ids)
    if not subsidy_ids:
        return set()
    rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.parent_id, FeoCategory.is_payroll)
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )).all()
    if not rows:
        return set()
    parent_of = {r.id: r.parent_id for r in rows}
    own_payroll = {r.id for r in rows if r.is_payroll}

    _memo: dict = {}

    def _effective(cid: int) -> bool:
        if cid in _memo:
            return _memo[cid]
        if cid in own_payroll:
            _memo[cid] = True
            return True
        parent_id = parent_of.get(cid)
        result = _effective(parent_id) if parent_id is not None and parent_id in parent_of else False
        _memo[cid] = result
        return result

    return {r.id for r in rows if _effective(r.id)}
