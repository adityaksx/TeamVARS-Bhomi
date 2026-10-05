from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BhoomiLens API"
    ai_provider: str = "mock"

    sarvam_api_key: str | None = None
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_model: str = "sarvam-105b"
    sarvam_digitise_enabled: bool = False
    sarvam_document_language: str = "en-IN"

    openmodel_api_key: str | None = None
    openmodel_base_url: str = "https://api.openmodel.ai"
    openmodel_model: str | None = None

    cors_origins: str = "http://localhost:3000"

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
