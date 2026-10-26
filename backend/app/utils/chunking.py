"""Разбивка длинных списков на порции — для SQL `WHERE col IN (...)`
с большим списком id (владелец, 26.10.2026: 53 797 товаров → один IN на
ВСЕ id разом ловил asyncpg "the number of query arguments cannot exceed
32767"). Переиспользовать эту функцию везде, где IN строится по списку,
который может вырасти на весь каталог/справочник (ПРАВИЛО №6 — не писать
свой цикл чанков в каждом месте)."""
from typing import Iterable, Iterator, List, TypeVar

T = TypeVar("T")

# asyncpg лимит — 32767 параметров на запрос. Берём с большим запасом,
# чтобы хватило места под остальные параметры того же запроса (там, где
# IN — не единственное условие).
DEFAULT_CHUNK_SIZE = 5000


def chunked(items: Iterable[T], size: int = DEFAULT_CHUNK_SIZE) -> Iterator[List[T]]:
    """Делит items на подряд идущие порции длиной ≤ size. Пустой items —
    ни одной порции (вызывающий код сам решает, что делать с пустым списком,
    как и раньше делали явные `if not ids: return`)."""
    if size <= 0:
        raise ValueError("size must be positive")
    buf: List[T] = []
    for item in items:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
