from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from app.schemas import (
    ProfileAchievementOut,
    ProfileLevelOut,
    ProfileRankTierOut,
    ProfileStreakOut,
)

HEARTBEAT_TIMEOUT_SECONDS = 45
MAX_CREDIT_PER_HEARTBEAT_SECONDS = 30
XP_SECONDS = 60
DAILY_GOAL_SECONDS = 20 * 60
RANK_TIERS: tuple[tuple[int, str], ...] = (
    (1, "newcomer"),
    (3, "explorer"),
    (5, "viewer"),
    (8, "enthusiast"),
    (12, "otaku"),
    (16, "senpai"),
    (22, "curator"),
    (30, "archivist"),
    (40, "kitsune"),
    (52, "yokai"),
    (65, "ronin"),
    (80, "shogun"),
    (100, "celestial"),
    (125, "legend"),
    (150, "anime_master"),
)


def watch_credit_seconds(
    *,
    previous_at: datetime | None,
    previous_position: float,
    previous_playing: bool,
    same_session: bool,
    now: datetime,
    position: float,
    playback_rate: float,
    visible: bool,
) -> int:
    """Return server-approved real viewing seconds for one heartbeat interval."""
    if (
        previous_at is None
        or not previous_playing
        or not same_session
        or not visible
    ):
        return 0

    elapsed = (now - previous_at).total_seconds()
    if elapsed <= 0 or elapsed > HEARTBEAT_TIMEOUT_SECONDS:
        return 0

    position_delta = position - previous_position
    if position_delta < 0.35:
        return 0

    # Seeking far ahead is progress, not watched time. The tolerance covers
    # player event jitter, buffering recovery, and legitimate 2x playback.
    maximum_natural_delta = elapsed * max(1.0, playback_rate) * 1.8 + 5
    if position_delta > maximum_natural_delta:
        return 0

    return max(0, round(min(elapsed, MAX_CREDIT_PER_HEARTBEAT_SECONDS)))


def episode_is_completed(
    *,
    watched_seconds: float,
    position: float,
    duration: float | None,
    ended: bool,
) -> bool:
    if duration is None or duration < 30:
        return False
    reached_ending = ended or position >= duration * 0.9
    required_watch = max(60.0, min(duration * 0.6, duration - 120.0))
    return reached_ending and watched_seconds >= required_watch


def level_threshold(level: int) -> int:
    """XP required to start a level. Level 1 starts at zero XP."""
    step = max(0, level - 1)
    return 5 * step**2 + 20 * step


def rank_key_for_level(level: int) -> str:
    current = RANK_TIERS[0][1]
    for minimum, key in RANK_TIERS:
        if level < minimum:
            break
        current = key
    return current


def rank_tiers_for_level(level: int) -> list[ProfileRankTierOut]:
    current_key = rank_key_for_level(level)
    return [
        ProfileRankTierOut(
            key=key,
            min_level=minimum,
            unlocked=level >= minimum,
            current=key == current_key,
        )
        for minimum, key in RANK_TIERS
    ]


def level_from_watch_seconds(total_watch_seconds: float) -> ProfileLevelOut:
    xp = max(0, int(total_watch_seconds // XP_SECONDS))
    completed_steps = max(0, int((-20 + math.sqrt(400 + 20 * xp)) / 10))
    level = completed_steps + 1
    current_level_xp = level_threshold(level)
    next_level_xp = level_threshold(level + 1)
    span = max(1, next_level_xp - current_level_xp)
    progress = min(1.0, max(0.0, (xp - current_level_xp) / span))
    current_tier_index = max(
        index
        for index, (minimum, _) in enumerate(RANK_TIERS)
        if level >= minimum
    )
    rank_level, rank_key = RANK_TIERS[current_tier_index]
    next_rank = (
        RANK_TIERS[current_tier_index + 1]
        if current_tier_index + 1 < len(RANK_TIERS)
        else None
    )
    virtual_level = level + progress
    rank_progress = (
        min(1.0, max(0.0, (virtual_level - rank_level) / (next_rank[0] - rank_level)))
        if next_rank
        else 1.0
    )
    return ProfileLevelOut(
        level=level,
        xp=xp,
        current_level_xp=current_level_xp,
        next_level_xp=next_level_xp,
        progress=progress,
        rank_key=rank_key,
        rank_level=rank_level,
        next_rank_key=next_rank[1] if next_rank else None,
        next_rank_level=next_rank[0] if next_rank else None,
        rank_progress=rank_progress,
    )


def calculate_streak(
    daily_rows: Iterable[tuple[date, float]],
    *,
    today: date,
) -> ProfileStreakOut:
    watched_by_date = {
        watch_date: max(0, round(watched_seconds))
        for watch_date, watched_seconds in daily_rows
        if watched_seconds > 0
    }
    watched_dates = sorted(watched_by_date)
    longest = 0
    running = 0
    previous: date | None = None
    for watch_date in watched_dates:
        running = running + 1 if previous and watch_date == previous + timedelta(days=1) else 1
        longest = max(longest, running)
        previous = watch_date

    latest = watched_dates[-1] if watched_dates else None
    current = 0
    if latest and latest >= today - timedelta(days=1):
        cursor = latest
        watched_set = set(watched_dates)
        while cursor in watched_set:
            current += 1
            cursor -= timedelta(days=1)

    today_seconds = watched_by_date.get(today, 0)
    return ProfileStreakOut(
        current_days=current,
        longest_days=longest,
        today_seconds=today_seconds,
        daily_goal_seconds=DAILY_GOAL_SECONDS,
        daily_goal_progress=min(1.0, today_seconds / DAILY_GOAL_SECONDS),
    )


def build_profile_achievements(
    *,
    watch_seconds: int,
    completed_episodes: int,
    completed_titles: int,
    library_count: int,
    favorite_count: int,
    ratings_count: int,
    authored_wall_posts: int,
    current_streak: int,
) -> list[ProfileAchievementOut]:
    definitions = (
        ("first_minute", "watch", "seconds", watch_seconds, 60),
        ("hour_one", "watch", "seconds", watch_seconds, 3_600),
        ("watch_10_hours", "watch", "seconds", watch_seconds, 36_000),
        ("watch_50_hours", "watch", "seconds", watch_seconds, 180_000),
        ("episode_10", "watch", "count", completed_episodes, 10),
        ("episode_50", "watch", "count", completed_episodes, 50),
        ("completed_5", "library", "count", completed_titles, 5),
        ("library_25", "library", "count", library_count, 25),
        ("favorites_10", "library", "count", favorite_count, 10),
        ("critic_10", "community", "count", ratings_count, 10),
        ("wall_writer", "community", "count", authored_wall_posts, 10),
        ("streak_3", "streak", "days", current_streak, 3),
        ("streak_7", "streak", "days", current_streak, 7),
    )
    return [
        ProfileAchievementOut(
            key=key,
            category=category,
            unit=unit,
            current=round(current),
            target=target,
            unlocked=current >= target,
        )
        for key, category, unit, current, target in definitions
    ]
