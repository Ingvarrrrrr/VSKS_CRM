"""PDF-экспорт отчётов (Phase 25-09).

Использует reportlab. Кириллица через DejaVuSans (либо встроенный CID-шрифт Cyrillic).

Поддерживает list/pivot/dashboard, аналогично report_excel.py.
"""

import io
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie

from app.services.field_registry import get_field

# === FONTS ===
# DejaVuSans поддерживает кириллицу. Если файла нет — fallback на builtin Helvetica-Cyrillic.
_FONTS_REGISTERED = False
_FONT_NAME = 'Helvetica'  # fallback


def _register_fonts():
    global _FONTS_REGISTERED, _FONT_NAME
    if _FONTS_REGISTERED:
        return _FONT_NAME

    # Пробуем несколько типичных путей DejaVuSans на Linux/Docker
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/DejaVuSans.ttf',
        '/Library/Fonts/DejaVuSans.ttf',
        'C:/Windows/Fonts/arial.ttf',  # для local dev на Windows
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('VskSans', path))
                _FONT_NAME = 'VskSans'
                # Bold variant если есть
                bold_path = path.replace('Sans.ttf', 'Sans-Bold.ttf').replace('arial.ttf', 'arialbd.ttf')
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont('VskSansBold', bold_path))
                _FONTS_REGISTERED = True
                return _FONT_NAME
            except Exception:
                continue

    # Last resort: reportlab built-in CID font для кириллицы
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))  # Japanese, also has Cyrillic
    except Exception:
        pass

    _FONTS_REGISTERED = True
    return _FONT_NAME


# === STYLES ===
def _get_styles():
    font = _register_fonts()
    bold_font = 'VskSansBold' if font == 'VskSans' else font
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('Title', parent=styles['Heading1'], fontName=bold_font, fontSize=16, alignment=TA_CENTER, spaceAfter=8),
        'h2': ParagraphStyle('H2', parent=styles['Heading2'], fontName=bold_font, fontSize=12, spaceAfter=4),
        'normal': ParagraphStyle('Normal', parent=styles['Normal'], fontName=font, fontSize=9, leading=11),
        'small': ParagraphStyle('Small', parent=styles['Normal'], fontName=font, fontSize=7, leading=9, textColor=grey),
        'cell': ParagraphStyle('Cell', parent=styles['Normal'], fontName=font, fontSize=8, leading=10),
        'cell_right': ParagraphStyle('CellR', parent=styles['Normal'], fontName=font, fontSize=8, leading=10, alignment=TA_RIGHT),
        'header_cell': ParagraphStyle('HCell', parent=styles['Normal'], fontName=bold_font, fontSize=9, leading=11, alignment=TA_CENTER, textColor=white),
        'font_name': font,
        'bold_font_name': bold_font,
    }


def _label_for(key: str) -> str:
    f = get_field(key)
    return f.label if f else key


def _fmt_value(v: Any) -> str:
    if v is None or v == '':
        return ''
    if isinstance(v, float):
        return f'{v:,.2f}'.replace(',', ' ')
    if isinstance(v, int):
        return f'{v:,}'.replace(',', ' ')
    return str(v)


def _header_paragraph(text: str, meta: Dict, styles) -> List:
    """Заголовок документа."""
    elements = []
    elements.append(Paragraph(meta.get('report_name', text), styles['title']))

    meta_text = (
        f"Организация: <b>{meta.get('org_name', '—')}</b> &nbsp;&nbsp; "
        f"Тип: {meta.get('kind', '—')} &nbsp;&nbsp; "
        f"Автор: {meta.get('author', '—')} &nbsp;&nbsp; "
        f"Сформирован: {meta.get('generated_at', datetime.utcnow().strftime('%d.%m.%Y %H:%M'))}"
    )
    elements.append(Paragraph(meta_text, styles['small']))
    elements.append(Spacer(1, 6))
    return elements


