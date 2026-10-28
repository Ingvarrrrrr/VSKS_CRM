"""«Без НМЦД» → «Не определена» (владелец, 28.10.2026, TASKS.md: пакет жалоб
28.10, пункт «без НМЦД» → «Не определена»).

Повод: выбор «Опубликовать без НМЦД» (PublishRequest.no_nmcd,
app/routers/publications.py) уже не шлёт НМЦД в SOAP-пакет Фабриканту —
app.services.publications_fabrikant_soap._initial_sum_xml пропускает элемент
`<pnc:initialSumInfo>` целиком, когда `payload["no_nmcd"]` истинно. Но
приложенные к той же публикации docx-документы («Документация.docx» и
другие файлы пакета Фабриканта, app.services.documents.fabrikant_package)
до этой правки продолжали печатать настоящую НМЦД (или 0/"0,00") независимо
от этого выбора — несогласованно с тем, что реально уходит на площадку.

Единственная функция-источник (ПРАВИЛО №6): переопределяет ВСЕ три алиаса
одного значения НМЦД (total_nmcd/total_nmck/nmck — см. docstring
contexts_build.py::build_base_context_part1 про «Phase 19: total_nmcd —
новое каноническое имя») ОДНИМ местом. Второй такой проверки флага в
fabrikant_package.py заводить не нужно — вызывается оттуда один раз, сразу
после того как total_nmcd/total_nmck/nmck уже посчитаны обычным путём.
"""

NMCD_VARIABLE_KEYS = ("total_nmcd", "total_nmck", "nmck")

# Та же константа, что в doc_types.py (единственный источник текста — ПРАВИЛО №6).
from .doc_types import NMCD_UNDETERMINED_TEXT  # noqa: F401 — реэкспорт для вызывающих


def apply_no_nmcd_override(context: dict, no_nmcd: bool) -> None:
    """Если `no_nmcd` истинно — все переменные НМЦД (NMCD_VARIABLE_KEYS)
    в `context` становятся ровно NMCD_UNDETERMINED_TEXT ("Не определена").
    Иначе — context не трогается.

    Мутирует `context` на месте (тот же приём, что у add_*_context в
    contexts_extra.py), ничего не возвращает.
    """
    if not no_nmcd:
        return
    for key in NMCD_VARIABLE_KEYS:
        context[key] = NMCD_UNDETERMINED_TEXT
