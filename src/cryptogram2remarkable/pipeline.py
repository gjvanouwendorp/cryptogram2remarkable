"""Stap 6: orkestratie met logging, idempotentie en een lock.

Ketent scrape -> normalize -> render -> upload. Houdt in data/state.json bij welke
puzzle-ID het laatst is verwerkt/geüpload, zodat een dubbele run niet twee keer
dezelfde pagina naar de reMarkable stuurt. Een file-lock voorkomt parallelle runs.
"""
from __future__ import annotations

import fcntl
import json
import logging
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .config import Settings
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


def run(settings: Settings, on_date: date | None = None, dry_run: bool = False) -> dict:
    on_date = on_date or date.today()
    settings.ensure_dirs()
    state_path = settings.data_dir / "state.json"

    with _lock(settings.data_dir):
        state = _load_state(state_path)

        log.info("Scrape gestart (%s)", on_date.isoformat())
        raw = scrape(settings, on_date)
        puzzleid = raw["meta"].get("puzzleid", "")
        (settings.data_dir / f"raw-{on_date.isoformat()}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Puzzel gevonden: id=%s, %sx%s", puzzleid,
                 raw["cells"]["rows"], raw["cells"]["columns"])

        # Idempotentie: al verwerkt én geüpload? Dan stoppen.
        if puzzleid and state.get("last_puzzleid") == puzzleid and state.get("uploaded"):
            log.info("Puzzel %s is al geüpload — niets te doen.", puzzleid)
            return {"status": "skipped", "puzzleid": puzzleid}

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
        }
        _save_state(state_path, state)

        return {"status": "ok", "puzzleid": puzzleid, "pdf": str(pdf_path), "uploaded": uploaded}