# === EXPORTERS ===
def export_list(rows: List[Dict], config: Dict, meta: Dict) -> bytes:
    """Тип A — реестр в PDF."""
    styles = _get_styles()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)

    elements = _header_paragraph('Реестр', meta, styles)

    col_keys = list(config.get('columns', []))
    # computed columns
    computed_keys: List[str] = []
    for cc in config.get('computed_columns', []):
        if cc.get('type') in ('composite', 'constant'):
            computed_keys.append(cc.get('key'))

    all_keys = col_keys + computed_keys
    headers = [_label_for(k) for k in col_keys] + computed_keys

    if not all_keys:
        elements.append(Paragraph('Нет данных', styles['normal']))
        doc.build(elements)
        return bio.getvalue()

    # Build table data
    header_row = [Paragraph(h, styles['header_cell']) for h in headers]
    data = [header_row]
    row_styles = []  # для группировки

    for idx, row in enumerate(rows, start=1):
        rtype = row.get('_row_type', 'data')
        cells = []
        for k in all_keys:
            val = row.get(k)
            if isinstance(val, (int, float)):
                cells.append(Paragraph(_fmt_value(val), styles['cell_right']))
            else:
                cells.append(Paragraph(_fmt_value(val), styles['cell']))
        data.append(cells)

        # Style для row
        if rtype == 'group_header':
            row_styles.append(('BACKGROUND', (0, idx), (-1, idx), HexColor('#D9E2F3')))
            row_styles.append(('FONTNAME', (0, idx), (-1, idx), styles['bold_font_name']))
        elif rtype == 'subtotal':
            row_styles.append(('BACKGROUND', (0, idx), (-1, idx), HexColor('#F2F2F2')))
            row_styles.append(('FONTNAME', (0, idx), (-1, idx), styles['bold_font_name']))
        elif rtype == 'grand_total':
            row_styles.append(('BACKGROUND', (0, idx), (-1, idx), HexColor('#BDD7EE')))
            row_styles.append(('FONTNAME', (0, idx), (-1, idx), styles['bold_font_name']))

    table = Table(data, repeatRows=1)
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), styles['bold_font_name']),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BFBFBF')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ] + row_styles)
    table.setStyle(table_style)
    elements.append(table)

    doc.build(elements)
    return bio.getvalue()


def export_pivot(result: Dict, config: Dict, meta: Dict) -> bytes:
    """Тип B — сводная в PDF."""
    styles = _get_styles()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)

    elements = _header_paragraph('Сводная', meta, styles)

    rows_dims = config.get('rows', [])
    cols_dims = config.get('cols', [])
    measures = config.get('measures', [])
    calc_columns = config.get('calc_columns', [])

    headers = [_label_for(d) for d in rows_dims] + [_label_for(d) for d in cols_dims]
    measure_keys = []
    for m in measures:
        field = m.get('field')
        agg = m.get('agg', 'sum')
        headers.append(f'{_label_for(field)} ({agg})')
        measure_keys.append(f'{agg}_{field}')

    calc_keys = []
    for cc in calc_columns:
        if cc.get('type') == 'share':
            headers.append('% от итога')
            calc_keys.append(f'share_{cc.get("measure")}')
        elif cc.get('type') == 'cumulative':
            headers.append('Нараст.')
            calc_keys.append(f'cumulative_{cc.get("measure")}')
        elif cc.get('type') == 'delta':
            headers.append('Δ')
            calc_keys.append(f'delta_{cc.get("actual")}_vs_{cc.get("plan")}')

    if not headers:
        elements.append(Paragraph('Нет данных', styles['normal']))
        doc.build(elements)
        return bio.getvalue()

    header_row = [Paragraph(h, styles['header_cell']) for h in headers]
    data = [header_row]
    all_dim_keys = rows_dims + cols_dims

    for row in result.get('rows', []):
        cells = []
        for d in all_dim_keys:
            cells.append(Paragraph(_fmt_value(row.get(d)), styles['cell']))
        for mk in measure_keys:
            cells.append(Paragraph(_fmt_value(row.get(mk)), styles['cell_right']))
        for ck in calc_keys:
            v = row.get(ck)
            if ck.startswith('share_') and isinstance(v, (int, float)):
                cells.append(Paragraph(f'{float(v)*100:.1f}%', styles['cell_right']))
            else:
                cells.append(Paragraph(_fmt_value(v), styles['cell_right']))
        data.append(cells)

    # Grand total
    totals = result.get('totals', {})
    if totals:
        total_cells = [Paragraph('Итого', styles['cell'])] + [Paragraph('', styles['cell'])] * (len(all_dim_keys) - 1)
        for mk in measure_keys:
            total_cells.append(Paragraph(_fmt_value(totals.get(mk)), styles['cell_right']))
        for ck in calc_keys:
            total_cells.append(Paragraph('', styles['cell_right']))
        data.append(total_cells)

    table = Table(data, repeatRows=1)
    table_style_list = [
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), styles['bold_font_name']),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BFBFBF')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]
    if totals:
        # Highlight last row (grand total)
        last_idx = len(data) - 1
        table_style_list.append(('BACKGROUND', (0, last_idx), (-1, last_idx), HexColor('#BDD7EE')))
        table_style_list.append(('FONTNAME', (0, last_idx), (-1, last_idx), styles['bold_font_name']))

    table.setStyle(TableStyle(table_style_list))
    elements.append(table)

    # Простой bar-chart если 1 measure + 1 dim
    if len(rows_dims) == 1 and len(measure_keys) == 1 and result.get('rows'):
        chart_data = []
        labels = []
        for r in result['rows'][:15]:  # топ-15
            v = r.get(measure_keys[0])
            if v is not None:
                chart_data.append(float(v))
                labels.append(str(r.get(rows_dims[0], ''))[:20])
        if chart_data:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph('График', styles['h2']))
            drawing = Drawing(700, 250)
            chart = VerticalBarChart()
            chart.x = 50
            chart.y = 30
            chart.height = 200
            chart.width = 600
            chart.data = [chart_data]
            chart.categoryAxis.categoryNames = labels
            chart.categoryAxis.labels.fontSize = 7
            chart.categoryAxis.labels.angle = 30
            chart.categoryAxis.labels.dy = -8
            chart.valueAxis.labels.fontSize = 7
            chart.bars[0].fillColor = HexColor('#4472C4')
            drawing.add(chart)
            elements.append(drawing)

    doc.build(elements)
    return bio.getvalue()


