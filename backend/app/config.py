from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="SHIYI_")
    database_url: str = "sqlite:///./data/shiyi.db"
    data_dir: Path = Path("./data")
    public_url: str = "http://127.0.0.1:8765"
    frontend_dir: Path = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    secure_cookies: bool = False
    allow_registration: bool = False
    session_days: int = 30
    max_upload_mb: int = 15
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    allowed_origins: str = ""


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "media").mkdir(parents=True, exist_ok=True)
