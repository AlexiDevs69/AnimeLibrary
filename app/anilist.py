from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


ANIME_SEARCH_QUERY = """
query AnimeSearch($search: String, $page: Int!, $perPage: Int!, $sort: [MediaSort]) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, search: $search, sort: $sort, isAdult: false) {
      id
      title { romaji english native }
      description(asHtml: false)
      coverImage { extraLarge large color }
      bannerImage
      seasonYear
      status
      episodes
      duration
      genres
      averageScore
      siteUrl
    }
  }
}
"""


class AniListError(RuntimeError):
    pass


async def fetch_anime(
    search: str | None = None,
    *,
    page: int = 1,
    per_page: int = 24,
) -> list[dict[str, Any]]:
    variables = {
        "search": search or None,
        "page": page,
        "perPage": min(max(per_page, 1), 50),
        "sort": ["SEARCH_MATCH"] if search else ["TRENDING_DESC", "POPULARITY_DESC"],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                settings.anilist_api_url,
                json={"query": ANIME_SEARCH_QUERY, "variables": variables},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AniListError("AniList тимчасово недоступний") from exc

    payload = response.json()
    if payload.get("errors"):
        message = payload["errors"][0].get("message", "AniList повернув помилку")
        raise AniListError(message)

    return payload.get("data", {}).get("Page", {}).get("media", [])

