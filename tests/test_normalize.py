import json
from pathlib import Path

import pytest

from cryptogram2remarkable.model import CellKind
from cryptogram2remarkable.normalize import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "sample_raw.json"


@pytest.fixture
def raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_dimensions_and_clue_counts(raw):
    p = normalize(raw)
    assert (p.rows, p.cols) == (21, 15)
    assert len(p.horizontal) == 13
    assert len(p.vertical) == 9


def test_cell_taxonomy_matches_live_measurements(raw):
    p = normalize(raw)
    kinds = [c.kind for row in p.grid for c in row]
    assert kinds.count(CellKind.LETTER) == 162
    assert kinds.count(CellKind.BLOCK) == 90
    assert kinds.count(CellKind.VOID) == 63


def test_ij_is_one_cell(raw):
    p = normalize(raw)
    ijs = [c for row in p.grid for c in row if c.solution == "IJ"]
    assert len(ijs) == 3  # index 147, 256, 277 in de brondata


def test_clue_numbers_land_on_first_cell(raw):
    p = normalize(raw)
    # horizontale clue 4 begint op grid-index 15 -> (row 1, col 0)
    clue4 = next(c for c in p.horizontal if c.number == 4)
    r, c = clue4.cells[0]
    assert (r, c) == (1, 0)
    assert p.cell(r, c).number == 4
    assert p.cell(r, c).kind is CellKind.LETTER


def test_every_clue_cell_is_a_letter(raw):
    p = normalize(raw)
    for clue in p.clues:
        for r, c in clue.cells:
            assert p.cell(r, c).kind is CellKind.LETTER


def test_roundtrip_serialisation(raw):
    p = normalize(raw)
    from cryptogram2remarkable.model import Puzzle
    p2 = Puzzle.from_dict(p.to_dict())
    assert p2 == p
