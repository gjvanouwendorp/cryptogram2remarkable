"""Push-notificaties via ntfy (https://ntfy.sh of een eigen server).

Publiceert als JSON naar de server-root, zodat titel en tekst gewoon UTF-8
mogen bevatten (HTTP-headers als `Title:` zijn alleen latin-1).
Een mislukte notificatie mag de pipeline nooit laten falen: fouten worden
gelogd en ingeslikt.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date
from urllib.parse import urlparse

from .config import Settings
from .errors import SessionExpiredError

log = logging.getLogger("c2rm")

_DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
            "augustus", "september", "oktober", "november", "december"]


def _nl_date(d: date) -> str:
    return f"{_DAGEN[d.weekday()]} {d.day} {_MAANDEN[d.month - 1]}"


def send(settings: Settings, title: str, message: str,
         priority: int = 3, tags: list[str] | None = None) -> bool:
    """Stuur één notificatie; True bij succes, False als uit of mislukt."""
    if not settings.ntfy_url:
        return False
    u = urlparse(settings.ntfy_url)
    topic = u.path.strip("/")
    if not (u.scheme and u.netloc and topic):
        log.warning("C2RM_NTFY_URL ongeldig (verwacht https://server/<topic>): %s",
                    settings.ntfy_url)
        return False
    body = json.dumps({"topic": topic, "title": title, "message": message,
                       "priority": priority, "tags": tags or []}).encode("utf-8")
    req = urllib.request.Request(f"{u.scheme}://{u.netloc}/", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    if settings.ntfy_token:
        req.add_header("Authorization", f"Bearer {settings.ntfy_token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except Exception as e:  # noqa: BLE001 — notificatie is best-effort
        log.warning("ntfy-notificatie mislukt: %s", e)
        return False


def notify_result(settings: Settings, result: dict) -> None:
    status = result.get("status")
    if status in ("ok", "skipped"):
        published = result.get("published")
        wanneer = _nl_date(date.fromisoformat(published)) if published else "deze week"
        if status == "ok" and result.get("uploaded"):
            msg = f"Het cryptogram van {wanneer} staat op je reMarkable ({settings.rm_folder})."
        else:
            msg = f"Het cryptogram van {wanneer} stond al op je reMarkable ({settings.rm_folder})."
        send(settings, "Cryptogram binnen", msg, tags=["white_check_mark"])
    elif status == "not_available":
        send(settings, "Cryptogram nog niet online",
             f"{result.get('reason', '')} Een latere run probeert het opnieuw.",
             tags=["hourglass"])


def notify_failure(settings: Settings, exc: BaseException) -> None:
    if isinstance(exc, SessionExpiredError):
        send(settings, "Cryptogram: sessie verlopen", str(exc), priority=4, tags=["key"])
    else:
        send(settings, "Cryptogram ophalen mislukt", f"{type(exc).__name__}: {exc}",
             priority=4, tags=["x"])
