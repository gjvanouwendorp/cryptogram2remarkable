"""Eén plek waar de browser wordt gestart, gehard tegen bot-detectie (Akamai).

De Volkskrant/DPG-login zit achter Akamai Bot Manager. Een kale Playwright-launch
wordt geweigerd met HTTP 406 ("verdacht verkeer"), óók met `channel="chrome"`,
omdat Akamai de CDP-automation detecteert (de bekende `Runtime.enable`-lek).

Oplossing: **patchright**, een gepatchte Playwright die die lek dichttimmert, met
echte Google Chrome. Empirisch (2026-07): patchright + Chrome passeert het scrapen
van volkskrant.nl.

Sessie: we injecteren de cookies uit een DRAAGBARE `session.json` (storage_state),
niet uit de OS-versleutelde cookies van het gekopieerde profiel. Chrome versleutelt
cookies met een OS-specifieke sleutel (macOS Keychain vs. Linux keyring), dus een
macOS-profiel logt op Linux niet in. De platte JSON is wél overdraagbaar.
"""
from __future__ import annotations

import json

from .config import Settings


def launch_persistent(pw, settings: Settings, headless: bool, inject_session: bool = True):
    """Start een persistent context; injecteer indien aanwezig de draagbare sessie."""
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
    ctx = pw.chromium.launch_persistent_context(**kwargs)

    if inject_session and settings.session_file.exists():
        state = json.loads(settings.session_file.read_text(encoding="utf-8"))
        cookies = state.get("cookies") or []
        if cookies:
            ctx.add_cookies(cookies)
    return ctx
