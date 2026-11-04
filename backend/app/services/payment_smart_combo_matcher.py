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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.purchase_sheet_ref import resolve_sheet_ref

AMOUNT_TOL = Decimal("0.02")
MAX_COMBO_SIZE = 4
MAX_POOL_SIZE = 60
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
        "тушенк", "тушёнк", "консерв", "чай", "кофе", "сахар", "молок", "мяс",
        "рыб", "овощ", "фрукт", "кондитер", "печень",
    )),
    ("Автотранспорт, ГСМ и запчасти", (
        "автомоб", "машин", "шин", "колес", "колёс", "масл", "аккумулят",
        "запчаст", "топлив", "бензин", "дизел", "гсм", "антифриз", "тормоз",
        "фильтр", "свеч", "ремонт тс", "техобслуж", "шиномонтаж", "лебедк",
    )),
    ("ИТ, связь и оргтехника", (
        "ноутбук", "компьютер", "моноблок", "монитор", "принтер", "мфу",
        "картридж", "тонер", "мышь", "клавиатур", "кабел", "роутер", "маршрутиз",
        "коммутат", "сервер", "диск", "флешк", "радиостанц", "рация", "рации",
        "антенн", "связ", "интернет",
    )),
    ("Канцелярия и хозтовары", (
        "бумаг", "ручк", "карандаш", "папк", "скоросшив", "степлер", "скрепк",
        "блокнот", "тетрад", "маркер", "клей", "ножниц", "скотч", "конверт",
        "мыло", "салфетк", "мешк", "пакет", "перчатк", "ведро", "швабр",
    )),
    ("Мебель и оборудование лагеря", (
        "стол", "стул", "кресл", "шкаф", "тумб", "кроват", "матрас", "стеллаж",
        "палатк", "тент", "шатер", "шатёр", "спальник", "спальн", "коврик",
        "генератор", "обогреват", "тепловентилят", "пушк",
    )),
    ("Полиграфия, форма и сувенирная продукция", (
        "баннер", "флаг", "вымпел", "футболк", "кепк", "бейсболк", "куртк",
        "жилет", "костюм", "обувь", "берц", "ботинк", "значк", "медал",
        "грамот", "диплом", "буклет", "листовк", "печат", "брендир", "шеврон",
        "нашивк", "табличк", "стенд",
    )),
    ("Проживание и транспортные услуги", (
        "проживан", "гостиниц", "отел", "хостел", "перевозк", "автобус",
        "трансфер", "билет", "авиабилет", "жд билет", "аренд",
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
    u_text = f"{u.contractor_name or ''} {u.subject or ''}".lower().replace("«", '"').replace("»", '"')

    # Ищем кавычки организаций в названии/предмете закупки: например "ПРЕДРЕЙСОВЫЙ"
    quotes = re.findall(r'"([^"]{4,})"', u_text)
    for q in quotes:
        q_clean = q.strip().lower()
        if q_clean not in ("прочее", "товар", "услуга", "товары", "услуги", "договор", "заказ"):
            if p_name_low and q_clean not in p_name_low:
                return True

    # Если у закупки явно задан контрагент, а у платежа другое имя
    if u.contractor_name and p_name_low:
        u_cname = u.contractor_name.lower().replace("«", '"').replace("»", '"')
        if u_cname and u_cname not in p_name_low and p_name_low not in u_cname:
            u_stems = _word_stems(u_cname)
            p_stems = _word_stems(p_name_low)
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

    combined = f"{u.contractor_name or ''} {u.subject or ''}".lower().replace("«", '"').replace("»", '"')
    if p_name:
        quotes = re.findall(r'"([^"]{4,})"', combined)
        for q in quotes:
            q_clean = q.strip().lower()
            if q_clean not in ("прочее", "товар", "услуга", "товары", "услуги") and q_clean in p_name:
                return 0

    if u.contractor_id is None and not u.contractor_inn:
        return 1

    return 2


def evaluate_combo_coherence(
    units: list[CandidateUnit],
    purpose_text: Optional[str] = None,
    payee_name: Optional[str] = None,
    payee_inn: Optional[str] = None,
) -> dict:
    """Оценивает смысловую и категорийную связность комбинации позиций/закупок.

    Возвращает:
      {
        "score": int (0..100),
        "probability": "high" | "medium" | "low",
        "probability_label": "Очень вероятно" | "Вероятно" | "Маловероятно",
        "coherence_reason": str,
      }
    """
    if len(units) == 1:
        u = units[0]
        sig = _unit_category_signature(u)
        cat_label = sig["semantic"] or sig["product_category"] or sig["feo_category_name"]
        score = 85
        reasons = ["точное совпадение суммы одной позиции"]
        if cat_label:
            reasons.append(f"категория «{cat_label}»")
        if purpose_text:
            p_stems = _word_stems(purpose_text)
            if p_stems & sig["stems"]:
                score += 10
                reasons.append("совпадает с назначением платежа")
        return {
            "score": min(100, score),
            "probability": "high",
            "probability_label": "Очень вероятно",
            "coherence_reason": " · ".join(reasons),
        }

    sigs = [_unit_category_signature(u) for u in units]
    score = 60
    reasons: list[str] = []
    penalties: list[str] = []

    # 1. Смысловые кластеры и каталожные категории
    semantics = [s["semantic"] for s in sigs if s["semantic"]]
    prod_cats = [s["product_category"] for s in sigs if s["product_category"]]
    feo_cats = [s["feo_category_id"] for s in sigs if s["feo_category_id"] is not None]
    feo_parents = [s["feo_parent_id"] for s in sigs if s["feo_parent_id"] is not None]

    distinct_semantics = set(semantics)
    distinct_prod_cats = set(prod_cats)

    # Если у всех (или ≥2) определился ОДИН И ТОТ ЖЕ смысловой кластер:
    if len(semantics) >= 2 and len(distinct_semantics) == 1:
        cluster_name = next(iter(distinct_semantics))
        score += 30
        reasons.append(f"одна тематическая группа «{cluster_name}»")
    elif len(distinct_semantics) >= 2:
        # Явный конфликт смысловых категорий (например, Пожарное + Продукты питания)
        score -= 38
        penalties.append(f"разные тематические категории ({' + '.join(sorted(distinct_semantics))})")

    # Каталожные категории товаров
    if len(prod_cats) >= 2 and len(distinct_prod_cats) == 1:
        pcat = next(iter(distinct_prod_cats))
        # Не давать бонус за фиктивную категорию "Прочее"
        if pcat.strip().lower() not in ("прочее", "прочие", "разное", "не указано"):
            score += 25
            if not reasons:
                reasons.append(f"одна категория каталога «{pcat}»")
    elif len(distinct_prod_cats) >= 2 and len(distinct_semantics) < 2:
        score -= 25
        penalties.append(f"разные категории товаров ({' + '.join(sorted(distinct_prod_cats))})")

    # Категории ФЭО
    if len(feo_cats) == len(units) and len(set(feo_cats)) == 1:
        feo_name = next((s["feo_category_name"] for s in sigs if s["feo_category_name"]), None)
        score += 15
        reasons.append(f"одна категория ФЭО{f' «{feo_name}»' if feo_name else ''}")
    elif len(feo_parents) == len(units) and len(set(feo_parents)) == 1:
        score += 8
        reasons.append("одна ветка ФЭО")
    elif len(set(feo_cats)) >= 2:
        score -= 12
        penalties.append("разные категории ФЭО")

    # 2. Общие корни слов в названиях
    common_stems = set.intersection(*(s["stems"] for s in sigs)) if all(s["stems"] for s in sigs) else set()
    if common_stems:
        score += 12
        reasons.append("общие ключевые слова в названиях")

    # 3. Тип позиций (товар vs услуга)
    item_types = {s["item_type"] for s in sigs if s["item_type"]}
    if len(item_types) > 1:
        score -= 15
        penalties.append("смешаны товары и услуги")

    # 4. Контрагент: все без контрагента или у всех один и тот же контрагент
    c_ids = {u.contractor_id for u in units if u.contractor_id is not None}
    if len(c_ids) == 1 and all(u.contractor_id is not None for u in units):
        score += 10
        reasons.append("один контрагент")
    elif len(c_ids) > 1:
        score -= 25
        penalties.append("указаны разные контрагенты")

    # 5. Близость строк (соседние ID или строки импорта)
    ids_sorted = sorted(u.purchase_id for u in units)
    max_gap = max(ids_sorted[i + 1] - ids_sorted[i] for i in range(len(ids_sorted) - 1))
    if max_gap <= 3:
        score += 8
        reasons.append("соседние строки в таблице/реестре")

    # 6. Пересечение с текстом назначения платежа
    if purpose_text:
        p_stems = _word_stems(purpose_text)
        all_unit_stems = set().union(*(s["stems"] for s in sigs))
        if p_stems & all_unit_stems:
            score += 15
            reasons.append("совпадает с назначением платежа")

        # Штраф за несовпадение услуг и товаров:
        # Если в платеже прямо написано "услуг", "работ", "перевозк", "медосмотр", "обслуживан",
        # а в комбинации намешаны товары или чисто товарные категории (чайники, посуда, мыши)
        p_low = purpose_text.lower()
        is_payment_service = any(w in p_low for w in ("услуг", "работ", "перевозк", "медосмотр", "техосмотр", "обслуживан", "страхован"))
        has_goods = any(s["item_type"] == "товар" or (s["semantic"] and s["semantic"] in ("Продукты питания и вода", "ИТ, связь и оргтехника", "Канцелярия и хозтовары")) for s in sigs)
        if is_payment_service and has_goods:
            score -= 60
            penalties.append("товары не соответствуют запрашиваемым услугам в платеже")

    # 7. Бонус за совпадение контрагента с получателем платежа
    if payee_inn or payee_name:
        for u in units:
            if _unit_payee_priority(u, payee_name, payee_inn) == 0:
                score += 30
                reasons.append(f"совпадает контрагент «{payee_name or u.contractor_name}»")
                break

    # Штраф за размер комбинации (2 лучше, чем 4 при прочих равных)
    score -= (len(units) - 2) * 3
    score = max(5, min(99, score))

    has_service_goods_conflict = bool(purpose_text and is_payment_service and has_goods)
    if has_service_goods_conflict or (penalties and score < 50):
        probability = "low"
        probability_label = "Маловероятно"
        reason_text = "; ".join(penalties + reasons)
    elif score >= 72 and not penalties:
        probability = "high"
        probability_label = "Очень вероятно"
        reason_text = "; ".join(reasons) if reasons else "совпадает сумма и категория"
    elif score >= 50:
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
) -> list[dict]:
    """Находит комбинации из 1..max_combo_size позиций/закупок, дающие в сумме
    target_amount ± tol, и ранжирует их по смысловой/категорийной близости."""
    if target_amount is None or target_amount <= Decimal(0):
        return []

    valid_units = [
        u for u in units
        if u.amount is not None
        and Decimal(0) < u.amount <= target_amount + tol
        and not is_unit_contractor_conflicting(u, payee_name=payee_name, payee_inn=payee_inn)
    ]
    # Сортируем кандидатов:
    # 0 — совпадение по контрагенту (ИНН/название) — приоритет №1;
    # 1 — без контрагента («забыли проставить»);
    # затем по ID закупки.
    valid_units.sort(key=lambda u: (_unit_payee_priority(u, payee_name, payee_inn), u.purchase_id))
    pool = valid_units[:MAX_POOL_SIZE]

    results: list[dict] = []
    upper_k = min(max_combo_size, len(pool))
    for k in range(1, upper_k + 1):
        for combo in itertools.combinations(pool, k):
            total = sum((u.amount for u in combo), Decimal(0))
            if abs(total - target_amount) <= tol:
                eval_res = evaluate_combo_coherence(list(combo), purpose_text=purpose_text, payee_name=payee_name, payee_inn=payee_inn)
                can_merge = len(combo) >= 2 and len({u.contractor_id for u in combo if u.contractor_id is not None}) <= 1
                results.append({
                    "purchase_ids": [u.purchase_id for u in combo],
                    "items": [
                        {
                            "purchase_id": u.purchase_id,
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
                        for u in combo
                    ],
                    "total_amount": float(total),
                    "delta": float(total - target_amount),
                    "count": len(combo),
                    "score": eval_res["score"],
                    "probability": eval_res["probability"],
                    "probability_label": eval_res["probability_label"],
                    "coherence_reason": eval_res["coherence_reason"],
                    "can_merge": can_merge,
                })

    # Сортируем: сначала high → medium → low, внутри по убыванию score, затем меньшее кол-во позиций
    prob_rank = {"high": 3, "medium": 2, "low": 1}
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
        ))

    return units


