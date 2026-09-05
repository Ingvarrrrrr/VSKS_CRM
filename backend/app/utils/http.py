"""HTTP response helpers shared across routers (Правило №6 — один источник истины)."""
from urllib.parse import quote


def content_disposition(filename: str) -> str:
    """RFC 5987 — кириллица в имени файла недопустима в latin-1 заголовке."""
    ascii_fallback = filename.encode('ascii', 'ignore').decode('ascii').strip() or 'export'
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"
