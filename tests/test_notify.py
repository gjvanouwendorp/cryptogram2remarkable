"""Notificatiebeleid: zaterdagochtend altijd een melding, herkansingen alleen
zolang de puzzel van deze week nog niet binnen is."""
import json
from datetime import date
from pathlib import Path

import pytest

from cryptogram2remarkable import pipeline
from cryptogram2remarkable.config import Settings
from cryptogram2remarkable.errors import PuzzleNotAvailableError, StructureChangedError

FIXTURE = Path(__file__).parent / "fixtures" / "sample_raw.json"
SAT = date(2026, 9, 26)


@pytest.fixture
def env(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, ntfy_url="https://ntfy.sh/test", _env_file=None)
    sent = []
    monkeypatch.setattr("cryptogram2remarkable.notify.send",
                        lambda s, title, msg, **kw: sent.append(title) or True)
    monkeypatch.setattr(pipeline, "render_pdf", lambda puzzle, path, layout: path.touch())
    monkeypatch.setattr(pipeline, "upload", lambda *a: True)

    outcome = {}

    def fake_scrape(settings, on_date):
        if "exc" in outcome:
            raise outcome["exc"]
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["meta"]["published"] = outcome.get("published", SAT.isoformat())
        return raw

    monkeypatch.setattr(pipeline, "scrape", fake_scrape)
    return settings, sent, outcome


def test_success_notifies(env):
    settings, sent, _ = env
    assert pipeline.run(settings, SAT)["status"] == "ok"
    assert sent == ["Cryptogram binnen"]


def test_later_run_after_success_is_silent(env):
    settings, sent, outcome = env
    pipeline.run(settings, SAT)
    sent.clear()
    pipeline.run(settings, SAT)  # skipped
    outcome["exc"] = StructureChangedError("storing")
    with pytest.raises(StructureChangedError):
        pipeline.run(settings, date(2026, 9, 27))
    assert sent == []


def test_retries_notify_until_success(env):
    settings, sent, outcome = env
    outcome["exc"] = StructureChangedError("storing")
    with pytest.raises(StructureChangedError):
        pipeline.run(settings, SAT)
    outcome["exc"] = PuzzleNotAvailableError("nog niet online")
    assert pipeline.run(settings, SAT)["status"] == "not_available"
    del outcome["exc"]
    pipeline.run(settings, SAT)
    assert sent == ["Cryptogram ophalen mislukt", "Cryptogram nog niet online",
                    "Cryptogram binnen"]


def test_next_week_notifies_again(env):
    settings, sent, outcome = env
    pipeline.run(settings, SAT)
    outcome["published"] = "2026-10-03"
    pipeline.run(settings, date(2026, 10, 3))
    assert sent == ["Cryptogram binnen", "Cryptogram binnen"]


def test_dry_run_is_silent_and_does_not_mark_week(env):
    settings, sent, _ = env
    pipeline.run(settings, SAT, dry_run=True)
    assert sent == []
    pipeline.run(settings, SAT)
    assert sent == ["Cryptogram binnen"]
