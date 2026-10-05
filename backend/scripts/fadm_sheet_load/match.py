"""Сопоставление со старой субсидией («ФАДМ_2026»): найти субсидию-источник
по имени, найти «двойника» старой закупки для каждой единицы сопоставления
(parse.MatchUnit) и резолвить запасную категорию «Не определена».

Нормализация контрагента — contractor_norm.normalize_contractor_name (сама
опирается на ЕДИНЫЙ хелпер проекта app.services.vehicle_org_matching.
normalize_org_name, ПРАВИЛО №6 — см. её докстринг про найденный баг).

Matcher — ДВУХПРОХОДНОЕ сопоставление (владелец, правки 04.10.2026):
  1) match_contractor для каждого unit — контрагент (нормализован) + сумма
     unit'а ИЛИ одной из его строк совпадает с КАНОНИЧЕСКОЙ суммой старой
     закупки (допуск 0.01 ₽, см. _canonical_amount — contract_price →
     final_total_amount → planned_total_price → Σ PurchaseItem.total_price).
     Кандидат с канонической суммой ≤0 («без суммы») никогда не матчится —
     не должен создавать неоднозначность с реальными кандидатами.
  2) match_amount_only — запасной матч для того, что осталось НЕ
     сопоставлено контрагентом: сумма ≥1000 ₽, которая среди ОСТАВШИХСЯ (ещё
     не разобранных первым проходом) старых закупок и ОСТАВШИХСЯ unit'ов
     встречается РОВНО по одному разу с каждой стороны.
  Одна старая закупка используется только ОДИН раз за весь прогон (Matcher
  хранит _used между вызовами обоих проходов, на ОБА прохода).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy

from .contractor_norm import normalize_contractor_name
from .parse import MatchUnit, PurchaseGroup, is_monthly_group

AMOUNT_TOLERANCE = Decimal("0.01")
MIN_AMOUNT_ONLY = Decimal("1000")

TECH_CATEGORY_PARENT_NAME = "Техническое оснащение деятельности штаба"
NA_CATEGORY_NAME = "Не определена"

# Правило владельца (правки 2, прод-находка 04.10.2026) — тай-брейк при
# нескольких кандидатах с одинаковой суммой у ОДНОГО и того же контрагента:
# «живой» (более продвинутый по жизненному циклу) статус побеждает, при
# равенстве статуса — меньший id (более старая запись). Пример: СОБОЛЕВ №20
# 169 000 — закупки 771 (delivered) и 913 (contracted, известный дубль по
# проду) — тай-брейк отдаёт 771, 913 остаётся без пары.
STATUS_RANK: dict = {
    "paid": 7, "delivered": 6, "ordered": 5, "contracted": 4,
    "work_in_progress": 3, "plan_schedule": 2, "wishes": 1,
}


def _status_rank(status: Optional[str]) -> int:
    return STATUS_RANK.get(status or "", 0)


async def find_source_subsidy(db: AsyncSession, name: str) -> Subsidy:
    rows = (await db.execute(
        select(Subsidy).where(Subsidy.name == name).order_by(Subsidy.id.desc())
    )).scalars().all()
    if not rows:
        raise ValueError(f"Субсидия-источник {name!r} не найдена")
    return rows[0]


_STOPWORDS = {"и", "на", "для", "в", "с", "по", "к", "от", "из", "или", "не"}


def _name_words(*names: Optional[str]) -> set:
    out: set = set()
    for n in names:
        if not n:
            continue
        for w in str(n).lower().replace(",", " ").replace(".", " ").split():
            w = w.strip()
            if len(w) >= 3 and w not in _STOPWORDS:
                out.add(w)
    return out


def _canonical_amount(p: Purchase, item_totals: list[Decimal]) -> Decimal:
    """Правило владельца (п.1б): contract_price → final_total_amount →
    planned_total_price → Σ PurchaseItem.total_price. Первое заполненное
    (не None) побеждает — ОДНО число на старую закупку, а не список
    кандидатов (список из нескольких отдельных сумм позиций раньше создавал
    ложные совпадения — см. docstring Matcher)."""
    for v in (p.contract_price, p.final_total_amount, p.planned_total_price):
        if v is not None:
            return Decimal(str(v))
    return sum(item_totals, Decimal("0"))


@dataclass
class OldPurchase:
    id: int
    registry_number: Optional[str]
    contractor_id: Optional[int]
    contractor_name: Optional[str]
    contractor_norm: str
    has_contractor: bool
    status: str
    feo_category_id: Optional[int]
    assigned_user_id: Optional[int]
    service_note_to_user_id: Optional[int]
    service_note_by: Optional[int]
    responsible_person: Optional[str]
    total: Decimal
    name_words: set


async def load_old_purchases(db: AsyncSession, source_sid: int) -> list[OldPurchase]:
    purchases = (await db.execute(
        select(Purchase).where(Purchase.subsidy_id == source_sid)
    )).scalars().all()
    if not purchases:
        return []
    contractor_ids = {p.contractor_id for p in purchases if p.contractor_id}
    contractors: dict[int, Contractor] = {}
    if contractor_ids:
        rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors = {c.id: c for c in rows}

    items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_([p.id for p in purchases]))
    )).scalars().all()
    items_by_purchase: dict[int, list[PurchaseItem]] = {}
    for it in items:
        items_by_purchase.setdefault(it.purchase_id, []).append(it)

    out: list[OldPurchase] = []
    for p in purchases:
        contractor = contractors.get(p.contractor_id) if p.contractor_id else None
        c_norm = normalize_contractor_name(contractor.name) if contractor else ""
        p_items = items_by_purchase.get(p.id, [])
        item_totals = [Decimal(str(it.total_price)) for it in p_items if it.total_price is not None]
        words = _name_words(p.item_name, p.subject, *(it.item_name for it in p_items))
        out.append(OldPurchase(
            id=p.id,
            registry_number=p.registry_number,
            contractor_id=p.contractor_id,
            contractor_name=contractor.name if contractor else None,
            contractor_norm=c_norm,
            has_contractor=bool(p.contractor_id),
            status=p.status,
            feo_category_id=p.feo_category_id,
            assigned_user_id=p.assigned_user_id,
            service_note_to_user_id=p.service_note_to_user_id,
            service_note_by=p.service_note_by,
            responsible_person=p.responsible_person,
            total=_canonical_amount(p, item_totals),
            name_words=words,
        ))
    return out


@dataclass
class MatchResult:
    twin: Optional[OldPurchase] = None
    ambiguous: bool = False
    candidates: Optional[list] = None
    method: Optional[str] = None  # 'контрагент+сумма' | 'по сумме'


class Matcher:
    """Стейтфул-сопоставитель на весь прогон — см. docstring модуля. Один
    экземпляр на всю загрузку (и на --match-only, и на build.py), чтобы
    «одна старая закупка — максимум один двойник» выполнялось ГЛОБАЛЬНО, а
    не в пределах одной группы."""

    def __init__(self, old_purchases: list[OldPurchase]):
        self._old = {op.id: op for op in old_purchases}
        self._used: set = set()

    def unused(self) -> list[OldPurchase]:
        return [op for op in self._old.values() if op.id not in self._used]

    def mark_used(self, old_id: int) -> None:
        self._used.add(old_id)

    def match_contractor(self, unit: MatchUnit) -> MatchResult:
        """Правило владельца — два РАЗНЫХ пула кандидатов, НЕ смешиваются:
        1) контрагент (нормализован) совпал — основной путь;
        2) «без контрагента у старой закупки» (п.1 задания) — запасной путь
           ТОЛЬКО для контрагентов-пустышек, проверяется, ЕСЛИ пул (1) пуст.

        Находка на реальных данных (СОБОЛЕВ №20, 169 000 ₽): старая закупка
        771 (контрагент «ИП Соболев...», та же сумма) и старая закупка 913
        (контрагент НЕ указан, но contract_price тоже 169 000 И название
        «Багажник…» пересекается словами) раньше считались РАВНОЦЕННЫМИ
        кандидатами и давали ложную неоднозначность. 913 — валидный кандидат
        ТОЛЬКО в отсутствие совпадения по контрагенту; раз контрагент прямо
        указан в таблице И нашёлся у старой закупки 771 — пул (2) вообще не
        рассматривается."""
        targets = [unit.total_amount] + [r.amount for r in unit.rows]
        unit_words = _name_words(unit.first_name, *(r.name for r in unit.rows))

        def _best(op: OldPurchase) -> Optional[Decimal]:
            best = None
            for t in targets:
                d = abs(op.total - t)
                if d <= AMOUNT_TOLERANCE and (best is None or d < best):
                    best = d
            return best

        by_contractor: list[tuple[Decimal, OldPurchase]] = []
        by_words: list[tuple[Decimal, OldPurchase]] = []
        for op in self.unused():
            if op.total <= 0:
                continue  # «без суммы» — никогда не кандидат
            if op.has_contractor:
                if unit.contractor_norm and op.contractor_norm == unit.contractor_norm:
                    d = _best(op)
                    if d is not None:
                        by_contractor.append((d, op))
            else:
                if unit_words & op.name_words:
                    d = _best(op)
                    if d is not None:
                        by_words.append((d, op))

        scored = by_contractor or by_words
        method = "контрагент+сумма" if by_contractor else "без контрагента+сумма+название"
        if not scored:
            return MatchResult(twin=None, ambiguous=False)
        scored.sort(key=lambda x: x[0])
        tied = [s for s in scored if s[0] == scored[0][0]]
        if len(tied) > 1:
            # Тай-брейк (правило владельца, правки 2): выше статус побеждает,
            # при равенстве статуса — меньший id. Остальные тай-кандидаты
            # просто не выбираются (не помечаются used) — остаются доступны
            # более поздним проходам/других unit'ов, если им подойдут иначе.
            tied.sort(key=lambda s: (-_status_rank(s[1].status), s[1].id))
            twin = tied[0][1]
            self._used.add(twin.id)
            return MatchResult(twin=twin, ambiguous=False, method=f"{method} [тай-брейк]")
        twin = scored[0][1]
        self._used.add(twin.id)
        return MatchResult(twin=twin, ambiguous=False, method=method)

    def match_amount_only(self, pending: list[MatchUnit]) -> dict:
        """Правило владельца (п.1г) — запасной матч «по сумме» для того, что
        НЕ сопоставилось контрагентом: amount ≥1000 ₽, встречающаяся РОВНО
        один раз и среди оставшихся старых закупок, и среди оставшихся
        unit'ов. Возвращает {unit.key: MatchResult}."""
        avail = self.unused()
        old_count: Counter = Counter()
        old_by_amount: dict[Decimal, OldPurchase] = {}
        for op in avail:
            if op.total >= MIN_AMOUNT_ONLY:
                old_count[op.total] += 1
                old_by_amount[op.total] = op
        unit_count: Counter = Counter()
        for u in pending:
            if u.total_amount >= MIN_AMOUNT_ONLY:
                unit_count[u.total_amount] += 1

        results: dict = {}
        for u in pending:
            amt = u.total_amount
            if amt < MIN_AMOUNT_ONLY:
                continue
            if old_count.get(amt) == 1 and unit_count.get(amt) == 1:
                op = old_by_amount[amt]
                self._used.add(op.id)
                results[u.key] = MatchResult(twin=op, ambiguous=False, method="по сумме")
        return results

    def match_contractor_only_zero(self, groups: list[PurchaseGroup], matches: dict) -> None:
        """Правило владельца (правки 3): если по контрагенту+сумме НЕ
        нашлось (match_contractor вернул пусто/не used), а у старой ФАДМ
        РОВНО одна ещё свободная закупка этого контрагента с суммой 0/пусто,
        И в таблице у этого контрагента РОВНО одна группа (рамочная/
        помесячная считается ОДНОЙ группой — PurchaseGroup, не заказ) —
        матчим. Примеры с прода: РИТЕЙЛ-ГРУПП №75 (рамочная) → РЕЕ-843;
        ПРЕДРЕЙСОВЫЙ №8 (помесячная) → РЕЕ-820.

        Для рамочной — twin садится на ГОЛОВУ (ключ (contractor_norm,
        purchase_no, None), которого обычные MatchUnit'ы не используют — его
        подставляет build.py/match_only.py при построении головы) И на
        КАЖДЫЙ заказ, у которого нет СВОЕГО отдельного двойника (правило:
        «исполнитель/направление идёт на голову и на все заказы без своего
        двойника») — мутирует `matches` на месте."""
        group_count: Counter = Counter(g.contractor_norm for g in groups if g.contractor_norm)
        zero_by_contractor: dict[str, list[OldPurchase]] = {}
        for op in self.unused():
            if op.has_contractor and op.total <= 0:
                zero_by_contractor.setdefault(op.contractor_norm, []).append(op)

        for g in groups:
            cnorm = g.contractor_norm
            if not cnorm or group_count.get(cnorm) != 1:
                continue
            candidates = zero_by_contractor.get(cnorm) or []
            if len(candidates) != 1:
                continue
            twin = candidates[0]
            result = MatchResult(twin=twin, ambiguous=False, method="контрагент, сумма пустая")

            is_monthly = is_monthly_group(g)
            is_framework = (not is_monthly) and len(g.distinct_order_nos) >= 2
            if not is_framework:
                key = (cnorm, g.purchase_no, None)
                existing = matches.get(key)
                if existing and existing.twin:
                    continue  # уже сопоставлено иначе — не перетирать
                matches[key] = result
                self.mark_used(twin.id)
                continue

            order_nos = {(r.order_no or "") for r in g.rows}
            orphan_keys = []
            for order_no in order_nos:
                k = (cnorm, g.purchase_no, order_no)
                m = matches.get(k)
                if not (m and m.twin):
                    orphan_keys.append(k)
            if not orphan_keys:
                continue  # все заказы уже сопоставлены своими двойниками
            head_key = (cnorm, g.purchase_no, None)
            matches[head_key] = result
            for k in orphan_keys:
                matches[k] = result
            self.mark_used(twin.id)


