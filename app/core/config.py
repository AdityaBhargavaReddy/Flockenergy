"""Application configuration management via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Urja API Gateway."""

    # Upstream portal settings
    urja_portal_url: str = "https://urja-ops.flockenergy.tech"
    urja_username: str = "operator@urja.local"
    urja_password: str = "urja-ops-2026"

    # In-memory cache & sync configuration
    cache_ttl_seconds: int = 300  # 5 minutes
    sync_on_startup: bool = True

    # Server runtime settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    # Upstream HTTP client tuning
    request_timeout_seconds: float = 20.0
    max_retries: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
