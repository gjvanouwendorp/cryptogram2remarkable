"""Eén plek waar de browser wordt gestart, gehard tegen bot-detectie (Akamai).

De Volkskrant/DPG-login zit achter Akamai Bot Manager. Een kale Playwright-launch
wordt geweigerd met HTTP 406 ("verdacht verkeer"), óók met `channel="chrome"`,
omdat Akamai de CDP-automation detecteert (de bekende `Runtime.enable`-lek).

Oplossing: **patchright**, een gepatchte Playwright die die lek dichttimmert.
Empirisch (2026-07): patchright + echte Chrome passeert zowel de login (headed)
als het scrapen van volkskrant.nl (headless).

patchright-aanbevelingen die we volgen: gebruik `channel="chrome"`, `no_viewport`,
en géén extra automation-onthullende opties/init-scripts.
"""
from __future__ import annotations

from .config import Settings


def launch_persistent(pw, settings: Settings, headless: bool):
    """Start een persistent context op het (opgewarmde) Chrome-profiel."""
    settings.profile_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(settings.profile_dir),
        headless=headless,
        no_viewport=True,
        # Forceer een desktop-venster; anders toont volkskrant.nl de mobiele
        # layout en ontbreekt de tegel "Cryptogram - Puzzel uit de krant".
        args=["--window-size=1400,940"],
        locale="nl-NL",
    )
    if settings.browser_channel:
        kwargs["channel"] = settings.browser_channel  # "chrome" = echte Google Chrome
    return pw.chromium.launch_persistent_context(**kwargs)
