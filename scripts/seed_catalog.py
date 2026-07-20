from __future__ import annotations

import argparse
import asyncio

from app.anilist import fetch_anime
from app.crud import cache_anime_batch
from app.database import AsyncSessionLocal


async def seed(pages: int, per_page: int) -> None:
    total = 0
    async with AsyncSessionLocal() as db:
        for page in range(1, pages + 1):
            items = await fetch_anime(page=page, per_page=per_page)
            cached = await cache_anime_batch(db, items)
            total += len(cached)
            print(f"Page {page}/{pages}: cached {len(cached)} anime")
    print(f"Done: {total} catalog entries cached")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache popular AniList anime in PostgreSQL")
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--per-page", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.pages <= 100:
        parser.error("--pages must be between 1 and 100")
    if not 1 <= args.per_page <= 50:
        parser.error("--per-page must be between 1 and 50")
    asyncio.run(seed(args.pages, args.per_page))


if __name__ == "__main__":
    main()

