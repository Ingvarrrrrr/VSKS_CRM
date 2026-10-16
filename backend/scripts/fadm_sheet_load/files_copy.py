"""--relink, шаг 3: документы двойника → новая закупка.

ПЕРЕНЕСЕНО в app/services/purchase_transfer/doc_transfer.py (ПРАВИЛО №6 —
задача «копирование закупок в другую субсидию»: тот же перенос файлов/чеков
нужен и штатному HTTP-эндпоинту POST /api/purchase-transfer/apply, второй
копии тут больше нет). Этот файл — тонкий ре-экспорт для существующих
импортов (`from .files_copy import DocCopyCounters, copy_purchase_documents`
в sheet_v2_enrich.py и других местах этого пакета).
"""
from app.services.purchase_transfer.doc_transfer import (  # noqa: F401
    DocCopyCounters,
    copy_purchase_documents,
)
