import os
from io import BytesIO
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.models.feo_category import FeoCategory
from app.models.event import Event
from app.auth.jwt import get_current_user
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Phase 26-V: падежные склонения для шаблонов СЗ.
# pymorphy3 — для общих слов (должность), petrovich — для ФИО.
_morph = None
_petro = None

def _get_morph():
    global _morph
    if _morph is None:
        try:
            from pymorphy3 import MorphAnalyzer
            _morph = MorphAnalyzer()
        except Exception:
            _morph = False
    return _morph or None

def _get_petro():
    global _petro
    if _petro is None:
        try:
            from petrovich.main import Petrovich
            from petrovich.enums import Case, Gender
            _petro = (Petrovich(), Case, Gender)
        except Exception:
            _petro = False
    return _petro or None

def _to_gen_word_heuristic(word: str) -> str:
    """Эвристическое склонение слова в родительный падеж без pymorphy3.

    Покрывает 80-90% русских должностей (мужской род, второе склонение).
    Phase 26-SS: fallback после удаления pymorphy3 (OOM на проде, e2dee47).
    """
    if not word or len(word) < 2:
        return word
    lower = word.lower()
    # Сохраняем регистр первой буквы
    cap = word[0].isupper()
    # Окончания:
    # Слова УЖЕ в родительном падеже (атрибуты): «отдела», «управления»,
    # «фирмы» → не трогаем. Эвристика: -а/-я/-ы/-и/-ов/-ей часто = gen.sg/pl.
    if lower.endswith(('ия', 'ой', 'ого', 'его', 'ев', 'ов', 'ей')) and len(lower) > 3:
        result = lower
    elif lower.endswith('ый'):     # «главный» → «главного»
        result = lower[:-2] + 'ого'
    elif lower.endswith('ий'):     # «ведущий» → «ведущего» (после ж/ч/ш/щ → -его),
                                    # «генеральный» → «генерального» (после др. → -ого)
        prev = lower[-3] if len(lower) >= 3 else ''
        result = lower[:-2] + ('его' if prev in ('ж', 'ч', 'ш', 'щ') else 'ого')
    elif lower.endswith('ая'):     # «заведующая» → «заведующей»
        result = lower[:-2] + 'ей'
    elif lower.endswith('я'):      # «дядя» → «дяди»
        result = lower[:-1] + 'и'
    elif lower.endswith('а'):      # «бухгалтера» — уже gen.sg → не трогаем
        result = lower
    elif lower.endswith('ь'):      # «руководитель» → «руководителя»
        result = lower[:-1] + 'я'
    elif lower.endswith('й'):      # «специалистей» — редко
        result = lower[:-1] + 'я'
    elif lower.endswith(('о', 'е', 'у', 'ы', 'э', 'ю')):
        # Несклоняемые: фамилии типа «Лопатко», иностранные «такси»
        result = lower
    else:                          # consonant
        # «специалист» → «специалиста», «директор» → «директора»
        result = lower + 'а'

    if cap:
        result = result[0].upper() + result[1:]
    return result


def _to_gen_word(word: str) -> str:
    """Склонить одно слово в родительный падеж: pymorphy3 → эвристика."""
    if not word:
        return word
    morph = _get_morph()
    if morph:
        try:
            parsed = morph.parse(word)[0]
            inflected = parsed.inflect({'gent'})
            if inflected:
                out = inflected.word
                if word[0].isupper():
                    out = out[0].upper() + out[1:]
                return out
        except Exception:
            pass
    # Phase 26-SS: fallback на эвристику если pymorphy3 нет (e2dee47 OOM revert)
    return _to_gen_word_heuristic(word)

def _to_gen_phrase(phrase: str) -> str:
    """Склонить фразу (должность) в родительный падеж — каждое слово отдельно."""
    if not phrase:
        return phrase
    import re as _re
    parts = _re.split(r'(\s+|-)', phrase)
    return ''.join(_to_gen_word(p) if p.strip() and p != '-' else p for p in parts)

def _to_gen_fio(full_name: str) -> str:
    """Склонить ФИО (Фамилия Имя Отчество) в родительный падеж через petrovich."""
    petro_pack = _get_petro()
    if not petro_pack or not full_name:
        return full_name
    petro, Case, Gender = petro_pack
    parts = full_name.strip().split()
    if not parts:
        return full_name
    try:
        gender = Gender.MALE
        if len(parts) >= 3 and parts[2].endswith(('вна', 'чна')):
            gender = Gender.FEMALE
        elif len(parts) >= 3 and parts[2].endswith('вич'):
            gender = Gender.MALE
        result = []
        if len(parts) >= 1:
            result.append(petro.lastname(parts[0], Case.GENITIVE, gender))
        if len(parts) >= 2:
            result.append(petro.firstname(parts[1], Case.GENITIVE, gender))
        if len(parts) >= 3:
            result.append(petro.middlename(parts[2], Case.GENITIVE, gender))
        return ' '.join(result)
    except Exception:
        return _to_gen_phrase(full_name)

router = APIRouter(prefix="/api/purchases", tags=["documents"])
guide_router = APIRouter(prefix="/api/documents", tags=["documents"])

TEMPLATES_DIR = "/app/templates"
SUBSIDY_TEMPLATES_DIR = "/app/uploads/templates"

DOC_TYPES = {
    "service_note_delivery": ("service_note_delivery.docx", "SZ_Vydacha"),
    "service_note_payment":  ("service_note_payment.docx",  "SZ_Oplata"),
    # Phase 19.05: dedicated SZ for procurement (distinct from generic service_note)
    "service_note_procurement": ("service_note_procurement.docx", "SZ_Zakupka"),
    # Phase 19.07: СЗ на аванс
    "service_note_advance":  ("service_note_advance.docx",  "SZ_Avans"),
    # Legacy — kept for backwards compat with existing uploaded subsidy overrides.
    "contract_tz":           ("contract_tz.docx",           "Contract_TZ"),
    # tech_spec falls back to contract_tz.docx — separation kept for future
    # when a dedicated tech_spec template is uploaded, but both resolve to
    # the same file today so there is no confusing "empty ТЗ slot" in UI.
    "tech_spec":             ("contract_tz.docx",           "Tech_Spec"),
    # Phase 19.05: split ТЗ into request-of-prices and contract-appendix variants.
    # Default template file is a copy of contract_tz.docx; admins upload
    # per-subsidy overrides via SubsidiesView.
    "tech_spec_request":     ("tech_spec_request.docx",     "TZ_Zapros_Cen"),
    "tech_spec_contract":    ("tech_spec_contract.docx",    "TZ_Dogovor"),
    "contract":              ("contract.docx",              "Contract"),
    # Phase 23.1: contract_services / contract_goods merged into universal contract.docx
    # (removed — subject_kind auto-detected from purchase_items.product.item_kind)
    "approval_sheet":        ("approval_sheet.docx",        "Approval_Sheet"),
    "order_purchase":        ("order_purchase.docx",        "Prikaz_zakupki"),
}

# Phase 19.05: fallback map — if a dedicated template file is missing,
# fall back to the legacy file so the endpoint still works before admins
# upload per-subsidy overrides.
DOC_TYPE_FALLBACK_FILES = {
    "service_note_procurement": "service_note.docx",
    # Phase 19.07: fall back to generic service_note until a dedicated
    # advance template is uploaded (per-subsidy or globally).
    "service_note_advance":     "service_note.docx",
    "tech_spec_request":        "contract_tz.docx",
    "tech_spec_contract":       "contract_tz.docx",
}

# Fields required to generate a FADM contract; maps field_path → label
_CONTRACT_REQUIRED_FIELDS = {
    "contractor": "Контрагент",
    "contractor.org_type": "Тип контрагента (Юр.лицо / ИП / Самозанятый)",
    "contractor.inn": "ИНН контрагента",
    "contractor.address": "Юридический адрес контрагента",
    "contractor.settlement_account": "Расчётный счёт контрагента",
    "contractor.bank_name": "Наименование банка",
    "contractor.bik": "БИК банка",
    "contract_number": "Номер договора",
    "contract_date": "Дата договора",
    "subject": "Предмет договора (услуги)",
    "contract_price": "Цена договора",
    "service_period_type": "Тип срока (период / дата)",
    "execution_term": "Срок оказания услуг",
}

_BASIS_LABELS = {
    "plan_schedule": "план-график",
    "service_note": "служебная записка",
}


