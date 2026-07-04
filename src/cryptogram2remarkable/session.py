"""Herbruikbaar browserprofiel: eenmalig inloggen en de sessie controleren.

De DPG-login zit achter Akamai bot-detectie die ELKE door Playwright/patchright
bestuurde browser weigert (HTTP 406) — ook echte Chrome, want de CDP-besturing
is detecteerbaar. Daarom automatiseren we de login NIET: `login` start een gewone
Chrome als los proces (geen automation, geen CDP) die naar de profielmap schrijft.
Jij logt in als mens (dat werkt wél), en de sessie belandt in `./profile`.

Het wekelijkse scrapen raakt daarna alleen volkskrant.nl/braintainment — domeinen
die een geautomatiseerde (patchright) browser wél toelaten.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .browser import launch_persistent
from .config import OVERVIEW_URL, Settings
from .errors import C2RMError


def _chrome_binary() -> str:
    if sys.platform == "darwin":
        mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(mac).exists():
            return mac
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise C2RMError(
        "Google Chrome niet gevonden. Installeer Chrome (VPS: google-chrome-stable)."
    )


def login(settings: Settings) -> None:
    profile = settings.profile_dir.absolute()
    profile.mkdir(parents=True, exist_ok=True)
    chrome = _chrome_binary()

    # Losse, MENSELIJK bestuurde Chrome: geen --enable-automation, geen CDP.
    args = [
        chrome,
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        OVERVIEW_URL,
    ]
    print("Er opent een gewone Chrome met een eigen profielmap.")
    print("1) Log in bij de Volkskrant en open een cryptogram.")
    print("2) SLUIT daarna het Chrome-venster (belangrijk: dan wordt de sessie opgeslagen).")
    proc = subprocess.Popen(args)
    input("\nDruk op Enter zodra je bent ingelogd én Chrome hebt gesloten... ")
    if proc.poll() is None:
        proc.terminate()  # vangnet als het venster nog openstaat
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"\nProfiel opgeslagen in {profile}.")

    # Exporteer een draagbare sessie (platte cookies) voor de VPS.
    export_session(settings)
    print(f"Draagbare sessie geschreven naar {settings.session_file}.")
    print("Kopieer ALLEEN dit bestand naar de VPS (OS-onafhankelijk), bv.:")
    print(f"  rsync -a {settings.session_file} vps:/opt/cryptogram2remarkable/session.json")


def export_session(settings: Settings) -> None:
    """Lees de cookies uit het ingelogde profiel en schrijf ze als storage_state.

    Draait lokaal (macOS), waar Chrome de cookies wél kan ontsleutelen; de
    resulterende JSON bevat de platte waarden en is overdraagbaar naar Linux.
    """
    from patchright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # inject_session=False: we willen de EIGEN profielcookies exporteren.
        ctx = launch_persistent(pw, settings, headless=True, inject_session=False)
        try:
            ctx.storage_state(path=str(settings.session_file))
        finally:
            ctx.close()


def check_session(settings: Settings) -> bool:
    """Headless controle of het profiel nog ingelogd is (via patchright)."""
    from patchright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = launch_persistent(pw, settings, headless=settings.headless)
        page = ctx.new_page()
        try:
            resp = page.goto(OVERVIEW_URL, wait_until="domcontentloaded", timeout=45_000)
            if "login.dpgmedia.nl" in page.url:
                return False
            if resp is not None and resp.status >= 400:
                return False
            return True
        finally:
            ctx.close()
