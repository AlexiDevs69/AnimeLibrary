from datetime import date, datetime, timedelta, timezone

from app.schemas import ProfileUpdateIn
from app.watch_tracking import (
    build_profile_achievements,
    calculate_streak,
    episode_is_completed,
    level_from_watch_seconds,
    rank_tiers_for_level,
    watch_credit_seconds,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def credit(**overrides: object) -> int:
    values = {
        "previous_at": NOW - timedelta(seconds=15),
        "previous_position": 100.0,
        "previous_playing": True,
        "same_session": True,
        "now": NOW,
        "position": 115.0,
        "playback_rate": 1.0,
        "visible": True,
    }
    values.update(overrides)
    return watch_credit_seconds(**values)  # type: ignore[arg-type]


def test_heartbeat_credits_real_playing_interval() -> None:
    assert credit() == 15


def test_heartbeat_rejects_pause_hidden_seek_and_stale_session() -> None:
    assert credit(previous_playing=False) == 0
    assert credit(visible=False) == 0
    assert credit(position=500.0) == 0
    assert credit(same_session=False) == 0
    assert credit(previous_at=NOW - timedelta(seconds=60)) == 0


def test_episode_completion_needs_position_and_real_watch_time() -> None:
    assert not episode_is_completed(
        watched_seconds=10,
        position=1_350,
        duration=1_400,
        ended=True,
    )
    assert not episode_is_completed(
        watched_seconds=900,
        position=700,
        duration=1_400,
        ended=False,
    )
    assert episode_is_completed(
        watched_seconds=900,
        position=1_300,
        duration=1_400,
        ended=False,
    )


def test_level_curve_uses_verified_minutes() -> None:
    first = level_from_watch_seconds(0)
    second = level_from_watch_seconds(50 * 60)
    assert first.level == 1
    assert first.xp == 0
    assert second.level == 2
    assert second.xp == 50
    assert len(rank_tiers_for_level(second.level)) == 15


def test_streak_counts_consecutive_real_watch_days() -> None:
    streak = calculate_streak(
        [
            (date(2026, 8, 5), 600),
            (date(2026, 8, 7), 600),
            (date(2026, 8, 8), 1_200),
            (date(2026, 8, 9), 900),
        ],
        today=date(2026, 8, 9),
    )
    assert streak.current_days == 3
    assert streak.longest_days == 3
    assert streak.today_seconds == 900
    assert streak.daily_goal_progress == 0.75


def test_achievements_expose_locked_and_unlocked_progress() -> None:
    achievements = build_profile_achievements(
        watch_seconds=3_600,
        completed_episodes=12,
        completed_titles=2,
        library_count=8,
        favorite_count=3,
        ratings_count=1,
        authored_wall_posts=0,
        current_streak=3,
    )
    by_key = {item.key: item for item in achievements}
    assert by_key["hour_one"].unlocked
    assert by_key["episode_10"].unlocked
    assert by_key["streak_3"].unlocked
    assert not by_key["completed_5"].unlocked


def test_profile_tags_are_deduplicated() -> None:
    profile = ProfileUpdateIn(
        display_name="Viewer",
        profile_tags=["night_owl", "night_owl", "critic", "hidden_gem_hunter"],
    )
    assert profile.profile_tags == ["night_owl", "critic", "hidden_gem_hunter"]
