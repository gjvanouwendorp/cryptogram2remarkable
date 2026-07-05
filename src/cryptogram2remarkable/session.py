"""Herbruikbare sessie: inloggen (mensgestuurd) en de cookies eruit halen.

De DPG-login zit achter Akamai bot-detectie die ELKE door Playwright/patchright
bestuurde browser weigert (HTTP 406). Daarom automatiseren we de login NIET: we
starten een gewone Chrome als los proces (geen automation).

Voor het EXPORTEREN van de sessie lezen we de cookies uit de nog DRAAIENDE,
ingelogde Chrome via CDP (remote-debugging-port). Dat is cruciaal op macOS: cookies
worden versleuteld met een Keychain-sleutel, en alleen de Chrome die ze schreef (of
een normale Chrome met Keychain-toegang) kan ze ontsleutelen. Een los door
patchright geopend profiel geeft 0 cookies -> lege session.json.

De resulterende session.json bevat de platte cookies en is overdraagbaar naar de
Linux-VPS (zie browser.py voor de injectie).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .browser import launch_persistent
from .config import OVERVIEW_URL, Settings
from .errors import C2RMError

_CDP_PORT = 9222


def _chrome_binary() -> str:
    if sys.platform == "darwin":
        mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(mac).exists():
            return mac
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise C2RMError("Google Chrome niet gevonden. Installeer Chrome (VPS: google-chrome-stable).")


def _launch_chrome(profile: Path, port: int, url: str) -> subprocess.Popen:
    args = [
        _chrome_binary(),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    return subprocess.Popen(args)


def _wait_for_cdp(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise C2RMError(f"CDP-poort {port} reageerde niet binnen {timeout}s.")


def _export_via_cdp(settings: Settings, port: int) -> int:
    """Lees cookies uit de draaiende Chrome via CDP en schrijf session.json."""
    from patchright.sync_api import sync_playwright

    _wait_for_cdp(port)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            ctx = browser.contexts[0]
            state = ctx.storage_state()
        finally:
            browser.close()
    settings.session_file.write_text(json.dumps(state), encoding="utf-8")
    return len(state.get("cookies", []))


def login(settings: Settings) -> None:
    profile = settings.profile_dir.absolute()
    profile.mkdir(parents=True, exist_ok=True)

    print("Er opent een gewone Chrome met een eigen profielmap.")
    print("1) Log in bij de Volkskrant en open een cryptogram.")
    print("2) LAAT Chrome open staan en druk hier op Enter (niet sluiten).")
    proc = _launch_chrome(profile, _CDP_PORT, OVERVIEW_URL)
    input("\nDruk op Enter zodra je bent ingelogd (Chrome open laten)... ")

    n = _export_via_cdp(settings, _CDP_PORT)
    if n == 0:
        print("\nLET OP: 0 cookies gevonden. Ben je zeker ingelogd? Probeer opnieuw.")
    else:
        print(f"\nDraagbare sessie geschreven naar {settings.session_file} ({n} cookies).")
        print("Kopieer ALLEEN dit bestand naar de VPS, bv.:")
        print(f"  rsync -a {settings.session_file} vps:/opt/cryptogram2remarkable/session.json")

    # Chrome netjes sluiten.
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def export_session(settings: Settings) -> int:
    """Her-exporteer de sessie uit een bestaand (ingelogd) profiel, zonder opnieuw
    in te loggen: start een gewone Chrome op het profiel en lees via CDP."""
    profile = settings.profile_dir.absolute()
    if not profile.exists():
        raise C2RMError(f"Profielmap bestaat niet: {profile}. Draai eerst 'c2rm login'.")
    proc = _launch_chrome(profile, _CDP_PORT, OVERVIEW_URL)
    try:
        n = _export_via_cdp(settings, _CDP_PORT)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return n


def check_session(settings: Settings) -> bool:
    """Headless controle of de sessie (session.json) nog ingelogd is (via patchright)."""
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