def _fmt_date(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return d
    return d.strftime("%d.%m.%Y")


def _clean_id(v) -> str:
    """Strip trailing .0 from INN/KPP imported as float strings."""
    if not v:
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def _fmt_money(v) -> str:
    if v is None:
        return ""
    return f"{float(v):,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def _fmt_money_plain(v) -> str:
    """Money without currency symbol, with space thousand separator, comma decimal."""
    if v is None:
        return ""
    return f"{float(v):,.2f}".replace(",", " ").replace(".", ",")


def _sum_items_price(p) -> float:
    """Fallback: manually sum item.total_price when p.total_nmck is NULL."""
    items = getattr(p, "items", None) or []
    total = 0.0
    for it in items:
        try:
            total += float(getattr(it, "total_price", 0) or 0)
        except Exception:
            pass
    return total


async def _build_contract_items_context(p, db) -> dict:
    """Phase 27.1 CD-5: build docxtpl context entries for {{contract_items}} loop.

    Returns dict with keys:
      - contract_items: list[dict] for loop in template (fields num/name/quantity/unit/unit_price/total)
      - contract_items_total: formatted string like "150 000,00 ₽"
      - contract_items_total_numeric: float for arithmetic in template
      - contract_item_count: int, len of contract_items list

    Fallback (D-08 deprecated alias): if purchase has no contract_items —
    populate from purchase_items so legacy templates keep working.
    """
    from app.models.contract_item import ContractItem as _ContractItem
    ci_query = await db.execute(
        select(_ContractItem)
        .where(_ContractItem.purchase_id == p.id)
        .order_by(_ContractItem.id)
    )
    contract_items_db = ci_query.scalars().all()

    result_list = []
    total_numeric = 0.0
    if contract_items_db:
        # Primary path: contract_items exist — use them
        for idx, ci in enumerate(contract_items_db, start=1):
            tot = float(ci.total) if ci.total else 0.0
            result_list.append({
                "num": idx,
                "name": ci.name or "",
                "quantity": float(ci.quantity) if ci.quantity else "",
                "unit": ci.unit or "",
                "unit_price": _fmt_money(ci.unit_price),
                "total": _fmt_money(ci.total),
                "total_numeric": tot,
            })
            total_numeric += tot
    else:
        # D-08 fallback: contract_items empty — use purchase_items as deprecated alias
        for idx, item in enumerate(getattr(p, "items", None) or [], start=1):
            tot = float(item.total_price) if item.total_price else 0.0
            result_list.append({
                "num": idx,
                "name": item.item_name or "",
                "quantity": float(item.quantity) if item.quantity else "",
                "unit": item.unit or "",
                "unit_price": _fmt_money(item.unit_price),
                "total": _fmt_money(item.total_price),
                "total_numeric": tot,
            })
            total_numeric += tot

    return {
        "contract_items": result_list,
        "contract_items_total": _fmt_money(total_numeric),
        "contract_items_total_numeric": total_numeric,
        "contract_item_count": len(result_list),
    }


async def _resolve_user_dept(user, db, org_id: Optional[int] = None) -> str:
    """Возвращает название отдела пользователя для шаблона СЗ.

    Бизнес-правило: должность/отдел берутся per-org, по той организации,
    к которой привязана субсидия закупки. Если юзер в этой org в нескольких
    отделах — берём первый (по user_organizations.id).

    Приоритет:
      1) Department.name через user_organizations где org_id == org_id (если задан)
      2) Department.name через user_organizations первая запись (любая org)
      3) User.department (legacy строковое поле)
      4) "" если ничего нет
    """
    if user is None:
        return ""
    try:
        from app.models.user_organization import UserOrganization
        from app.models.department import Department
        from sqlalchemy import select as _sel
        # 1. В пределах org закупки
        if org_id is not None:
            res = await db.execute(
                _sel(Department.name)
                .join(UserOrganization, UserOrganization.dept_id == Department.id)
                .where(
                    UserOrganization.user_id == user.id,
                    UserOrganization.org_id == org_id,
                )
                .order_by(UserOrganization.id)
                .limit(1)
            )
            name = res.scalar_one_or_none()
            if name:
                return name
        # 2. Любая первая
        res = await db.execute(
            _sel(Department.name)
            .join(UserOrganization, UserOrganization.dept_id == Department.id)
            .where(UserOrganization.user_id == user.id)
            .order_by(UserOrganization.id)
            .limit(1)
        )
        name = res.scalar_one_or_none()
        if name:
            return name
    except Exception:
        pass
    # 3. Legacy строковое поле
    return getattr(user, "department", None) or ""


async def _resolve_user_position(user, db, org_id: Optional[int] = None) -> str:
    """Возвращает должность пользователя для шаблона СЗ.

    Приоритет:
      1) user_organizations.position где org_id == org_id (если задан и не пустой)
      2) user_organizations.position первая (любая org)
      3) User.position (legacy)
      4) "" если нет
    """
    if user is None:
        return ""
    try:
        from app.models.user_organization import UserOrganization
        from sqlalchemy import select as _sel
        if org_id is not None:
            res = await db.execute(
                _sel(UserOrganization.position)
                .where(
                    UserOrganization.user_id == user.id,
                    UserOrganization.org_id == org_id,
                )
                .order_by(UserOrganization.id)
                .limit(1)
            )
            pos = res.scalar_one_or_none()
            if pos:
                return pos
        res = await db.execute(
            _sel(UserOrganization.position)
            .where(UserOrganization.user_id == user.id)
            .order_by(UserOrganization.id)
            .limit(1)
        )
        pos = res.scalar_one_or_none()
        if pos:
            return pos
    except Exception:
        pass
    return getattr(user, "position", None) or ""


def _format_service_term(p) -> str:
    """Build the human-readable service-term string for docx templates.

    Phase 19 — three modes:
      - range:    "с 01.05.2026 по 31.05.2026"
      - duration: "в течение 30 календарных дней после заключения договора"
      - deadline: "до 30.06.2026 включительно"
    """
    mode = getattr(p, "service_term_mode", None)
    if mode == "range" and p.service_start_date and p.service_end_date:
        return (
            f"с {p.service_start_date.strftime('%d.%m.%Y')} "
            f"по {p.service_end_date.strftime('%d.%m.%Y')}"
        )
    if mode == "duration" and getattr(p, "service_term_days", None):
        type_name = {
            "calendar": "календарных",
            "working":  "рабочих",
        }.get(getattr(p, "service_term_type", None) or "calendar", "календарных")
        return f"в течение {p.service_term_days} {type_name} дней после заключения договора"
    if mode == "deadline" and getattr(p, "service_deadline_date", None):
        return f"до {p.service_deadline_date.strftime('%d.%m.%Y')} включительно"
    return ""


_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
         "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_ONES_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
           "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
           "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]


def _chunk_to_words(n: int, feminine: bool = False) -> str:
    parts = []
    h = n // 100
    r = n % 100
    t = r // 10
    o = r % 10
    if h:
        parts.append(_HUNDREDS[h])
    if r < 20:
        w = (_ONES_F[r] if feminine else _ONES[r])
        if w:
            parts.append(w)
    else:
        if t:
            parts.append(_TENS[t])
        w = (_ONES_F[o] if feminine else _ONES[o])
        if w:
            parts.append(w)
    return " ".join(parts)


def _rubles_to_words(amount) -> str:
    """Convert numeric amount to Russian words (рублей XX копеек)."""
    if amount is None:
        return ""
    try:
        val = round(float(amount), 2)
    except (TypeError, ValueError):
        return ""
    rubles = int(val)
    kopecks = round((val - rubles) * 100)
    billions = rubles // 1_000_000_000
    millions = (rubles % 1_000_000_000) // 1_000_000
    thousands = (rubles % 1_000_000) // 1_000
    rest = rubles % 1_000

    parts = []
    if billions:
        w = _chunk_to_words(billions)
        if w:
            parts.append(w)
        if billions % 10 == 1 and billions % 100 != 11:
            parts.append("миллиард")
        elif 2 <= billions % 10 <= 4 and not (11 <= billions % 100 <= 14):
            parts.append("миллиарда")
        else:
            parts.append("миллиардов")
    if millions:
        w = _chunk_to_words(millions)
        if w:
            parts.append(w)
        if millions % 10 == 1 and millions % 100 != 11:
            parts.append("миллион")
        elif 2 <= millions % 10 <= 4 and not (11 <= millions % 100 <= 14):
            parts.append("миллиона")
        else:
            parts.append("миллионов")
    if thousands:
        w = _chunk_to_words(thousands, feminine=True)
        if w:
            parts.append(w)
        if thousands % 10 == 1 and thousands % 100 != 11:
            parts.append("тысяча")
        elif 2 <= thousands % 10 <= 4 and not (11 <= thousands % 100 <= 14):
            parts.append("тысячи")
        else:
            parts.append("тысяч")
    if rest or not parts:
        w = _chunk_to_words(rest, feminine=True)
        if w:
            parts.append(w)
    if rubles == 0:
        parts = ["ноль"]

    # Ruble ending
    r10 = rubles % 10
    r100 = rubles % 100
    if r10 == 1 and r100 != 11:
        rub_word = "рубль"
    elif 2 <= r10 <= 4 and not (11 <= r100 <= 14):
        rub_word = "рубля"
    else:
        rub_word = "рублей"

    parts.append(rub_word)
    parts.append(f"{kopecks:02d}")
    k10 = kopecks % 10
    k100 = kopecks % 100
    if k10 == 1 and k100 != 11:
        parts.append("копейка")
    elif 2 <= k10 <= 4 and not (11 <= k100 <= 14):
        parts.append("копейки")
    else:
        parts.append("копеек")

    return " ".join(parts)


def _validate_contract_fields(p, c) -> list[str]:
    """Return list of missing required fields for contract generation."""
    missing = []
    if not c:
        return ["Контрагент не указан в закупке"]
    checks = [
        (c.org_type, "Тип контрагента (org_type)"),
        (c.inn, "ИНН контрагента"),
        (c.address, "Юридический адрес контрагента"),
        (c.settlement_account, "Расчётный счёт контрагента"),
        (c.bank_name, "Наименование банка"),
        (c.bik, "БИК банка"),
        (p.contract_number, "Номер договора"),
        (p.contract_date, "Дата договора"),
        (p.subject, "Предмет договора"),
        (p.contract_price, "Цена договора"),
        (p.service_period_type, "Тип срока (period/date)"),
        (p.execution_term, "Срок оказания услуг / дата"),
    ]
    if c.org_type == "Юр.лицо":
        checks += [
            (c.kpp, "КПП контрагента"),
            (c.ogrn, "ОГРН контрагента"),
            (c.signatory, "ФИО подписанта"),
            (c.signatory_basis, "Основание полномочий подписанта"),
        ]
    elif c.org_type == "ИП":
        checks += [
            (c.ogrn, "ОГРНИП контрагента"),
        ]
    for val, label in checks:
        if not val and val != 0:
            missing.append(label)
    return missing


@router.get("/{pid}/documents/{doc_type}")
async def generate_document(
    pid: int,
    doc_type: str,
    approver_ids: Optional[str] = Query(default=None, description="ID согласующих через запятую"),
    initiator_id: Optional[int] = Query(default=None, description="ID инициатора служебной записки"),
    responsible_name: Optional[str] = Query(default=None, description="ФИО ответственного исполнителя (переопределяет поле закупки)"),
    tz_override_mode: Optional[str] = Query(default=None, description="Переопределить режим ТЗ: 'exact' или '44fz'"),
    merge: Optional[str] = Query(default=None, description="Phase 19.06: merge with another doc_type (e.g. 'tech_spec_contract') — appends its paragraphs/tables as a new section after the primary doc"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}. Доступны: {', '.join(DOC_TYPES)}")

    template_file, filename_base = DOC_TYPES[doc_type]
    template_path = os.path.join(TEMPLATES_DIR, template_file)

    # For contract documents: check subsidy-specific template first
    # (loaded after purchase is fetched below, but we need subsidy_id from the purchase)
    # We'll resolve the path after loading the purchase — placeholder here

    # Phase 19.05: for new split doc_types, fall back to legacy template file
    # if the dedicated one hasn't been uploaded yet.
    if not os.path.exists(template_path):
        fallback = DOC_TYPE_FALLBACK_FILES.get(doc_type)
        if fallback:
            fallback_path = os.path.join(TEMPLATES_DIR, fallback)
            if os.path.exists(fallback_path):
                template_path = fallback_path
                template_file = fallback
    if not os.path.exists(template_path):
        raise HTTPException(
            404,
            f"Шаблон '{template_file}' не найден. "
            f"Поместите файл в backend/templates/{template_file}"
        )

    # Load purchase with related data
    from app.models.contract_item import ContractItem as _ContractItem  # Phase 27.1 CD-5
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.contract_items),  # Phase 27.1 CD-5: eager-load for docxtpl context
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    # Override template path with subsidy-specific template if available
    if p.subsidy_id:
        subsidy_template = os.path.join(SUBSIDY_TEMPLATES_DIR, "subsidies", str(p.subsidy_id), f"{doc_type}.docx")
        if os.path.exists(subsidy_template):
            template_path = subsidy_template

    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
    subsidy = subsidy_r.scalar_one_or_none()

    # Phase 23: Customer = Organization owning the subsidy. Loads linked Contractor (FK)
    # for banking details (r/s, bank_name, BIK, k/s).
    customer_org = None
    customer_ctr = None  # Contractor linked to org via FK
    if subsidy and subsidy.org_id:
        from app.models.organization import Organization
        org_r = await db.execute(select(Organization).where(Organization.id == subsidy.org_id))
        customer_org = org_r.scalar_one_or_none()
        if customer_org and customer_org.contractor_id:
            from app.models.contractor import Contractor as _CtrCust
            ctr_r = await db.execute(select(_CtrCust).where(_CtrCust.id == customer_org.contractor_id))
            customer_ctr = ctr_r.scalar_one_or_none()

    # Load event if linked
    event = None
    if p.event_id:
        ev_r = await db.execute(select(Event).where(Event.id == p.event_id))
        event = ev_r.scalar_one_or_none()

    # Load approvers if requested
    selected_approvers = []
    if approver_ids:
        ids = [int(x.strip()) for x in approver_ids.split(",") if x.strip().isdigit()]
        if ids:
            res = await db.execute(
                select(SubsidyApprover)
                .where(SubsidyApprover.id.in_(ids))
                .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
            )
            selected_approvers = res.scalars().all()

    # Load initiator if requested (frontend always sends User.id, not SubsidyApprover.id).
    # Бизнес-правило: за другого человека делать СЗ может только тот, кому
    # подчинён этот человек (видим через _get_visible_user_ids — тот же scope,
    # что для постановки задач). Самого себя — всегда можно.
    initiator = None
    if initiator_id and initiator_id != getattr(current_user, "id", None):
        from app.routers.task_visibility import _get_visible_user_ids
        visible = await _get_visible_user_ids(current_user, db)
        if visible is not None and initiator_id not in visible:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INITIATOR_FORBIDDEN",
                    "message": (
                        "Указанный инициатор вам не подчинён. Сделать служебную "
                        "записку за другого человека может только его руководитель."
                    ),
                },
            )
    # Стратегия резолва:
    #   1) SubsidyApprover.user_id == initiator_id (привязанный approver субсидии) →
    #      берём full_name/role_name из карточки approver'а
    #   2) Иначе SimpleNamespace из User (full_name/position/department)
    if initiator_id:
        # 1. Привязанный approver субсидии (если есть)
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.user_id == initiator_id)
            .options(selectinload(SubsidyApprover.user))
            .order_by(SubsidyApprover.id)
            .limit(1)
        )
        initiator = res.scalar_one_or_none()
        # 2. Виртуальный approver из User
        if initiator is None:
            from app.models.user import User as UserModel
            from types import SimpleNamespace
            u = (
                await db.execute(select(UserModel).where(UserModel.id == initiator_id))
            ).scalar_one_or_none()
            if u:
                initiator = SimpleNamespace(
                    full_name=u.full_name or u.username,
                    role_name=u.position or "",
                    user=u,
                )

        # Membership-check: инициатор должен состоять в организации, к которой
        # привязана субсидия закупки. Без этого должность/отдел не определены,
        # СЗ от имени постороннего сотрудника недопустима.
        subsidy_org_id = getattr(subsidy, "org_id", None) if subsidy else None
        init_user = initiator.user if (initiator and getattr(initiator, "user", None)) else None
        if subsidy_org_id and init_user:
            from app.models.user_organization import UserOrganization
            mem = (await db.execute(
                select(UserOrganization.id).where(
                    UserOrganization.user_id == init_user.id,
                    UserOrganization.org_id == subsidy_org_id,
                ).limit(1)
            )).first()
            # Legacy fallback — User.org_id (primary)
            if not mem and getattr(init_user, "org_id", None) != subsidy_org_id:
                org_name = getattr(customer_org, "name", "") if customer_org else ""
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "INITIATOR_NOT_IN_ORG",
                        "message": (
                            f"Инициатор не состоит в организации"
                            + (f" «{org_name}»" if org_name else "")
                            + ", к которой привязана субсидия закупки. Выберите "
                            "сотрудника этой организации."
                        ),
                    },
                )

    # If no approvers specified — load defaults for this subsidy
    if not selected_approvers and p.subsidy_id:
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.subsidy_id == p.subsidy_id, SubsidyApprover.is_default == True)
            .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
        )
        selected_approvers = res.scalars().all()

    # Build FEO category path (root → ... → selected) + individual levels
    feo_path = ""
    feo_level_1 = ""
    feo_level_2 = ""
    feo_level_3 = ""
    if p.feo_category_id:
        feo_res = await db.execute(select(FeoCategory))
        all_feo = {f.id: f for f in feo_res.scalars().all()}
        path_nodes: list = []
        node_id = p.feo_category_id
        visited: set = set()
        while node_id and node_id not in visited:
            visited.add(node_id)
            cat = all_feo.get(node_id)
            if not cat:
                break
            path_nodes.append(cat)
            node_id = cat.parent_id
        path_nodes.reverse()  # root → leaf
        feo_path = " → ".join(n.name.strip() for n in path_nodes)
        if len(path_nodes) >= 1: feo_level_1 = path_nodes[0].name.strip()
        if len(path_nodes) >= 2: feo_level_2 = path_nodes[1].name.strip()
        if len(path_nodes) >= 3: feo_level_3 = path_nodes[2].name.strip()

    # Resolved responsible person name
    resolved_responsible = responsible_name or p.responsible_person or ""

    # Build docxtpl template object early (needed for InlineImage)
    try:
        from docxtpl import DocxTemplate, InlineImage
        from docx.shared import Cm as _Cm

        # Templates are normalized at upload time (subsidies.py
        # _normalize_docx_template) — proofErr / bookmark / comment /
        # lastRenderedPageBreak markers are already stripped on disk, so
        # docxtpl reads the cleaned file directly.
        tpl = DocxTemplate(template_path)
    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        logger.exception("Document template load failed for purchase %s, doc_type=%s", pid, doc_type)
        raise HTTPException(500, detail={
            "code": "DOCUMENT_GENERATION_FAILED",
            "message": f"Не удалось загрузить шаблон «{doc_type}»: {type(e).__name__}",
            "doc_type": doc_type,
            "purchase_id": pid,
            "error_class": type(e).__name__,
            "error_raw": str(e),
            "traceback": "".join(_tb.format_exception(type(e), e, e.__traceback__))[:4000],
            "hint": (
                "Ошибка при загрузке файла шаблона docxtpl. "
                "Возможные причины: повреждённый .docx файл шаблона, "
                "отсутствие библиотеки docxtpl/python-docx. "
                "Передайте администратору error_class + traceback."
            ),
        })

    UPLOADS_DIR = "/app/uploads/products"

    def _resolve_photo(photo_url):
        """Return InlineImage or empty string."""
        import tempfile, urllib.request as _ur
        if not photo_url:
            return ""
        url = str(photo_url).strip()
        local_path = None

        if url.startswith("/api/products/photos/"):
            fname = url.split("/")[-1]
            local_path = f"{UPLOADS_DIR}/{fname}"
        elif url.isdigit():
            for ext in ("jpg", "jpeg", "png"):
                p = f"{UPLOADS_DIR}/product_{url}.{ext}"
                if os.path.exists(p):
                    local_path = p
                    break
        elif url.startswith("http://") or url.startswith("https://"):
            # Download external image; convert webp via Pillow if available
            try:
                with _ur.urlopen(url, timeout=5) as r:
                    ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    raw = r.read()
                is_webp = "webp" in ct or url.lower().endswith(".webp")
                if is_webp:
                    try:
                        from PIL import Image as _Img
                        import io as _io
                        img = _Img.open(_io.BytesIO(raw)).convert("RGB")
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        img.save(tmp, format="JPEG", quality=85)
                        tmp.close()
                        local_path = tmp.name
                    except Exception:
                        return ""  # Pillow not available or conversion failed
                else:
                    ext_map = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
                               "image/gif": ".gif", "image/bmp": ".bmp", "image/tiff": ".tiff"}
                    suffix = ext_map.get(ct, ".jpg")
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tmp.write(raw)
                    tmp.close()
                    local_path = tmp.name
            except Exception:
                return ""

        if not local_path or not os.path.exists(local_path):
            return ""
        try:
            return InlineImage(tpl, local_path, width=_Cm(2.5))
        except Exception:
            return ""

    # Build template context
    items_list = []
    for idx, item in enumerate(p.items or [], start=1):
        photo_url = item.product.photo_url if item.product else None
        items_list.append({
            "num": idx,
            "name": item.item_name or "",
            "description": (
                (item.product.description_44fz if (tz_override_mode or p.description_mode or "exact") == "44fz" else item.product.description)
                if item.product else ""
            ) or "",
            "type": item.item_type or "",
            "item_kind": (item.product.item_kind if item.product else None) or "товар",
            "quantity": float(item.quantity) if item.quantity else "",
            "unit": item.unit or "",
            "unit_price": _fmt_money(item.unit_price),
            "total_price": _fmt_money(item.total_price),
            "photo": _resolve_photo(photo_url),
        })

    # Phase 23.1: auto-detect subject_kind for universal contract.docx
    # 'services' if ALL items have item_kind='услуга', otherwise 'goods' (default)
    subject_kind = "goods"
    if items_list:
        kinds = {it.get("item_kind", "товар").lower() for it in items_list}
        if kinds == {"услуга"}:
            subject_kind = "services"

    # Load existing PurchaseApproval records (electronic signatures)
    from app.models.purchase_approval import PurchaseApproval
    pa_res = await db.execute(
        select(PurchaseApproval)
        .where(PurchaseApproval.purchase_id == pid, PurchaseApproval.status == "approved")
        .order_by(PurchaseApproval.order_num)
    )
    # Map subsidy_approver_id → PurchaseApproval (for signature lookup)
    approval_map: dict[int, PurchaseApproval] = {}
    for pa in pa_res.scalars().all():
        if pa.subsidy_approver_id:
            approval_map[pa.subsidy_approver_id] = pa

    def _base64_to_inline(tpl_obj, b64_data: str):
        """Convert base64 PNG data URL to docxtpl InlineImage."""
        import tempfile, base64, re as _re
        try:
            from docxtpl import InlineImage
            from docx.shared import Cm as _Cm
            m = _re.match(r"data:image/\w+;base64,(.+)", b64_data, _re.DOTALL)
            if not m:
                return ""
            raw = base64.b64decode(m.group(1))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(raw)
            tmp.close()
            return InlineImage(tpl_obj, tmp.name, width=_Cm(3.0))
        except Exception:
            return ""

    # Collect unique product categories from items
    item_categories = list(dict.fromkeys(
        item.product.category
        for item in (p.items or [])
        if item.product and item.product.category
    ))
    item_categories_str = ", ".join(item_categories)

    approvers_list = []
    for i, a in enumerate(selected_approvers):
        full_name = a.full_name or ""
        # Substitute responsible person into rows with empty or placeholder full_name
        if not full_name.strip().strip("_").strip():
            full_name = resolved_responsible
        if getattr(a, "show_feo_path", False) and feo_path:
            item_type_label = {"товар": "Товары", "услуга": "Услуги"}.get(p.item_type or "", "")
            note = feo_path + (f" ({item_type_label})" if item_type_label else "")
        else:
            note = ""

        # Electronic signature
        pa = approval_map.get(a.id)
        signature_img = ""
        decided_date = ""
        if pa and pa.signature_data and pa.signature_algorithm == "visual":
            signature_img = _base64_to_inline(tpl, pa.signature_data)
            if pa.decided_at:
                decided_date = pa.decided_at.strftime("%d.%m.%Y")

        approvers_list.append({
            "num": i + 1,
            "role_name": a.role_name,
            "full_name": full_name,
            "signature_img": signature_img,
            "decided_date": decided_date,
            "note": note,
            # Phase 26-V: родительный падеж
            "full_name_gen": _to_gen_fio(full_name),
            "role_name_gen": _to_gen_phrase(a.role_name or ""),
        })

    c = p.contractor

    # ── Contract-specific context helpers ────────────────────────────────────
    def _contract_date_parts():
        d = p.contract_date
        if not d:
            return "", "", ""
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                return "", "", ""
        months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        return str(d.day).zfill(2), months_ru[d.month - 1], str(d.year)

    cd_day, cd_month, cd_year = _contract_date_parts()

    # Short name: extract parenthetical or use first word
    def _short_name(full_name: str) -> str:
        import re
        m = re.search(r'[«""]([^»""]+)[»""]', full_name)
        if m:
            return m.group(1)
        parts = full_name.split()
        return parts[-1] if parts else full_name

    # Signatory position: extract from signatory field if "Директор ФИО" format
    def _signatory_position(signatory: str) -> str:
        if not signatory:
            return ""
        parts = signatory.strip().split()
        if len(parts) > 1 and not parts[0][0].isupper():
            return parts[0]
        return "Директор"

    # Phase 23: split "Президент Козеев Евгений Викторович" into structured parts
    def _signatory_split(signatory: str) -> dict:
        """Split 'Position Lastname Firstname Patronymic' into structured dict.

        Returns:
            position      — all words before the ФИО (last 3 words treated as ФИО)
            name_full     — last 3 words (ФИО)
            name_genitive — rough genitive: add '-а'/'-я' to each part where possible
            name_initials — "Козеев Е.В." (Lastname + Initials)
        """
        import re as _re
        if not signatory:
            return {"position": "", "name_full": "", "name_genitive": "", "name_initials": ""}
        parts = signatory.strip().split()
        if len(parts) <= 1:
            return {"position": "", "name_full": signatory, "name_genitive": signatory, "name_initials": signatory}
        # Heuristic: ФИО = last 3 words if ≥4 words total, else last 2
        if len(parts) >= 4:
            pos_words = parts[:-3]
            fio_words = parts[-3:]  # Фамилия Имя Отчество
        elif len(parts) == 3:
            # Could be "Иванов Иван Иванович" (no position) or "Директор Иванов Иван"
            # Heuristic: first word starts with uppercase → probably all ФИО or pos+2
            pos_words = []
            fio_words = parts
        else:
            pos_words = parts[:1]
            fio_words = parts[1:]

        position = " ".join(pos_words)
        name_full = " ".join(fio_words)

        # Rough genitive: Козеев→Козеева, Евгений→Евгения, Викторович→Викторовича
        def _to_genitive(word: str) -> str:
            w = word
            if w.endswith("ич"):  # Иванович → Ивановича
                return w + "а"
            if w.endswith("ий"):  # Евгений → Евгения
                return w[:-2] + "ия"
            if w.endswith("ья"):  # Илья → Ильи
                return w[:-2] + "ьи"
            if w.endswith("а") and len(w) > 2:
                return w[:-1] + "ы"
            # Last consonant cluster: add -а
            vowels = set("аеёиоуыьъэюяАЕЁИОУЫЭЮЯ")
            if w and w[-1] not in vowels and w[-1] not in "ьъ":
                return w + "а"
            return w  # fallback: as-is

        genitive_parts = [_to_genitive(w) for w in fio_words]
        name_genitive = " ".join(genitive_parts)

        # Initials: "Козеев Е.В." — Фамилия + инициалы Имени и Отчества
        if len(fio_words) >= 3:
            lastname, firstname, patronymic = fio_words[0], fio_words[1], fio_words[2]
            name_initials = f"{lastname} {firstname[0]}.{patronymic[0]}."
        elif len(fio_words) == 2:
            name_initials = f"{fio_words[0]} {fio_words[1][0]}."
        else:
            name_initials = name_full

        return {
            "position": position,
            "name_full": name_full,
            "name_genitive": name_genitive,
            "name_initials": name_initials,
        }

    # VAT calculations
    vat_app = bool(p.vat_applicable)
    vat_rate_val = p.vat_rate or 20
    price_val = float(p.contract_price or 0)
    if vat_app and price_val:
        vat_amount_val = price_val * vat_rate_val / (100 + vat_rate_val)
    else:
        vat_amount_val = 0.0

    # НДС info for approval sheet
    # Phase 26-TT: для авансового отчёта не придумывать «НДС не облагается» если
    # в чеке/items нет данных VAT — пишем только то, что реально есть.
    is_advance = (p.purchase_method == 'advance')
    items_with_vat = [it for it in (p.items or []) if getattr(it, 'vat_rate', None)]

    if vat_app:
        vat_info_line = f"В том числе НДС {vat_rate_val}%: {_fmt_money_plain(vat_amount_val)} руб."
    elif is_advance:
        # Авансовый: данные из чеков ФНС; если в чеке нет НДС — не пишем ничего лишнего.
        if items_with_vat:
            # Per-item VAT — показать сводку по факту
            unique_rates = sorted({str(it.vat_rate) for it in items_with_vat if it.vat_rate})
            vat_info_line = f"НДС по позициям: {', '.join(unique_rates)}"
        else:
            vat_info_line = ""  # пусто — не придумываем
    else:
        art = (p.vat_exemption_article or "").strip()
        vat_info_line = f"НДС не облагается" + (f" ({art})" if art else "")

    context = {
        # Закупка
        "purchase_number": p.purchase_number or "",
        "registry_number": p.registry_number or "",
        "purchase_method": {"single": "Единственный поставщик", "competitive": "Конкурсная процедура", "advance": "Авансовый отчёт"}.get(p.purchase_method or "", p.purchase_method or ""),
        "subject": p.subject or "",
        "status": p.status or "",
        "purchase_basis": _BASIS_LABELS.get(p.purchase_basis or "", ""),
        "responsible_person": resolved_responsible,
        # Субсидия
        "subsidy_name": subsidy.name if subsidy else "",
        "subsidy_year": subsidy.year if subsidy else "",
        "subsidy_budget": _fmt_money(subsidy.budget) if subsidy else "",
        # Контрагент — основные
        "contractor_name": (c.name or "") if c else "",
        "contractor_inn": _clean_id(c.inn) if c else "",
        "contractor_kpp": _clean_id(c.kpp) if c else "",
        "contractor_address": (c.address or "") if c else "",
        "contractor_postal_address": (c.postal_address or "") if c else "",
        "contractor_ogrn": (c.ogrn or "") if c else "",
        "contractor_phone": (c.phone or "") if c else "",
        "contractor_email": (c.email or "") if c else "",
        # Контрагент — подписант
        "contractor_signatory": (c.signatory or "") if c else "",
        "contractor_signatory_basis": (c.signatory_basis or "") if c else "",
        # Контрагент — банк
        "contractor_settlement_account": (c.settlement_account or "") if c else "",
        "contractor_bank_name": (c.bank_name or "") if c else "",
        "contractor_bik": (c.bik or "") if c else "",
        "contractor_correspondent_account": (c.correspondent_account or "") if c else "",
        # Комбинированные поля контрагента для шаблонов
        "contractor_bank_details": (c.bank_name or "") if c else "",
        "contractor_signatory_line": (
            f"{c.signatory}, действует на основании {c.signatory_basis}"
            if c and c.signatory and c.signatory_basis
            else ((c.signatory or "") if c else "")
        ),
        # FEO
        "feo_category_name": p.feo_category.name if p.feo_category else "",
        "feo_path":    feo_path,
        "feo_level_1": feo_level_1,
        "feo_level_2": feo_level_2,
        "feo_level_3": feo_level_3,
        # Финансы
        # Phase 19: total_nmcd is the new canonical name (НМЦД — начальная
        # максимальная цена договора). total_nmck is kept as a deprecated
        # alias so existing templates keep rendering. Use total_nmcd in new
        # templates.
        "total_nmcd": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price),
        "total_nmck": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price),
        "nmck": _fmt_money(p.nmck or p.total_nmck),
        "contract_price": _fmt_money(p.contract_price),
        "economy": _fmt_money(p.economy),
        "price_increase": _fmt_money(p.price_increase),
        # Договор
        "contract_number": p.contract_number or "",
        "contract_date": _fmt_date(p.contract_date) or "__.__._____ г.",
        "execution_term": _fmt_date(p.execution_term),
        "execution_term_changed": _fmt_date(p.execution_term_changed),
        "delivery_date": _fmt_date(p.delivery_date),
        "country_origin": p.country_origin or "",
        # Акт приёмки — если нет закрывающих документов, подставляем данные договора
        # (статус «Заказано» — оплата до поставки, документов ещё нет)
        "acceptance_doc_name": (
            p.acceptance_doc_name
            if p.acceptance_doc_name
            else "договору"
        ),
        "acceptance_doc_number": (
            p.acceptance_doc_number
            if p.acceptance_doc_number
            else (p.contract_number or "")
        ),
        "acceptance_doc_date": (
            _fmt_date(p.acceptance_doc_date)
            if p.acceptance_doc_date
            else (_fmt_date(p.contract_date) if p.contract_date else "")
        ),
        "acceptance_doc_amount": (
            _fmt_money(p.acceptance_doc_amount)
            if p.acceptance_doc_amount
            else _fmt_money(
                p.contract_price
                or p.planned_total_price
                or p.total_nmck            # SUM(items.total_price) — always set when items exist
                or _sum_items_price(p)     # manual fallback if total_nmck is NULL
                or 0
            )
        ),
        # Платёж
        "payment_doc_number": p.payment_doc_number or "",
        "payment_doc_date": _fmt_date(p.payment_doc_date),
        "payment_amount": _fmt_money(p.payment_amount),
        "payment_federal": _fmt_money(p.payment_federal),
        # Позиции
        "items": items_list,
        "items_count": len(items_list),
        "item_names": p.subject or ", ".join(i["name"] for i in items_list if i["name"]),
        "item_categories": item_categories_str,
        # Согласующие
        "approvers": approvers_list,
        # Инициатор: ФИО берётся как есть; должность и отдел резолвятся per-org
        # — по организации, к которой привязана субсидия закупки. Если у юзера
        # несколько отделов в этой org — первый.
        "initiator_name": initiator.full_name if initiator else "",
        "initiator_role": (
            await _resolve_user_position(
                initiator.user if (initiator and getattr(initiator, "user", None)) else None,
                db,
                getattr(subsidy, "org_id", None) if subsidy else None,
            )
            or (initiator.role_name if initiator else "")
        ),
        "initiator_dept": await _resolve_user_dept(
            initiator.user if (initiator and getattr(initiator, "user", None)) else None,
            db,
            getattr(subsidy, "org_id", None) if subsidy else None,
        ),
        # Мероприятие
        "event_name": event.name if event else "",
        # Тип договора
        "contract_type": {"single": "Единственный поставщик", "framework_cumulative": "Рамочный (накопительный)", "framework_with_amount": "Рамочный (с суммой)"}.get(p.purchase_contract_type or "", p.purchase_contract_type or ""),
        # Служебные
        "today": _fmt_date(date.today()),
        "today_iso": date.today().isoformat(),
        # ── Расширенные поля для договорных шаблонов ─────────────────────────
        # Дата по частям
        "contract_date_day":   cd_day,
        "contract_date_month": cd_month,
        "contract_date_year":  cd_year,
        # Тип контрагента
        "contractor_org_type": (c.org_type or "") if c else "",
        "contractor_short_name": _short_name(c.name) if c and c.name else "",
        "contractor_signatory_position": _signatory_position(c.signatory) if c else "",
        # Предмет (сервисное имя)
        "service_name": p.subject or "",
        # Срок оказания услуг
        # Phase 19: service_start_date / service_end_date now prefer the real
        # Purchase columns (used by 'range' mode). If those are empty we fall
        # back to the legacy mapping (contract_date / execution_term).
        "period_type": p.service_period_type or "period",
        "service_start_date": _fmt_date(p.service_start_date) or _fmt_date(p.contract_date),
        "service_end_date":   _fmt_date(p.service_end_date)   or _fmt_date(p.execution_term),
        "service_date":       _fmt_date(p.execution_term),
        # Phase 19: extended service-term context
        "service_term":            _format_service_term(p),
        "service_term_mode":       p.service_term_mode or "",
        "service_term_days":       p.service_term_days or "",
        "service_term_type":       p.service_term_type or "",
        "service_term_type_name":  {"calendar": "календарных", "working": "рабочих"}.get(p.service_term_type or "", ""),
        "service_deadline_date":   _fmt_date(p.service_deadline_date),
        # Phase 19: submission deadline (дата+время завершения приёма заявок)
        "submission_deadline_date":     p.submission_deadline.date().isoformat() if p.submission_deadline else "",
        "submission_deadline_time":     p.submission_deadline.strftime("%H:%M") if p.submission_deadline else "",
        "submission_deadline_datetime": p.submission_deadline.strftime("%d.%m.%Y %H:%M") if p.submission_deadline else "",
        # Phase 19: delivery location
        "delivery_location": p.delivery_location or "",
        # Phase 19: agreement text from subsidy
        "subsidy_agreement_text": (subsidy.agreement_text if (subsidy and subsidy.agreement_text) else ""),
        # Третьи лица
        "third_party_involved": bool(p.third_party_involved),
        # НДС
        "vat_applicable":        vat_app,
        "vat_rate":              vat_rate_val,
        "vat_amount_num":        _fmt_money_plain(vat_amount_val),
        "vat_amount_words":      _rubles_to_words(vat_amount_val),
        "vat_exemption_article": p.vat_exemption_article or "",
        "vat_info_line":         vat_info_line,
        # Цена прописью
        "contract_price_num":   _fmt_money_plain(p.contract_price),
        "contract_price_words": _rubles_to_words(p.contract_price),
        # Phase 23: service_subject alias (same as subject but clearer name in services template)
        "service_subject": p.subject or "",
        # Phase 23.1: subject_kind for universal contract.docx auto-switch
        "subject_kind": subject_kind,
    }

    # Phase 26-V: родительный падеж для инициатора и ответственного
    context["initiator_name_gen"] = _to_gen_fio(context.get("initiator_name", ""))
    context["initiator_position_gen"] = _to_gen_phrase(context.get("initiator_role", ""))
    context["responsible_name_gen"] = _to_gen_fio(resolved_responsible)
    context["responsible_position_gen"] = _to_gen_phrase(p.responsible_position or "" if hasattr(p, "responsible_position") else "")

    # ── Phase 23: Заказчик (Customer = Organization владелец субсидии + linked Contractor) ──
    def _g(*sources, default=""):
        """Coalesce — return first non-empty value."""
        for s in sources:
            if s:
                return s
        return default

    cust_signatory_full = _g(
        customer_org.signatory if customer_org else None,
        customer_ctr.signatory if customer_ctr else None,
    )
    cust_sig = _signatory_split(cust_signatory_full)
    cust_signatory_basis = _g(
        customer_ctr.signatory_basis if customer_ctr else None,
        "Устава",
    )

    context.update({
        "customer_name":         _g(customer_org.name if customer_org else None,
                                    customer_ctr.name if customer_ctr else None),
        "customer_full_name":    _g(customer_org.full_name if customer_org else None,
                                    customer_ctr.name if customer_ctr else None,
                                    customer_org.name if customer_org else None),
        "customer_short_name":   _short_name(_g(customer_org.name if customer_org else None,
                                                 customer_ctr.name if customer_ctr else None)) or "",
        "customer_address":      _g(customer_org.address if customer_org else None,
                                    customer_ctr.address if customer_ctr else None),
        "customer_postal_address": _g(customer_ctr.postal_address if customer_ctr else None,
                                      customer_org.address if customer_org else None),
        "customer_inn":          _clean_id(_g(customer_org.inn if customer_org else None,
                                              customer_ctr.inn if customer_ctr else None)),
        "customer_kpp":          _clean_id(_g(customer_org.kpp if customer_org else None,
                                              customer_ctr.kpp if customer_ctr else None)),
        "customer_ogrn":         _g(customer_org.ogrn if customer_org else None,
                                    customer_ctr.ogrn if customer_ctr else None),
        "customer_bank_name":    _g(customer_ctr.bank_name if customer_ctr else None),
        "customer_settlement_account":    _g(customer_ctr.settlement_account if customer_ctr else None),
        "customer_correspondent_account": _g(customer_ctr.correspondent_account if customer_ctr else None),
        "customer_bik":          _g(customer_ctr.bik if customer_ctr else None),
        "customer_phone":        _g(customer_ctr.phone if customer_ctr else None),
        "customer_email":        _g(customer_ctr.email if customer_ctr else None),
        # Подписант Заказчика
        "customer_signatory":                cust_signatory_full,
        "customer_signatory_position":       cust_sig["position"],
        "customer_signatory_name":           cust_sig["name_full"],
        "customer_signatory_name_genitive":  cust_sig["name_genitive"],
        "customer_signatory_initials":       cust_sig["name_initials"],
        "customer_signatory_basis":          cust_signatory_basis,
        # Город заключения (default Москва; будущая настройка per-org)
        "contract_city": "Москва",
    })

    # Phase 23: расширенные поля подписанта Исполнителя (name_genitive, initials, ogrnip)
    ctr_sig = _signatory_split(c.signatory if c else "")
    context.update({
        "contractor_signatory_name":          ctr_sig["name_full"],
        "contractor_signatory_name_genitive": ctr_sig["name_genitive"],
        "contractor_signatory_initials":      ctr_sig["name_initials"],
        "contractor_ogrnip":                  (c.ogrn or "") if (c and (c.org_type or "").lower().startswith("ип")) else "",
        # contractor_full_name — полное официальное название (fallback на name)
        "contractor_full_name":               (c.full_name or c.name or "") if c else "",
    })

    # Phase 27.1 CD-5: contract_items loop context (+ D-08 fallback on purchase_items)
    # Phase 26-U: wrap pre-render context building — any exception → structured DOCUMENT_GENERATION_FAILED
    try:
        ci_ctx = await _build_contract_items_context(p, db)
        context.update(ci_ctx)

        # Phase 26-R: receipts images for advance reports' service note
        if p.purchase_method == "advance":
            import tempfile as _tempfile
            from app.models.purchase_receipt import PurchaseReceipt as _PurchaseReceipt
            from app.routers.purchase_receipts import _render_receipt_png as _rrpng
            _receipts_q = await db.execute(
                select(_PurchaseReceipt)
                .where(_PurchaseReceipt.purchase_id == p.id)
                .order_by(_PurchaseReceipt.id.asc())
            )
            _receipts = _receipts_q.scalars().all()
            receipt_images = []
            for _r in _receipts:
                try:
                    _png_bytes = _rrpng(_r)
                    _tmp = _tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    _tmp.write(_png_bytes)
                    _tmp.close()
                    receipt_images.append(InlineImage(tpl, _tmp.name, width=_Cm(6.5)))
                except Exception as _re:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(f"render receipt {_r.id} skipped: {_re}")
            context["receipts"] = receipt_images
            context["receipt_images"] = receipt_images  # alias
            # Phase 26-LL: chunked в пары для таблицы 2 колонки в шаблоне СЗ
            receipt_pairs = []
            for _i in range(0, len(receipt_images), 2):
                _left = receipt_images[_i]
                _right = receipt_images[_i + 1] if _i + 1 < len(receipt_images) else None
                receipt_pairs.append({'left': _left, 'right': _right})
            context["receipt_pairs"] = receipt_pairs
            # Phase 26-RR: split на 2 потока для статичной таблицы 1×2 в шаблоне.
            # left_receipts = чётные позиции (1,3,5...), right_receipts = нечётные (2,4,6...)
            # → 2 колонки чередуются по порядку загрузки.
            context["left_receipts"] = receipt_images[::2]
            context["right_receipts"] = receipt_images[1::2]
        else:
            context["receipts"] = []
            context["receipt_images"] = []
            context["receipt_pairs"] = []
            context["left_receipts"] = []
            context["right_receipts"] = []
    except HTTPException:
        raise
    except Exception as _ctx_exc:
        import traceback as _tb
        logger.exception("Document context build failed (pre-render) for purchase %s, doc_type=%s", pid, doc_type)
        _err_class = type(_ctx_exc).__name__
        _err_msg = str(_ctx_exc)
        _err_tb = "".join(_tb.format_exception(type(_ctx_exc), _ctx_exc, _ctx_exc.__traceback__))[:4000]
        raise HTTPException(500, detail={
            "code": "DOCUMENT_GENERATION_FAILED",
            "message": f"Не удалось сформировать данные для «{doc_type}»: {_err_class}",
            "doc_type": doc_type,
            "purchase_id": pid,
            "error_class": _err_class,
            "error_raw": _err_msg,
            "traceback": _err_tb,
            "hint": (
                "Ошибка при сборке контекста шаблона (до рендеринга). "
                "Возможные причины: ошибка загрузки чеков/изображений, "
                "проблема с данными закупки (FK, пустые обязательные поля), "
                "отсутствующая зависимость (PIL, qrcode). "
                "Передайте администратору error_class + traceback."
            ),
        })

    try:
        tpl.render(context)
    except Exception as render_err:
        # phase26-nn: auto-fallback на базовый шаблон если кастомный из БД сломан.
        # Lessons.md (2026-05-15): кастомные шаблоны с {% tr %} вне таблицы или
        # повреждённой структурой валят TemplateSyntaxError → user видит белый экран.
        # Безопаснее упасть на базовый из репо и предупредить.
        is_custom_template = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))
        if is_custom_template:
            base_path = os.path.join(TEMPLATES_DIR, f"{doc_type}.docx")
            if os.path.exists(base_path) and base_path != template_path:
                import logging
                logging.getLogger(__name__).warning(
                    f"Custom template {template_path} render failed ({type(render_err).__name__}: {render_err}). "
                    f"Falling back to base template {base_path}."
                )
                tpl = DocxTemplate(base_path)
                template_path = base_path
                tpl.render(context)
            else:
                raise
        else:
            raise

    try:
        # Post-process: fix approvers table if docxtpl loop didn't render all rows
        if doc_type == "approval_sheet" and len(approvers_list) > 0:
            from docx import Document as _DocxDoc
            from docx.shared import Pt
            from copy import deepcopy
            from lxml import etree

            _buf = BytesIO()
            tpl.save(_buf)
            _buf.seek(0)
            _doc = _DocxDoc(_buf)

            # Find the approvers table (has header row with "Должность" or "ФИО")
            target_table = None
            for _t in _doc.tables:
                hdr = " ".join(c.text.strip() for c in _t.rows[0].cells)
                if "Должность" in hdr or "ФИО" in hdr:
                    target_table = _t
                    break

            if target_table:
                # Count current data rows (skip header)
                current_data_rows = len(target_table.rows) - 1
                needed = len(approvers_list)

                ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

                def _set_cell_text(cell_el, text):
                    """Replace all cell content with plain text."""
                    for p_el in list(cell_el.findall(f'{ns}p')):
                        cell_el.remove(p_el)
                    p = etree.SubElement(cell_el, f'{ns}p')
                    r = etree.SubElement(p, f'{ns}r')
                    t = etree.SubElement(r, f'{ns}t')
                    t.text = text or ""

                def _set_cell_two_lines(cell_el, line1, line2):
                    """Replace cell content with two paragraphs."""
                    for p_el in list(cell_el.findall(f'{ns}p')):
                        cell_el.remove(p_el)
                    p1 = etree.SubElement(cell_el, f'{ns}p')
                    r1 = etree.SubElement(p1, f'{ns}r')
                    t1 = etree.SubElement(r1, f'{ns}t')
                    t1.text = line1 or ""
                    p2 = etree.SubElement(cell_el, f'{ns}p')
                    r2 = etree.SubElement(p2, f'{ns}r')
                    t2 = etree.SubElement(r2, f'{ns}t')
                    t2.text = line2 or ""

                if current_data_rows < needed:
                    # Rebuild table: template loop didn't render all rows
                    template_row_el = target_table.rows[1]._tr
                    for row in list(target_table.rows[1:]):
                        target_table._tbl.remove(row._tr)
                    for a in approvers_list:
                        new_tr = deepcopy(template_row_el)
                        cells = new_tr.findall(f'.//{ns}tc')
                        if len(cells) >= 4:
                            _set_cell_text(cells[0], str(a.get("num", "")))
                            _set_cell_two_lines(cells[1], a.get("role_name", ""), a.get("full_name", ""))
                            _set_cell_text(cells[2], "")
                            _set_cell_text(cells[3], a.get("note", ""))
                        target_table._tbl.append(new_tr)
                else:
                    # Rows match — patch note/FEO into last column of each data row
                    for idx, a in enumerate(approvers_list):
                        row_idx = idx + 1  # skip header
                        if row_idx >= len(target_table.rows):
                            break
                        row_el = target_table.rows[row_idx]._tr
                        cells = row_el.findall(f'.//{ns}tc')
                        note_val = a.get("note", "")
                        if note_val and len(cells) >= 4:
                            _set_cell_text(cells[-1], note_val)

                buf = BytesIO()
                _doc.save(buf)
                buf.seek(0)
            else:
                buf = BytesIO()
                tpl.save(buf)
                buf.seek(0)
        else:
            buf = BytesIO()
            tpl.save(buf)
            buf.seek(0)
    except Exception as e:
        logger.exception("Document generation error for purchase %s, doc_type=%s, template=%s", pid, doc_type, template_path)

        # Phase 23.2: human-friendly error explanations for Jinja/docxtpl errors
        import re as _re
        err_class = type(e).__name__
        err_msg = str(e)
        template_name = os.path.basename(template_path) if template_path else f"{doc_type}.docx"
        is_custom = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))

        detail = {
            "code": "TEMPLATE_RENDER_ERROR",
            "message": f"Не удалось сгенерировать «{template_name}»",
            "template": template_name,
            "template_source": "Шаблон субсидии (загруженный пользователем)" if is_custom else "Глобальный шаблон",
            "error_class": err_class,
            "error_raw": err_msg,
            "hint": None,
        }

        # Pattern: Jinja2 UndefinedError ('X' is undefined)
        m = _re.match(r"'([a-zA-Z_][a-zA-Z0-9_]*)' is undefined", err_msg)
        if m:
            var_name = m.group(1)
            detail["message"] = f"В шаблоне «{template_name}» используется переменная {{{{{var_name}.…}}}} вне цикла"
            loop_hints = {
                "a": "{% tr for a in approvers %}…{{a.full_name}}…{% tr endfor %}  — переменная для согласующих (approval_sheet, лист согласования)",
                "item": "{% tr for item in items %}…{{item.name}}…{% tr endfor %}  — переменная для позиций закупки",
            }
            if var_name in loop_hints:
                detail["hint"] = (
                    f"Переменная «{var_name}» доступна только внутри цикла. "
                    f"Оберните строки/ячейки таблицы в:\n  {loop_hints[var_name]}\n\n"
                    f"Либо удалите кастомный шаблон в UI «Субсидии → Шаблоны → {template_name} → 🗑» и используйте глобальный."
                )
            else:
                detail["hint"] = (
                    f"В словаре переменных нет «{var_name}». Возможно, переменная переименована или удалена. "
                    f"См. справочник «Руководство по переменным» в Subsidies → Шаблоны."
                )

        # Pattern: 'X' has no attribute 'Y'
        m2 = _re.match(r"'(\w+)' (?:object )?has no attribute '(\w+)'", err_msg)
        if not m and m2:
            obj_name = m2.group(1)
            attr = m2.group(2)
            detail["message"] = f"В шаблоне «{template_name}» используется {{{{{obj_name}.{attr}}}}} но поле «{attr}» отсутствует"
            detail["hint"] = (
                f"Возможные причины:\n"
                f"• опечатка в имени переменной — см. «Руководство по переменным»\n"
                f"• данные ещё не заполнены в закупке (например, попытка использовать {{{{{obj_name}.{attr}}}}} когда поле пустое)"
            )

        # Pattern: TemplateSyntaxError
        if err_class == "TemplateSyntaxError":
            detail["message"] = f"Синтаксическая ошибка в шаблоне «{template_name}»: {err_msg}"
            detail["hint"] = (
                "Проверьте парные теги в Word: `{% if ... %}` ↔ `{% endif %}`, "
                "`{% for ... %}` ↔ `{% endfor %}`. Откройте шаблон в Word и убедитесь, "
                "что все условные блоки закрыты."
            )

        # Pattern: file not found / permission
        if isinstance(e, FileNotFoundError) or "no such file" in err_msg.lower():
            detail["message"] = f"Файл шаблона не найден: {template_name}"
            detail["hint"] = "Загрузите шаблон через UI «Субсидии → Шаблоны → Загрузить свой шаблон»."

        raise HTTPException(500, detail=detail)

    # For contract docs: append ТЗ table with items
    if doc_type == "contract" and items_list:
        try:
            from docx import Document as _DocxDoc
            from docx.shared import Pt, Cm, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement

            doc = _DocxDoc(buf)

            # Add page break before ТЗ
            doc.add_page_break()

            # Title
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = title_para.add_run("ТЕХНИЧЕСКОЕ ЗАДАНИЕ")
            run.bold = True
            run.font.size = Pt(12)

            subtitle = doc.add_paragraph()
            subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
            subtitle.add_run(f"(Приложение к договору № {p.contract_number or '___'} от {_fmt_date(p.contract_date) or '__.__.____'})")

            doc.add_paragraph()  # spacer

            # Table with columns: №, Фото, Наименование и описание, Кол-во, Ед., Цена ед., Сумма
            table = doc.add_table(rows=1, cols=7)
            table.style = 'Table Grid'

            # Header row
            hdr_cells = table.rows[0].cells
            headers_tz = ["№", "Фото", "Наименование и описание", "Кол-во", "Ед.", "Цена ед., ₽", "Сумма, ₽"]
            col_widths_cm = [1.0, 2.5, 8.0, 1.8, 1.5, 2.8, 2.8]
            for i, (hdr_cell, hdr_text, w) in enumerate(zip(hdr_cells, headers_tz, col_widths_cm)):
                hdr_cell.width = Cm(w)
                para = hdr_cell.paragraphs[0]
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = para.add_run(hdr_text)
                run.bold = True
                run.font.size = Pt(9)
                # Blue background
                tc = hdr_cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:fill'), '1E40AF')
                shd.set(qn('w:color'), 'FFFFFF')
                shd.set(qn('w:val'), 'clear')
                tcPr.append(shd)
                # White font
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

            # Data rows
            total_sum = 0.0
            for item_data in items_list:
                row_cells = table.add_row().cells
                row_cells[0].text = str(item_data["num"])
                row_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                # Photo cell: leave empty
                row_cells[1].text = ""
                # Name + description
                name_cell = row_cells[2]
                name_para = name_cell.paragraphs[0]
                name_run = name_para.add_run(str(item_data["name"]))
                name_run.bold = True
                name_run.font.size = Pt(9)
                if item_data.get("description"):
                    desc_para = name_cell.add_paragraph()
                    desc_run = desc_para.add_run(str(item_data["description"]))
                    desc_run.font.size = Pt(8)
                    desc_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

                qty_val = item_data.get("quantity", "")
                row_cells[3].text = str(qty_val) if qty_val != "" else "—"
                row_cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                row_cells[4].text = str(item_data.get("unit", "") or "—")
                row_cells[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                row_cells[5].text = str(item_data.get("unit_price", "") or "—")
                row_cells[5].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                row_cells[6].text = str(item_data.get("total_price", "") or "—")
                row_cells[6].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

                # Font size for all data cells
                for cell in row_cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            if not run.font.size:
                                run.font.size = Pt(9)

                try:
                    price_str = str(item_data.get("total_price", "")).replace(" ", "").replace(",", ".").replace("₽", "").strip()
                    total_sum += float(price_str) if price_str else 0
                except Exception:
                    pass

            # Total row
            total_row_cells = table.add_row().cells
            # Merge cells 0-5
            total_row_cells[5].merge(total_row_cells[0])
            merged_para = total_row_cells[0].paragraphs[0]
            merged_run = merged_para.add_run("НМЦК итого:")
            merged_run.bold = True
            merged_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            total_row_cells[6].text = _fmt_money_plain(total_sum)
            if total_row_cells[6].paragraphs[0].runs:
                total_row_cells[6].paragraphs[0].runs[0].bold = True
            total_row_cells[6].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

            # Save back to buf
            buf2 = BytesIO()
            doc.save(buf2)
            buf2.seek(0)
            buf = buf2
        except Exception as tz_err:
            # Don't fail the whole request if ТЗ append fails — just log
            import traceback
            print(f"ТЗ append error: {tz_err}\n{traceback.format_exc()}")

    # ── Phase 19.06: merge with secondary doc ──────────────────────────────
    # When ?merge=<doc_type> is passed, render the secondary template against
    # the same context and append its paragraphs/tables after a page break.
    if merge and merge in DOC_TYPES and merge != doc_type:
        try:
            from docxtpl import DocxTemplate as _Tpl
            from docx import Document as _Docx
            from copy import deepcopy

            secondary_file, secondary_base = DOC_TYPES[merge]
            secondary_path = os.path.join(TEMPLATES_DIR, secondary_file)
            # subsidy override for secondary
            if p.subsidy_id:
                sub_override = os.path.join(
                    SUBSIDY_TEMPLATES_DIR, "subsidies", str(p.subsidy_id), f"{merge}.docx"
                )
                if os.path.exists(sub_override):
                    secondary_path = sub_override
            # fallback if the dedicated secondary file is missing
            if not os.path.exists(secondary_path):
                fb = DOC_TYPE_FALLBACK_FILES.get(merge)
                if fb:
                    fb_path = os.path.join(TEMPLATES_DIR, fb)
                    if os.path.exists(fb_path):
                        secondary_path = fb_path

            if os.path.exists(secondary_path):
                sec_tpl = _Tpl(secondary_path)
                sec_tpl.render(context)
                sec_buf = BytesIO()
                sec_tpl.save(sec_buf)
                sec_buf.seek(0)

                # Append secondary into primary
                buf.seek(0)
                main_doc = _Docx(buf)
                sec_doc = _Docx(sec_buf)

                main_doc.add_page_break()
                # Copy every top-level element (paragraphs, tables, etc.) from body
                for element in sec_doc.element.body:
                    main_doc.element.body.append(deepcopy(element))

                merged_buf = BytesIO()
                main_doc.save(merged_buf)
                merged_buf.seek(0)
                buf = merged_buf
                # Update filename to reflect merge
                filename_base = f"{filename_base}_i_{secondary_base}"
        except Exception as merge_err:
            import traceback
            print(f"Doc merge error ({doc_type} + {merge}): {merge_err}\n{traceback.format_exc()}")

    safe_name = f"{filename_base}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    encoded_name = quote(safe_name, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


# ── KP xlsx export ───────────────────────────────────────────────────────────

@guide_router.get("/purchases/{pid}/kp-xlsx")
async def download_kp_xlsx(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate xlsx with purchase items (for КП request attachment)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(500, "openpyxl не установлен")

    result = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items).selectinload(PurchaseItem.product))
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    wb = Workbook()
    ws = wb.active
    ws.title = "Перечень товаров"

    # Header style
    header_fill = PatternFill("solid", fgColor="1E40AF")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = ["№", "Фото", "Наименование и описание", "Кол-во", "Ед.", "Цена ед., ₽", "Сумма, ₽"]
    col_widths = [5, 12, 50, 10, 8, 16, 16]

    for col, (h, w) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.row_dimensions[1].height = 32

    # Data rows
    data_align = Alignment(vertical="center", wrap_text=True)
    data_align_center = Alignment(horizontal="center", vertical="center")
    data_align_right = Alignment(horizontal="right", vertical="center")

    items = [i for i in (p.items or []) if i.item_name and i.item_name.strip()]
    for idx, item in enumerate(items, start=1):
        row = idx + 1
        description = ""
        if item.product:
            description = item.product.description or ""

        full_name = item.item_name or ""
        if description:
            full_name = full_name + "\n" + description

        ws.cell(row=row, column=1, value=idx).alignment = data_align_center
        ws.cell(row=row, column=2, value="").alignment = data_align_center  # Фото — пусто
        ws.cell(row=row, column=3, value=full_name).alignment = data_align
        ws.cell(row=row, column=4, value=float(item.quantity) if item.quantity else "").alignment = data_align_center
        ws.cell(row=row, column=5, value=item.unit or "").alignment = data_align_center
        price_cell = ws.cell(row=row, column=6, value=float(item.unit_price) if item.unit_price else "")
        price_cell.alignment = data_align_right
        if item.unit_price:
            price_cell.number_format = '# ##0.00'
        total_cell = ws.cell(row=row, column=7, value=float(item.total_price) if item.total_price else "")
        total_cell.alignment = data_align_right
        if item.total_price:
            total_cell.number_format = '# ##0.00'

        ws.row_dimensions[row].height = 40 if description else 20

        for col in range(1, 8):
            ws.cell(row=row, column=col).border = border

    # Total row
    total_row = len(items) + 2
    total_nmck = sum(float(i.total_price or 0) for i in items)
    ws.cell(row=total_row, column=6, value="НМЦК итого:").font = Font(bold=True)
    ws.cell(row=total_row, column=6).alignment = data_align_right
    total_cell = ws.cell(row=total_row, column=7, value=total_nmck)
    total_cell.font = Font(bold=True)
    total_cell.number_format = '# ##0.00'
    total_cell.alignment = data_align_right

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = f"KP_items_{p.purchase_number or pid}.xlsx"
    from urllib.parse import quote as _quote
    encoded = _quote(fname, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    )