def export_table(title: str, columns: list, rows: list, meta: dict) -> bytes:
    """Generic «как на экране» экспорт в PDF. columns=[{key,title,align?}], rows=[{key:value}]."""
    _register_fonts()
    styles = _get_styles()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)

    elements = []

    # Title + meta
    elements.append(Paragraph(title, styles['title']))
    meta_text = (
        f"Автор: {meta.get('author', '—')} &nbsp;&nbsp; "
        f"Сформирован: {meta.get('generated_at', datetime.utcnow().strftime('%d.%m.%Y %H:%M'))}"
    )
    elements.append(Paragraph(meta_text, styles['small']))
    elements.append(Spacer(1, 6))

    if not columns:
        elements.append(Paragraph('Нет данных', styles['normal']))
        doc.build(elements)
        return bio.getvalue()

    _ALIGN_MAP = {'start': TA_LEFT, 'center': TA_CENTER, 'end': TA_RIGHT}

    # Header row
    header_row = [Paragraph(col.get('title', col.get('key', '')), styles['header_cell']) for col in columns]
    data = [header_row]

    # Data rows
    for row in rows:
        cells = []
        for col in columns:
            key = col.get('key', '')
            val = row.get(key)
            align_key = col.get('align', 'start')
            ta = _ALIGN_MAP.get(align_key, TA_LEFT)
            cell_style = ParagraphStyle('GenCell', parent=styles['cell'], alignment=ta)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                cell_style = ParagraphStyle('GenCellR', parent=styles['cell_right'], alignment=ta if align_key != 'start' else TA_RIGHT)
            cells.append(Paragraph(_fmt_value(val), cell_style))
        data.append(cells)

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), styles['bold_font_name']),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BFBFBF')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)

    doc.build(elements)
    return bio.getvalue()


