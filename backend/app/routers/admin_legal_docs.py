"""Закрытый раздел «Документы» админки — внутренние документы по 152-ФЗ
(модель угроз, акт уровня защищённости, уведомление в РКН, приказы и т. п.),
которые не публикуются на сайте (решение владельца 08.10.2026, см.
legal/README.md и legal/CONTRACT.md). Публичные документы (политика,
согласие, оферта, cookie, реквизиты) открыты без входа — /legal/:slug
(app/routers/legal.py этим не занимается, они отдаются фронтендом из
frontend/src/legal/documents.generated.ts).

Список и содержимое документов — ЕДИНЫЙ реестр
app/services/internal_legal_docs.py (сгенерирован legal/build.py). Этот
роутер только проверяет доступ и отдаёт то, что реестр возвращает, — не
хранит и не пересчитывает список документов второй раз (ПРАВИЛО №6); slug
ищется исключительно по словарю реестра, без обращения к файловой системе,
поэтому произвольный slug не может прочитать файл за пределами реестра
(без path traversal).

Проверка доступа — require_role('superadmin', 'admin', 'account_owner'),
тот же кортеж ролей, что уже применяется в app/routers/legal.py::
list_personal_data_requests для другой account-level compliance-операции
по 152-ФЗ (список обращений субъектов персональных данных). Не
require_tab(...): права по tab_key настраиваются account_owner/admin через
UI «Роли и права» (app/routers/permissions.py) и могут быть делегированы
вниз по организационной иерархии — для документов, которые сами описывают
модель угроз и готовятся для уведомления в РКН, доступ должен определяться
только принадлежностью к административной роли, а не настраиваемым в
интерфейсе правом, которое легко выдать по ошибке.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth.jwt import require_role
from app.services.internal_legal_docs import get_internal_legal_doc, list_internal_legal_docs

router = APIRouter(prefix="/api/admin/legal-docs", tags=["admin-legal-docs"])

_require_admin = require_role('superadmin', 'admin', 'account_owner')


def _set_no_store(response: Response) -> None:
    # Внутренние документы (модель угроз и т. п.) не должны оседать ни в
    # кэше браузера/прокси, ни в поисковой индексации.
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"


@router.get("")
async def list_docs(response: Response, _admin=Depends(_require_admin)):
    _set_no_store(response)
    return list_internal_legal_docs()


@router.get("/{slug}")
async def get_doc(slug: str, response: Response, _admin=Depends(_require_admin)):
    doc = get_internal_legal_doc(slug)
    if doc is None:
        # app/errors.py::http_exception_handler строит JSONResponse заново и
        # берёт headers только из exc.headers — правки Response, сделанные ДО
        # raise (через _set_no_store(response)), в ответ по HTTPException не
        # попадают. Поэтому заголовок передаётся прямо в HTTPException.
        raise HTTPException(404, "Документ не найден", headers={"Cache-Control": "no-store"})
    _set_no_store(response)
    return doc
