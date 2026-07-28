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
