from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import settings


class KodikError(RuntimeError):
    """A provider error safe to surface without leaking the API token."""


@dataclass(frozen=True, slots=True)
class KodikCandidate:
    provider_key: str
    provider_id: str
    player_link: str
    content_type: str
    season_number: int
    episodes_count: int
    translation_id: int | None
    translation_title: str | None
    translation_type: str | None


def infer_season_number(*titles: str | None) -> int:
    patterns = (
        r"\bseason\s*(\d{1,2})\b",
        r"\b(\d{1,2})(?:st|nd|rd|th)\s+season\b",
        r"\bs(\d{1,2})\b",
        r"\bсезон\s*(\d{1,2})\b",
    )
    for title in titles:
        if not title:
            continue
        normalized = " ".join(title.lower().split())
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                number = int(match.group(1))
                if 1 <= number <= 99:
                    return number
    return 1


def normalize_player_link(link: str) -> str:
    cleaned = link.strip()
    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Kodik повернув некоректне посилання на плеєр")
    if parsed.username or parsed.password:
        raise ValueError("Посилання на плеєр не повинно містити облікові дані")
    origin = f"https://{parsed.netloc}"
    if origin not in settings.kodik_player_origins:
        raise ValueError(f"Origin плеєра {origin} не входить до KODIK_PLAYER_ORIGINS")
    return urlunparse(parsed._replace(fragment=""))


def build_player_url(
    player_link: str,
    *,
    content_type: str,
    season_number: int,
    episode_number: int,
    translation_id: int | None,
) -> str:
    normalized = normalize_player_link(player_link)
    parsed = urlparse(normalized)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if content_type == "anime-serial":
        query.update(
            {
                "season": str(max(1, season_number)),
                "episode": str(max(1, episode_number)),
                "only_episode": "true",
            }
        )
    if translation_id is not None:
        query["translation_id"] = str(translation_id)
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def candidates_from_results(
    results: list[dict[str, Any]],
    *,
    titles: tuple[str | None, ...],
    anime_episodes_count: int | None,
) -> list[KodikCandidate]:
    inferred_season = infer_season_number(*titles)
    candidates: list[KodikCandidate] = []
    seen: set[str] = set()

    for result in results:
        content_type = str(result.get("type") or "").strip()
        if content_type not in {"anime-serial", "anime"}:
            continue
        provider_id = str(result.get("id") or "").strip()
        if not provider_id:
            continue
        try:
            player_link = normalize_player_link(str(result.get("link") or ""))
        except ValueError:
            continue

        translation = result.get("translation") or {}
        raw_translation_id = translation.get("id")
        try:
            translation_id = int(raw_translation_id) if raw_translation_id is not None else None
        except (TypeError, ValueError):
            translation_id = None
        translation_title = str(translation.get("title") or "").strip() or None
        translation_type = str(translation.get("type") or "").strip() or None

        try:
            last_season = max(1, int(result.get("last_season") or 1))
        except (TypeError, ValueError):
            last_season = 1
        season_number = min(inferred_season, last_season)

        provider_episode_count = (
            result.get("episodes_count")
            or result.get("last_episode")
            or anime_episodes_count
            or 1
        )
        try:
            provider_episode_count = max(1, min(int(provider_episode_count), 2000))
        except (TypeError, ValueError):
            provider_episode_count = 1
        if content_type == "anime":
            episodes_count = 1
            season_number = 1
        elif anime_episodes_count:
            episodes_count = max(1, min(int(anime_episodes_count), provider_episode_count, 2000))
        else:
            episodes_count = provider_episode_count

        provider_key = ":".join(
            (
                provider_id,
                str(translation_id or 0),
                str(season_number),
            )
        )
        if provider_key in seen:
            continue
        seen.add(provider_key)
        candidates.append(
            KodikCandidate(
                provider_key=provider_key,
                provider_id=provider_id,
                player_link=player_link,
                content_type=content_type,
                season_number=season_number,
                episodes_count=episodes_count,
                translation_id=translation_id,
                translation_title=translation_title,
                translation_type=translation_type,
            )
        )
        if len(candidates) >= settings.kodik_max_translations:
            break
    return candidates


async def search_by_mal_id(mal_id: int) -> list[dict[str, Any]]:
    if not settings.kodik_token:
        return []
    try:
        async with httpx.AsyncClient(
            base_url=settings.kodik_api_url,
            timeout=15.0,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                "/search",
                params={
                    "token": settings.kodik_token,
                    "mal_id": mal_id,
                    "limit": max(1, min(settings.kodik_max_translations * 2, 100)),
                },
            )
    except httpx.HTTPError:
        raise KodikError("Kodik API тимчасово недоступний") from None

    if response.status_code != 200:
        raise KodikError(f"Kodik API повернув HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise KodikError("Kodik API повернув некоректну відповідь") from None
    if not isinstance(payload, dict):
        raise KodikError("Kodik API повернув некоректну відповідь")
    results = payload.get("results") or []
    if not isinstance(results, list):
        raise KodikError("Kodik API повернув некоректний список результатів")
    return [item for item in results if isinstance(item, dict)]
