"""Stap 6: orkestratie met logging, idempotentie en een lock.

Ketent scrape -> normalize -> render -> upload. Houdt in data/state.json bij welke
puzzle-ID het laatst is verwerkt/geüpload, zodat een dubbele run niet twee keer
dezelfde pagina naar de reMarkable stuurt. Een file-lock voorkomt parallelle runs.

Notificaties (ntfy): elke run meldt zijn uitkomst, behalve als de puzzel van deze
week al eerder is binnengehaald. Zo krijg je zaterdagochtend altijd bericht, en
van de herkansingen later alleen zolang het nog niet gelukt is.
"""
from __future__ import annotations

import fcntl
import json
import logging
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .config import Settings
from .errors import PuzzleNotAvailableError
from .notify import notify_failure, notify_result
from .normalize import normalize
from .render_pdf import render_pdf
from .scrape import scrape
from .upload import upload

log = logging.getLogger("c2rm")


@contextmanager
def _lock(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / ".lock"
    with open(lock_path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Een andere run is al bezig (lock actief).")
        yield


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetched_this_week(state: dict, on_date: date) -> bool:
    """Is de puzzel die bij `on_date` hoort al eerder binnengehaald?"""
    pd = state.get("puzzle_date")
    if not pd:
        return False
    return 0 <= (on_date - date.fromisoformat(pd)).days < 7


def run(settings: Settings, on_date: date | None = None, dry_run: bool = False,
        notify: bool = True) -> dict:
    on_date = on_date or date.today()
    settings.ensure_dirs()
    state_path = settings.data_dir / "state.json"
    # Geen meldingen bij een dry-run of als deze week al binnen is.
    notify = notify and not dry_run and not _fetched_this_week(
        _load_state(state_path), on_date)

    try:
        result = _run(settings, on_date, dry_run, state_path)
    except Exception as e:
        if notify:
            notify_failure(settings, e)
        raise
    if notify:
        notify_result(settings, result)
    return result


def _run(settings: Settings, on_date: date, dry_run: bool, state_path: Path) -> dict:
    with _lock(settings.data_dir):
        state = _load_state(state_path)

        log.info("Scrape gestart (%s)", on_date.isoformat())
        try:
            raw = scrape(settings, on_date)
        except PuzzleNotAvailableError as e:
            log.warning("%s Een latere timer-run probeert het opnieuw.", e)
            return {"status": "not_available", "reason": str(e)}
        puzzleid = raw["meta"].get("puzzleid", "")
        # Zonder datum in de Speel-link: neem aan dat het de puzzel van vandaag is.
        published = raw["meta"].get("published") or on_date.isoformat()
        (settings.data_dir / f"raw-{on_date.isoformat()}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Puzzel gevonden: id=%s, %sx%s", puzzleid,
                 raw["cells"]["rows"], raw["cells"]["columns"])

        # Idempotentie: al verwerkt én geüpload? Dan stoppen.
        if puzzleid and state.get("last_puzzleid") == puzzleid and state.get("uploaded"):
            log.info("Puzzel %s is al geüpload — niets te doen.", puzzleid)
            if not dry_run and state.get("puzzle_date") != published:
                _save_state(state_path, {**state, "puzzle_date": published})
            return {"status": "skipped", "puzzleid": puzzleid, "published": published}

        puzzle = normalize(raw)
        (settings.data_dir / f"puzzle-{on_date.isoformat()}.json").write_text(
            json.dumps(puzzle.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Genormaliseerd: %sH + %sV clues", len(puzzle.horizontal), len(puzzle.vertical))

        pdf_path = settings.data_dir / f"cryptogram-{on_date.isoformat()}.pdf"
        render_pdf(puzzle, pdf_path, layout=settings.layout)
        log.info("PDF gegenereerd: %s", pdf_path)

        uploaded = False
        if dry_run:
            log.info("dry-run: upload overgeslagen.")
        else:
            uploaded = upload(pdf_path, settings.rm_folder, settings.rmapi_config)
            log.info("Upload %s naar %s", "gelukt" if uploaded else "overgeslagen (al aanwezig)",
                     settings.rm_folder)

        # 'uploaded' true houden als deze puzzel eerder al was geüpload.
        already = state.get("last_puzzleid") == puzzleid and state.get("uploaded", False)
        state = {
            "last_puzzleid": puzzleid,
            "last_date": on_date.isoformat(),
            "uploaded": bool(uploaded) or already,
            # Markeert deze week als binnen; een dry-run telt niet.
            "puzzle_date": state.get("puzzle_date") if dry_run else published,
        }
        _save_state(state_path, state)

        return {"status": "ok", "puzzleid": puzzleid, "published": published,
                "pdf": str(pdf_path), "uploaded": uploaded}
