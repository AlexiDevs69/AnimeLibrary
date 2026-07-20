from app.crud import anime_payload, make_slug


def test_make_slug_has_stable_anilist_suffix() -> None:
    assert make_slug("Attack on Titan", 16498) == "attack-on-titan-16498"
    assert make_slug("進撃の巨人", 16498) == "anime-16498"


def test_anilist_payload_mapping() -> None:
    payload = anime_payload(
        {
            "id": 16498,
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
    assert payload["episodes_count"] == 25
    assert payload["slug"] == "shingeki-no-kyojin-16498"
    assert payload["genres"] == ["Action", "Drama"]
