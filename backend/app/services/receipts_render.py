"""PDF/PNG rendering of a fiscal receipt (no DB, no HTTP).

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08).
Pure functions taking a PurchaseReceipt-like object (`r`, duck-typed) and
returning bytes — the HTTP endpoints (receipt_pdf/receipt_png, now in
app/routers/purchase_receipts_export.py) are thin wrappers around these.

Historical import path app.routers.purchase_receipts re-exports
_render_receipt_png (used by purchase_files.py and
services/documents/stages_receipts.py).
"""
import os
from io import BytesIO

from app.services.receipts_parsing import _build_qr_string, _get_raw_receipt, _items_for_render

# Constant maps for ФФД 1.2 codes → human-readable Russian labels.
OPERATION_TYPE_RU = {
    1: "Приход",
    2: "Возврат прихода",
    3: "Расход",
    4: "Возврат расхода",
}
PRODUCT_TYPE_RU = {
    1: "ТОВАР",
    2: "ПОДАКЦИЗНЫЙ ТОВАР",
    3: "РАБОТА",
    4: "УСЛУГА",
    5: "СТАВКА АЗАРТНОЙ ИГРЫ",
    6: "ВЫИГРЫШ АЗАРТНОЙ ИГРЫ",
    7: "ЛОТЕРЕЙНЫЙ БИЛЕТ",
    8: "ВЫИГРЫШ ЛОТЕРЕИ",
    9: "ПРЕДОСТАВЛЕНИЕ РИД",
    10: "ПЛАТЕЖ",
    11: "АГЕНТСКОЕ ВОЗНАГРАЖДЕНИЕ",
    12: "ВЫПЛАТА",
    13: "ИНОЙ ПРЕДМЕТ РАСЧЕТА",
    14: "ИМУЩЕСТВЕННОЕ ПРАВО",
    15: "ВНЕРЕАЛИЗАЦИОННЫЙ ДОХОД",
    16: "СТРАХОВЫЕ ВЗНОСЫ",
    17: "ТОРГОВЫЙ СБОР",
    18: "КУРОРТНЫЙ СБОР",
    19: "ЗАЛОГ",
    20: "РАСХОД",
    21: "ВЗНОСЫ НА ОПС ИП",
    22: "ВЗНОСЫ НА ОПС",
    23: "ВЗНОСЫ НА ОМС ИП",
    24: "ВЗНОСЫ НА ОМС",
    25: "ВЗНОСЫ НА ОСС",
    26: "ПЛАТЕЖ КАЗИНО",
    27: "ВЫДАЧА ДЕНЕЖНЫХ СРЕДСТВ",
    30: "АТНМ",
    31: "АТМ",
    32: "АТНМ",
    33: "АТМ",
}
PAYMENT_TYPE_RU = {
    1: "ПРЕДОПЛАТА 100%",
    2: "ПРЕДОПЛАТА",
    3: "АВАНС",
    4: "ПОЛНЫЙ РАСЧЕТ",
    5: "ЧАСТИЧНЫЙ РАСЧЕТ И КРЕДИТ",
    6: "ПЕРЕДАЧА В КРЕДИТ",
    7: "ОПЛАТА КРЕДИТА",
}
# ФФД 1.2 тег 1199 «Ставка НДС» — полная таблица (КонсультантПлюс табл. 8):
#   1=20%, 2=10%, 3=20/120, 4=10/110, 5=0%, 6=без НДС
#   7=5% / 8=7% / 9=5/105 / 10=7/107  — новые ставки УСН с 01.01.2025
#   11=22% / 12=22/122                — стандартная ставка с 01.01.2026
NDS_LABEL_RU = {
    1: "НДС 20%",
    2: "НДС 10%",
    3: "НДС 20/120",
    4: "НДС 10/110",
    5: "НДС 0%",
    6: "НДС не облагается",
    7: "НДС 5%",
    8: "НДС 7%",
    9: "НДС 5/105",
    10: "НДС 7/107",
    11: "НДС 22%",
    12: "НДС 22/122",
}

