"""Единая точка выбора disposition/media_type при отдаче ЗАГРУЖЕННОГО
ПОЛЬЗОВАТЕЛЕМ файла (Правило №6 — один механизм, не плодить по роутеру).

Повод (аудит безопасности 2026-10-20): purchase_files.py::view_file отдавал
файл с Content-Disposition: inline и media_type = mime_type КЛИЕНТА (поле
file.content_type из запроса на загрузку, не проверено сервером). Загруженный
.html (ALLOWED_MIME содержит "text/html" — для HTML-чеков proverkacheka.com)
открывался в браузере КАК СТРАНИЦА САЙТА: встроенный <script> исполнялся в
origin приложения (доступ к cookie gala_session и т.д.). image/svg+xml несёт
тот же риск (<script> внутри SVG).

Правило: inline — ТОЛЬКО для безопасного списка (растровые изображения +
PDF, которые браузер показывает, а не исполняет как HTML/JS). Для всего
остального — всегда attachment И media_type подменяется на
application/octet-stream, даже если вызывающий код просил inline: это и
подавляет MIME-сниффинг у старых браузеров, и не даёт будущей правке molча
вернуть inline для опасного типа.
"""
from fastapi.responses import FileResponse

from app.utils.http import content_disposition as _content_disposition

# Показываются В БРАУЗЕРЕ как есть (растровые изображения не исполняют код;
# PDF — через встроенный PDF-вьюер, не HTML-парсер страницы).
SAFE_INLINE_MIME = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "application/pdf",
}


def resolve_file_disposition(mime_type: str | None, requested: str = "attachment") -> tuple[str, str]:
    """(disposition, media_type) для заголовков ответа.

    - requested="inline" уважается ТОЛЬКО если mime_type в SAFE_INLINE_MIME —
      иначе понижается до "attachment".
    - media_type вне SAFE_INLINE_MIME всегда подменяется на
      application/octet-stream (в т.ч. под attachment) — text/html,
      image/svg+xml, и любой непредусмотренный тип никогда не уходят клиенту
      с их исходным Content-Type.
    """
    mime = mime_type or "application/octet-stream"
    if mime in SAFE_INLINE_MIME:
        disposition = "inline" if requested == "inline" else "attachment"
        return disposition, mime
    return "attachment", "application/octet-stream"


def safe_file_response(
    filepath: str,
    filename: str,
    mime_type: str | None,
    requested_disposition: str = "attachment",
) -> FileResponse:
    """FileResponse с безопасными disposition/media_type + nosniff.

    `filename` — оригинальное имя (для Content-Disposition), не меняется
    независимо от того, подменён ли media_type — пользователь должен видеть
    своё имя файла при скачивании.
    """
    disposition, media_type = resolve_file_disposition(mime_type, requested_disposition)
    return FileResponse(
        filepath,
        media_type=media_type,
        headers={
            "Content-Disposition": _content_disposition(filename, disposition),
            "X-Content-Type-Options": "nosniff",
        },
    )