# ── Template markup guide ────────────────────────────────────────────────────

TEMPLATE_VARIABLES = [
    # (template_var, description, example_template, example_result)
    # ── Выбор шаблона ──
    ("", "ВЫБОР ШАБЛОНА", "", ""),
    ("", "  contract.docx — универсальный договор (Phase 23.1): subject_kind определяется автоматически.", "", ""),
    ("", "  Все позиции 'услуга' → договор оказания услуг; иначе → договор поставки.", "", ""),
    ("{{subject_kind}}", "Тип договора (auto): вычисляется из позиций закупки", "{{subject_kind}}", "services"),
    # ── Закупка ──
    ("", "ЗАКУПКА", "", ""),
    ("{{purchase_number}}", "Номер закупки", "{{purchase_number}}", "42"),
    ("{{registry_number}}", "Реестровый номер", "{{registry_number}}", "РЕЕ-2026-00042"),
    ("{{subject}}", "Предмет закупки", "{{subject}}", "Оказание услуг связи"),
    ("{{status}}", "Статус", "{{status}}", "contracted"),
    ("{{purchase_method}}", "Способ закупки", "{{purchase_method}}", "Единственный поставщик"),
    ("{{purchase_basis}}", "Основание", "{{purchase_basis}}", "план-график"),
    ("{{contract_type}}", "Тип договора", "{{contract_type}}", "Единственный поставщик"),
    ("{{responsible_person}}", "ФИО ответственного исполнителя", "{{responsible_person}}", "Иванов Иван Иванович"),
    ("{{feo_category_name}}", "Категория ФЭО (только выбранный узел)", "{{feo_category_name}}", "Услуги связи"),
    ("{{feo_path}}", "Полный путь ФЭО", "{{feo_path}}", "1. Адм → 1.2 IT → 1.2.3 Услуги связи"),
    ("{{feo_level_1}}", "ФЭО уровень 1 — Направление расходов", "{{feo_level_1}}", "1. Административные расходы"),
    ("{{feo_level_2}}", "ФЭО уровень 2 — Тип расходов", "{{feo_level_2}}", "1.2 IT и коммуникации"),
    ("{{feo_level_3}}", "ФЭО уровень 3 — Конкретизированная категория", "{{feo_level_3}}", "1.2.3 Услуги связи"),
    # ── Субсидия и мероприятие ──
    ("", "СУБСИДИЯ И МЕРОПРИЯТИЕ", "", ""),
    ("{{subsidy_name}}", "Наименование субсидии", "{{subsidy_name}}", "ФАДМ-2026"),
    ("{{subsidy_year}}", "Год субсидии", "{{subsidy_year}}", "2026"),
    ("{{subsidy_budget}}", "Бюджет субсидии", "{{subsidy_budget}}", "15 500 000,00 ₽"),
    ("{{event_name}}", "Название мероприятия", "{{event_name}}", "Сборы спасателей"),
    # ── Заказчик (Phase 23) ──
    ("", "ЗАКАЗЧИК", "", ""),
    ("{{customer_name}}", "Краткое название организации Заказчика", "{{customer_name}}", "АНО «ВСКС»"),
    ("{{customer_full_name}}", "Полное наименование", "{{customer_full_name}}", "Автономная некоммерческая организация «ВСКС»"),
    ("{{customer_short_name}}", "Из кавычек: «...»", "{{customer_short_name}}", "ВСКС"),
    ("{{customer_address}}", "Юридический адрес", "{{customer_address}}", "г. Москва, ул. Ленина, д. 1"),
    ("{{customer_postal_address}}", "Почтовый адрес", "{{customer_postal_address}}", "г. Москва, ул. Ленина, д. 1"),
    ("{{customer_inn}}", "ИНН Заказчика", "{{customer_inn}}", "7700000001"),
    ("{{customer_kpp}}", "КПП Заказчика", "{{customer_kpp}}", "770001001"),
    ("{{customer_ogrn}}", "ОГРН Заказчика", "{{customer_ogrn}}", "1027700000001"),
    ("{{customer_bank_name}}", "Банк Заказчика", "{{customer_bank_name}}", "ПАО «Сбербанк»"),
    ("{{customer_settlement_account}}", "Расчётный счёт Заказчика", "{{customer_settlement_account}}", "40703810400000000001"),
    ("{{customer_correspondent_account}}", "Корр. счёт Заказчика", "{{customer_correspondent_account}}", "30101810400000000225"),
    ("{{customer_bik}}", "БИК банка Заказчика", "{{customer_bik}}", "044525225"),
    ("{{customer_phone}}", "Телефон", "{{customer_phone}}", "+7 (495) 000-00-01"),
    ("{{customer_email}}", "Email", "{{customer_email}}", "info@vsks.ru"),
    ("{{customer_signatory}}", "Полная строка подписанта", "{{customer_signatory}}", "Президент Козеев Е.В."),
    ("{{customer_signatory_position}}", "Должность подписанта", "{{customer_signatory_position}}", "Президент"),
    ("{{customer_signatory_name}}", "ФИО подписанта (им.падеж)", "{{customer_signatory_name}}", "Козеев Евгений Викторович"),
    ("{{customer_signatory_name_genitive}}", "ФИО в род.падеже", "{{customer_signatory_name_genitive}}", "Козеева Евгения Викторовича"),
    ("{{customer_signatory_initials}}", "Фамилия + инициалы", "{{customer_signatory_initials}}", "Козеев Е.В."),
    ("{{customer_signatory_basis}}", "Основание полномочий", "{{customer_signatory_basis}}", "Устава"),
    ("{{contract_city}}", "Город заключения договора", "{{contract_city}}", "Москва"),
    # ── Контрагент ──
    ("", "КОНТРАГЕНТ (ИСПОЛНИТЕЛЬ)", "", ""),
    ("{{contractor_name}}", "Полное наименование контрагента", "{{contractor_name}}", "ООО «Ромашка»"),
    ("{{contractor_short_name}}", "Краткое наименование", "{{contractor_short_name}}", "Ромашка"),
    ("{{contractor_org_type}}", "Тип организации", "{{contractor_org_type}}", "Юр.лицо"),
    ("{{contractor_inn}}", "ИНН контрагента", "{{contractor_inn}}", "7701234567"),
    ("{{contractor_kpp}}", "КПП контрагента", "{{contractor_kpp}}", "770101001"),
    ("{{contractor_ogrn}}", "ОГРН / ОГРНИП", "{{contractor_ogrn}}", "1027701234567"),
    ("{{contractor_address}}", "Юридический адрес", "{{contractor_address}}", "г. Москва, ул. Садовая, д. 5"),
    ("{{contractor_postal_address}}", "Почтовый адрес", "{{contractor_postal_address}}", "г. Москва, ул. Садовая, д. 5"),
    ("{{contractor_phone}}", "Телефон", "{{contractor_phone}}", "+7 (495) 111-22-33"),
    ("{{contractor_email}}", "E-mail", "{{contractor_email}}", "info@romashka.ru"),
    ("{{contractor_signatory}}", "ФИО подписанта", "{{contractor_signatory}}", "Сидоров Пётр Павлович"),
    ("{{contractor_signatory_basis}}", "Основание полномочий", "{{contractor_signatory_basis}}", "Устава"),
    ("{{contractor_signatory_position}}", "Должность подписанта", "{{contractor_signatory_position}}", "Директор"),
    ("{{contractor_signatory_name}}", "ФИО в им.падеже", "{{contractor_signatory_name}}", "Сидоров Пётр Павлович"),
    ("{{contractor_signatory_name_genitive}}", "ФИО в род.падеже", "{{contractor_signatory_name_genitive}}", "Сидорова Петра Павловича"),
    ("{{contractor_signatory_initials}}", "Фамилия + инициалы", "{{contractor_signatory_initials}}", "Сидоров П.П."),
    ("{{contractor_signatory_line}}", "ФИО + основание", "{{contractor_signatory_line}}", "Сидоров П.П., действующий на основании Устава"),
    ("{{contractor_ogrnip}}", "ОГРНИП (только для ИП)", "{{contractor_ogrnip}}", "304770000000001"),
    ("{{service_subject}}", "Предмет услуг (синоним subject)", "{{service_subject}}", "Оказание услуг связи"),
    ("{{contractor_settlement_account}}", "Расчётный счёт", "{{contractor_settlement_account}}", "40702810400000000002"),
    ("{{contractor_bank_name}}", "Наименование банка", "{{contractor_bank_name}}", "ПАО «Сбербанк»"),
    ("{{contractor_bank_details}}", "Реквизиты банка", "{{contractor_bank_details}}", "БИК 044525225, к/с 30101810400000000225"),
    ("{{contractor_bik}}", "БИК банка", "{{contractor_bik}}", "044525225"),
    ("{{contractor_correspondent_account}}", "Корреспондентский счёт", "{{contractor_correspondent_account}}", "30101810400000000225"),
    # ── Финансы ──
    ("", "ФИНАНСЫ", "", ""),
    ("{{total_nmcd}}", "НМЦД — начальная максимальная цена договора", "{{total_nmcd}}", "130 000,00 ₽"),
    ("{{total_nmck}}", "НМЦК (устаревшее)", "{{total_nmck}}", "130 000,00 ₽"),
    ("{{nmck}}", "НМЦК (синоним total_nmck)", "{{nmck}}", "130 000,00 ₽"),
    ("{{contract_price}}", "Цена договора", "{{contract_price}}", "130 000,00 ₽"),
    ("{{contract_price_num}}", "Цена без валюты", "{{contract_price_num}}", "130 000,00"),
    ("{{contract_price_words}}", "Цена прописью", "{{contract_price_words}}", "сто тридцать тысяч рублей 00 копеек"),
    ("{{economy}}", "Экономия", "{{economy}}", "5 000,00 ₽"),
    ("{{price_increase}}", "Увеличение цены", "{{price_increase}}", "0,00 ₽"),
    # ── НДС ──
    ("", "НДС", "", ""),
    ("{{vat_applicable}}", "Облагается НДС", "{{vat_applicable}}", "true"),
    ("{{vat_rate}}", "Ставка НДС", "{{vat_rate}}", "20"),
    ("{{vat_amount_num}}", "Сумма НДС цифрами", "{{vat_amount_num}}", "21 666,67"),
    ("{{vat_amount_words}}", "Сумма НДС прописью", "{{vat_amount_words}}", "двадцать одна тысяча 666 руб. 67 коп."),
    ("{{vat_exemption_article}}", "Статья освобождения от НДС", "{{vat_exemption_article}}", "ст. 149 НК РФ"),
    ("{{vat_info_line}}", "Готовая строка НДС", "{{vat_info_line}}", "В том числе НДС 20%: 21 666,67 руб."),
    # ── Договор ──
    ("", "ДОГОВОР", "", ""),
    ("{{contract_number}}", "Номер договора", "{{contract_number}}", "2026/42"),
    ("{{contract_date}}", "Дата договора", "{{contract_date}}", "15.01.2026"),
    ("{{contract_date_day}}", "День", "{{contract_date_day}}", "15"),
    ("{{contract_date_month}}", "Месяц прописью", "{{contract_date_month}}", "января"),
    ("{{contract_date_year}}", "Год", "{{contract_date_year}}", "2026"),
    ("{{execution_term}}", "Срок исполнения", "{{execution_term}}", "28.02.2026"),
    ("{{execution_term_changed}}", "Изменённый срок", "{{execution_term_changed}}", "31.03.2026"),
    ("{{delivery_date}}", "Дата поставки", "{{delivery_date}}", "20.01.2026"),
    ("{{country_origin}}", "Страна происхождения", "{{country_origin}}", "Российская Федерация"),
    ("{{service_name}}", "Предмет (синоним subject)", "{{service_name}}", "Оказание услуг связи"),
    ("{{period_type}}", "Тип срока", "{{period_type}}", "date"),
    ("{{service_start_date}}", "Начало оказания услуг", "{{service_start_date}}", "15.01.2026"),
    ("{{service_end_date}}", "Конец оказания услуг", "{{service_end_date}}", "28.02.2026"),
    ("{{service_date}}", "Дата оказания (разовая)", "{{service_date}}", "20.01.2026"),
    ("{{third_party_involved}}", "Привлечение третьих лиц", "{{third_party_involved}}", "false"),
    # ── Phase 19: срок услуг расширенный ──
    ("", "СРОК УСЛУГ (Phase 19)", "", ""),
    ("{{service_term}}", "Готовая строка срока", "{{service_term}}", "с 15.01.2026 по 28.02.2026"),
    ("{{service_term_mode}}", "Режим срока", "{{service_term_mode}}", "range"),
    ("{{service_term_days}}", "Кол-во дней (для mode=duration)", "{{service_term_days}}", "30"),
    ("{{service_term_type}}", "Тип дней", "{{service_term_type}}", "calendar"),
    ("{{service_term_type_name}}", "Тип дней прописью", "{{service_term_type_name}}", "календарных"),
    ("{{service_deadline_date}}", "Срок \"до даты\"", "{{service_deadline_date}}", "28.02.2026"),
    # ── Phase 19: приём заявок ──
    ("", "ПРИЁМ ЗАЯВОК (Phase 19)", "", ""),
    ("{{submission_deadline_date}}", "Дата завершения приёма заявок", "{{submission_deadline_date}}", "10.01.2026"),
    ("{{submission_deadline_time}}", "Время завершения приёма заявок", "{{submission_deadline_time}}", "17:00"),
    ("{{submission_deadline_datetime}}", "Дата+время завершения", "{{submission_deadline_datetime}}", "10.01.2026 17:00"),
    # ── Phase 19: место доставки ──
    ("", "МЕСТО ДОСТАВКИ / ОКАЗАНИЯ УСЛУГ (Phase 19)", "", ""),
    ("{{delivery_location}}", "Место оказания услуг / доставки", "{{delivery_location}}", "г. Москва, ул. Ленина, д. 1"),
    # ── Phase 19: соглашение субсидии ──
    ("", "СОГЛАШЕНИЕ ПО СУБСИДИИ (Phase 19)", "", ""),
    ("{{subsidy_agreement_text}}", "Большой текст соглашения", "{{subsidy_agreement_text}}", "(многострочный текст)"),
    # ── Акт приёмки ──
    ("", "АКТ ПРИЁМКИ", "", ""),
    ("{{acceptance_doc_name}}", "Наименование акта", "{{acceptance_doc_name}}", "АКТ"),
    ("{{acceptance_doc_number}}", "Номер акта", "{{acceptance_doc_number}}", "001"),
    ("{{acceptance_doc_date}}", "Дата акта", "{{acceptance_doc_date}}", "28.02.2026"),
    ("{{acceptance_doc_amount}}", "Сумма акта", "{{acceptance_doc_amount}}", "130 000,00"),
    # ── Платёж ──
    ("", "ПЛАТЁЖ", "", ""),
    ("{{payment_doc_number}}", "Номер платёжного поручения", "{{payment_doc_number}}", "П-00125"),
    ("{{payment_doc_date}}", "Дата ПП", "{{payment_doc_date}}", "05.03.2026"),
    ("{{payment_amount}}", "Сумма платежа", "{{payment_amount}}", "130 000,00"),
    ("{{payment_federal}}", "В т.ч. федеральный бюджет", "{{payment_federal}}", "100 000,00"),
    # ── Инициатор ──
    ("", "ИНИЦИАТОР (для служебных записок)", "", ""),
    ("{{initiator_name}}", "ФИО инициатора", "{{initiator_name}}", "Иванов И.И."),
    ("{{initiator_role}}", "Должность инициатора", "{{initiator_role}}", "начальник отдела"),
    ("{{initiator_dept}}", "Отдел инициатора (если несколько — первый)", "{{initiator_dept}}", "Отдел спасательных операций"),
    # ── Согласующие (цикл) ──
    ("", "СОГЛАСУЮЩИЕ (цикл для таблицы)", "", ""),
    ("{%tr for a in approvers %} ... {%tr endfor %}", "Цикл по согласующим (в строке таблицы)", "{%tr for a in approvers %}<строка>{%tr endfor %}", "повторяется по числу согласующих"),
    ("{{a.num}}", "Порядковый номер (1, 2, 3...)", "{{a.num}}", "1"),
    ("{{a.role_name}}", "Должность согласующего", "{{a.role_name}}", "начальник отдела"),
    ("{{a.full_name}}", "ФИО согласующего", "{{a.full_name}}", "Петров П.П."),
    ("{{a.signature_img}}", "Электронная подпись (картинка)", "{{a.signature_img}}", "(изображение подписи)"),
    ("{{a.decided_date}}", "Дата подписания", "{{a.decided_date}}", "12.05.2026"),
    ("{{a.note}}", "Примечание (путь ФЭО)", "{{a.note}}", "Согласовано"),
    # ── Позиции (цикл) ──
    ("", "ПОЗИЦИИ ЗАКУПКИ (цикл для таблицы)", "", ""),
    ("{%tr for item in items %} ... {%tr endfor %}", "Цикл по позициям (в строке таблицы)", "{%tr for item in items %}<строка>{%tr endfor %}", "повторяется по числу позиций"),
    ("{{item.num}}", "Порядковый номер", "{{item.num}}", "1"),
    ("{{item.name}}", "Наименование товара/услуги", "{{item.name}}", "Услуги мобильной связи"),
    ("{{item.description}}", "Описание (из карточки продукта)", "{{item.description}}", "Корпоративная SIM-карта"),
    ("{{item.type}}", "Тип (товар/услуга)", "{{item.type}}", "услуга"),
    ("{{item.quantity}}", "Количество", "{{item.quantity}}", "10"),
    ("{{item.unit}}", "Единица измерения", "{{item.unit}}", "шт."),
    ("{{item.unit_price}}", "Цена за единицу", "{{item.unit_price}}", "13 000,00"),
    ("{{item.total_price}}", "Сумма строки", "{{item.total_price}}", "130 000,00"),
    ("{{item.photo}}", "Фото товара (картинка)", "{{item.photo}}", "(изображение)"),
    ("{{items_count}}", "Общее количество позиций", "{{items_count}}", "3"),
    ("{{item_names}}", "Перечень названий через запятую", "{{item_names}}", "Услуги связи, Интернет, Хостинг"),
    # ── Чеки (авансовый отчёт) ──
    ("", "ЧЕКИ — АВАНСОВЫЙ ОТЧЁТ (только для закупок с purchase_method=advance)", "", ""),
    ("{{receipts}}", "Список InlineImage чеков по порядку загрузки — для авансовых отчётов", "{% for r in receipts %}{{ r }}{% endfor %}", "(изображения чеков)"),
    ("{{receipt_images}}", "Алиас receipts — список изображений чеков", "{% for img in receipt_images %}{{ img }}{% endfor %}", "(изображения чеков)"),
    # ── Родительный падеж (Phase 26-V) ──
    ("", "РОДИТЕЛЬНЫЙ ПАДЕЖ (Phase 26-V)", "", ""),
    ("{{initiator_name_gen}}", "ФИО инициатора в родительном падеже", "{{initiator_name_gen}}", "Иванова И.И."),
    ("{{initiator_position_gen}}", "Должность инициатора в родительном падеже", "{{initiator_position_gen}}", "начальника отдела"),
    ("{{responsible_name_gen}}", "ФИО ответственного в родительном падеже", "{{responsible_name_gen}}", "Петрова П.П."),
    ("{{responsible_position_gen}}", "Должность ответственного в родительном падеже", "{{responsible_position_gen}}", "главного специалиста"),
    ("{{a.full_name_gen}}", "ФИО согласующего в родительном падеже (внутри цикла)", "{{a.full_name_gen}}", "Сидорова С.С."),
    ("{{a.role_name_gen}}", "Должность согласующего в родительном падеже (внутри цикла)", "{{a.role_name_gen}}", "директора по правовым вопросам"),
    # ── Служебные ──
    ("", "СЛУЖЕБНЫЕ", "", ""),
    ("{{today}}", "Сегодняшняя дата", "{{today}}", "13.05.2026"),
    ("{{today_iso}}", "Дата ISO", "{{today_iso}}", "2026-05-13"),
]



