import pytest

from app.anilibria import (
    episodes_from_release,
    normalize_hls_url,
    normalize_title,
    select_release,
)


def test_normalize_title_ignores_case_and_punctuation() -> None:
    assert normalize_title("Attack on Titan: Final Season") == (
        "attack on titan final season"
    )


def test_select_release_requires_a_confident_title_and_honors_blocks() -> None:
    releases = [
        {
            "id": 1,
            "name": {"english": "Boruto: Naruto Next Generations"},
            "year": 2017,
        },
        {
            "id": 2,
            "name": {"english": "Naruto"},
            "year": 2002,
            "is_blocked_by_copyrights": True,
        },
        {
            "id": 3,
            "name": {"english": "Naruto", "main": "Наруто"},
            "year": 2002,
        },
    ]
    selected = select_release(releases, titles=("Naruto", "NARUTO"), year=2002)
    assert selected is not None
    assert selected["id"] == 3


def test_normalize_hls_url_allows_only_known_https_cdn() -> None:
    assert normalize_hls_url(
        "/videos/20/1/1080/master.m3u8",
        host="cache.libria.fun",
    ) == "https://cache.libria.fun/videos/20/1/1080/master.m3u8"
    with pytest.raises(ValueError):
        normalize_hls_url("https://attacker.example/episode.m3u8")
    with pytest.raises(ValueError):
        normalize_hls_url("http://cache.libria.fun/episode.m3u8")


def test_episodes_from_current_v1_release_prefers_1080() -> None:
    release = {
        "episodes": [
            {
                "id": "episode-1",
                "ordinal": 1,
                "name": "Пролог",
                "duration": 1432,
                "hls_480": "https://cache.libria.fun/videos/1/480/index.m3u8",
                "hls_720": "https://cache.libria.fun/videos/1/720/index.m3u8",
                "hls_1080": "https://cache.libria.fun/videos/1/1080/index.m3u8",
            },
            {
                "id": "special",
                "ordinal": 1.5,
                "hls_1080": "https://cache.libria.fun/videos/1-5/1080/index.m3u8",
            },
        ]
    }
    episodes = episodes_from_release(release)
    assert len(episodes) == 1
    assert episodes[0].number == 1
    assert episodes[0].title == "Пролог"
    assert episodes[0].duration_minutes == 24
    assert episodes[0].stream_url.endswith("/1080/index.m3u8")


def test_episodes_from_legacy_v3_release_is_supported_during_transition() -> None:
    release = {
        "player": {
            "host": "cache.libria.fun",
            "list": {
                "1": {
                    "episode": 1,
                    "hls": {
                        "hd": "/videos/20/1/720/index.m3u8",
                        "sd": "/videos/20/1/480/index.m3u8",
                    },
                }
            },
        }
    }
    episodes = episodes_from_release(release)
    assert len(episodes) == 1
    assert episodes[0].stream_url.endswith("/720/index.m3u8")