async def find_na_category(db: AsyncSession, new_subsidy_id: int) -> Optional[int]:
    """Категория «Не определена» уровня 3 под «Техническое оснащение
    деятельности штаба» в НОВОМ дереве — поиск по имени, не по id."""
    parent = (await db.execute(
        select(FeoCategory).where(
            FeoCategory.subsidy_id == new_subsidy_id,
            FeoCategory.name == TECH_CATEGORY_PARENT_NAME,
        )
    )).scalars().first()
    if not parent:
        return None
    child = (await db.execute(
        select(FeoCategory).where(
            FeoCategory.subsidy_id == new_subsidy_id,
            FeoCategory.parent_id == parent.id,
            FeoCategory.name == NA_CATEGORY_NAME,
        )
    )).scalars().first()
    if child:
        return child.id
    any_na = (await db.execute(
        select(FeoCategory).where(
            FeoCategory.subsidy_id == new_subsidy_id,
            FeoCategory.name == NA_CATEGORY_NAME,
        )
    )).scalars().first()
    return any_na.id if any_na else None


@dataclass
class ContractorLookup:
    """Превью поиска контрагента (задание, п.2) — ТОЛЬКО чтение, не создаёт
    ничего; find_or_create_contractor (писатель) вызывается уже в build.py,
    НЕ здесь — match-only не должен импортировать ни одной функции записи."""
    by_norm: dict = field(default_factory=dict)  # normalized name -> [contractor_id,...]

    def find_one(self, raw_name: str) -> Optional[int]:
        norm = normalize_contractor_name(raw_name)
        if not norm:
            return None
        ids = self.by_norm.get(norm) or []
        return ids[0] if len(ids) == 1 else None

    def ambiguous(self, raw_name: str) -> bool:
        norm = normalize_contractor_name(raw_name)
        return len(self.by_norm.get(norm) or []) > 1


