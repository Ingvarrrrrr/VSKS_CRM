"""export_dashboard_charts.py — общие фабрики графиков openpyxl.chart для
листов «Дашборд»/«Сводная» экспортов плана-графика и ФЭО (ПРАВИЛО №6:
построение графика — в одном месте, не второй раз по месту). Вынесено из
app.services.plan_graph_export_dashboard (владелец 08.10.2026) при добавлении
дашборда выгрузки ФЭО (владелец 20.10.2026, app.services.feo_export_summary),
чтобы не копировать создание BarChart/DoughnutChart.

Ничего не считает — ТОЛЬКО оформляет уже готовые Reference на ячейки,
которые передаёт вызывающий код."""
from __future__ import annotations

from typing import Optional, Sequence

try:
    from openpyxl.chart import BarChart, DoughnutChart, Series
except ImportError:  # pragma: no cover — openpyxl отсутствует, роутер уже отказал раньше
    pass


def build_bar_chart(
    *,
    title: str,
    cats_ref,
    data_refs: Sequence[tuple],
    bar_type: str = "col",
    stacked: bool = False,
    width: float = 16,
    height: float = 8,
    show_legend: bool = True,
    from_rows: bool = False,
):
    """BarChart (или `bar` — горизонтальный) с одной или несколькими сериями.

    `data_refs` — список (Reference, titles_from_data|series_title):
      - (ref, None) — одна серия БЕЗ подписи (titles_from_data=False,
        add_data) — как «Деньги по стадиям»/«общий итог по стадиям»;
      - (ref, "Подпись") — именованная серия (Series(ref, title=...)) — как
        накопительные столбцы по направлениям/видам, где на графике нужна
        легенда с названием каждой серии."""
    chart = BarChart()
    chart.type = bar_type
    if stacked:
        chart.grouping = "stacked"
        chart.overlap = 100
    chart.title = title
    chart.width, chart.height = width, height
    if not show_legend:
        chart.legend = None
    for ref, series_title in data_refs:
        if series_title is None:
            chart.add_data(ref, titles_from_data=False, from_rows=from_rows)
        else:
            chart.series.append(Series(ref, title=series_title))
    chart.set_categories(cats_ref)
    return chart


def build_doughnut_chart(*, title: str, cats_ref, data_ref, width: float = 16, height: float = 8):
    chart = DoughnutChart()
    chart.title = title
    chart.width, chart.height = width, height
    chart.add_data(data_ref, titles_from_data=False)
    chart.set_categories(cats_ref)
    return chart
