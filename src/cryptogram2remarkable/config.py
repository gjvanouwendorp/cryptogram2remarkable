"""Configuratie via environment variables (prefix C2RM_). Zie .env.example.

Secrets (VK-sessie, reMarkable-token) zitten NIET hier: de VK-sessie leeft in de
Playwright-profielmap, het reMarkable-token in de rmapi-config van de gebruiker.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bevestigde URL's (live vastgesteld 2026-07-04).
OVERVIEW_URL = "https://www.volkskrant.nl/puzzels/ontdekken/cryptogram~genre23"
WIDGET_HOST = "web.braintainment.com"
# De krantenpuzzel draait op deze customerid/variatie (i.t.t. de dagelijkse 'aldagpremium').
KRANT_CUSTOMERID = "volkskrant"
KRANT_PUZZLEVARIATION = "weekendPuzzlecrypto"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="C2RM_", env_file=".env", extra="ignore")

    profile_dir: Path = Field(default=Path("./profile"))
    # Draagbare sessie (cookies als platte JSON). OS-onafhankelijk, i.t.t. de
    # OS-versleutelde cookies in het Chrome-profiel — dit is wat je naar de VPS
    # kopieert.
    session_file: Path = Field(default=Path("./session.json"))
    data_dir: Path = Field(default=Path("./data"))
    rm_folder: str = Field(default="/Cryptogrammen")
    layout: str = Field(default="single_page")

    # Browser: echte Chrome tegen Akamai bot-detectie. Leeg = Playwright-Chromium.
    browser_channel: str = Field(default="chrome")
    headless: bool = Field(default=True)
    timezone: str = Field(default="Europe/Amsterdam")
    log_level: str = Field(default="INFO")

    notify_email: str = Field(default="")
    smtp_url: str = Field(default="")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings()
