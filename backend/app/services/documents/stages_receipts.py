"""generate_document: contract_items context + advance-report receipts images.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
Wraps the whole block in the same try/except → structured
DOCUMENT_GENERATION_FAILED 500 as the original "Phase 26-U" comment describes.
"""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Cm as _Cm

from app.models.purchase import Purchase
from app.services.documents.doc_types import RECEIPTS_TABLE_MARKER
from app.services.documents.contexts import _build_contract_items_context

logger = logging.getLogger(__name__)


async def build_contract_items_and_receipts_context(
    context: dict, p: Purchase, db: AsyncSession, tpl: DocxTemplate, pid: int, doc_type: str,
) -> list:
    """Mutates `context` in place; returns receipt_png_paths (Phase 26-ggg:
    scoped outside the try in the original so the post-render receipts-table
    insert can see it even if nothing was appended here)."""
    receipt_png_paths: list = []
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
            # Phase 26-fff: одно превью PNG используется для нескольких InlineImage
            # с разной шириной — для разных layouts в шаблоне.
            #   default (6.5cm) → одиночная колонка/полный текст СЗ
            #   small (4.5cm)   → 2-колоночная таблица с узкими ячейками
            #   full  (14cm)    → отдельная страница на чек
            receipt_images = []        # default 6.5 cm — backward compat
            receipt_images_small = []  # 4.5 cm — для 2-col layouts
            receipt_images_full = []   # 14 cm — для full-width layouts
            receipt_png_paths = []     # Phase 26-ggg: пути PNG для post-render таблицы
            for _r in _receipts:
                try:
                    _png_bytes = _rrpng(_r)
                    _tmp = _tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    _tmp.write(_png_bytes)
                    _tmp.close()
                    receipt_png_paths.append(_tmp.name)
                    receipt_images.append(InlineImage(tpl, _tmp.name, width=_Cm(6.5)))
                    receipt_images_small.append(InlineImage(tpl, _tmp.name, width=_Cm(4.5)))
                    receipt_images_full.append(InlineImage(tpl, _tmp.name, width=_Cm(14)))
                except Exception as _re:
                    logging.getLogger(__name__).warning(f"render receipt {_r.id} skipped: {_re}")
            context["receipts"] = receipt_images
            context["receipt_images"] = receipt_images  # alias
            context["receipts_small"] = receipt_images_small
            context["receipts_full"] = receipt_images_full
            # Phase 26-ggg: sentinel-маркер. Пользователь ставит {{ receipts_table }}
            # в шаблон одним параграфом — после render текст становится
            # RECEIPTS_TABLE_MARKER, post-process находит и заменяет на
            # настоящую docx-таблицу 2-col с PNG чеков в каждой ячейке.
            # Решает проблему clip'а inline-images в узких ячейках/параграфах.
            context["receipts_table"] = RECEIPTS_TABLE_MARKER
            # Phase 26-LL: chunked в пары для таблицы 2 колонки в шаблоне СЗ
            receipt_pairs = []
            for _i in range(0, len(receipt_images_small), 2):
                _left = receipt_images_small[_i]
                _right = receipt_images_small[_i + 1] if _i + 1 < len(receipt_images_small) else None
                receipt_pairs.append({'left': _left, 'right': _right})
            context["receipt_pairs"] = receipt_pairs
            # Phase 26-RR: split на 2 потока для статичной таблицы 1×2 в шаблоне.
            # left/right берут МАЛЫЕ изображения (4.5 cm) — таблица 2-колоночная,
            # узкие ячейки. Старый шаблон с _Cm(6.5) клипал картинку и пользователь
            # видел пустую узкую полоску.
            context["left_receipts"] = receipt_images_small[::2]
            context["right_receipts"] = receipt_images_small[1::2]
        else:
            context["receipts"] = []
            context["receipt_images"] = []
            context["receipts_small"] = []
            context["receipts_full"] = []
            context["receipt_pairs"] = []
            context["left_receipts"] = []
            context["right_receipts"] = []
            context["receipts_table"] = ""  # marker отсутствует — paragraph будет пустой
            receipt_png_paths = []
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

    return receipt_png_paths
