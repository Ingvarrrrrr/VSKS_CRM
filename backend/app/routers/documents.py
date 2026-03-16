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
from app.auth.jwt import get_current_user
from typing import Optional

router = APIRouter(prefix="/api/purchases", tags=["documents"])
guide_router = APIRouter(prefix="/api/documents", tags=["documents"])

TEMPLATES_DIR = "/app/templates"

DOC_TYPES = {
    "service_note":          ("service_note.docx",          "SZ_Organizaciya"),
    "service_note_delivery": ("service_note_delivery.docx", "SZ_Vydacha"),
    "service_note_payment":  ("service_note_payment.docx",  "SZ_Oplata"),
    "contract_tz":           ("contract_tz.docx",           "Contract_TZ"),
    "contract":              ("contract.docx",              "Contract"),
    "contract_fadm":         ("contract_fadm.docx",         "Contract_FADM"),
    "approval_sheet":        ("approval_sheet.docx",        "Approval_Sheet"),
    "order_purchase":        ("order_purchase.docx",        "Prikaz_zakupki"),
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
        subsidy_template = os.path.join(TEMPLATES_DIR, "subsidies", str(p.subsidy_id), f"{doc_type}.docx")
        if os.path.exists(subsidy_template):
            template_path = subsidy_template

    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
    subsidy = subsidy_r.scalar_one_or_none()

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

    # Build FEO category path (root → ... → selected)
    feo_path = ""
    if p.feo_category_id:
        feo_res = await db.execute(select(FeoCategory))
        all_feo = {f.id: f for f in feo_res.scalars().all()}
        path_parts = []
        node_id = p.feo_category_id
        visited = set()
        while node_id and node_id not in visited:
            visited.add(node_id)
            cat = all_feo.get(node_id)
            if not cat:
                break
            path_parts.append(cat.name.strip())
            node_id = cat.parent_id
        feo_path = " → ".join(reversed(path_parts))

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

    approvers_list = []
    for i, a in enumerate(selected_approvers):
        full_name = a.full_name or ""
        # Substitute responsible person into rows with empty or placeholder full_name
        if not full_name.strip().strip("_").strip():
            full_name = resolved_responsible
        note = feo_path if getattr(a, "show_feo_path", False) else ""

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
        # Финансы
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
        # Согласующие
        "approvers": approvers_list,
        "initiator_name": initiator.full_name if initiator else "",
        "initiator_role": initiator.role_name if initiator else "",
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
        "period_type": p.service_period_type or "period",
        "service_start_date": _fmt_date(p.contract_date),
        "service_end_date":   _fmt_date(p.execution_term),
        "service_date":       _fmt_date(p.execution_term),
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
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
    except Exception as e:
        raise HTTPException(500, f"Ошибка генерации документа: {e}")

    safe_name = f"{filename_base}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    encoded_name = quote(safe_name, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


# ── Template markup guide ────────────────────────────────────────────────────

TEMPLATE_VARIABLES = [
    ("{{purchase_number}}", "Номер закупки (например: 42)"),
    ("{{registry_number}}", "Реестровый номер (например: ЗК-2026-042)"),
    ("{{contract_number}}", "Номер договора (например: 2026/42)"),
    ("{{contract_date}}", "Дата договора (например: 16.03.2026)"),
    ("{{subject}}", "Предмет договора / закупки"),
    ("{{contract_price}}", "Сумма договора цифрами (например: 150 000,00)"),
    ("{{contract_price_words}}", "Сумма прописью (например: сто пятьдесят тысяч рублей 00 копеек)"),
    ("{{purchase_method}}", "Способ закупки"),
    ("{{execution_term}}", "Срок исполнения"),
    ("{{subsidy_name}}", "Наименование субсидии"),
    ("{{subsidy_year}}", "Год субсидии"),
    ("{{org_name}}", "Наименование организации-заказчика"),
    ("{{contractor_name}}", "Полное наименование контрагента"),
    ("{{contractor_short_name}}", "Сокращённое наименование контрагента"),
    ("{{contractor_inn}}", "ИНН контрагента"),
    ("{{contractor_kpp}}", "КПП контрагента"),
    ("{{contractor_address}}", "Юридический адрес контрагента"),
    ("{{contractor_postal_address}}", "Почтовый адрес контрагента"),
    ("{{contractor_signatory}}", "Подписант контрагента (ФИО)"),
    ("{{contractor_signatory_basis}}", "Основание (Устав / Доверенность №...)"),
    ("{{contractor_bank_name}}", "Наименование банка контрагента"),
    ("{{contractor_bik}}", "БИК банка"),
    ("{{contractor_settlement_account}}", "Расчётный счёт"),
    ("{{contractor_correspondent_account}}", "Корреспондентский счёт"),
    ("{{responsible_person}}", "ФИО ответственного исполнителя"),
    ("{{delivery_address}}", "Адрес доставки"),
    ("{%tr for a in approvers %} ... {%tr endfor %}", "Цикл по согласующим (для таблицы)"),
    ("{{a.num}}", "Порядковый номер согласующего"),
    ("{{a.role_name}}", "Должность согласующего"),
    ("{{a.full_name}}", "ФИО согласующего"),
    ("{{a.decided_date}}", "Дата согласования"),
    ("{{a.note}}", "Примечание (ФЭО путь)"),
    ("{{a.signature_img}}", "Электронная подпись (изображение)"),
    ("{%tr for item in items %} ... {%tr endfor %}", "Цикл по позициям закупки"),
    ("{{item.num}}", "Порядковый номер позиции"),
    ("{{item.name}}", "Наименование товара/услуги"),
    ("{{item.quantity}}", "Количество"),
    ("{{item.unit}}", "Единица измерения"),
    ("{{item.price}}", "Цена за единицу"),
    ("{{item.total}}", "Итого по позиции"),
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
        row = table.add_row().cells
        row[0].text = var
        row[1].text = desc

    doc.add_heading("Пример строки таблицы согласующих", 1)
    doc.add_paragraph(
        '{%tr for a in approvers %}\n'
        '| {{a.num}} | {{a.role_name}} | {{a.full_name}} | {{a.signature_img}} {{a.decided_date}} | {{a.note}} |\n'
        '{%tr endfor %}'
    )

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''Template_Guide.docx"},
    )