async def merge_and_attach_combo(
    db: AsyncSession,
    subsidy_id: int,
    bp: BankPayment,
    purchase_ids: list[int],
    *,
    merge_purchases: bool = True,
) -> dict:
    """Объединяет выбранную комбинацию разрозненных закупок (без номеров/контрагента)
    в одну закупку (либо оставляет раздельными при merge_purchases=False),
    проставляет контрагента из BankPayment и привязывает платёж через единый
    payment_lookup.attach (ПРАВИЛО №6)."""
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

    purchases: list[Purchase] = []
    for pid in purchase_ids:
        p = await db.get(Purchase, pid)
        if not p or p.subsidy_id != subsidy_id:
            raise HTTPException(404, f"Закупка #{pid} не найдена в этой субсидии")
        purchases.append(p)

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

    if merge_purchases and len(purchases) > 1:
        main_p = purchases[0]
        other_ps = purchases[1:]
        other_pids = [op.id for op in other_ps]

        # Переносим все PurchaseItem из вторичных закупок в основную
        other_items = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id.in_(other_pids)).order_by(PurchaseItem.id)
        )).scalars().all()
        for pi in other_items:
            pi.purchase_id = main_p.id
            if contractor_obj and not pi.contractor_id:
                set_item_contractor(pi, contractor=contractor_obj, name=contractor_obj.name)

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

        # Собираем объединённый предмет закупки
        subjects = [
            (p.subject or p.item_name or "").strip()
            for p in purchases
            if (p.subject or p.item_name or "").strip()
        ]
        if subjects:
            combined_subj = " + ".join(dict.fromkeys(subjects))
            if len(combined_subj) > 250:
                combined_subj = f"{subjects[0][:180]} + ещё {len(subjects) - 1} поз."
            main_p.subject = combined_subj
            main_p.item_name = combined_subj

        # Суммируем contract_price/planned_total_price перед пересчётом на случай безпозиционных строк
        merged_contract_price = sum(
            (Decimal(str(p.contract_price or p.planned_total_price or p.total_nmck or 0)) for p in purchases),
            Decimal(0),
        )
        await db.flush()

        # Удаляем опустевшие вторичные закупки
        for op in other_ps:
            await delete_purchase_core(op, db)
        await db.flush()

        await recalc_purchase_money(db, main_p)
        if main_p.contract_price is not None or any(p.contract_price is not None for p in purchases):
            main_p.contract_price = merged_contract_price
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
        allocations = {main_p.id: Decimal(str(bp.amount or 0))}
    else:
        for p in purchases:
            if contractor_obj and not p.contractor_id:
                p.contractor_id = contractor_obj.id
        await db.flush()
        target_purchases = purchases
        bp_amt = Decimal(str(bp.amount or 0))
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
        # Пакетное применение: если месяц помесячной закупки не определился автоматически,
        # пробуем привязать к месяцу самого платежа, чтобы не срывать массовое сопоставление
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

    # Переводим закупку в статус paid и гарантируем контрагента на уровне закупки и позиций
    for p in target_purchases:
        if contractor_obj:
            if not p.contractor_id:
                p.contractor_id = contractor_obj.id
            # Обновляем контрагента и на позициях закупки
            p_items = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
            )).scalars().all()
            for pi in p_items:
                if not pi.contractor_id:
                    set_item_contractor(pi, contractor=contractor_obj, name=contractor_obj.name)
        p.status = "paid"
    await db.flush()

    return {
        "ok": True,
        "merged": merge_purchases and len(purchase_ids) > 1,
        "primary_purchase_id": first_p.id,
        "registry_number": first_p.registry_number,
        "merged_count": len(purchase_ids),
        "warnings": warnings,
    }

