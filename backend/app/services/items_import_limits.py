"""Лимит предпросмотра импорта позиций — ОДНА константа на ВСЕ пути (ПРАВИЛО
№6, владелец 14.10.2026, план item-tz-description.md): смарт-импорт (с pid и
без), маппинг-импорт (с pid и без) — Excel/Word/PDF/HTML. Раньше лимит был
захардкожен как `preview[:200]` в нескольких местах по отдельности — не
привязать к нему единое "total_in_file"/"truncated" без общей точки.
"""

IMPORT_PREVIEW_LIMIT = 200


def apply_import_preview_limit(rows: list) -> tuple[list, int, bool]:
    """Возвращает (обрезанные_строки, всего_в_файле, обрезано_ли).

    `rows` — ВСЕ распознанные строки файла (до обрезки). Обрезка — первые
    IMPORT_PREVIEW_LIMIT строк, остальные владелец загружает вторым файлом
    (жёлтая плашка на фронте, Этап Б)."""
    total = len(rows)
    truncated = total > IMPORT_PREVIEW_LIMIT
    return rows[:IMPORT_PREVIEW_LIMIT], total, truncated