async def load_contractor_lookup(db: AsyncSession) -> ContractorLookup:
    """Индекс ПО ВСЕЙ таблице contractors (не только старой ФАДМ) — задание
    владельца, п.2: «искать существующего по всей таблице contractors»."""
    rows = (await db.execute(select(Contractor.id, Contractor.name))).all()
    lookup = ContractorLookup()
    for cid, name in rows:
        norm = normalize_contractor_name(name)
        if not norm:
            continue
        lookup.by_norm.setdefault(norm, []).append(cid)
    return lookup


def run_matching(groups: list[PurchaseGroup], units: list[MatchUnit],
                  old_purchases: list[OldPurchase]) -> tuple[Matcher, dict]:
    """ТРИ прохода Matcher'а (см. докстринги match_contractor/match_amount_
    only/match_contractor_only_zero) — ЕДИНСТВЕННОЕ место, где они собраны по
    порядку (ПРАВИЛО №6): используется И --match-only (только отчёт, не
    пишет), И build.py (реальная сборка) — один и тот же результат."""
    matcher = Matcher(old_purchases)
    matches: dict = {}
    pending: list[MatchUnit] = []
    for u in units:
        res = matcher.match_contractor(u)
        matches[u.key] = res
        if not (res.twin or res.ambiguous):
            pending.append(u)
    matches.update(matcher.match_amount_only(pending))
    matcher.match_contractor_only_zero(groups, matches)
    return matcher, matches