TAXATION_RU = {
    1: "ОСН",
    2: "УСН доход",
    4: "УСН доход-расход",
    8: "ЕНВД",
    16: "ЕСХН",
    32: "ПАТЕНТ",
}

def _make_qr_image_buf(data: str) -> BytesIO:
    """Build a QR-code PNG into an in-memory buffer (for ReportLab drawImage)."""
    import qrcode
    img = qrcode.make(data, box_size=4, border=2)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def _register_cyrillic_font() -> str:
    """Register a Cyrillic-capable TTF font. Returns the registered font name
    (or "Helvetica" as a fallback). Idempotent — safe to call multiple times."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # If we've already registered DejaVu in a previous call, reuse it.
    try:
        if "DejaVu" in pdfmetrics.getRegisteredFontNames():
            return "DejaVu"
    except Exception:
        pass

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", path))
            bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_path))
            else:
                # No bold available — register the regular face under the bold name
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", path))
            return "DejaVu"
        except Exception:
            continue
    return "Helvetica"

def _render_fallback_pdf(r) -> bytes:
    """Minimal PDF when raw_json is missing or rendering threw."""
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)
    c.setFont(font_name, 10)
    w, h = A6
    c.drawString(8 * mm, h - 12 * mm, f"Чек #{r.id} — данные недоступны")
    if r.fiscal_drive_number:
        c.drawString(8 * mm, h - 20 * mm, f"ФН: {r.fiscal_drive_number}")
    if r.fiscal_document_number:
        c.drawString(8 * mm, h - 26 * mm, f"ФД: {r.fiscal_document_number}")
    c.showPage()
    c.save()
    return buf.getvalue()

def _render_receipt_pdf(r) -> bytes:
    """Render a fiscal receipt in ФФД 1.2 layout (matches ФНС 'Проверка чека' app).

    A5 portrait, dynamic height. Sections (top→bottom):
      • Header (КАССОВЫЙ ЧЕК / версия ФФД 1.2 / operation type)
      • Items table — for each item: row + НДС label + НДС sum + product type + payment type
      • Totals (ИТОГО, Безналичные/Наличные/Аванс/…, НДС итог)
      • Fiscal block (СНО, РЕГ.НОМЕР ККТ, ФН, ФД, ФПД)
      • Seller block (Пользователь, Адрес, Место, ИНН, Дата, Чек №, Смена №, Кассир)
      • QR code centered
    """
    import textwrap
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    bold_name = "DejaVu-Bold" if font_name == "DejaVu" else "Helvetica-Bold"

    raw = _get_raw_receipt(r)
    items_data = _items_for_render(r)

    # Dynamic height — A5 width (148mm) is enough; height grows with content.
    width = 148 * mm
    base_h = 180 * mm
    items_h = (25 * mm) * max(1, len(items_data))
    tail_h = 60 * mm
    height = base_h + items_h + tail_h

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    # Drawing state ----------------------------------------------------------
    state = {"y": height - 8 * mm}
    margin_l = 6 * mm
    margin_r = width - 6 * mm
    inner_w = margin_r - margin_l

    def set_font(size=9, bold=False, italic=False):
        # ReportLab DejaVu doesn't have an italic variant registered — use regular.
        c.setFont(bold_name if bold else font_name, size)

    def line(s, size=9, bold=False, x=None, dy=4.5):
        set_font(size, bold)
        c.drawString(x if x is not None else margin_l, state["y"], str(s))
        state["y"] -= dy * mm

    def line_center(s, size=9, bold=False, italic=False, dy=4.5):
        set_font(size, bold, italic)
        text_w = c.stringWidth(str(s), bold_name if bold else font_name, size)
        c.drawString((width - text_w) / 2, state["y"], str(s))
        state["y"] -= dy * mm

    def line_right(label, value, size=9, bold=False, dy=4.5):
        set_font(size, bold)
        c.drawString(margin_l, state["y"], str(label))
        text_w = c.stringWidth(str(value), bold_name if bold else font_name, size)
        c.drawString(margin_r - text_w, state["y"], str(value))
        state["y"] -= dy * mm

    def hr_dashed():
        c.setDash(2, 2)
        c.setLineWidth(0.4)
        c.line(margin_l, state["y"], margin_r, state["y"])
        c.setDash()
        state["y"] -= 3 * mm

    # ── Header ─────────────────────────────────────────────────────────────
    line_center("КАССОВЫЙ ЧЕК", 14, bold=True, dy=5.5)
    line_center("«версия ФФД 1.2»", 9, dy=5)
    op_code = raw.get('operationType') or 1
    op_word = OPERATION_TYPE_RU.get(op_code, "Приход")
    line_center(op_word, 11, bold=True, dy=6)

    hr_dashed()

    # ── Items table ────────────────────────────────────────────────────────
    # Header row
    set_font(8, bold=True)
    c.drawString(margin_l, state["y"], "№")
    c.drawString(margin_l + 6 * mm, state["y"], "Название")
    c.drawString(margin_l + 80 * mm, state["y"], "Цена")
    c.drawString(margin_l + 100 * mm, state["y"], "Кол.")
    c.drawString(margin_l + 118 * mm, state["y"], "Сумма")
    state["y"] -= 5 * mm

    if not items_data:
        line("(позиции не указаны)", 8, dy=5)

    for idx, it in enumerate(items_data, start=1):
        if not isinstance(it, dict):
            continue
        try:
            qty = float(it.get('quantity') or 1)
        except Exception:
            qty = 1.0
        price = float(it.get('price_rub') or 0)
        sm = float(it.get('sum_rub') or 0)
        nds_code = it.get('nds')
        nds_sum_rub = it.get('nds_sum_rub')  # уже в рублях
        product_type = it.get('productType')
        payment_type = it.get('paymentType')
        name = (it.get('name') or '').strip()

        # Wrap long names — the name column is ~70mm wide.
        wrapped = textwrap.wrap(name, width=42) or ['']

        # Row 1 — number + first name line + price/qty/sum
        set_font(8)
        c.drawString(margin_l, state["y"], str(idx))
        c.drawString(margin_l + 6 * mm, state["y"], wrapped[0][:42])
        c.drawString(margin_l + 80 * mm, state["y"], f"{price:.2f}")
        c.drawString(margin_l + 100 * mm, state["y"], f"{qty:g}")
        c.drawString(margin_l + 118 * mm, state["y"], f"{sm:.2f}")
        state["y"] -= 4.5 * mm

        # Continuation lines of the name (if wrapped)
        for cont in wrapped[1:]:
            set_font(8)
            c.drawString(margin_l + 6 * mm, state["y"], cont[:42])
            state["y"] -= 4 * mm

        # НДС label
        nds_label = NDS_LABEL_RU.get(nds_code, "НДС не облагается")
        line(f"   {nds_label}", 7, dy=3.8)

        # НДС sum (if non-zero)
        if nds_sum_rub is not None and nds_sum_rub > 0:
            line_right("   сумма НДС за товар", f"{nds_sum_rub:.2f}", 7, dy=3.8)

        # Product type
        if product_type:
            line(f"   {PRODUCT_TYPE_RU.get(product_type, '')}", 7, dy=3.8)

        # Payment type
        if payment_type:
            line(f"   {PAYMENT_TYPE_RU.get(payment_type, '')}", 7, dy=3.8)

        state["y"] -= 1 * mm

    hr_dashed()

    # ── Totals ─────────────────────────────────────────────────────────────
    if r.total_sum is not None:
        line_right("ИТОГО:", f"{float(r.total_sum):.2f}", 12, bold=True, dy=6)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        line_right("Безналичные", f"{float(r.ecash_sum):.2f}", 9, dy=4.5)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        line_right("Наличные", f"{float(r.cash_sum):.2f}", 9, dy=4.5)
    if r.prepaid_sum is not None and float(r.prepaid_sum) > 0:
        line_right("Аванс", f"{float(r.prepaid_sum):.2f}", 9, dy=4.5)
    if r.nds_sum is not None:
        try:
            nds_total = float(r.nds_sum)
        except Exception:
            nds_total = None
        if nds_total and nds_total > 0:
            line_right("НДС", f"{nds_total:.2f}", 9, dy=4.5)
        else:
            line_right("НДС не облагается", f"{float(r.total_sum or 0):.2f}", 9, dy=4.5)

    hr_dashed()

    # ── Fiscal block ───────────────────────────────────────────────────────
    if r.taxation_type is not None:
        sno = TAXATION_RU.get(r.taxation_type, str(r.taxation_type))
        line(f"ВИД НАЛОГООБЛОЖЕНИЯ {sno}", 8, dy=4.5)
    if r.kkt_reg_id:
        line(f"РЕГ. НОМЕР ККТ: {r.kkt_reg_id}", 8, dy=4.5)
    if r.fiscal_drive_number:
        line(f"ФН: № {r.fiscal_drive_number}", 8, dy=4.5)
    if r.fiscal_document_number:
        line(f"ФД: № {r.fiscal_document_number}", 8, dy=4.5)
    if r.fiscal_sign:
        line(f"ФПД: # {r.fiscal_sign}", 8, dy=4.5)

    hr_dashed()

    # ── Seller block ───────────────────────────────────────────────────────
    if r.seller_name:
        line(f"Пользователь: {r.seller_name}", 8, dy=4.5)
    if r.retail_place_address:
        line(f"Адрес расчета: {str(r.retail_place_address)[:90]}", 8, dy=4.5)
    if r.retail_place:
        line(f"Место расчета: {str(r.retail_place)[:90]}", 8, dy=4.5)
    if r.seller_inn:
        line(f"ИНН {r.seller_inn}", 8, dy=4.5)
    if r.receipt_datetime:
        try:
            line(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H.%M')}", 8, dy=4.5)
        except Exception:
            line(f"Дата: {r.receipt_datetime}", 8, dy=4.5)
    request_number = raw.get('requestNumber')
    if request_number:
        line(f"Чек № {request_number}", 8, dy=4.5)
    shift_number = raw.get('shiftNumber')
    if shift_number:
        line(f"Смена № {shift_number}", 8, dy=4.5)
    if r.operator:
        line(f"Кассир {r.operator}", 8, dy=4.5)
    if r.operator_inn:
        line(f"ИНН кассира: {r.operator_inn}", 8, dy=4.5)

    state["y"] -= 4 * mm

    # ── QR code ────────────────────────────────────────────────────────────
    try:
        qr_str = _build_qr_string(r)
        qr_buf = _make_qr_image_buf(qr_str)
        qr_size = 40 * mm
        qr_x = (width - qr_size) / 2
        qr_y = max(state["y"] - qr_size, 8 * mm)
        c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        pass

    c.showPage()
    c.save()
    return buf.getvalue()

def _render_receipt_png(r) -> bytes:
    """Render a fiscal receipt as PNG (Pillow). Same layout as PDF.

    Returns raw PNG bytes ready to send back as image/png.
    """
    import textwrap
    from PIL import Image, ImageDraw, ImageFont
    import qrcode

    raw = _get_raw_receipt(r)
    items_data = _items_for_render(r)

    width = 600

    # ── Font loading ───────────────────────────────────────────────────────
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    bold_paths = [p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf") for p in font_paths]
    font_path = next((p for p in font_paths if os.path.exists(p)), None)
    bold_path = next((p for p in bold_paths if os.path.exists(p)), font_path)

    def f(size, bold=False):
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size) \
                if (bold_path if bold else font_path) else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    F_TITLE = f(20, bold=True)
    F_SUB = f(13)
    F_OP = f(16, bold=True)
    F_TBL_HEAD = f(12, bold=True)
    F_TXT = f(12)
    F_SMALL = f(11)
    F_TOTAL = f(20, bold=True)
    F_TOTAL_NUM = f(20, bold=True)
    F_LINE = f(13)

    line_h = 18

    # ── Pre-compute height ─────────────────────────────────────────────────
    title_h = 28 + 22 + 28 + 12  # title + sub + op + spacing
    items_h = 28  # table header
    for it in items_data:
        name = (it.get('name') or '').strip()
        wrapped = textwrap.wrap(name, width=42) or ['']
        items_h += line_h * len(wrapped)  # name lines
        items_h += line_h  # nds label
        if it.get('ndsSum'):
            items_h += line_h
        if it.get('productType'):
            items_h += line_h
        if it.get('paymentType'):
            items_h += line_h
        items_h += 6
    if not items_data:
        items_h += line_h

    totals_h = 60 + line_h * 5
    fiscal_h = line_h * 6
    seller_h = line_h * 10
    qr_h = 220
    height = title_h + items_h + totals_h + fiscal_h + seller_h + qr_h + 60

    img = Image.new('RGB', (width, height), 'white')
    d = ImageDraw.Draw(img)

    margin_l = 20
    margin_r = width - 20

    state = {"y": 16}

    def hr():
        # Dashed
        x = margin_l
        while x < margin_r:
            d.line([(x, state["y"]), (min(x + 4, margin_r), state["y"])], fill='black', width=1)
            x += 8
        state["y"] += 10

    def text(s, font=F_TXT, x=None, dy=None, fill='black'):
        d.text((x if x is not None else margin_l, state["y"]), str(s), font=font, fill=fill)
        state["y"] += dy if dy is not None else line_h

    def text_center(s, font=F_TXT, dy=None, fill='black'):
        try:
            tw = d.textlength(str(s), font=font)
        except Exception:
            tw = len(str(s)) * 7
        d.text(((width - tw) / 2, state["y"]), str(s), font=font, fill=fill)
        state["y"] += dy if dy is not None else line_h

    def text_right(label, value, font=F_TXT, value_font=None, dy=None, fill='black'):
        vfont = value_font or font
        d.text((margin_l, state["y"]), str(label), font=font, fill=fill)
        try:
            vw = d.textlength(str(value), font=vfont)
        except Exception:
            vw = len(str(value)) * 7
        d.text((margin_r - vw, state["y"]), str(value), font=vfont, fill=fill)
        state["y"] += dy if dy is not None else line_h

    # ── Header ─────────────────────────────────────────────────────────────
    text_center("КАССОВЫЙ ЧЕК", F_TITLE, dy=28)
    text_center("«версия ФФД 1.2»", F_SUB, dy=22)
    op_code = raw.get('operationType') or 1
    op_word = OPERATION_TYPE_RU.get(op_code, "Приход")
    text_center(op_word, F_OP, dy=28)
    state["y"] += 4
    hr()

    # ── Items table ────────────────────────────────────────────────────────
    # Column header
    d.text((margin_l, state["y"]), "№", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 30, state["y"]), "Название", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 340, state["y"]), "Цена", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 420, state["y"]), "Кол.", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 480, state["y"]), "Сумма", font=F_TBL_HEAD, fill='black')
    state["y"] += line_h + 4

    if not items_data:
        text("(позиции не указаны)", F_SMALL)

    for idx, it in enumerate(items_data, start=1):
        try:
            qty = float(it.get('quantity') or 1)
        except Exception:
            qty = 1.0
        price = float(it.get('price_rub') or 0)
        sm = float(it.get('sum_rub') or 0)
        nds_code = it.get('nds')
        nds_sum_rub = it.get('nds_sum_rub')  # уже в рублях
        product_type = it.get('productType')
        payment_type = it.get('paymentType')
        name = (it.get('name') or '').strip()
        wrapped = textwrap.wrap(name, width=42) or ['']

        # Row 1
        d.text((margin_l, state["y"]), str(idx), font=F_TXT, fill='black')
        d.text((margin_l + 30, state["y"]), wrapped[0][:42], font=F_TXT, fill='black')
        d.text((margin_l + 340, state["y"]), f"{price:.2f}", font=F_TXT, fill='black')
        d.text((margin_l + 420, state["y"]), f"{qty:g}", font=F_TXT, fill='black')
        d.text((margin_l + 480, state["y"]), f"{sm:.2f}", font=F_TXT, fill='black')
        state["y"] += line_h

        # Wrapped name continuation
        for cont in wrapped[1:]:
            d.text((margin_l + 30, state["y"]), cont[:42], font=F_TXT, fill='black')
            state["y"] += line_h

        nds_label = NDS_LABEL_RU.get(nds_code, "НДС не облагается")
        text(f"   {nds_label}", F_SMALL)

        if nds_sum_rub is not None and nds_sum_rub > 0:
            text_right("   сумма НДС за товар", f"{nds_sum_rub:.2f}", F_SMALL)

        if product_type:
            text(f"   {PRODUCT_TYPE_RU.get(product_type, '')}", F_SMALL)

        if payment_type:
            text(f"   {PAYMENT_TYPE_RU.get(payment_type, '')}", F_SMALL)

        state["y"] += 4

    hr()

    # ── Totals ─────────────────────────────────────────────────────────────
    if r.total_sum is not None:
        text_right("ИТОГО:", f"{float(r.total_sum):.2f}", F_TOTAL, F_TOTAL_NUM, dy=30)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        text_right("Безналичные", f"{float(r.ecash_sum):.2f}", F_LINE)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        text_right("Наличные", f"{float(r.cash_sum):.2f}", F_LINE)
    if r.prepaid_sum is not None and float(r.prepaid_sum) > 0:
        text_right("Аванс", f"{float(r.prepaid_sum):.2f}", F_LINE)
    if r.nds_sum is not None:
        try:
            nds_total = float(r.nds_sum)
        except Exception:
            nds_total = None
        if nds_total and nds_total > 0:
            text_right("НДС", f"{nds_total:.2f}", F_LINE)
        else:
            text_right("НДС не облагается", f"{float(r.total_sum or 0):.2f}", F_LINE)

    hr()

    # ── Fiscal block ───────────────────────────────────────────────────────
    if r.taxation_type is not None:
        sno = TAXATION_RU.get(r.taxation_type, str(r.taxation_type))
        text(f"ВИД НАЛОГООБЛОЖЕНИЯ {sno}", F_LINE)
    if r.kkt_reg_id:
        text(f"РЕГ. НОМЕР ККТ: {r.kkt_reg_id}", F_LINE)
    if r.fiscal_drive_number:
        text(f"ФН: № {r.fiscal_drive_number}", F_LINE)
    if r.fiscal_document_number:
        text(f"ФД: № {r.fiscal_document_number}", F_LINE)
    if r.fiscal_sign:
        text(f"ФПД: # {r.fiscal_sign}", F_LINE)

    hr()

    # ── Seller block ───────────────────────────────────────────────────────
    if r.seller_name:
        text(f"Пользователь: {r.seller_name}", F_LINE)
    if r.retail_place_address:
        text(f"Адрес расчета: {str(r.retail_place_address)[:90]}", F_LINE)
    if r.retail_place:
        text(f"Место расчета: {str(r.retail_place)[:90]}", F_LINE)
    if r.seller_inn:
        text(f"ИНН {r.seller_inn}", F_LINE)
    if r.receipt_datetime:
        try:
            text(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H.%M')}", F_LINE)
        except Exception:
            text(f"Дата: {r.receipt_datetime}", F_LINE)
    request_number = raw.get('requestNumber')
    if request_number:
        text(f"Чек № {request_number}", F_LINE)
    shift_number = raw.get('shiftNumber')
    if shift_number:
        text(f"Смена № {shift_number}", F_LINE)
    if r.operator:
        text(f"Кассир {r.operator}", F_LINE)
    if r.operator_inn:
        text(f"ИНН кассира: {r.operator_inn}", F_LINE)

    state["y"] += 12

    # ── QR code ────────────────────────────────────────────────────────────
    try:
        qr_str = _build_qr_string(r)
        qr_img = qrcode.make(qr_str, box_size=5, border=2).get_image().convert('RGB')
        qr_size = 200
        qr_resized = qr_img.resize((qr_size, qr_size))
        img.paste(qr_resized, ((width - qr_size) // 2, state["y"]))
    except Exception:
        pass

    out = BytesIO()
    img.save(out, format='PNG', optimize=True)
    return out.getvalue()
