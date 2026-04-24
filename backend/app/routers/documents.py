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

router = APIRouter(prefix="/api/purchases", tags=["documents"])
guide_router = APIRouter(prefix="/api/documents", tags=["documents"])

TEMPLATES_DIR = "/app/templates"
SUBSIDY_TEMPLATES_DIR = "/app/uploads/templates"

DOC_TYPES = {
    "service_note":          ("service_note.docx",          "SZ_Organizaciya"),
    "service_note_delivery": ("service_note_delivery.docx", "SZ_Vydacha"),
    "service_note_payment":  ("service_note_payment.docx",  "SZ_Oplata"),
    # Phase 19.05: dedicated SZ for procurement (distinct from generic service_note)
    "service_note_procurement": ("service_note_procurement.docx", "SZ_Zakupka"),
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
    "contract_fadm":         ("contract_fadm.docx",         "Contract_FADM"),
    "approval_sheet":        ("approval_sheet.docx",        "Approval_Sheet"),
    "order_purchase":        ("order_purchase.docx",        "Prikaz_zakupki"),
}

# Phase 19.05: fallback map — if a dedicated template file is missing,
# fall back to the legacy file so the endpoint still works before admins
# upload per-subsidy overrides.
DOC_TYPE_FALLBACK_FILES = {
    "service_note_procurement": "service_note.docx",
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
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
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

    # Load initiator if requested
    initiator = None
    if initiator_id:
        res = await db.execute(select(SubsidyApprover).where(SubsidyApprover.id == initiator_id))
        initiator = res.scalar_one_or_none()

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
        tpl = DocxTemplate(template_path)
    except Exception as e:
        raise HTTPException(500, f"Ошибка загрузки шаблона: {e}")

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
            "quantity": float(item.quantity) if item.quantity else "",
            "unit": item.unit or "",
            "unit_price": _fmt_money(item.unit_price),
            "total_price": _fmt_money(item.total_price),
            "photo": _resolve_photo(photo_url),
        })

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
        })

    c = p.contractor

    # Validate required fields for contract_fadm
    if doc_type == "contract_fadm":
        missing = _validate_contract_fields(p, c)
        if missing:
            raise HTTPException(
                422,
                f"Для генерации договора необходимо заполнить: {'; '.join(missing)}"
            )

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

    # VAT calculations
    vat_app = bool(p.vat_applicable)
    vat_rate_val = p.vat_rate or 20
    price_val = float(p.contract_price or 0)
    if vat_app and price_val:
        vat_amount_val = price_val * vat_rate_val / (100 + vat_rate_val)
    else:
        vat_amount_val = 0.0

    # НДС info for approval sheet
    if vat_app:
        vat_info_line = f"В том числе НДС {vat_rate_val}%: {_fmt_money_plain(vat_amount_val)} руб."
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
        # Акт приёмки
        "acceptance_doc_name": p.acceptance_doc_name or "",
        "acceptance_doc_number": p.acceptance_doc_number or "",
        "acceptance_doc_date": _fmt_date(p.acceptance_doc_date),
        "acceptance_doc_amount": _fmt_money(p.acceptance_doc_amount),
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
        "initiator_name": initiator.full_name if initiator else "",
        "initiator_role": initiator.role_name if initiator else "",
        # Мероприятие
        "event_name": event.name if event else "",
        # Тип договора
        "contract_type": {"single": "Единственный поставщик", "framework_cumulative": "Рамочный (накопительный)", "framework_with_amount": "Рамочный (с суммой)"}.get(p.purchase_contract_type or "", p.purchase_contract_type or ""),
        # Служебные
        "today": _fmt_date(date.today()),
        "today_iso": date.today().isoformat(),
        # ── Поля для contract_fadm шаблона ───────────────────────────────────
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
        # back to the legacy mapping (contract_date / execution_term) so old
        # contract_fadm templates keep rendering correctly.
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
    }

    try:
        tpl.render(context)

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
        raise HTTPException(500, f"Ошибка генерации документа: {e}")

    # For contract docs: append ТЗ table with items
    if doc_type in ("contract", "contract_fadm") and items_list:
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
    # ── Закупка ──
    ("", "ЗАКУПКА"),
    ("{{purchase_number}}", "Номер закупки (например: 42)"),
    ("{{registry_number}}", "Реестровый номер (например: РЕЕ-2026-00042)"),
    ("{{subject}}", "Предмет закупки"),
    ("{{status}}", "Статус (planned / confirmed / contracted / delivered / paid)"),
    ("{{purchase_method}}", "Способ закупки (Единственный поставщик / Конкурсная процедура / Авансовый отчёт)"),
    ("{{purchase_basis}}", "Основание (план-график / служебная записка)"),
    ("{{contract_type}}", "Тип договора (Единственный поставщик / Рамочный)"),
    ("{{responsible_person}}", "ФИО ответственного исполнителя"),
    ("{{feo_category_name}}", "Категория ФЭО (только выбранный узел)"),
    ("{{feo_path}}",    "Полный путь ФЭО: Направление → Тип → Категория"),
    ("{{feo_level_1}}", "ФЭО уровень 1 — Направление расходов"),
    ("{{feo_level_2}}", "ФЭО уровень 2 — Тип расходов"),
    ("{{feo_level_3}}", "ФЭО уровень 3 — Конкретизированная категория"),
    # ── Субсидия и мероприятие ──
    ("", "СУБСИДИЯ И МЕРОПРИЯТИЕ"),
    ("{{subsidy_name}}", "Наименование субсидии"),
    ("{{subsidy_year}}", "Год субсидии"),
    ("{{subsidy_budget}}", "Бюджет субсидии (например: 15 500 000,00 ₽)"),
    ("{{event_name}}", "Название мероприятия"),
    # ── Контрагент ──
    ("", "КОНТРАГЕНТ"),
    ("{{contractor_name}}", "Полное наименование контрагента"),
    ("{{contractor_short_name}}", "Краткое наименование (из кавычек или первое слово)"),
    ("{{contractor_org_type}}", "Тип организации (Юр.лицо / ИП / Самозанятый)"),
    ("{{contractor_inn}}", "ИНН контрагента"),
    ("{{contractor_kpp}}", "КПП контрагента"),
    ("{{contractor_ogrn}}", "ОГРН / ОГРНИП"),
    ("{{contractor_address}}", "Юридический адрес"),
    ("{{contractor_postal_address}}", "Почтовый адрес"),
    ("{{contractor_phone}}", "Телефон"),
    ("{{contractor_email}}", "E-mail"),
    ("{{contractor_signatory}}", "ФИО подписанта"),
    ("{{contractor_signatory_basis}}", "Основание полномочий (Устав / Доверенность №...)"),
    ("{{contractor_signatory_position}}", "Должность подписанта (Директор)"),
    ("{{contractor_signatory_line}}", "ФИО + основание (комбинированное)"),
    ("{{contractor_settlement_account}}", "Расчётный счёт"),
    ("{{contractor_bank_name}}", "Наименование банка"),
    ("{{contractor_bank_details}}", "Реквизиты банка"),
    ("{{contractor_bik}}", "БИК банка"),
    ("{{contractor_correspondent_account}}", "Корреспондентский счёт"),
    # ── Финансы ──
    ("", "ФИНАНСЫ"),
    ("{{total_nmcd}}", "НМЦД — начальная максимальная цена договора (рекомендуется)"),
    ("{{total_nmck}}", "НМЦК — устаревшее, используйте total_nmcd"),
    ("{{nmck}}", "НМЦК (синоним total_nmck)"),
    ("{{contract_price}}", "Цена договора (например: 130 000,00 ₽)"),
    ("{{contract_price_num}}", "Цена без валюты (130 000,00)"),
    ("{{contract_price_words}}", "Цена прописью (сто тридцать тысяч рублей 00 копеек)"),
    ("{{economy}}", "Экономия"),
    ("{{price_increase}}", "Увеличение цены"),
    # ── НДС ──
    ("", "НДС"),
    ("{{vat_applicable}}", "Облагается НДС (true / false)"),
    ("{{vat_rate}}", "Ставка НДС (например: 20)"),
    ("{{vat_amount_num}}", "Сумма НДС цифрами (21 666,67)"),
    ("{{vat_amount_words}}", "Сумма НДС прописью"),
    ("{{vat_exemption_article}}", "Статья освобождения от НДС"),
    ("{{vat_info_line}}", "Готовая строка: «В том числе НДС 20%: ... руб.»"),
    # ── Договор ──
    ("", "ДОГОВОР"),
    ("{{contract_number}}", "Номер договора (например: 2026/42)"),
    ("{{contract_date}}", "Дата договора (15.01.2026)"),
    ("{{contract_date_day}}", "День (15)"),
    ("{{contract_date_month}}", "Месяц прописью (января)"),
    ("{{contract_date_year}}", "Год (2026)"),
    ("{{execution_term}}", "Срок исполнения (28.02.2026)"),
    ("{{execution_term_changed}}", "Изменённый срок"),
    ("{{delivery_date}}", "Дата поставки"),
    ("{{country_origin}}", "Страна происхождения (Российская Федерация)"),
    ("{{service_name}}", "Предмет (синоним subject)"),
    ("{{period_type}}", "Тип срока (period / date)"),
    ("{{service_start_date}}", "Начало оказания услуг (Phase 19 real column, fallback: contract_date)"),
    ("{{service_end_date}}", "Конец оказания услуг (Phase 19 real column, fallback: execution_term)"),
    ("{{service_date}}", "Дата оказания (разовая)"),
    ("{{third_party_involved}}", "Привлечение третьих лиц (true / false)"),
    # ── Phase 19: срок услуг расширенный ──
    ("", "СРОК УСЛУГ (Phase 19)"),
    ("{{service_term}}", "Готовая строка срока (range / duration / deadline)"),
    ("{{service_term_mode}}", "Режим: range | duration | deadline"),
    ("{{service_term_days}}", "Кол-во дней (для mode=duration)"),
    ("{{service_term_type}}", "Тип дней: calendar | working (для mode=duration)"),
    ("{{service_term_type_name}}", "Тип дней прописью: календарных | рабочих"),
    ("{{service_deadline_date}}", "Срок \"до даты\" (для mode=deadline)"),
    # ── Phase 19: приём заявок ──
    ("", "ПРИЁМ ЗАЯВОК (Phase 19)"),
    ("{{submission_deadline_date}}", "Дата завершения приёма заявок (ISO)"),
    ("{{submission_deadline_time}}", "Время завершения приёма заявок (HH:MM)"),
    ("{{submission_deadline_datetime}}", "Дата+время завершения (dd.mm.YYYY HH:MM)"),
    # ── Phase 19: место доставки ──
    ("", "МЕСТО ДОСТАВКИ / ОКАЗАНИЯ УСЛУГ (Phase 19)"),
    ("{{delivery_location}}", "Место оказания услуг / доставки"),
    # ── Phase 19: соглашение субсидии ──
    ("", "СОГЛАШЕНИЕ ПО СУБСИДИИ (Phase 19)"),
    ("{{subsidy_agreement_text}}", "Большой текст соглашения (федеральный бюджет / Росмолодёжь)"),
    # ── Акт приёмки ──
    ("", "АКТ ПРИЁМКИ"),
    ("{{acceptance_doc_name}}", "Наименование акта"),
    ("{{acceptance_doc_number}}", "Номер акта"),
    ("{{acceptance_doc_date}}", "Дата акта"),
    ("{{acceptance_doc_amount}}", "Сумма акта"),
    # ── Платёж ──
    ("", "ПЛАТЁЖ"),
    ("{{payment_doc_number}}", "Номер платёжного поручения"),
    ("{{payment_doc_date}}", "Дата ПП"),
    ("{{payment_amount}}", "Сумма платежа"),
    ("{{payment_federal}}", "В т.ч. федеральный бюджет"),
    # ── Инициатор ──
    ("", "ИНИЦИАТОР (для служебных записок)"),
    ("{{initiator_name}}", "ФИО инициатора"),
    ("{{initiator_role}}", "Должность инициатора"),
    # ── Согласующие (цикл) ──
    ("", "СОГЛАСУЮЩИЕ (цикл для таблицы)"),
    ("{%tr for a in approvers %} ... {%tr endfor %}", "Цикл по согласующим"),
    ("{{a.num}}", "Порядковый номер (1, 2, 3...)"),
    ("{{a.role_name}}", "Должность"),
    ("{{a.full_name}}", "ФИО"),
    ("{{a.signature_img}}", "Электронная подпись (картинка)"),
    ("{{a.decided_date}}", "Дата подписания"),
    ("{{a.note}}", "Примечание (путь ФЭО)"),
    # ── Позиции (цикл) ──
    ("", "ПОЗИЦИИ ЗАКУПКИ (цикл для таблицы)"),
    ("{%tr for item in items %} ... {%tr endfor %}", "Цикл по позициям"),
    ("{{item.num}}", "Порядковый номер"),
    ("{{item.name}}", "Наименование товара/услуги"),
    ("{{item.description}}", "Описание (из карточки продукта)"),
    ("{{item.type}}", "Тип (товар/услуга)"),
    ("{{item.quantity}}", "Количество"),
    ("{{item.unit}}", "Единица измерения"),
    ("{{item.unit_price}}", "Цена за единицу"),
    ("{{item.total_price}}", "Сумма строки"),
    ("{{item.photo}}", "Фото товара (картинка)"),
    ("{{items_count}}", "Общее количество позиций"),
    ("{{item_names}}", "Перечень названий через запятую"),
    # ── Служебные ──
    ("", "СЛУЖЕБНЫЕ"),
    ("{{today}}", "Сегодняшняя дата (20.03.2026)"),
    ("{{today_iso}}", "Дата ISO (2026-03-20)"),
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

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Переменная"
    hdr[1].text = "Описание"
    for cell in hdr:
        for run in cell.paragraphs[0].runs:
            run.bold = True

    for var, desc in TEMPLATE_VARIABLES:
        if not var:
            # Section header row
            row = table.add_row().cells
            row[0].merge(row[1])
            p = row[0].paragraphs[0]
            run = p.add_run(desc)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
            continue
        row = table.add_row().cells
        row[0].text = var
        row[1].text = desc

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
