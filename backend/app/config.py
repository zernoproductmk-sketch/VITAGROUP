from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VITAGROUP OEE API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://vitagroup:vitagroup@db:5432/vitagroup"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Coverse
    coverse_api_token: str = ""
    coverse_api_base_url: str = "https://api.coverse.team"
    coverse_read_range_path: str = "/v1/documents/{document_id}/values"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
