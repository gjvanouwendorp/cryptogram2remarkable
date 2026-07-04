"""Zet de ruwe Redux-scrapedata om naar het schone `Puzzle`-model.

De ruwe vorm (zie tests/fixtures/sample_raw.json) komt 1-op-1 uit de
Braintainment React/Redux-store:

    raw = {
      "meta":  {"date", "puzzleid", "rows", "columns", ...},
      "cells": {"rows", "columns", "cellData": [{solution, value, status, visible}, ...]},
      "clues": {"horizontalClues": [{text, label}], "horizontalClueCells": [[idx,...]],
                "verticalClues":   [{text, label}], "verticalClueCells":   [[idx,...]]},
    }

Regels die empirisch zijn vastgesteld (2026-07-04):
- cellData is een PLATTE array; index = rij * columns + kolom.
- visible=False  -> VOID (niet tekenen; puzzel is onregelmatig van vorm).
- visible=True & solution==""  -> BLOCK (zwart).
- visible=True & solution!=""  -> LETTER (wit, invulbaar). solution kan 2 tekens
  zijn ("IJ" is één vakje).
- Nummering: clue.label hoort bij het EERSTE vakje van dat woord; nummering is
  gedeeld tussen horizontaal en verticaal (standaard kruiswoordnummering).
"""
from __future__ import annotations

from .model import Cell, CellKind, Clue, Puzzle


def normalize(raw: dict) -> Puzzle:
    cells = raw["cells"]
    rows = int(cells["rows"])
    cols = int(cells["columns"])
    cell_data = cells["cellData"]
    if len(cell_data) != rows * cols:
        raise ValueError(f"cellData heeft {len(cell_data)} cellen, verwacht {rows*cols}")

    clues_raw = raw["clues"]
    # celindex -> clue-nummer (eerste vakje van elk woord)
    starts: dict[int, int] = {}
    for clue, cell_idxs in zip(clues_raw["horizontalClues"], clues_raw["horizontalClueCells"]):
        starts.setdefault(cell_idxs[0], clue["label"])
    for clue, cell_idxs in zip(clues_raw["verticalClues"], clues_raw["verticalClueCells"]):
        starts.setdefault(cell_idxs[0], clue["label"])

    def build_cell(idx: int) -> Cell:
        raw_cell = cell_data[idx]
        row, col = divmod(idx, cols)
        solution = raw_cell.get("solution") or ""
        if raw_cell.get("visible") is False:
            kind = CellKind.VOID
        elif solution == "":
            kind = CellKind.BLOCK
        else:
            kind = CellKind.LETTER
        number = starts.get(idx) if kind is CellKind.LETTER else None
        return Cell(row=row, col=col, kind=kind, number=number, solution=solution)

    grid = tuple(
        tuple(build_cell(r * cols + c) for c in range(cols))
        for r in range(rows)
    )

    clues: list[Clue] = []
    clues += _build_clues("H", clues_raw["horizontalClues"], clues_raw["horizontalClueCells"], cols)
    clues += _build_clues("V", clues_raw["verticalClues"], clues_raw["verticalClueCells"], cols)
    clues.sort(key=lambda c: (c.number, c.direction))

    meta = raw.get("meta", {})
    return Puzzle(
        date=meta.get("date", ""),
        puzzleid=meta.get("puzzleid", ""),
        rows=rows,
        cols=cols,
        grid=grid,
        clues=tuple(clues),
    )


def _build_clues(direction, clues_list, cells_list, cols) -> list[Clue]:
    out = []
    for clue, cell_idxs in zip(clues_list, cells_list):
        rc = tuple(divmod(idx, cols) for idx in cell_idxs)
        out.append(Clue(direction=direction, number=clue["label"],
                        text=clue["text"].strip(), cells=rc))
    return out
