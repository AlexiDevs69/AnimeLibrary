from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "AnimeLibrary"
    debug: bool = False
    auto_create_tables: bool = False
    database_url: str = "postgresql+asyncpg://anime:anime@localhost:5432/anime_together"
    redis_url: str = "redis://localhost:6379/0"
    anilist_api_url: str = "https://graphql.anilist.co"
    anilibria_enabled: bool = True
    anilibria_api_url: str = "https://anilibria.top/api/v1"
    anilibria_sync_ttl_seconds: int = 6 * 60 * 60
    anilibria_max_results: int = 10
    anilibria_preferred_quality: int = 1080
    anilibria_hls_host_suffixes: Annotated[list[str], NoDecode] = [
        "libria.fun",
        "anilibria.top",
    ]
    kodik_api_url: str = "https://kodikapi.com"
    kodik_token: str = ""
    kodik_player_origins: Annotated[list[str], NoDecode] = ["https://kodik.info"]
    kodik_sync_ttl_seconds: int = 6 * 60 * 60
    kodik_max_translations: int = 8
    admin_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("kodik_player_origins", mode="before")
    @classmethod
    def split_kodik_player_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("anilibria_hls_host_suffixes", mode="before")
    @classmethod
    def split_anilibria_hls_host_suffixes(cls, value: object) -> object:
        if isinstance(value, str):
            return [suffix.strip().lower() for suffix in value.split(",") if suffix.strip()]
        return value

    @field_validator("anilibria_api_url")
    @classmethod
    def validate_anilibria_api_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or parsed.hostname != "anilibria.top":
            raise ValueError("ANILIBRIA_API_URL має бути https://anilibria.top/api/v1")
        if parsed.path.rstrip("/") != "/api/v1":
            raise ValueError("ANILIBRIA_API_URL має завершуватися на /api/v1")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ANILIBRIA_API_URL не повинен містити облікові дані або параметри")
        return cleaned

    @field_validator("anilibria_preferred_quality")
    @classmethod
    def validate_anilibria_preferred_quality(cls, value: int) -> int:
        if value not in {480, 720, 1080}:
            raise ValueError("ANILIBRIA_PREFERRED_QUALITY має бути 480, 720 або 1080")
        return value

    @field_validator("anilibria_hls_host_suffixes")
    @classmethod
    def validate_anilibria_hls_host_suffixes(cls, values: list[str]) -> list[str]:
        suffixes: list[str] = []
        for value in values:
            suffix = value.strip().lower().lstrip(".").rstrip(".")
            if not suffix or ":" in suffix or "/" in suffix:
                raise ValueError("ANILIBRIA_HLS_HOST_SUFFIXES містить некоректний домен")
            if suffix not in suffixes:
                suffixes.append(suffix)
        if not suffixes:
            raise ValueError("ANILIBRIA_HLS_HOST_SUFFIXES не може бути порожнім")
        return suffixes

    @field_validator("kodik_api_url")
    @classmethod
    def validate_kodik_api_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or parsed.hostname != "kodikapi.com":
            raise ValueError("KODIK_API_URL має бути https://kodikapi.com")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("KODIK_API_URL не повинен містити облікові дані або параметри")
        return cleaned

    @field_validator("kodik_player_origins")
    @classmethod
    def validate_kodik_player_origins(cls, values: list[str]) -> list[str]:
        origins: list[str] = []
        for value in values:
            parsed = urlparse(value.strip())
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("KODIK_PLAYER_ORIGINS мають бути HTTPS-origin адресами")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("KODIK_PLAYER_ORIGINS не повинні містити зайві частини URL")
            origin = f"https://{parsed.netloc}"
            if origin not in origins:
                origins.append(origin)
        return origins

    @field_validator("database_url", mode="after")
    @classmethod
    def use_async_postgres_driver(cls, value: str) -> str:
        # Render exposes postgresql://, while SQLAlchemy's async engine needs
        # the explicit asyncpg driver name.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
