"""Schoon, eigen datamodel voor een cryptogram.

Ontkoppelt de renderlogica van de Braintainment/Redux-eigenaardigheden. Zie
`normalize.py` voor de omzetting vanuit de ruwe scrape-data.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Literal


class CellKind(str, Enum):
    LETTER = "letter"  # witte, invulbare cel
    BLOCK = "block"    # zwart vakje
    VOID = "void"      # onzichtbaar; valt buiten de puzzelvorm -> niet tekenen


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    kind: CellKind
    number: int | None = None  # clue-nummer als dit een startvakje is
    solution: str = ""         # één of meer tekens ("IJ" is één vakje); leeg voor blok/void


@dataclass(frozen=True)
class Clue:
    direction: Literal["H", "V"]
    number: int
    text: str
    cells: tuple[tuple[int, int], ...]  # (row, col) van elk vakje van het woord


@dataclass(frozen=True)
class Puzzle:
    date: str
    rows: int
    cols: int
    grid: tuple[tuple[Cell, ...], ...]  # [row][col]
    clues: tuple[Clue, ...]
    puzzleid: str = ""

    @property
    def horizontal(self) -> list[Clue]:
        return [c for c in self.clues if c.direction == "H"]

    @property
    def vertical(self) -> list[Clue]:
        return [c for c in self.clues if c.direction == "V"]

    def cell(self, row: int, col: int) -> Cell:
        return self.grid[row][col]

    # --- serialisatie, zodat een genormaliseerd model op schijf kan ---
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "puzzleid": self.puzzleid,
            "rows": self.rows,
            "cols": self.cols,
            "grid": [[_cell_to_dict(c) for c in row] for row in self.grid],
            "clues": [
                {"direction": c.direction, "number": c.number, "text": c.text,
                 "cells": [list(rc) for rc in c.cells]}
                for c in self.clues
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Puzzle":
        grid = tuple(
            tuple(
                Cell(row=c["row"], col=c["col"], kind=CellKind(c["kind"]),
                     number=c["number"], solution=c["solution"])
                for c in row
            )
            for row in d["grid"]
        )
        clues = tuple(
            Clue(direction=c["direction"], number=c["number"], text=c["text"],
                 cells=tuple(tuple(rc) for rc in c["cells"]))
            for c in d["clues"]
        )
        return cls(date=d["date"], rows=d["rows"], cols=d["cols"], grid=grid,
                   clues=clues, puzzleid=d.get("puzzleid", ""))


def _cell_to_dict(c: Cell) -> dict:
    out = asdict(c)
    out["kind"] = c.kind.value
    return out
