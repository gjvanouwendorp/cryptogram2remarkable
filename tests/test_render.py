import json
import re
from pathlib import Path

import pytest

from cryptogram2remarkable.normalize import normalize
from cryptogram2remarkable.render_pdf import render_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "sample_raw.json"


@pytest.fixture
def puzzle():
    return normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _mediaboxes(pdf_bytes: bytes) -> list[tuple[float, float]]:
    boxes = []
    for m in re.finditer(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", pdf_bytes):
        _, _, w, h = (float(x) for x in m.groups())
        boxes.append((w, h))
    return boxes


def _page_count(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes))


@pytest.mark.parametrize("layout", ["single_page", "grid_first"])
def test_render_produces_pdf(puzzle, tmp_path, layout):
    out = render_pdf(puzzle, tmp_path / "out.pdf", layout=layout)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 2000


def test_single_page_is_one_landscape_page(puzzle, tmp_path):
    # 22 clues passen naast het rooster -> één landscape-pagina.
    data = render_pdf(puzzle, tmp_path / "out.pdf", layout="single_page").read_bytes()
    assert _page_count(data) == 1
    (w, h), = _mediaboxes(data)
    assert w > h  # landscape


def test_grid_first_is_portrait_multipage(puzzle, tmp_path):
    # Expliciete twee-pagina-modus -> portrait.
    data = render_pdf(puzzle, tmp_path / "out.pdf", layout="grid_first").read_bytes()
    assert _page_count(data) >= 2
    for w, h in _mediaboxes(data):
        assert h > w  # portrait
