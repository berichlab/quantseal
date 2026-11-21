"""Runtime configuration loaded from environment variables and persisted settings."""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QUANTSEAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Security & Access
    admin_password: str = Field(default="", description="Admin password for dashboard and API auth")
    secret_key: str = Field(default="", description="HMAC signing secret for session cookies")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Storage
    data_dir: str = Field(default="./data")
    database_url: str = Field(default="")

    # First-boot demo
    auto_demo: bool = Field(default=True)

    # Market defaults
    default_market_preset: str = Field(default="us_equities")
    default_symbols: str = Field(
        default="SPY,QQQ,IWM,XLK,XLF,XLE,XLV,XLI,XLP,XLY,GLD,TLT"
    )

    # BYOK LLM
    llm_provider: str = Field(default="none")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_base_url: str = Field(default="")

    # 24/7 Background Scheduler
    scheduler_enabled: bool = Field(default=True)
    shadow_cron: str = Field(default="0 22 * * 1-5")
    campaign_cron: str = Field(default="")

    # Notifications
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    discord_webhook_url: str = Field(default="")
    generic_webhook_url: str = Field(default="")

    # External MCP Connectors (HTTP enabled; local stdio disabled by default for VPS safety)
    allow_stdio_mcp: bool = Field(default=False)

    def resolved_data_dir(self) -> Path:
        path = Path(self.data_dir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolved_database_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        db_path = self.resolved_data_dir() / "quantseal.db"
        return f"sqlite:///{db_path}"

    def resolved_secret_key(self) -> str:
        if self.secret_key.strip():
            return self.secret_key.strip()
        key_file = self.resolved_data_dir() / ".secret_key"
        if key_file.exists():
            stored = key_file.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        generated = secrets.token_hex(32)
        key_file.write_text(generated, encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return generated

    def default_symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.default_symbols.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
