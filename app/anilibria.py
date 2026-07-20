from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings


class AniLibriaError(RuntimeError):
    pass


@dataclass(frozen=True)
class AniLibriaEpisode:
    number: int
    title: str | None
    stream_url: str
    duration_minutes: int | None


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def release_titles(release: dict[str, Any]) -> tuple[str, ...]:
    names = release.get("name") or release.get("names") or {}
    raw_names = (
        names.get("english") or names.get("en"),
        names.get("main") or names.get("ru"),
        names.get("alternative"),
    )
    prepared: list[str] = []
    for raw_name in raw_names:
        if not raw_name:
            continue
        for name in re.split(r"[,;/|]", str(raw_name)):
            cleaned = " ".join(name.split())
            if cleaned and cleaned not in prepared:
                prepared.append(cleaned)
    return tuple(prepared)


def release_match_score(
    release: dict[str, Any],
    *,
    titles: tuple[str | None, ...],
    year: int | None,
) -> float:
    wanted = [normalize_title(title) for title in titles if normalize_title(title)]
    available = [normalize_title(title) for title in release_titles(release)]
    if not wanted or not available:
        return 0.0

    score = max(
        1.0 if expected == candidate else SequenceMatcher(None, expected, candidate).ratio()
        for expected in wanted
        for candidate in available
    )
    raw_year = release.get("year")
    try:
        release_year = int(raw_year) if raw_year is not None else None
    except (TypeError, ValueError):
        release_year = None
    if year is not None and release_year is not None:
        score += 0.05 if release_year == year else -0.18
    return score


def select_release(
    releases: list[dict[str, Any]],
    *,
    titles: tuple[str | None, ...],
    year: int | None,
) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for release in releases:
        if release.get("is_blocked_by_copyrights") or release.get("is_blocked_by_geo"):
            continue
        score = release_match_score(release, titles=titles, year=year)
        if score >= 0.86:
            candidates.append((score, release))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def normalize_hls_url(value: str, *, host: str | None = None) -> str:
    cleaned = value.strip()
    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"
    elif cleaned.startswith("/") and host:
        cleaned = urljoin(f"https://{host.strip().strip('/')}/", cleaned.lstrip("/"))

    parsed = urlparse(cleaned)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    allowed = any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in settings.anilibria_hls_host_suffixes
    )
    if (
        parsed.scheme != "https"
        or not hostname
        or not allowed
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
        or not parsed.path.lower().endswith(".m3u8")
    ):
        raise ValueError("AniLibria повернула недозволене HLS-посилання")
    return cleaned


def _episode_items(release: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    episodes = release.get("episodes")
    if isinstance(episodes, list):
        return [item for item in episodes if isinstance(item, dict)], None

    player = release.get("player") or {}
    host = str(player.get("host") or "").strip() or None
    playlist = player.get("list") or player.get("playlist") or {}
    if isinstance(playlist, dict):
        return [item for item in playlist.values() if isinstance(item, dict)], host
    if isinstance(playlist, list):
        return [item for item in playlist if isinstance(item, dict)], host
    return [], host


def episodes_from_release(release: dict[str, Any]) -> list[AniLibriaEpisode]:
    items, legacy_host = _episode_items(release)
    prepared: list[AniLibriaEpisode] = []
    seen: set[int] = set()
    quality_fields = {
        1080: ("hls_1080", "fhd"),
        720: ("hls_720", "hd"),
        480: ("hls_480", "sd"),
    }
    preferred = settings.anilibria_preferred_quality
    quality_order = [preferred, *(quality for quality in (1080, 720, 480) if quality != preferred)]

    for item in items:
        raw_number = item.get("ordinal", item.get("episode", item.get("sort_order")))
        try:
            number_float = float(raw_number)
        except (TypeError, ValueError):
            continue
        number = int(number_float)
        if number < 1 or abs(number_float - number) > 0.001 or number in seen:
            continue

        legacy_hls = item.get("hls") if isinstance(item.get("hls"), dict) else {}
        stream_url = None
        for quality in quality_order:
            current_field, legacy_field = quality_fields[quality]
            raw_url = item.get(current_field) or legacy_hls.get(legacy_field)
            if not raw_url:
                continue
            try:
                stream_url = normalize_hls_url(str(raw_url), host=legacy_host)
            except ValueError:
                continue
            break
        if stream_url is None:
            continue

        raw_duration = item.get("duration")
        try:
            duration_seconds = float(raw_duration) if raw_duration is not None else 0
        except (TypeError, ValueError):
            duration_seconds = 0
        duration_minutes = (
            max(1, min(600, round(duration_seconds / 60))) if duration_seconds > 0 else None
        )
        title = str(item.get("name") or item.get("name_english") or "").strip() or None
        seen.add(number)
        prepared.append(
            AniLibriaEpisode(
                number=number,
                title=title,
                stream_url=stream_url,
                duration_minutes=duration_minutes,
            )
        )
    return sorted(prepared, key=lambda episode: episode.number)


def _payload_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data") or []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    raise AniLibriaError("AniLibria API повернув некоректний список релізів")


async def fetch_release_episodes(
    *,
    titles: tuple[str | None, ...],
    year: int | None,
) -> list[AniLibriaEpisode]:
    if not settings.anilibria_enabled:
        return []
    queries: list[str] = []
    for title in titles:
        cleaned = " ".join(str(title or "").split())
        if cleaned and cleaned not in queries:
            queries.append(cleaned)
    if not queries:
        return []

    releases: dict[int, dict[str, Any]] = {}
    try:
        async with httpx.AsyncClient(
            base_url=settings.anilibria_api_url,
            timeout=15.0,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": f"{settings.app_name}/1.0"},
        ) as client:
            selected = None
            for query in queries:
                response = await client.get(
                    "/anime/catalog/releases",
                    params={
                        "f[search]": query,
                        "page": 1,
                        "limit": settings.anilibria_max_results,
                    },
                )
                if response.status_code != 200:
                    raise AniLibriaError(
                        f"AniLibria API повернув HTTP {response.status_code}"
                    )
                try:
                    items = _payload_items(response.json())
                except ValueError:
                    raise AniLibriaError("AniLibria API повернув некоректну відповідь") from None
                for item in items:
                    try:
                        release_id = int(item.get("id"))
                    except (TypeError, ValueError):
                        continue
                    releases[release_id] = item
                selected = select_release(list(releases.values()), titles=titles, year=year)
                if selected is not None and release_match_score(
                    selected, titles=titles, year=year
                ) >= 1.0:
                    break

            if selected is None:
                selected = select_release(list(releases.values()), titles=titles, year=year)
            if selected is None:
                return []
            try:
                release_id = int(selected.get("id"))
            except (TypeError, ValueError):
                return []

            response = await client.get(
                f"/anime/releases/{release_id}",
                params={"include": "episodes"},
            )
            if response.status_code != 200:
                raise AniLibriaError(f"AniLibria API повернув HTTP {response.status_code}")
            try:
                release = response.json()
            except ValueError:
                raise AniLibriaError("AniLibria API повернув некоректну відповідь") from None
    except httpx.HTTPError:
        raise AniLibriaError("AniLibria API тимчасово недоступний") from None

    if not isinstance(release, dict):
        raise AniLibriaError("AniLibria API повернув некоректний реліз")
    if release.get("is_blocked_by_copyrights") or release.get("is_blocked_by_geo"):
        return []
    return episodes_from_release(release)
