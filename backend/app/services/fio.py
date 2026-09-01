"""Utilities for structured FIO (Фамилия Имя Отчество) handling."""


def compose_fio(last: str | None, first: str | None, middle: str | None) -> str | None:
    """Join name parts into a single string, skipping empty parts.

    Returns None if all parts are empty/None.
    """
    parts = [p.strip() for p in (last, first, middle) if p and p.strip()]
    return " ".join(parts) if parts else None


def split_fio(raw: str | None) -> tuple[str | None, str | None, str | None]:
    """Split a raw FIO string into (last, first, middle).

    Rules:
      - 3+ words → (w[0], w[1], rest joined)
      - 2 words  → (w[0], w[1], None)
      - 1 word   → (w[0], None, None)
      - empty    → (None, None, None)
    """
    if not raw or not raw.strip():
        return (None, None, None)
    words = raw.strip().split()
    if len(words) >= 3:
        return (words[0], words[1], " ".join(words[2:]))
    if len(words) == 2:
        return (words[0], words[1], None)
    return (words[0], None, None)


def resolve_user_name_input(
    last_name: str | None,
    first_name: str | None,
    middle_name: str | None,
    full_name: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Единая точка входа "ФИО одной строкой" → три поля, с full_name как
    ПРОИЗВОДНЫМ (пересобирается через compose_fio). Используется при любом
    создании/переименовании User (users.py create/update, Excel-импорт,
    /api/register, fleet_seed) — единственное правило, чтобы full_name
    никогда не расходился со структурированными полями.

    Приоритет:
      1. last_name и/или first_name переданы → они источник истины,
         любой переданный full_name ИГНОРИРУЕТСЯ (пересобирается из частей).
      2. Иначе, если дан только full_name (обратная совместимость со старыми
         клиентами/формами) — разбираем его через split_fio.
      3. Ничего не передано → (None, None, None, None).

    Возвращает (last_name, first_name, middle_name, full_name) — всегда
    синхронизированные между собой.
    """
    last = last_name.strip() if last_name and last_name.strip() else None
    first = first_name.strip() if first_name and first_name.strip() else None
    middle = middle_name.strip() if middle_name and middle_name.strip() else None
    if last or first:
        return (last, first, middle, compose_fio(last, first, middle))
    if full_name and full_name.strip():
        s_last, s_first, s_middle = split_fio(full_name)
        return (s_last, s_first, s_middle, compose_fio(s_last, s_first, s_middle))
    return (None, None, None, None)


def split_position_and_fio(
    raw: str | None,
    position: str | None = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Split a raw signatory string into (last, first, middle, position).

    Resolution order:
      1. If *position* is already provided — use it and parse only FIO from *raw*.
      2. If *raw* contains ":" — text before colon is the position, after is FIO.
      3. If *raw* has more than 3 words — first (n−3) words are the position,
         last 3 words are FIO.
      4. Otherwise — position is None, whole *raw* treated as FIO.

    Returns (last, first, middle, position).
    """
    if not raw or not raw.strip():
        return (None, None, None, position or None)

    raw = raw.strip()

    if position:
        last, first, middle = split_fio(raw)
        return (last, first, middle, position.strip() or None)

    if ":" in raw:
        pos_part, fio_part = raw.split(":", 1)
        last, first, middle = split_fio(fio_part.strip())
        return (last, first, middle, pos_part.strip() or None)

    words = raw.split()
    if len(words) > 3:
        pos_words = words[:-3]
        fio_words = words[-3:]
        pos_str = " ".join(pos_words)
        last, first, middle = split_fio(" ".join(fio_words))
        return (last, first, middle, pos_str or None)

    last, first, middle = split_fio(raw)
    return (last, first, middle, None)
