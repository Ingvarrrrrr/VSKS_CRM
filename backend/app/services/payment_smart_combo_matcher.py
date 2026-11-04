"""Умный поиск составных сумм (Subset Sum) и ранжирование комбинаций по
смысловой и категорийной близости («Очень вероятно» vs «Маловероятно»).

Решает две задачи владельца (01.11.2026):
1. Когда в выписке есть платёж (например, на 800 ₽), у которого не нашёлся
   исполнитель/закупка (в т.ч. потому что закупки загружены из Excel со
   статусами Да/Нет без указания контрагента и порядковых номеров — «напокупали,
   а проставить у кого и как забыли»), находит комбинации из 1–4 непривязанных
   закупок/позиций, дающих в сумме сумму платежа, и оценивает вероятность каждой
   комбинации по близости категорий:
     - «Огнетушитель 500 + Рукав пожарный 300» → Очень вероятно (одна категория /
       пожарно-спасательная тематика / смежные строки);
     - «Огнетушитель 500 + Батон хлеба 300» → Маловероятно (разные категории:
       пожарное имущество vs продукты питания).
2. Позволяет найти источник произвольного расхождения (например, 28 000 ₽ в
   сверке/таблице): перебирает составные суммы (2–4 позиции), проверяет ловушку
   знака (14 000 ₽ = 28 000 ₽ ÷ 2) и предлагает объединить выбранную комбинацию
   закупок в одну закупку с автопростановкой контрагента из платёжки.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from datetime import date as _date
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy_allocation import PurchaseSubsidyAllocation
from app.services.purchase_sheet_ref import resolve_sheet_ref

# Правило владельца (04.11.2026): допуск для автоматического совпадения ЖЁСТКИЙ (0.00 ₽).
# Любое расхождение даже в 1 копейку или несколько рублей (0 < |Δ| <= APPROVAL_TOL)
# НЕ приравнивается автоматически, а помечается статусом "needs_approval"
# («Требует согласования суммы») и выносится на ручное подтверждение человека.
AMOUNT_TOL = Decimal("0.00")
APPROVAL_TOL = Decimal("5.00")
SINGLE_ROUNDING_TOL = APPROVAL_TOL
MAX_COMBO_SIZE = 100
MAX_POOL_SIZE = 150
MAX_COMBO_RESULTS = 10

_WORD_RE = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)

# Тематические кластеры по корням слов для определения смысловой категории,
# когда в импортированных строках не указан справочный товар или одна общая ФЭО.
_SEMANTIC_CLUSTERS: list[tuple[str, tuple[str, ...]]] = [
    ("Пожарно-спасательное имущество и СИЗ", (
        "огнетуш", "рукав", "пожар", "боп", "каск", "шлем", "фонар", "сиз",
        "спасат", "респират", "противогаз", "аптечк", "носилк", "карабин",
        "веревк", "верёвк", "альпинист", "мотопомп", "ствол", "гидрант",
    )),
    ("Продукты питания и вода", (
        "хлеб", "батон", "булк", "питан", "продукт", "обед", "завтрак", "ужин",
        "вода", "воды", "питьев", "сухпа", "паёк", "паек", "круп", "макарон",
        "тушенк", "тушёнк", "консерв", "кофе", "сахар", "молок", "мяс",
        "рыб", "овощ", "фрукт", "кондитер", "печень",
    )),
    ("Автотранспорт, ГСМ и запчасти", (
        "автомоб", "машин", "шин", "колес", "колёс", "масл", "аккумулят",
        "запчаст", "топлив", "бензин", "дизел", "гсм", "антифриз", "тормоз",
        "фильтр", "свеч", "ремонт тс", "техобслуж", "шиномонтаж", "лебедк",
        "бортировк", "балансировк", "мойк", "химчистк", "уаз", "патриот",
        "haval", "lada", "junfeng",
    )),
    ("ИТ, связь и оргтехника", (
        "ноутбук", "компьютер", "моноблок", "монитор", "принтер", "мфу",
        "картридж", "тонер", "мышь", "клавиатур", "кабел", "роутер", "маршрутиз",
        "коммутат", "сервер", "диск", "флешк", "радиостанц", "рация", "рации",
        "антенн", "связ", "интернет",
    )),
    ("Полиграфия, форма и сувенирная продукция", (
        "баннер", "флаг", "вымпел", "футболк", "кепк", "бейсболк", "куртк",
        "жилет", "костюм", "обувь", "берц", "ботинк", "значк", "медал",
        "грамот", "диплом", "буклет", "листовк", "печат", "брендир", "шеврон",
        "нашивк", "табличк", "стенд", "календар", "ежедневник", "гравировк",
        "сувенир", "полиграф", "логотип", "плакат", "открытк",
    )),
    ("Канцелярия и хозтовары", (
        "бумаг", "ручк", "карандаш", "папк", "скоросшив", "степлер", "скрепк",
        "блокнот", "тетрад", "маркер", "клей", "ножниц", "скотч", "конверт",
        "мыло", "салфетк", "мешк", "пакет", "перчатк", "ведро", "швабр",
        "чайник", "термопот", "кулер",
    )),
    ("Мебель и оборудование лагеря", (
        "стол", "стул", "кресл", "шкаф", "тумб", "кроват", "матрас", "стеллаж",
        "палатк", "тент", "шатер", "шатёр", "спальник", "спальн", "коврик",
        "генератор", "обогреват", "тепловентилят", "пушк", "сейф", "стремянк",
    )),
    ("Проживание и транспортные услуги", (
        "проживан", "гостиниц", "отел", "хостел", "перевозк", "автобус",
        "трансфер", "билет", "авиабилет", "жд билет", "аренд", "медосмотр",
        "предрейсов",
    )),
]


@dataclass
class CandidateUnit:
    """Единица для перебора: закупка (или её конкретная позиция), ещё не
    оплаченная по выписке."""
    purchase_id: int
    registry_number: Optional[str]
    subject: str
    amount: Decimal
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    contractor_inn: Optional[str] = None
    feo_category_id: Optional[int] = None
    feo_category_name: Optional[str] = None
    feo_parent_id: Optional[int] = None
    product_category: Optional[str] = None
    item_type: Optional[str] = None
    item_names: list[str] = field(default_factory=list)
    sheet_ref: Optional[str] = None
    row_hint: Optional[int] = None
    is_declared_paid: bool = False
    is_sub_item: bool = False
    purchase_item_id: Optional[int] = None


def detect_semantic_cluster(text: str) -> Optional[str]:
    """Определяет смысловой кластер по названию позиции/предмета закупки."""
    if not text:
        return None
    low = text.lower().replace("ё", "е")
    for label, stems in _SEMANTIC_CLUSTERS:
        for stem in stems:
            if stem in low:
                return label
    return None


def _word_stems(text: str) -> set[str]:
    if not text:
        return set()
    low = text.lower().replace("ё", "е")
    words = _WORD_RE.findall(low)
    return {w[:5] if len(w) >= 6 else w for w in words if len(w) >= 3}


def _unit_category_signature(u: CandidateUnit) -> dict:
    combined_text = " ".join([u.subject or ""] + (u.item_names or []))
    semantic = detect_semantic_cluster(combined_text)
    return {
        "semantic": semantic,
        "product_category": (u.product_category or "").strip() or None,
        "feo_category_id": u.feo_category_id,
        "feo_category_name": u.feo_category_name,
        "feo_parent_id": u.feo_parent_id,
        "item_type": (u.item_type or "").strip().lower() or None,
        "stems": _word_stems(combined_text),
    }



def is_unit_contractor_conflicting(
    u: CandidateUnit,
    payee_name: Optional[str] = None,
    payee_inn: Optional[str] = None,
) -> bool:
    """Возвращает True, если закупка явно принадлежит ДРУГОМУ контрагенту,
    и не может быть привязана к платежу с данным payee_name / payee_inn."""
    p_inn = str(payee_inn or "").strip()
    u_inn = str(u.contractor_inn or "").strip()
    if p_inn and u_inn and p_inn != u_inn:
        return True

    p_name_low = str(payee_name or "").lower().replace("«", '"').replace("»", '"')
    # Кавычки проверяем ТОЛЬКО в названии контрагента, а не в предмете закупки
    # (в предмете в кавычках бывают марки товаров: Авто хранитель "Премиум", "Таир", "Защита").
    u_cname_text = str(u.contractor_name or "").lower().replace("«", '"').replace("»", '"')
    quotes = re.findall(r'"([^"]{3,})"', u_cname_text)
    for q in quotes:
        q_clean = q.strip().lower()
        if q_clean not in ("прочее", "товар", "услуга", "товары", "услуги", "договор", "заказ"):
            if p_name_low and q_clean not in p_name_low:
                return True

    # Если у закупки явно задан контрагент, а у платежа другое имя
    if u.contractor_name and p_name_low:
        u_cname = u.contractor_name.lower().replace("«", '"').replace("»", '"')
        if u_cname and u_cname not in p_name_low and p_name_low not in u_cname:
            u_stems = _word_stems(u_cname) - {"общ", "огран", "ответ", "ооо", "индив", "предп"}
            p_stems = _word_stems(p_name_low) - {"общ", "огран", "ответ", "ооо", "индив", "предп"}
            if u_stems and not (u_stems & p_stems):
                return True

    return False


def _unit_payee_priority(u: CandidateUnit, payee_name: Optional[str], payee_inn: Optional[str]) -> int:
    """Приоритет кандидата для конкретного платежа:
    0 — точное совпадение ИНН или названия контрагента;
    1 — закупка без контрагента;
    2 — прочие."""
    p_inn = str(payee_inn or "").strip()
    u_inn = str(u.contractor_inn or "").strip()
    if p_inn and u_inn and p_inn == u_inn:
        return 0

    p_name = str(payee_name or "").lower().replace("«", '"').replace("»", '"')
    u_name = str(u.contractor_name or "").lower().replace("«", '"').replace("»", '"')
    if p_name and u_name and (p_name in u_name or u_name in p_name):
        return 0

    if p_name and u_name:
        quotes = re.findall(r'"([^"]{3,})"', u_name)
        for q in quotes:
            q_clean = q.strip().lower()
            if q_clean not in ("прочее", "товар", "услуга", "товары", "услуги") and q_clean in p_name:
                return 0

    if u.contractor_id is None and not u.contractor_inn:
        return 1

    return 2


def is_same_contractor_unit(
    u: CandidateUnit,
    payee_name: Optional[str],
    payee_inn: Optional[str],
) -> bool:
    """Возвращает True, если у закупки УЖЕ указан конкретный подрядчик и он
    совпадает с получателем выплаты (по ИНН или названию)."""
    if u.contractor_id is None and not u.contractor_inn and not u.contractor_name:
        return False
    return _unit_payee_priority(u, payee_name, payee_inn) == 0


def evaluate_combo_coherence(
    units: list[CandidateUnit],
    purpose_text: Optional[str] = None,
    payee_name: Optional[str] = None,
    payee_inn: Optional[str] = None,
    delta_amount: Decimal = Decimal(0),
) -> dict:
    """Оценивает смысловую и категорийную связность комбинации позиций/закупок.

    Возвращает:
      {
        "score": int (0..100),
        "probability": "high" | "medium" | "needs_approval" | "low",
        "probability_label": "Очень вероятно" | "Вероятно" | "Требует согласования суммы" | "Маловероятно",
        "coherence_reason": str,
        "needs_amount_approval": bool,
      }
    """
    needs_approval = abs(delta_amount) > AMOUNT_TOL
    if len(units) == 1:
        u = units[0]
        sig = _unit_category_signature(u)
        cat_label = sig["semantic"] or sig["product_category"] or sig["feo_category_name"]
        score = 84
        reasons: list[str] = []
        penalties: list[str] = []
        if not needs_approval:
            if u.is_sub_item:
                reasons.append("точное совпадение позиции (до копейки)")
            else:
                reasons.append("точное совпадение суммы одной закупки")
        else:
            score -= 10
            reasons.append(
                f"расхождение суммы {float(delta_amount):+.2f} ₽ (в закупке {float(u.amount):,.2f} ₽) — требует согласования человека".replace(",", " ")
            )

        if u.is_declared_paid:
            score += 8
            reasons.append("отмечена оплаченной в факте")
        if _unit_payee_priority(u, payee_name, payee_inn) == 0:
            score += 12
            reasons.append(f"совпадает контрагент «{payee_name or u.contractor_name}»")
        if cat_label:
            reasons.append(f"категория «{cat_label}»")

        if purpose_text:
            p_stems = _word_stems(purpose_text)
            if p_stems & sig["stems"]:
                score += 10
                reasons.append("совпадает с назначением платежа")

            p_low = purpose_text.lower()
            is_payment_service = any(
                w in p_low for w in ("услуг", "работ", "перевозк", "медосмотр", "техосмотр", "обслуживан", "страхован", "шиномонтаж", "бортировк", "мойк", "ремонт")
            )
            is_payment_goods = "закупка товаров" in p_low or "поставка товар" in p_low
            if is_payment_service and sig["item_type"] == "товар":
                score -= 40
                penalties.append("товар не соответствует услуге в назначении платежа")
            elif is_payment_goods and sig["item_type"] in ("услуга", "работа"):
                score -= 30
                penalties.append("услуга не соответствует закупке товаров в платеже")

            p_sem = detect_semantic_cluster(purpose_text)
            if p_sem and sig["semantic"]:
                if p_sem == sig["semantic"]:
                    score += 8
                elif not (p_stems & sig["stems"]) and _unit_payee_priority(u, payee_name, payee_inn) != 0:
                    score -= 30
                    penalties.append(f"расхождение тематики («{sig['semantic']}» vs «{p_sem}»)")

        score = max(10, min(99, score))
        if penalties and score < 60:
            prob, plabel = "low", "Маловероятно"
            rtext = "; ".join(penalties + reasons)
        elif needs_approval:
            prob, plabel = "needs_approval", "Требует согласования суммы"
            rtext = " · ".join(reasons + penalties)
        elif score >= 75 and not penalties:
            prob, plabel = "high", "Очень вероятно"
            rtext = " · ".join(reasons)
        else:
            prob, plabel = "medium", "Вероятно"
            rtext = " · ".join(reasons + penalties)
        return {
            "score": score,
            "probability": prob,
            "probability_label": plabel,
            "coherence_reason": rtext,
            "needs_amount_approval": needs_approval,
        }

    sigs = [_unit_category_signature(u) for u in units]
    score = 60
    reasons = []
    penalties = []

    # 1. Смысловые кластеры и каталожные категории
    semantics = [s["semantic"] for s in sigs if s["semantic"]]
    prod_cats = [s["product_category"] for s in sigs if s["product_category"]]
    feo_cats = [s["feo_category_id"] for s in sigs if s["feo_category_id"] is not None]
    feo_parents = [s["feo_parent_id"] for s in sigs if s["feo_parent_id"] is not None]

    distinct_semantics = set(semantics)
    distinct_prod_cats = set(prod_cats)
    same_feo = len(feo_cats) == len(units) and len(set(feo_cats)) == 1

    if len(distinct_semantics) == 1 and (len(semantics) == len(units) or (len(semantics) >= 2 and same_feo)):
        cluster_name = next(iter(distinct_semantics))
        score += 30
        reasons.append(f"одна тематическая группа «{cluster_name}»")
    elif len(distinct_semantics) >= 2 and not same_feo:
        score -= 38
        penalties.append(f"разные тематические категории ({' + '.join(sorted(distinct_semantics))})")

    if len(prod_cats) >= 2 and len(distinct_prod_cats) == 1:
        pcat = next(iter(distinct_prod_cats))
        if pcat.strip().lower() not in ("прочее", "прочие", "разное", "не указано"):
            score += 25
            if not reasons:
                reasons.append(f"одна категория каталога «{pcat}»")
    elif len(distinct_prod_cats) >= 2 and len(distinct_semantics) < 2 and not same_feo:
        score -= 25
        penalties.append(f"разные категории товаров ({' + '.join(sorted(distinct_prod_cats))})")

    if same_feo:
        feo_name = next((s["feo_category_name"] for s in sigs if s["feo_category_name"]), None)
        score += 18
        reasons.append(f"одна категория ФЭО{f' «{feo_name}»' if feo_name else ''}")
    elif len(feo_parents) == len(units) and len(set(feo_parents)) == 1:
        score += 8
        reasons.append("одна ветка ФЭО")
    elif len(set(feo_cats)) >= 2:
        score -= 15
        penalties.append("разные категории ФЭО")

    common_stems = set.intersection(*(s["stems"] for s in sigs)) if all(s["stems"] for s in sigs) else set()
    if common_stems:
        score += 12
        reasons.append("общие ключевые слова в названиях")

    item_types = {s["item_type"] for s in sigs if s["item_type"]}
    if len(item_types) > 1:
        score -= 15
        penalties.append("смешаны товары и услуги")

    c_ids = {u.contractor_id for u in units if u.contractor_id is not None}
    if len(c_ids) == 1 and all(u.contractor_id is not None for u in units):
        score += 10
        reasons.append("один контрагент")
    elif len(c_ids) > 1:
        score -= 25
        penalties.append("указаны разные контрагенты")

    ids_sorted = sorted(u.purchase_id for u in units)
    max_gap = max(ids_sorted[i + 1] - ids_sorted[i] for i in range(len(ids_sorted) - 1))
    if max_gap <= 3:
        score += 8
        reasons.append("соседние строки в таблице/реестре")

    if all(u.is_declared_paid for u in units):
        score += 10
        reasons.append("отмечены оплаченными в факте")

    is_payment_service = False
    has_goods = False
    if purpose_text:
        p_stems = _word_stems(purpose_text)
        all_unit_stems = set().union(*(s["stems"] for s in sigs))
        p_sem = detect_semantic_cluster(purpose_text)
        has_contractor_match = any(_unit_payee_priority(u, payee_name, payee_inn) == 0 for u in units)

        if p_stems & all_unit_stems:
            score += 15
            reasons.append("совпадает с назначением платежа")
        elif p_sem and p_sem in distinct_semantics:
            score += 12
            reasons.append(f"тематика совпадает с назначением («{p_sem}»)")
        elif not has_contractor_match:
            if p_sem and distinct_semantics and p_sem not in distinct_semantics:
                score -= 35
                penalties.append(f"назначение платежа («{p_sem}») не совпадает с позициями")
            elif ":" in purpose_text and not same_feo:
                score -= 25
                penalties.append("предмет в назначении платежа не пересекается с позициями")

        p_low = purpose_text.lower()
        is_payment_service = any(w in p_low for w in ("услуг", "работ", "перевозк", "медосмотр", "техосмотр", "обслуживан", "страхован"))
        has_goods = any(s["item_type"] == "товар" or (s["semantic"] and s["semantic"] in ("Продукты питания и вода", "ИТ, связь и оргтехника", "Канцелярия и хозтовары")) for s in sigs)
        if is_payment_service and has_goods:
            score -= 60
            penalties.append("товары не соответствуют запрашиваемым услугам в платеже")

    if payee_inn or payee_name:
        for u in units:
            if _unit_payee_priority(u, payee_name, payee_inn) == 0:
                score += 30
                reasons.append(f"совпадает контрагент «{payee_name or u.contractor_name}»")
                break

    # Не штрафуем крупные накладные (5..100 позиций), если все позиции из одной категории ФЭО или одной тематической группы
    if not same_feo and len(distinct_semantics) != 1:
        score -= min(15, (len(units) - 2) * 3)
    score = max(5, min(99, score))

    has_service_goods_conflict = bool(purpose_text and is_payment_service and has_goods)
    if has_service_goods_conflict or (penalties and score < 55):
        probability = "low"
        probability_label = "Маловероятно"
        reason_text = "; ".join(penalties + reasons)
    elif needs_approval:
        probability = "needs_approval"
        probability_label = "Требует согласования суммы"
        reason_text = "; ".join(reasons + penalties)
    elif score >= 72 and not penalties:
        probability = "high"
        probability_label = "Очень вероятно"
        reason_text = "; ".join(reasons) if reasons else "совпадает сумма и категория"
    elif score >= 55:
        probability = "medium"
        probability_label = "Вероятно"
        reason_text = "; ".join(reasons + penalties) if (reasons or penalties) else "совпадает по сумме"
    else:
        probability = "low"
        probability_label = "Маловероятно"
        reason_text = "; ".join(penalties + reasons) if (penalties or reasons) else "разнородные позиции"

    return {
        "score": score,
        "probability": probability,
        "probability_label": probability_label,
        "coherence_reason": reason_text,
        "needs_amount_approval": needs_approval,
    }


def find_subset_sum_combinations(
    units: list[CandidateUnit],
    target_amount: Decimal,
    *,
    purpose_text: Optional[str] = None,
    payee_name: Optional[str] = None,
    payee_inn: Optional[str] = None,
    tol: Decimal = AMOUNT_TOL,
    max_combo_size: int = MAX_COMBO_SIZE,
    max_results: int = MAX_COMBO_RESULTS,
    allow_single: bool = True,
    allow_multi: bool = True,
    allow_approval_tol: bool = True,
) -> list[dict]:
    """Находит комбинации из 1..max_combo_size позиций/закупок, дающие в сумме
    ровно target_amount (tol = 0.00 ₽), либо (при allow_approval_tol=True)
    одиночные позиции с расхождением в копейки/рубли (0 < |Δ| <= APPROVAL_TOL),
    которые помечаются needs_amount_approval=True и требуют согласования человека."""
    if target_amount is None or target_amount <= Decimal(0):
        return []

    single_tol = (
        max(tol, APPROVAL_TOL if target_amount >= Decimal("100.00") else tol)
        if allow_approval_tol
        else tol
    )
    valid_units = [
        u for u in units
        if u.amount is not None
        and Decimal(0) < u.amount <= target_amount + single_tol
        and not is_unit_contractor_conflicting(u, payee_name=payee_name, payee_inn=payee_inn)
    ]
    valid_units.sort(
        key=lambda u: (
            _unit_payee_priority(u, payee_name, payee_inn),
            0 if u.is_declared_paid else 1,
            1 if u.is_sub_item else 0,
            u.purchase_id,
            u.purchase_item_id or 0,
        )
    )

    results: list[dict] = []

    # 1. Одиночные совпадения (k = 1)
    if allow_single:
        for u in valid_units:
            delta = u.amount - target_amount
            allowed_tol = tol if u.is_sub_item else single_tol
            if abs(delta) <= allowed_tol:
                eval_res = evaluate_combo_coherence(
                    [u],
                    purpose_text=purpose_text,
                    payee_name=payee_name,
                    payee_inn=payee_inn,
                    delta_amount=delta,
                )
                if abs(delta) > tol and eval_res["probability"] == "low":
                    continue
                results.append({
                    "purchase_ids": [u.purchase_id],
                    "items": [
                        {
                            "purchase_id": u.purchase_id,
                            "purchase_item_id": u.purchase_item_id,
                            "is_sub_item": u.is_sub_item,
                            "registry_number": u.registry_number,
                            "subject": u.subject,
                            "amount": float(u.amount),
                            "contractor_id": u.contractor_id,
                            "contractor_name": u.contractor_name,
                            "feo_category_name": u.feo_category_name,
                            "product_category": u.product_category,
                            "semantic_cluster": detect_semantic_cluster(" ".join([u.subject or ""] + (u.item_names or []))),
                            "sheet_ref": u.sheet_ref,
                        }
                    ],
                    "total_amount": float(u.amount),
                    "delta": float(delta),
                    "count": 1,
                    "score": eval_res["score"],
                    "probability": eval_res["probability"],
                    "probability_label": eval_res["probability_label"],
                    "coherence_reason": eval_res["coherence_reason"],
                    "needs_amount_approval": bool(eval_res.get("needs_amount_approval")),
                    "can_merge": False,
                    "is_sub_item_match": u.is_sub_item,
                })

    # 2. Составные комбинации (k = 2..max_combo_size, вплоть до 100+ позиций):
    # Вместо «слепого» полного перебора всех со всеми (который зависнет на >5 позициях),
    # используем 3 быстрых этапа с точностью до копейки (tol = 0.00 ₽):
    #   а) Скользящее окно (O(N)) по подряд идущим строкам таблицы и внутри категорий ФЭО —
    #      мгновенно (< 0.1 мс) находит накладные из 2..100+ подряд идущих позиций;
    #   б) Метод ветвей и границ (Branch-and-Bound DFS с отсечением по суффиксным суммам в копейках)
    #      внутри каждой категории ФЭО и смыслового кластера — находит комбинации любого размера (2..100 поз.);
    #   в) Глобальный Branch-and-Bound DFS по общему пулу с бюджетом шагов — находит меж-категорийные связки.
    if allow_multi and max_combo_size >= 2:
        whole_units = [u for u in valid_units if not u.is_sub_item and u.amount <= target_amount + tol]
        seen_combo_keys: set[tuple[int, ...]] = set()

        def _register_combo(combo_units: list[CandidateUnit]) -> None:
            if len(combo_units) < 2 or len(combo_units) > max_combo_size:
                return
            key = tuple(sorted(u.purchase_id for u in combo_units))
            if len(key) != len(combo_units) or key in seen_combo_keys:
                return
            # Не смешиваем разных уже назначенных контрагентов в одну закупку
            c_set = {u.contractor_id for u in combo_units if u.contractor_id is not None}
            if len(c_set) > 1:
                return
            seen_combo_keys.add(key)
            total = sum((u.amount for u in combo_units), Decimal(0))
            eval_res = evaluate_combo_coherence(
                combo_units,
                purpose_text=purpose_text,
                payee_name=payee_name,
                payee_inn=payee_inn,
                delta_amount=total - target_amount,
            )
            results.append({
                "purchase_ids": [u.purchase_id for u in combo_units],
                "items": [
                    {
                        "purchase_id": u.purchase_id,
                        "purchase_item_id": None,
                        "is_sub_item": False,
                        "registry_number": u.registry_number,
                        "subject": u.subject,
                        "amount": float(u.amount),
                        "contractor_id": u.contractor_id,
                        "contractor_name": u.contractor_name,
                        "feo_category_name": u.feo_category_name,
                        "product_category": u.product_category,
                        "semantic_cluster": detect_semantic_cluster(" ".join([u.subject or ""] + (u.item_names or []))),
                        "sheet_ref": u.sheet_ref,
                    }
                    for u in combo_units
                ],
                "total_amount": float(total),
                "delta": float(total - target_amount),
                "count": len(combo_units),
                "score": eval_res["score"],
                "probability": eval_res["probability"],
                "probability_label": eval_res["probability_label"],
                "coherence_reason": eval_res["coherence_reason"],
                "needs_amount_approval": bool(eval_res.get("needs_amount_approval")),
                "can_merge": len(c_set) <= 1,
                "is_sub_item_match": False,
            })

        target_cents = int((target_amount * 100).to_integral_value())
        tol_cents = int((tol * 100).to_integral_value())

        def _sliding_window_scan(seq: list[CandidateUnit]) -> None:
            """За O(N) находит любые подряд идущие блоки из 2..100+ позиций с суммой target_amount."""
            n = len(seq)
            if n < 2:
                return
            left = 0
            win_cents = 0
            for right in range(n):
                win_cents += int((seq[right].amount * 100).to_integral_value())
                while win_cents > target_cents + tol_cents and left <= right:
                    win_cents -= int((seq[left].amount * 100).to_integral_value())
                    left += 1
                if right - left + 1 >= 2 and abs(win_cents - target_cents) <= tol_cents:
                    _register_combo(seq[left : right + 1])

        def _branch_and_bound_scan(
            pool_seq: list[CandidateUnit],
            *,
            max_steps: int = 30000,
            max_found: int = 8,
        ) -> None:
            """Поиск комбинаций произвольной длины (2..max_combo_size) методом ветвей и границ
            с отсечением по суффиксной сумме оставшихся элементов."""
            if len(pool_seq) < 2:
                return
            # Сортируем по убыванию суммы для максимальной скорости отсечения ветвей
            indexed = sorted(
                [(int((u.amount * 100).to_integral_value()), u) for u in pool_seq],
                key=lambda x: (-x[0], x[1].purchase_id),
            )
            n = len(indexed)
            amounts_c = [x[0] for x in indexed]
            units_c = [x[1] for x in indexed]

            suffix = [0] * (n + 1)
            for i in range(n - 1, -1, -1):
                suffix[i] = suffix[i + 1] + amounts_c[i]

            steps = 0
            found = 0
            chosen: list[CandidateUnit] = []

            def _dfs(idx: int, curr_cents: int) -> None:
                nonlocal steps, found
                if steps >= max_steps or found >= max_found:
                    return
                steps += 1

                if len(chosen) >= 2 and abs(curr_cents - target_cents) <= tol_cents:
                    _register_combo(list(chosen))
                    found += 1
                    return

                if idx >= n or len(chosen) >= max_combo_size:
                    return

                # Отсечение 1: даже если взять ВСЕ оставшиеся позиции, до target_cents не дотянем
                if curr_cents + suffix[idx] < target_cents - tol_cents:
                    return

                # Отсечение 2: даже самая маленькая оставшаяся позиция перевалит за target_cents
                if curr_cents + amounts_c[-1] > target_cents + tol_cents:
                    return

                prev_skipped_amt = -1
                for i in range(idx, n):
                    if steps >= max_steps or found >= max_found:
                        return
                    amt_i = amounts_c[i]
                    if amt_i == prev_skipped_amt:
                        continue
                    if curr_cents + amt_i > target_cents + tol_cents:
                        continue
                    if curr_cents + suffix[i] < target_cents - tol_cents:
                        break
                    chosen.append(units_c[i])
                    _dfs(i + 1, curr_cents + amt_i)
                    chosen.pop()
                    prev_skipped_amt = amt_i

            _dfs(0, 0)

        # 2а. Скользящее окно по порядку строк/ID в реестре и внутри каждой категории ФЭО
        by_id_order = sorted(whole_units, key=lambda u: u.purchase_id)
        _sliding_window_scan(by_id_order)

        by_feo: dict[Optional[int], list[CandidateUnit]] = {}
        by_sem: dict[str, list[CandidateUnit]] = {}
        for u in by_id_order:
            by_feo.setdefault(u.feo_category_id, []).append(u)
            sem = detect_semantic_cluster(" ".join([u.subject or ""] + (u.item_names or [])))
            if sem:
                by_sem.setdefault(sem, []).append(u)

        for feo_group in by_feo.values():
            if len(feo_group) >= 2:
                _sliding_window_scan(feo_group)
                _branch_and_bound_scan(feo_group, max_steps=25000, max_found=6)

        for sem_group in by_sem.values():
            if len(sem_group) >= 2:
                _sliding_window_scan(sem_group)
                _branch_and_bound_scan(sem_group, max_steps=20000, max_found=5)

        # 2б. Глобальный поиск методом ветвей и границ (на случай позиций из разных категорий)
        global_pool = whole_units[:MAX_POOL_SIZE]
        _branch_and_bound_scan(global_pool, max_steps=35000, max_found=8)

    # Сортируем: сначала high → medium → needs_approval → low, внутри по убыванию score, затем меньшее кол-во позиций
    prob_rank = {"high": 4, "medium": 3, "needs_approval": 2, "low": 1}
    results.sort(
        key=lambda r: (prob_rank.get(r["probability"], 0), r["score"], -r["count"]),
        reverse=True,
    )
    return results[:max_results]


def find_sign_error_candidates(
    units: list[CandidateUnit],
    discrepancy_amount: Decimal,
    *,
    tol: Decimal = AMOUNT_TOL,
) -> list[dict]:
    """Проверяет классическую бухгалтерскую ловушку «ошибка знака»: если сумму
    X записали с противоположным знаком или учли не в ту сторону, расхождение
    составит ровно 2×X (например, строка на 14 000 ₽ даёт расхождение 28 000 ₽)."""
    if discrepancy_amount is None or abs(discrepancy_amount) <= Decimal(0):
        return []
    half = (abs(discrepancy_amount) / Decimal(2)).quantize(Decimal("0.01"))
    out: list[dict] = []
    for u in units:
        if u.amount is not None and abs(u.amount - half) <= tol:
            out.append({
                "purchase_id": u.purchase_id,
                "registry_number": u.registry_number,
                "subject": u.subject,
                "amount": float(u.amount),
                "discrepancy_explained": float(u.amount * Decimal(2)),
                "contractor_name": u.contractor_name,
                "feo_category_name": u.feo_category_name,
                "sheet_ref": u.sheet_ref,
                "reason": (
                    f"Ошибка знака (÷2): позиция на {float(u.amount):,.2f} ₽ при инверсии знака "
                    f"даёт расхождение ровно {float(u.amount * 2):,.2f} ₽"
                ).replace(",", " "),
            })
    return out[:10]


async def split_uncontracted_multi_item_purchases(
    db: AsyncSession,
    subsidy_id: int,
) -> int:
    """Правило владельца (04.11.2026): если у закупки не указан контрагент,
    а внутри неё сгруппировано несколько позиций (например, из старого импорта
    по № закупки), каждая позиция обязана стать отдельной самостоятельной
    закупкой с виртуальным номером РЕЕ-..., чтобы у одной закупки никогда не
    оказалось нескольких разных контрагентов-получателей, а единичные позиции
    свободно сопоставлялись на Шаге 2 (1-к-1) и Шаге 3 (комбинаторика 2–4 поз.).

    Возвращает количество выделенных новых единичных закупок.
    """
    from app.services.historical_fact_import.existing_update import materialize_contract
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.services.purchase_payments import recompute_purchase_payments

    # Закупки, у которых уже есть подтверждённый выпиской платёж — не трогаем
    confirmed_pids_rows = (await db.execute(
        select(Payment.purchase_id)
        .join(Purchase, Purchase.id == Payment.purchase_id)
        .where(
            Purchase.subsidy_id == subsidy_id,
            Payment.confirmed_by_statement.is_(True),
        )
    )).all()
    confirmed_pids = {r[0] for r in confirmed_pids_rows if r[0]}

    purchases = (await db.execute(
        select(Purchase).where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.contractor_id.is_(None),
            Purchase.parent_purchase_id.is_(None),
            Purchase.stopped_at.is_(None),
            Purchase.status != "cancelled",
        ).order_by(Purchase.id)
    )).scalars().all()

    if not purchases:
        return 0

    pids = [p.id for p in purchases if p.id not in confirmed_pids]
    if not pids:
        return 0

    pitems = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_(pids)).order_by(PurchaseItem.id)
    )).scalars().all()
    items_by_pid: dict[int, list[PurchaseItem]] = {}
    for pi in pitems:
        items_by_pid.setdefault(pi.purchase_id, []).append(pi)

    multi_purchases = [
        p for p in purchases
        if p.id in items_by_pid and len(items_by_pid[p.id]) > 1
    ]
    if not multi_purchases:
        return 0

    max_pnum_res = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
    next_pnum = int(max_pnum_res.scalar() or 0) + 1
    year = _date.today().year
    created_count = 0

    for p in multi_purchases:
        pis = items_by_pid[p.id]
        if len(pis) <= 1:
            continue

        # Проверяем, были ли на исходной закупке неподтверждённые платежи «по отметке»
        manual_payments = (await db.execute(
            select(Payment).where(
                Payment.purchase_id == p.id,
                Payment.confirmed_by_statement.is_(False),
            ).order_by(Payment.id)
        )).scalars().all()
        had_manual_paid = bool(manual_payments) or p.status == "paid"

        first_pi = pis[0]
        other_pis = pis[1:]
        first_amt = Decimal(str(first_pi.total_price or 0))

        # Создаём отдельную закупку с виртуальным номером РЕЕ-... для каждой позиции начиная со 2-й
        for pi in other_pis:
            pi_amt = Decimal(str(pi.total_price or 0))
            pi_subj = (pi.item_name or p.subject or p.item_name or f"Позиция #{pi.id}").strip()[:500]
            new_p = Purchase(
                purchase_number=next_pnum,
                subsidy_id=p.subsidy_id,
                status=p.status,
                contractor_id=pi.contractor_id,
                purchase_method=p.purchase_method or "single",
                purchase_contract_type=p.purchase_contract_type or "single",
                feo_category_id=pi.feo_category_id or p.feo_category_id,
                feo_per_item=False,
                subject=pi_subj,
                item_name=pi_subj,
                item_type=pi.item_type or p.item_type,
                assigned_user_id=p.assigned_user_id,
                import_run_id=p.import_run_id,
                is_prepayment=p.is_prepayment,
                task_comment=p.task_comment,
                planned_total_price=pi_amt,
                total_nmck=pi_amt,
                nmck=pi_amt,
                contract_price=pi_amt if p.contract_price is not None else None,
            )
            next_pnum += 1
            db.add(new_p)
            await db.flush()
            new_p.registry_number = f"РЕЕ-{year}-{new_p.id:05d}"

            # Переносим позицию PurchaseItem и её ContractItem в новую закупку
            pi.purchase_id = new_p.id
            await db.execute(
                delete(ContractItem).where(
                    ContractItem.purchase_id == p.id,
                    ContractItem.source_item_id == pi.id,
                )
            )
            db.add(PurchaseSubsidyAllocation(
                purchase_id=new_p.id,
                subsidy_id=p.subsidy_id,
                amount=pi_amt,
            ))
            await db.flush()

            if new_p.status in ("contracted", "ordered", "delivered", "paid"):
                await materialize_contract(db, new_p, force_temp_number=True)
                if new_p.contract_id:
                    c_new = await db.get(Contract, new_p.contract_id)
                    if c_new:
                        c_new.max_amount = pi_amt
                        c_new.subject = pi_subj

            if had_manual_paid and pi_amt > 0:
                db.add(Payment(
                    purchase_id=new_p.id,
                    amount=pi_amt,
                    payment_source="manual",
                    confirmed_by_statement=False,
                    import_run_id=p.import_run_id,
                ))
                await db.flush()
                await recompute_purchase_payments(db, new_p.id)

            created_count += 1

        # Обновляем исходную закупку p (в ней осталась ровно 1-я позиция first_pi)
        first_subj = (first_pi.item_name or p.subject or p.item_name or f"Закупка #{p.id}").strip()[:500]
        p.subject = first_subj
        p.item_name = first_subj
        p.item_type = first_pi.item_type or p.item_type
        p.feo_category_id = first_pi.feo_category_id or p.feo_category_id
        p.feo_per_item = False
        if not p.registry_number or not str(p.registry_number).startswith("РЕЕ-"):
            p.registry_number = f"РЕЕ-{year}-{p.id:05d}"
        p.planned_total_price = first_amt
        p.total_nmck = first_amt
        p.nmck = first_amt
        if p.contract_price is not None:
            p.contract_price = first_amt

        await db.execute(
            delete(PurchaseSubsidyAllocation).where(PurchaseSubsidyAllocation.purchase_id == p.id)
        )
        db.add(PurchaseSubsidyAllocation(
            purchase_id=p.id,
            subsidy_id=p.subsidy_id,
            amount=first_amt,
        ))

        if p.contract_id:
            c_orig = await db.get(Contract, p.contract_id)
            if c_orig:
                c_orig.max_amount = first_amt
                c_orig.subject = first_subj

        if manual_payments:
            main_mp = manual_payments[0]
            main_mp.amount = first_amt
            for extra_mp in manual_payments[1:]:
                await db.delete(extra_mp)
            await db.flush()
            await recompute_purchase_payments(db, p.id)

        await recalc_purchase_money(db, p)
        if p.contract_price is not None:
            p.contract_price = first_amt
        await db.flush()

    return created_count


async def enrich_purchase_from_bank_payment(
    db: AsyncSession,
    p: Purchase,
    bp: BankPayment,
    amount: Decimal,
    contractor_obj: Optional[Contractor] = None,
) -> None:
    """Проставляет в закупку (единичную или объединённую) контрагента, номер/дату
    договора и закрывающие документы (УПД / Акт / Счёт / Накладная / Реестр)
    из банковской платёжки."""
    from app.services.item_contractor import set_item_contractor
    from app.services.payment_basis import extract_basis, _parse_doc_date
    from app.services.acceptance_docs import add_doc
    from app.services.contract_items_materialize import copy_items_to_contract
    from app.services.contracts_linking import ensure_contract_linked

    # 1. Контрагент на закупке и её позициях
    if contractor_obj:
        if not p.contractor_id:
            p.contractor_id = contractor_obj.id
        p_items = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == p.id).order_by(PurchaseItem.id)
        )).scalars().all()
        for pi in p_items:
            if not pi.contractor_id:
                set_item_contractor(pi, contractor=contractor_obj, name=contractor_obj.name)

    # 2. Номер и дата договора из платёжки (если в закупке нет реального номера договора)
    docs = getattr(bp, "parsed_documents", None) or {}
    real_cnum = getattr(bp, "parsed_contract_number", None)
    real_cdate = getattr(bp, "parsed_contract_date", None)
    if not real_cnum and docs.get("contracts"):
        first_c = (docs.get("contracts") or [{}])[0] or {}
        real_cnum = first_c.get("number")
        real_cdate = _parse_doc_date(first_c.get("date"))

    cur_cnum = str(p.contract_number or "").strip()
    is_temp_cnum = (
        not cur_cnum
        or bool(p.contract_number_is_temporary)
        or cur_cnum.startswith("ВРЕМ-")
        or bool(re.match(r"^\d{4}/\d+$", cur_cnum))
    )
    if real_cnum and is_temp_cnum:
        p.contract_number = str(real_cnum).strip()
        if real_cdate:
            p.contract_date = real_cdate
        p.contract_number_is_temporary = False

    # 3. Закрывающие документы (УПД / Акт / Накладная / Счёт / Реестр / Авансовый отчёт)
    closing_doc_types = [
        ("upd", "upd", "УПД"),
        ("acts", "act", "Акт"),
        ("waybills", "waybill", "Товарная накладная"),
        ("invoices", "invoice", "Счёт"),
        ("registry", "registry", "Реестр док.-осн."),
        ("advance_reports", "advance_report", "Авансовый отчёт"),
    ]
    added_any_doc = False
    latest_doc_date: Optional[_date] = None
    for doc_key, kind, label_prefix in closing_doc_types:
        for d_item in (docs.get(doc_key) or []):
            if not isinstance(d_item, dict):
                continue
            num = str(d_item.get("number") or "").strip()
            if not num:
                continue
            ddate = _parse_doc_date(d_item.get("date"))
            if ddate and (latest_doc_date is None or ddate > latest_doc_date):
                latest_doc_date = ddate
            add_doc(p, {
                "name": label_prefix,
                "type": kind,
                "number": num,
                "date": ddate.isoformat() if ddate else (bp.payment_date.isoformat() if bp.payment_date else None),
                "amount": float(amount),
                "source": "bank_statement",
            })
            added_any_doc = True

    if not added_any_doc:
        basis = extract_basis(bp)
        if basis.kind and basis.kind != "contract" and basis.number:
            if basis.date:
                latest_doc_date = basis.date
            add_doc(p, {
                "name": (basis.label or basis.kind).split()[0],
                "type": basis.kind,
                "number": basis.number,
                "date": basis.date.isoformat() if basis.date else (bp.payment_date.isoformat() if bp.payment_date else None),
                "amount": float(amount),
                "source": "bank_statement",
            })

    if p.delivery_date is None and (latest_doc_date or bp.payment_date):
        p.delivery_date = latest_doc_date or bp.payment_date

    # 4. Синхронизируем договорные позиции и запись в реестре договоров (Contract)
    await copy_items_to_contract(db, p.id)
    await ensure_contract_linked(p, db)
    if p.contract_id:
        c_rec = await db.get(Contract, p.contract_id)
        if c_rec:
            if p.contractor_id and c_rec.contractor_id != p.contractor_id:
                c_rec.contractor_id = p.contractor_id
            if p.contract_number and c_rec.number != p.contract_number:
                c_rec.number = p.contract_number
            if p.contract_date and c_rec.date != p.contract_date:
                c_rec.date = p.contract_date
            if p.subject and not c_rec.subject:
                c_rec.subject = p.subject


async def load_unpaid_candidate_units(
    db: AsyncSession,
    subsidy_id: int,
    *,
    preferred_contractor_inn: Optional[str] = None,
) -> list[CandidateUnit]:
    """Загружает из БД закупки субсидии, ещё не закрытые подтверждёнными
    платежами выписки, и обогащает их категориями ФЭО и каталога товаров."""
    # Закупки субсидии, у которых уже есть подтверждённый выпиской платёж
    paid_rows = (await db.execute(
        select(Payment.purchase_id, Payment.amount)
        .join(Purchase, Purchase.id == Payment.purchase_id)
        .where(
            Purchase.subsidy_id == subsidy_id,
            Payment.confirmed_by_statement.is_(True),
        )
    )).all()
    paid_by_purchase: dict[int, Decimal] = {}
    for pid, pamt in paid_rows:
        if pid:
            paid_by_purchase[pid] = paid_by_purchase.get(pid, Decimal(0)) + Decimal(str(pamt or 0))

    purchases = (await db.execute(
        select(Purchase).where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.stopped_at.is_(None),
            Purchase.status != "cancelled",
        ).order_by(Purchase.id)
    )).scalars().all()

    if not purchases:
        return []

    pids = [p.id for p in purchases]
    cids = {p.contractor_id for p in purchases if p.contractor_id}
    contractors_map: dict[int, Contractor] = {}
    if cids:
        crows = (await db.execute(select(Contractor).where(Contractor.id.in_(cids)))).scalars().all()
        contractors_map = {c.id: c for c in crows}

    frows = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    feo_map = {f.id: f for f in frows}

    pitems = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_(pids)).order_by(PurchaseItem.id)
    )).scalars().all()
    items_by_pid: dict[int, list[PurchaseItem]] = {}
    prod_ids: set[int] = set()
    for pi in pitems:
        items_by_pid.setdefault(pi.purchase_id, []).append(pi)
        if pi.product_id:
            prod_ids.add(pi.product_id)

    prod_map: dict[int, Product] = {}
    if prod_ids:
        prows = (await db.execute(select(Product).where(Product.id.in_(prod_ids)))).scalars().all()
        prod_map = {pr.id: pr for pr in prows}

    units: list[CandidateUnit] = []
    for p in purchases:
        pis = items_by_pid.get(p.id, [])
        pis_sum = sum((Decimal(str(pi.total_price)) for pi in pis if pi.total_price is not None), Decimal(0))

        raw_amt = p.contract_price if p.contract_price is not None else (
            p.planned_total_price if p.planned_total_price is not None else (
                p.total_nmck if p.total_nmck is not None else (pis_sum if pis_sum > 0 else None)
            )
        )
        if raw_amt is None:
            continue
        full_amt = Decimal(str(raw_amt))
        already_paid = paid_by_purchase.get(p.id, Decimal(0))
        rem_amt = full_amt - already_paid
        if rem_amt <= AMOUNT_TOL:
            continue

        c_obj = contractors_map.get(p.contractor_id) if p.contractor_id else None
        # Если у платёжки известен ИНН, в пул берём либо закупки этого ИНН,
        # либо закупки БЕЗ контрагента («забыли проставить у кого и как»).
        if preferred_contractor_inn and c_obj and c_obj.inn and c_obj.inn != preferred_contractor_inn:
            continue

        feo_id = p.feo_category_id or next((pi.feo_category_id for pi in pis if pi.feo_category_id), None)
        feo_obj = feo_map.get(feo_id) if feo_id else None

        prod_cat = None
        for pi in pis:
            if pi.product_id and pi.product_id in prod_map and prod_map[pi.product_id].category:
                prod_cat = prod_map[pi.product_id].category
                break

        item_type = p.item_type or next((pi.item_type for pi in pis if pi.item_type), None)
        item_names = [pi.item_name for pi in pis if pi.item_name]
        subject = (p.subject or p.item_name or (", ".join(item_names[:2]) if item_names else f"Закупка #{p.id}")).strip()
        is_declared_paid = bool(
            p.status == "paid"
            or (p.payment_amount is not None and Decimal(str(p.payment_amount)) > Decimal(0))
        )

        units.append(CandidateUnit(
            purchase_id=p.id,
            registry_number=p.registry_number,
            subject=subject,
            amount=rem_amt,
            contractor_id=p.contractor_id,
            contractor_name=c_obj.name if c_obj else None,
            contractor_inn=c_obj.inn if c_obj else None,
            feo_category_id=feo_id,
            feo_category_name=feo_obj.name if feo_obj else None,
            feo_parent_id=feo_obj.parent_id if feo_obj else None,
            product_category=prod_cat,
            item_type=item_type,
            item_names=item_names,
            sheet_ref=resolve_sheet_ref(p),
            is_declared_paid=is_declared_paid,
            is_sub_item=False,
            purchase_item_id=None,
        ))

    return units


async def merge_and_attach_combo(
    db: AsyncSession,
    subsidy_id: int,
    bp: BankPayment,
    purchase_ids: list[int],
    *,
    merge_purchases: bool = True,
    approve_amount_diff: bool = False,
) -> dict:
    """Объединяет выбранную комбинацию разрозненных единичных закупок
    в одну общую закупку (удаляя вторичные единичные закупки), проставляет
    контрагента, номер/дату договора и закрывающие документы из BankPayment,
    и привязывает платёж через единый payment_lookup.attach (ПРАВИЛО №6).

    Если между суммой закупки и суммой выписки есть расхождение (даже в 1 копейку),
    изменение суммы закупки допускается ТОЛЬКО при approve_amount_diff=True
    (явном согласовании человека)."""
    from fastapi import HTTPException
    from app.services.contractor_resolve import find_or_create_contractor
    from app.services.item_contractor import set_item_contractor
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.routers.purchases import delete_purchase_core
    from app.services.payment_target import PaymentGroup
    from app.services.payment_lookup import attach, PaymentAttachError, ServicePeriodAttachConflict
    from app.services.payment_service_period import service_period_conflict_detail

    if not purchase_ids:
        raise HTTPException(400, "Не выбрано ни одной закупки")

    # Убираем дубликаты ID с сохранением порядка
    unique_pids = list(dict.fromkeys(purchase_ids))
    purchases: list[Purchase] = []
    for pid in unique_pids:
        p = await db.get(Purchase, pid)
        if not p or p.subsidy_id != subsidy_id:
            raise HTTPException(404, f"Закупка #{pid} не найдена в этой субсидии")
        purchases.append(p)

    # Правило владельца: у одной закупки не может быть нескольких разных контрагентов
    existing_cids = {p.contractor_id for p in purchases if p.contractor_id is not None}
    if len(existing_cids) > 1:
        raise HTTPException(
            422,
            "Нельзя объединить закупки разных контрагентов в одну закупку (один платёж всегда относится к одному контрагенту).",
        )

    # Резолвим или создаём контрагента из банковской выписки, если он там указан
    contractor_obj: Optional[Contractor] = None
    if bp.matched_contractor_id:
        contractor_obj = await db.get(Contractor, bp.matched_contractor_id)
    if not contractor_obj and (bp.payee_inn or bp.payee_name):
        cid = await find_or_create_contractor(db, bp.payee_name, bp.payee_inn)
        if cid:
            contractor_obj = await db.get(Contractor, cid)
            bp.matched_contractor_id = cid

    warnings: list[str] = []
    bp_amt = Decimal(str(bp.amount or 0))

    if merge_purchases and len(purchases) > 1:
        main_p = purchases[0]
        other_ps = purchases[1:]
        other_pids = [op.id for op in other_ps]

        # Удаляем неподтверждённые ручные платежи («по отметке») у вторичных закупок,
        # а у основной оставляем не более одного, чтобы attach() чисто заменил его
        # подтверждённым платежом выписки на полную сумму.
        await db.execute(
            delete(Payment).where(
                Payment.purchase_id.in_(other_pids),
                Payment.confirmed_by_statement.is_(False),
            )
        )
        main_unconfirmed = (await db.execute(
            select(Payment).where(
                Payment.purchase_id == main_p.id,
                Payment.confirmed_by_statement.is_(False),
            ).order_by(Payment.id)
        )).scalars().all()
        if len(main_unconfirmed) > 1:
            for extra_mp in main_unconfirmed[1:]:
                await db.delete(extra_mp)

        # Переносим все PurchaseItem из вторичных закупок в основную
        other_items = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id.in_(other_pids)).order_by(PurchaseItem.id)
        )).scalars().all()
        for pi in other_items:
            pi.purchase_id = main_p.id
            if contractor_obj and not pi.contractor_id:
                set_item_contractor(pi, contractor=contractor_obj, name=contractor_obj.name)

        # Удаляем старые ContractItem вторичных закупок (copy_items_to_contract пересоздаст их в main_p)
        await db.execute(
            delete(ContractItem).where(ContractItem.purchase_id.in_(other_pids))
        )

        # Обновляем контрагента также у существующих позиций основной закупки
        main_items = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == main_p.id).order_by(PurchaseItem.id)
        )).scalars().all()
        for pi in main_items:
            if contractor_obj and not pi.contractor_id:
                set_item_contractor(pi, contractor=contractor_obj, name=contractor_obj.name)

        if contractor_obj and not main_p.contractor_id:
            main_p.contractor_id = contractor_obj.id

        # Если категории ФЭО отличаются — включаем feo_per_item на основной закупке
        all_cats = {pi.feo_category_id for pi in (main_items + other_items) if pi.feo_category_id}
        if len(all_cats) > 1:
            main_p.feo_per_item = True

        # Собираем объединённый предмет закупки из наименований всех позиций
        subjects = [
            (pi.item_name or "").strip()
            for pi in (main_items + other_items)
            if (pi.item_name or "").strip()
        ] or [
            (p.subject or p.item_name or "").strip()
            for p in purchases
            if (p.subject or p.item_name or "").strip()
        ]
        if subjects:
            combined_subj = ", ".join(dict.fromkeys(subjects))
            if len(combined_subj) > 490:
                combined_subj = combined_subj[:490] + "..."
            main_p.subject = combined_subj
            main_p.item_name = combined_subj

        merged_contract_price = sum(
            (Decimal(str(p.contract_price or p.planned_total_price or p.total_nmck or 0)) for p in purchases),
            Decimal(0),
        )
        await db.flush()

        # Удаляем опустевшие вторичные единичные закупки
        for op in other_ps:
            await delete_purchase_core(op, db)
        await db.flush()

        await recalc_purchase_money(db, main_p)
        main_p.planned_total_price = merged_contract_price
        main_p.total_nmck = merged_contract_price
        main_p.nmck = merged_contract_price
        main_p.contract_price = merged_contract_price
        await db.execute(
            delete(PurchaseSubsidyAllocation).where(PurchaseSubsidyAllocation.purchase_id == main_p.id)
        )
        db.add(PurchaseSubsidyAllocation(
            purchase_id=main_p.id,
            subsidy_id=subsidy_id,
            amount=merged_contract_price,
        ))
        await db.flush()

        # Фиксируем объединение в истории изменений закупки (EntityChange)
        try:
            from app.models.entity_change import EntityChange
            db.add(EntityChange(
                entity_type="purchase",
                entity_id=main_p.id,
                field_name="subject",
                old_value=purchases[0].subject,
                new_value=main_p.subject,
                changed_by_id=None,
                changed_by_name="Авто-сверка выписки (Subset Sum)",
                source="autoassign",
                source_ref=bp.id,
            ))
        except Exception as _ec_err:
            import logging
            logging.getLogger(__name__).warning("Не удалось записать EntityChange при слиянии: %s", _ec_err)

        target_purchases = [main_p]
        allocations = {main_p.id: bp_amt}
    else:
        if len(purchases) == 1:
            p0 = purchases[0]
            p0_amt = Decimal(str(p0.contract_price or p0.planned_total_price or p0.total_nmck or 0))
            diff = abs(bp_amt - p0_amt)
            if diff > AMOUNT_TOL:
                if not approve_amount_diff:
                    raise HTTPException(
                        422,
                        f"Сумма закупки ({p0_amt:,.2f} ₽) отличается от суммы выписки ({bp_amt:,.2f} ₽) на {bp_amt - p0_amt:+.2f} ₽. "
                        "Для привязки необходимо подтвердить согласование изменения суммы.".replace(",", " "),
                    )
                if diff <= APPROVAL_TOL:
                    from app.services.payment_control_fix_amount import fix_purchase_amount
                    await fix_purchase_amount(db, p0, bp_amt)
        for p in purchases:
            if contractor_obj and not p.contractor_id:
                p.contractor_id = contractor_obj.id
        await db.flush()
        target_purchases = purchases
        allocations = {}
        allocated = Decimal(0)
        for idx, p in enumerate(target_purchases):
            p_amt = Decimal(str(p.contract_price or p.planned_total_price or p.total_nmck or 0))
            share = p_amt if idx < len(target_purchases) - 1 else (bp_amt - allocated)
            allocations[p.id] = share
            allocated += share

    first_p = target_purchases[0]
    group = PaymentGroup(
        group_key=f"payment-control-combo-{first_p.id}",
        subsidy_id=subsidy_id,
        registry_number=first_p.registry_number,
        contract_number=first_p.contract_number,
        is_framework=False,
        contractor_id=first_p.contractor_id,
        contractor_inn=bp.payee_inn,
        contractor_name=bp.payee_name,
        goods_amount=Decimal(0),
        services_amount=Decimal(0),
        unspecified_amount=Decimal(0),
        purchase_ids=[p.id for p in target_purchases],
        payments=[],
    )
    try:
        await attach(
            db, group, [bp.id],
            allocations=allocations,
            warnings_out=warnings,
        )
    except ServicePeriodAttachConflict as exc:
        if bp.payment_date:
            fallback_month = bp.payment_date.replace(day=1)
            try:
                await attach(
                    db, group, [bp.id],
                    allocations=allocations,
                    service_periods={p.id: fallback_month for p in target_purchases if p.is_monthly_payment},
                    warnings_out=warnings,
                )
            except Exception:
                raise HTTPException(409, service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period))
        else:
            raise HTTPException(409, service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period))
    except PaymentAttachError as exc:
        raise HTTPException(409, str(exc))

    # Обогащаем целевую закупку контрагентом, договором и закрывающими документами из выписки
    for p in target_purchases:
        alloc_amt = allocations.get(p.id, bp_amt)
        await enrich_purchase_from_bank_payment(db, p, bp, alloc_amt, contractor_obj=contractor_obj)
        p.status = "paid"
    await db.flush()

    return {
        "ok": True,
        "merged": merge_purchases and len(unique_pids) > 1,
        "primary_purchase_id": first_p.id,
        "registry_number": first_p.registry_number,
        "merged_count": len(unique_pids),
        "warnings": warnings,
    }

