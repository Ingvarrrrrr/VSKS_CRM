"""Загрузка .docx-шаблона плана-графика и заполнение его через docxtpl.

Вынесено из app/routers/subsidy_plan_graph_export.py (Правило №5, рефакторинг
2026-09-08): POST .../plan-graph/template (загрузка шаблона),
GET .../plan-graph/export-docx (заполнение шаблона данными последней версии).
"""
import io
import os
from datetime import datetime

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None

TEMPLATE_DIR = "media/plan_graph_templates"


def template_path_for(subsidy_id: int) -> str:
    return os.path.join(TEMPLATE_DIR, f"subsidy_{subsidy_id}.docx")


async def save_plan_graph_template(subsidy_id: int, content: bytes) -> str:
    """Сохраняет загруженный .docx-шаблон на диск, возвращает путь."""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    dest = template_path_for(subsidy_id)
    with open(dest, "wb") as f:
        f.write(content)
    return dest


def render_plan_graph_docx(template_path: str, sub, latest_ver) -> io.BytesIO:
    """Заполняет .docx-шаблон контекстом субсидии/последней версии плана-графика.

    Args:
        template_path: путь к загруженному .docx-шаблону.
        sub: Subsidy.
        latest_ver: PlanGraphVersion|None — последняя версия (для items/planned/used).

    Returns:
        BytesIO с готовым .docx (позиция курсора — 0).

    Примечание: наличие docxtpl проверяет вызывающий роутер до вызова этой
    функции — второй проверки здесь нет, чтобы не дублировать исключение сверх
    существовавших в дорефакторинговом коде.
    """
    if latest_ver and latest_ver.snapshot:
        snap = latest_ver.snapshot
        items_ctx = snap.get("items", [])
        total_planned = snap.get("total_planned", 0)
        total_used = snap.get("total_used", 0)
    else:
        items_ctx = []
        total_planned = 0.0
        total_used = 0.0

    context = {
        "subsidy_name": sub.name,
        "subsidy_year": sub.year,
        "items": items_ctx,
        "total_planned": f"{total_planned:,.2f}",
        "total_used": f"{total_used:,.2f}",
        "total_residual": f"{total_planned - total_used:,.2f}",
        "export_date": datetime.now().strftime("%d.%m.%Y"),
    }

    doc = DocxTemplate(template_path)
    doc.render(context)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
