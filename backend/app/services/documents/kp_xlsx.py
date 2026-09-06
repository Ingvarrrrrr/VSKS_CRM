"""Экспорт позиций закупки в .xlsx для приложения к запросу КП."""


from io import BytesIO

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


async def build_kp_xlsx(pid: int, db: AsyncSession) -> StreamingResponse:
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

    fname = f"Сравнение_КП_закупка_{p.purchase_number or pid}.xlsx"
    from urllib.parse import quote as _quote
    encoded = _quote(fname, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    )
