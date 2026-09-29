"""HTTP response helpers shared across routers (Правило №6 — один источник истины)."""
from urllib.parse import quote


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """RFC 5987 — кириллица в имени файла недопустима в latin-1 заголовке.

    `disposition` — 'attachment' (по умолчанию, как раньше) или 'inline'
    (открыть в браузере, а не скачать) — добавлено 2026-09-29 для
    purchase_files.py::view_file/download_file (баг РЕЕ-2026-00960: голый
    f'inline; filename=\"{{pf.filename}}\"' с кириллицей в имени валил
    Starlette UnicodeEncodeError на кодировке latin-1 заголовка). Один и тот
    же ascii_fallback + filename*=UTF-8'' для обоих режимов, второй
    RFC5987-хелпер не заводим (ПРАВИЛО №6)."""
    ascii_fallback = filename.encode('ascii', 'ignore').decode('ascii').strip() or 'export'
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"
