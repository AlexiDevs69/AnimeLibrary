from urllib.parse import parse_qs, urlparse

import pytest

from app.kodik import (
    build_player_url,
    candidates_from_results,
    infer_season_number,
    normalize_player_link,
)


def test_normalize_player_link_accepts_only_allowlisted_https_origin() -> None:
    assert normalize_player_link("//kodik.info/serial/123/abc/720p") == (
        "https://kodik.info/serial/123/abc/720p"
    )
    with pytest.raises(ValueError):
        normalize_player_link("https://attacker.example/serial/123")
    with pytest.raises(ValueError):
        normalize_player_link("http://kodik.info/serial/123")


def test_build_player_url_locks_episode_and_translation() -> None:
    url = build_player_url(
        "//kodik.info/serial/123/abc/720p?existing=1",
        content_type="anime-serial",
        season_number=4,
        episode_number=5,
        translation_id=609,
    )
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "kodik.info"
    assert parse_qs(parsed.query) == {
        "existing": ["1"],
        "season": ["4"],
        "episode": ["5"],
        "only_episode": ["true"],
        "translation_id": ["609"],
    }


def test_candidates_are_compact_and_mapped_to_anilist_season() -> None:
    results = [
        {
            "id": "video-123456",
            "type": "anime-serial",
            "link": "//kodik.info/serial/12345/abcdef/720p",
            "last_season": 4,
            "episodes_count": 28,
            "translation": {"id": 609, "title": "UA Team", "type": "voice"},
        }
    ]
    candidates = candidates_from_results(
        results,
        titles=("Attack on Titan Season 4", "Shingeki no Kyojin Season 4"),
        anime_episodes_count=16,
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider_key == "video-123456:609:4"
    assert candidate.season_number == 4
    assert candidate.episodes_count == 16
    assert candidate.translation_title == "UA Team"


def test_infer_season_number_defaults_to_first_season() -> None:
    assert infer_season_number("Attack on Titan") == 1
    assert infer_season_number("Attack on Titan 3rd Season") == 3
