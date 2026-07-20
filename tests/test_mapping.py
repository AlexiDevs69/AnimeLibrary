from app.crud import (
    anime_payload,
    make_slug,
    official_youtube_episodes,
    streaming_episode_number,
    youtube_video_id,
)


def test_make_slug_has_stable_anilist_suffix() -> None:
    assert make_slug("Attack on Titan", 16498) == "attack-on-titan-16498"
    assert make_slug("進撃の巨人", 16498) == "anime-16498"


def test_anilist_payload_mapping() -> None:
    payload = anime_payload(
        {
            "id": 16498,
            "idMal": 16498,
            "title": {"romaji": "Shingeki no Kyojin", "english": "Attack on Titan"},
            "coverImage": {"extraLarge": "poster.jpg", "color": "#123456"},
            "bannerImage": "banner.jpg",
            "seasonYear": 2013,
            "status": "FINISHED",
            "episodes": 25,
            "duration": 24,
            "genres": ["Action", "Drama"],
            "averageScore": 84,
            "siteUrl": "https://anilist.co/anime/16498",
        }
    )

    assert payload["anilist_id"] == 16498
    assert payload["mal_id"] == 16498
    assert payload["episodes_count"] == 25
    assert payload["slug"] == "shingeki-no-kyojin-16498"
    assert payload["genres"] == ["Action", "Drama"]


def test_youtube_episode_filter_accepts_only_episode_links() -> None:
    item = {
        "streamingEpisodes": [
            {
                "title": "Episode 1 - The Beginning",
                "url": "https://www.youtube.com/watch?v=abcdefghijk",
                "thumbnail": "episode-1.jpg",
                "site": "YouTube",
            },
            {
                "title": "Episode 2 Preview",
                "url": "https://youtu.be/lmnopqrstuv",
                "site": "YouTube",
            },
            {
                "title": "Episode 3",
                "url": "https://example.com/watch/3",
                "site": "Other",
            },
        ]
    }

    assert official_youtube_episodes(item) == [(1, "abcdefghijk", "episode-1.jpg")]
    assert streaming_episode_number("EP. 12 — Finale") == 12
    assert streaming_episode_number("Episode 7 - Eclipse") == 7
    assert streaming_episode_number("Official trailer") is None
    assert youtube_video_id("https://youtu.be/abcdefghijk?t=4") == "abcdefghijk"
    assert youtube_video_id("https://example.com/abcdefghijk") is None
