"""Read-only прогон поиска похожих карточек каталога (owner, 27.10.2026,
пилот product_merge) — печатает группы для `q`, НИЧЕГО не пишет в БД. Удобно
прогнать на копии прода перед тем, как давать кнопку «похожие товары» в UI.

Запуск: python -m scripts.similar_groups_report --q огнетуш [--limit 20]
"""
import argparse
import asyncio

from app.database import async_session
from app.services.product_similar import find_similar_groups


async def main(q: str, limit: int) -> None:
    async with async_session() as db:
        groups = await find_similar_groups(db, q, limit_groups=limit)
        print(f"Запрос «{q}»: {len(groups)} групп(ы)\n")
        for g in groups:
            print(f"=== brand={g.brand!r} base_model={g.base_model!r} confidence={g.confidence} "
                  f"match_key={g.match_key} suggested_winner={g.suggested_winner_id} ===")
            for c in g.cards:
                marker = " <- winner" if c.id == g.suggested_winner_id else ""
                same_store = " [тот же магазин, что winner]" if c.same_store_as_winner else ""
                print(
                    f"  #{c.id} {c.name!r} | manufacturer={c.manufacturer!r} price={c.price} "
                    f"contractor_id={c.contractor_id} history={c.history_count} "
                    f"photo={c.has_photo} desc={c.has_description} diff={c.diff_tokens}{marker}{same_store}"
                )
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", required=True, help="подстрока названия (ILIKE), от 3 символов")
    parser.add_argument("--limit", type=int, default=50, help="максимум групп")
    args = parser.parse_args()
    asyncio.run(main(args.q, args.limit))