def export_kanban(title: str, columns: List[Dict], meta: dict) -> bytes:
    """Канбан в PDF. columns=[{status_title, cards:[{title, subtitle?, fields?:[{label,value}]}]}]"""
    _register_fonts()
    styles = _get_styles()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(
        bio, pagesize=landscape(A4),
        leftMargin=10*mm, rightMargin=10*mm, topMargin=12*mm, bottomMargin=10*mm,
    )
    elements = []
    elements.append(Paragraph(title, styles['title']))
    meta_text = (
        f"Автор: {meta.get('author', '—')} &nbsp;&nbsp; "
        f"Сформирован: {meta.get('generated_at', datetime.utcnow().strftime('%d.%m.%Y %H:%M'))}"
    )
    elements.append(Paragraph(meta_text, styles['small']))
    elements.append(Spacer(1, 8))

    if not columns:
        elements.append(Paragraph('Нет данных', styles['normal']))
        doc.build(elements)
        return bio.getvalue()

    font = styles['font_name']
    bold_font = styles['bold_font_name']

    # Распределяем колонки по ширине страницы landscape A4 ~ 277мм − 20мм margins = 257мм
    page_w = landscape(A4)[0] - 20*mm
    n_cols = len(columns)
    col_w = page_w / n_cols

    # Строим таблицу: 1 ряд заголовков + максимальное кол-во карточек
    max_cards = max((len(c.get('cards', [])) for c in columns), default=0)

    header_row = []
    for col in columns:
        p = Paragraph(col.get('status_title', ''), ParagraphStyle(
            'KanbanHeader', fontName=bold_font, fontSize=10, alignment=TA_CENTER,
            textColor=white, leading=13,
        ))
        header_row.append(p)

    data = [header_row]
    for card_i in range(max_cards):
        row = []
        for col in columns:
            cards = col.get('cards', [])
            if card_i < len(cards):
                card = cards[card_i]
                card_title = card.get('title', '')
                card_subtitle = card.get('subtitle', '')
                fields = card.get('fields') or []
                parts = [f'<b>{card_title}</b>']
                if card_subtitle:
                    parts.append(f'<font size="7" color="grey">{card_subtitle}</font>')
                for f in fields:
                    parts.append(f'<font size="7"><b>{f.get("label","")}</b>: {f.get("value","")}</font>')
                cell_text = '<br/>'.join(parts)
                p = Paragraph(cell_text, ParagraphStyle(
                    'KanbanCard', fontName=font, fontSize=8, leading=11, spaceAfter=2,
                ))
                row.append(p)
            else:
                row.append('')
        data.append(row)

    col_widths = [col_w] * n_cols
    table = Table(data, colWidths=col_widths, repeatRows=1)

    # Стиль: header синий, строки с отступами, сетка
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), bold_font),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BFBFBF')),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    # Чередование фонов строк
    for i in range(1, len(data)):
        if i % 2 == 0:
            ts.append(('BACKGROUND', (0, i), (-1, i), HexColor('#F7F9FC')))

    table.setStyle(TableStyle(ts))
    elements.append(table)

    doc.build(elements)
    return bio.getvalue()


async def export_dashboard(widget_results: List[Dict], config: Dict, meta: Dict) -> bytes:
    """Тип C — дашборд в PDF. Каждый виджет = таблица."""
    styles = _get_styles()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)

    elements = _header_paragraph('Дашборд', meta, styles)

    for idx, wr in enumerate(widget_results):
        widget = wr.get('widget', {})
        result = wr.get('result', {})

        if idx > 0:
            elements.append(Spacer(1, 12))
        elements.append(Paragraph(widget.get('title', 'Виджет'), styles['h2']))

        rows = result.get('rows', [])
        if not rows:
            elements.append(Paragraph('Нет данных', styles['normal']))
            continue

        # Виджет = таблица
        keys = [k for k in rows[0].keys() if not k.startswith('_')]
        headers = [_label_for(k) for k in keys]
        header_row = [Paragraph(h, styles['header_cell']) for h in headers]
        data = [header_row]
        for r in rows[:30]:  # max 30 строк на виджет
            cells = []
            for k in keys:
                v = r.get(k)
                if isinstance(v, (int, float)):
                    cells.append(Paragraph(_fmt_value(v), styles['cell_right']))
                else:
                    cells.append(Paragraph(_fmt_value(v), styles['cell']))
            data.append(cells)

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), styles['bold_font_name']),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#BFBFBF')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)

    doc.build(elements)
    return bio.getvalue()
