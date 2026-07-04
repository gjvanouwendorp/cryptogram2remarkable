"""Rendert een `Puzzle` naar een PDF op reMarkable-2-maat.

reMarkable 2: 1872 x 1404 px @ 226 dpi. We werken in points op de fysieke maat,
zodat lettergroottes echte points zijn.

Oriëntatie volgt de inhoud:
- Past rooster + alle clues op EEN pagina -> **landscape** (rooster links,
  omschrijvingen rechts in één kolom: secties "Horizontaal" en "Verticaal").
- Zijn er TWEE pagina's nodig -> **portrait**: rooster groot op pagina 1,
  omschrijvingen op pagina 2 (één kolom). Dit geldt zowel als `single_page`
  overloopt als voor de expliciete `grid_first`-layout.

Alleen de lege puzzel wordt getekend; `solution` wordt niet ingevuld. Cellen met
kind VOID vallen buiten de vorm en worden niet getekend.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer,
)

from .model import CellKind, Puzzle

# --- reMarkable 2 geometrie (points) ---
DPI = 226
_LONG = 1872 / DPI * 72.0   # 596.3
_SHORT = 1404 / DPI * 72.0  # 447.4
LANDSCAPE = (_LONG, _SHORT)
PORTRAIT = (_SHORT, _LONG)

MARGIN = 28.0
GAP = 18.0              # tussen rooster en clues (landscape)
TITLE_H = 20.0
GRID_MAX_W_FRAC = 0.62  # rooster beslaat max dit deel van de breedte (landscape)

_NL_MONTHS = ["", "januari", "februari", "maart", "april", "mei", "juni", "juli",
              "augustus", "september", "oktober", "november", "december"]
_NL_DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def render_pdf(puzzle: Puzzle, out_path: str | Path, layout: str = "single_page") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if layout == "grid_first":
        _render_two_page_portrait(puzzle, out_path)
        return out_path

    # single_page: probeer één landscape-pagina; bij overloop -> twee portrait-pagina's.
    pages = _render_single_landscape(puzzle, out_path)
    if pages > 1:
        _render_two_page_portrait(puzzle, out_path)
    return out_path


# --- landscape: rooster links, clues rechts (1 pagina indien passend) ---
def _render_single_landscape(puzzle: Puzzle, out_path: Path) -> int:
    page_w, page_h = LANDSCAPE
    usable_w = page_w - 2 * MARGIN
    usable_h = page_h - 2 * MARGIN
    band_h = usable_h - TITLE_H

    cell = min((usable_w * GRID_MAX_W_FRAC) / puzzle.cols, band_h / puzzle.rows)
    grid_w = cell * puzzle.cols
    title = _title_text(puzzle)

    def draw_first(canvas, _doc):
        _draw_title(canvas, page_h, title)
        _draw_grid(canvas, puzzle, MARGIN, page_h - MARGIN - TITLE_H, cell)

    def draw_later(canvas, _doc):
        _draw_title(canvas, page_h, title)

    clue_x = MARGIN + grid_w + GAP
    clue_w = usable_w - grid_w - GAP
    clue_frame = Frame(clue_x, MARGIN, clue_w, band_h, id="clues",
                       leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later_frame = Frame(MARGIN, MARGIN, usable_w, band_h, id="clues2",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(str(out_path), pagesize=(page_w, page_h),
                          title=title, author="cryptogram2remarkable")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[clue_frame], onPage=draw_first),
        PageTemplate(id="later", frames=[later_frame], onPage=draw_later),
    ])
    doc.build([NextPageTemplate("later"), *_clue_flowables(puzzle)])
    return doc.page


# --- portrait: rooster groot op pagina 1, clues op pagina 2+ ---
def _render_two_page_portrait(puzzle: Puzzle, out_path: Path) -> int:
    page_w, page_h = PORTRAIT
    usable_w = page_w - 2 * MARGIN
    usable_h = page_h - 2 * MARGIN
    band_h = usable_h - TITLE_H

    cell = min(usable_w / puzzle.cols, band_h / puzzle.rows)
    grid_w = cell * puzzle.cols
    title = _title_text(puzzle)

    def draw_grid_page(canvas, _doc):
        _draw_title(canvas, page_h, title)
        x0 = MARGIN + (usable_w - grid_w) / 2  # horizontaal gecentreerd
        _draw_grid(canvas, puzzle, x0, page_h - MARGIN - TITLE_H, cell)

    def draw_clue_page(canvas, _doc):
        _draw_title(canvas, page_h, title)

    empty_frame = Frame(MARGIN, MARGIN, usable_w, band_h, id="empty")
    clue_frame = Frame(MARGIN, MARGIN, usable_w, band_h, id="clues",
                       leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(str(out_path), pagesize=(page_w, page_h),
                          title=title, author="cryptogram2remarkable")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[empty_frame], onPage=draw_grid_page),
        PageTemplate(id="later", frames=[clue_frame], onPage=draw_clue_page),
    ])
    doc.build([NextPageTemplate("later"), PageBreak(), *_clue_flowables(puzzle)])
    return doc.page


def _draw_title(canvas, page_h: float, title: str) -> None:
    canvas.setFont("Helvetica-Bold", 12)
    canvas.setFillGray(0.0)
    canvas.drawString(MARGIN, page_h - MARGIN - 12, title)


def _draw_grid(canvas, puzzle: Puzzle, x0: float, top_y: float, cell: float) -> None:
    num_font = max(4.0, cell * 0.26)
    canvas.setLineWidth(max(0.5, cell * 0.03))
    for row in puzzle.grid:
        for c in row:
            if c.kind is CellKind.VOID:
                continue
            x = x0 + c.col * cell
            y = top_y - (c.row + 1) * cell  # onderkant van de cel
            if c.kind is CellKind.BLOCK:
                canvas.setFillGray(0.0)
                canvas.rect(x, y, cell, cell, stroke=0, fill=1)
            else:  # LETTER
                canvas.setFillGray(1.0)
                canvas.setStrokeGray(0.0)
                canvas.rect(x, y, cell, cell, stroke=1, fill=1)
                if c.number is not None:
                    canvas.setFillGray(0.0)
                    canvas.setFont("Helvetica", num_font)
                    canvas.drawString(x + cell * 0.06, y + cell - num_font * 0.95, str(c.number))


def _clue_flowables(puzzle: Puzzle) -> list:
    header = ParagraphStyle("clueHeader", fontName="Helvetica-Bold", fontSize=11,
                            leading=13, spaceBefore=2, spaceAfter=5, alignment=TA_LEFT)
    body = ParagraphStyle("clueBody", fontName="Helvetica", fontSize=8.6,
                          leading=11.0, spaceAfter=2.4, alignment=TA_LEFT,
                          leftIndent=15, firstLineIndent=-15)

    def clue_para(clue) -> Paragraph:
        return Paragraph(f"<b>{clue.number}</b>&nbsp;&nbsp;{escape(clue.text)}", body)

    flow: list = [Paragraph("Horizontaal", header)]
    flow += [clue_para(c) for c in sorted(puzzle.horizontal, key=lambda c: c.number)]
    flow += [Spacer(1, 8), Paragraph("Verticaal", header)]
    flow += [clue_para(c) for c in sorted(puzzle.vertical, key=lambda c: c.number)]
    return flow


def _title_text(puzzle: Puzzle) -> str:
    try:
        d = date.fromisoformat(puzzle.date)
        return f"Cryptogram · {_NL_DAYS[d.weekday()]} {d.day} {_NL_MONTHS[d.month]} {d.year}"
    except (ValueError, TypeError):
        return "Cryptogram"
