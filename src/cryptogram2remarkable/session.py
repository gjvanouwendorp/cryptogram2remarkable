"""Herbruikbaar browserprofiel: eenmalig inloggen en de sessie controleren.

`login` draai je LOKAAL (met beeldscherm): er opent een browser, jij logt in bij
de Volkskrant/DPG, daarna kopieer je de profielmap naar de VPS. `check_session`
draait headless en faalt snel als het profiel niet meer is ingelogd.
"""
from __future__ import annotations

from .config import OVERVIEW_URL, Settings
from .errors import SessionExpiredError


def login(settings: Settings) -> None:
    from playwright.sync_api import sync_playwright

    settings.profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(settings.profile_dir), headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(OVERVIEW_URL)
        print("\nLog nu in het geopende browservenster in bij de Volkskrant.")
        input("Druk op Enter zodra je ingelogd bent (en een puzzel zichtbaar is)... ")
        ctx.close()
    print(f"Profiel opgeslagen in {settings.profile_dir}. "
          "Kopieer deze map naar de VPS (bv. met rsync).")


def check_session(settings: Settings) -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(settings.profile_dir), headless=True)
        page = ctx.new_page()
        try:
            page.goto(OVERVIEW_URL, wait_until="domcontentloaded", timeout=45_000)
            if "login.dpgmedia.nl" in page.url:
                return False
            return True
        finally:
            ctx.close()