@guide_router.get("/template-guide")
async def download_template_guide(
    current_user=Depends(get_current_user),
):
    """Download a .docx reference guide with all available template variables."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    doc.add_heading("Руководство по разметке шаблонов документов", 0)

    p = doc.add_paragraph(
        "Шаблоны документов используют синтаксис Jinja2 (docxtpl). "
        "Переменные заключаются в двойные фигурные скобки: {{variable}}. "
        "Для циклов используется синтаксис: {%tr for item in items %} ... {%tr endfor %}."
    )

    doc.add_heading("Доступные переменные", 1)

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Переменная"
    hdr[1].text = "Описание"
    hdr[2].text = "Пример записи"
    hdr[3].text = "Результат"
    for cell in hdr:
        for run in cell.paragraphs[0].runs:
            run.bold = True

    for var, desc, ex_t, ex_r in TEMPLATE_VARIABLES:
        if not var:
            # Section header row
            row = table.add_row().cells
            row[0].merge(row[3])
            p = row[0].paragraphs[0]
            run = p.add_run(desc)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
            continue
        row = table.add_row().cells
        row[0].text = var
        row[1].text = desc
        row[2].text = ex_t
        row[3].text = ex_r

    doc.add_heading("Примеры использования в шаблоне Word", 1)

    doc.add_heading("Таблица согласующих", 2)
    doc.add_paragraph(
        '{%tr for a in approvers %}\n'
        '| {{a.num}} | {{a.role_name}} | {{a.full_name}} | {{a.signature_img}} | {{a.decided_date}} |\n'
        '{%tr endfor %}'
    )

    doc.add_heading("Таблица позиций закупки", 2)
    doc.add_paragraph(
        '{%tr for item in items %}\n'
        '| {{item.num}} | {{item.name}} | {{item.quantity}} | {{item.unit}} | {{item.unit_price}} | {{item.total_price}} |\n'
        '{%tr endfor %}'
    )

    doc.add_heading("Уровни субсидии (ФЭО)", 2)
    doc.add_paragraph(
        "Вставьте одну из этих переменных в нужное место шаблона Word:\n\n"
        "  Полный путь одной строкой:\n"
        "    {{feo_path}}\n"
        "  → Пример: «Персонал → Зарплата → Основной ФОТ»\n\n"
        "  Отдельные уровни:\n"
        "    Направление: {{feo_level_1}}\n"
        "    Тип:         {{feo_level_2}}\n"
        "    Категория:   {{feo_level_3}}\n\n"
        "Если закупка без ФЭО-категорий — переменные будут пустыми.\n"
        "Если у субсидии только 1 уровень — feo_level_2 и feo_level_3 пустые."
    )

    doc.add_heading("Условные блоки (НДС)", 2)
    doc.add_paragraph(
        '{% if vat_applicable %}\n'
        'В том числе НДС {{vat_rate}}%: {{vat_amount_num}} руб.\n'
        '{% else %}\n'
        'НДС не облагается {{vat_exemption_article}}\n'
        '{% endif %}'
    )

    doc.add_heading("Частые ошибки", 1)
    doc.add_paragraph(
        "1. Русский текст внутри {{ }} — ошибка: {{ contract_date г. }}\n"
        "   Правильно: {{ contract_date }} г.\n\n"
        "2. Word разбивает переменную на фрагменты — удалите и наберите заново\n\n"
        "3. Пустое значение — поле не заполнено в карточке закупки"
    )

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''Template_Guide.docx"},
    )


@guide_router.get("/template-vars")
async def get_template_vars(current_user=Depends(get_current_user)):
    """Return all template variables with description, example template text, and example result."""
    result = []
    for entry in TEMPLATE_VARIABLES:
        var, desc, ex_t, ex_r = entry
        if not var:
            continue  # skip section headers
        result.append({
            "var": var,
            "description": desc,
            "example_template": ex_t,
            "example_result": ex_r,
        })
    return result
