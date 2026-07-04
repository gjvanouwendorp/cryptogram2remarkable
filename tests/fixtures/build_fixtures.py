"""Genereert tests/fixtures/sample_raw.json uit het Volkskrant WEEKEND-cryptogram
"uit de krant" van 2026-07-04.

  puzzleid=KNL-13577910, customerid=volkskrant, puzzlevariation=weekendPuzzlecrypto
  rooster 21 rijen x 15 kolommen (315 cellen), 13 horizontale + 9 verticale clues.

Belangrijk: dit is de KRANTENpuzzel, niet de losse dagelijkse cryptogram. De vorm
is ONREGELMATIG. Drie celtypes:
  - lettercel : visible=True,  solution!="" -> witte, invulbare cel
  - blok      : visible=True,  solution==""  -> zwart vakje
  - onzichtbaar: visible=False               -> valt buiten de puzzelvorm, NIET tekenen

De ruwe Redux-store is compact vastgelegd. Omdat de celvorm constant is
(value="", status="", visible varieert) reconstrueren we hier `cells.cellData` in
exact dezelfde vorm als `store.getState()`. Let op: sommige cellen hebben een
meerletterige oplossing (Nederlandse "IJ" als een vakje) -> daarom is het rooster
'|'-gescheiden i.p.v. een platte string.

Draai: python3 tests/fixtures/build_fixtures.py
"""
import json
from pathlib import Path

ROWS, COLUMNS = 21, 15  # 315 cellen

# 315 '|'-gescheiden tokens. letter = oplossing (incl. "IJ"), '#' = blok, '.' = onzichtbaar.
GRID = (
    "#|K|#|D|#|G|#|.|.|.|.|.|.|.|.|"
    "S|L|U|R|P|E|N|.|.|.|.|.|.|.|.|"
    "#|A|#|I|#|E|#|#|#|N|#|.|.|.|.|"
    "#|S|T|E|E|N|U|I|L|E|N|.|.|.|.|"
    "#|S|#|D|#|W|#|N|#|E|#|.|.|.|.|"
    "L|E|E|U|W|E|N|H|A|R|T|#|.|.|.|"
    "#|N|#|B|#|G|#|O|#|G|#|V|#|.|.|"
    "O|M|#|B|O|W|L|G|L|A|Z|E|N|.|.|"
    "#|A|#|E|#|E|#|E|#|A|#|R|#|#|#|"
    "T|A|B|L|E|T|#|R|A|N|G|L|IJ|S|T|"
    "#|T|#|#|#|E|#|E|#|#|#|E|#|T|#|"
    "#|S|P|R|O|N|G|S|E|R|V|I|C|E|#|"
    "#|C|#|E|#|M|#|F|#|O|#|D|#|E|#|"
    "#|H|E|T|B|E|T|E|R|E|W|E|R|K|#|"
    "#|A|#|R|#|T|#|R|#|R|#|N|#|#|.|"
    "#|P|R|O|F|I|L|E|R|E|N|#|.|.|.|"
    "#|P|#|F|#|E|#|N|#|I|#|.|.|.|.|"
    "Z|IJ|D|E|#|M|U|Z|I|E|K|.|.|.|.|"
    "#|#|#|E|#|A|#|IJ|#|R|#|.|.|.|.|"
    ".|.|#|S|Y|N|O|N|I|E|M|.|.|.|.|"
    ".|.|#|T|#|D|#|#|#|N|#|.|.|.|."
)

HORIZONTAL_CLUES = [
    {"text": "Drinken? Zo hoort het! (7)", "label": 4},
    {"text": "Braken die keiharde ballen uit? (10)", "label": 6},
    {"text": "Was die koning diep van binnen voor het Marokkaanse elftal of toch voor Oranje? (11)", "label": 8},
    {"text": "Van gedachten veranderd over het parket. (2)", "label": 10},
    {"text": "Zijn verwant aan met kegelen gewonnen bekers. (10)", "label": 11},
    {"text": "Computer waar we beter van worden. (6)", "label": 12},
    {"text": "Stalles, parterre, loge, balkon. (8)", "label": 13},
    {"text": "Klantvriendelijkheid die zorgt voor afzet. (13)", "label": 15},
    {"text": "Is meer dan een goed boek. (3,6,4)", "label": 18},
    {"text": "Om zich te onderscheiden scherpe kritiek geven op Klaver c.s. (10)", "label": 19},
    {"text": "Is goed aan kant. (4)", "label": 20},
    {"text": "Het is een kunst om ernaar te luisteren. (6)", "label": 21},
    {"text": "Van evenveel betekenis. (8)", "label": 22},
]
HORIZONTAL_CLUE_CELLS = [
    [15, 16, 17, 18, 19, 20, 21],
    [46, 47, 48, 49, 50, 51, 52, 53, 54, 55],
    [75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85],
    [105, 106],
    [108, 109, 110, 111, 112, 113, 114, 115, 116, 117],
    [135, 136, 137, 138, 139, 140],
    [142, 143, 144, 145, 146, 147, 148, 149],
    [166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178],
    [196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208],
    [226, 227, 228, 229, 230, 231, 232, 233, 234, 235],
    [255, 256, 257, 258],
    [260, 261, 262, 263, 264, 265],
    [288, 289, 290, 291, 292, 293, 294, 295],
]

VERTICAL_CLUES = [
    {"text": "Een hiërarchisch bedrijf als de NS of KLM. (18)", "label": 1},
    {"text": "33 of 6. (10)", "label": 2},
    {"text": "Samen verdwaald zijn heeft iets ongemakkelijks. (4,3,5,3,6)", "label": 3},
    {"text": "Vallen tijdens de afdaling. (8)", "label": 5},
    {"text": "Wegdromen tijdens een vliegreis. (2,6,6,3)", "label": 7},
    {"text": "Naar een afgelegen plaats lokken. (9)", "label": 9},
    {"text": "Breiwerk of bijwerk. (5)", "label": 14},
    {"text": "Een partij die terug is heeft iets te vieren. (10)", "label": 16},
    {"text": "Eet de stuurman bij het ontbijt. (10)", "label": 17},
]
VERTICAL_CLUE_CELLS = [
    [1, 16, 31, 46, 61, 76, 91, 106, 121, 136, 151, 166, 181, 196, 211, 226, 241, 256],
    [3, 18, 33, 48, 63, 78, 93, 108, 123, 138],
    [5, 20, 35, 50, 65, 80, 95, 110, 125, 140, 155, 170, 185, 200, 215, 230, 245, 260, 275, 290, 305],
    [39, 54, 69, 84, 99, 114, 129, 144],
    [52, 67, 82, 97, 112, 127, 142, 157, 172, 187, 202, 217, 232, 247, 262, 277, 292],
    [101, 116, 131, 146, 161, 176, 191, 206, 221],
    [148, 163, 178, 193, 208],
    [168, 183, 198, 213, 228, 243, 258, 273, 288, 303],
    [174, 189, 204, 219, 234, 249, 264, 279, 294, 309],
]


def build_raw() -> dict:
    tokens = GRID.split("|")
    assert len(tokens) == ROWS * COLUMNS, f"tokens={len(tokens)} verwacht {ROWS*COLUMNS}"
    cell_data = []
    for t in tokens:
        if t == ".":
            cell_data.append({"solution": "", "value": "", "status": "", "visible": False})
        elif t == "#":
            cell_data.append({"solution": "", "value": "", "status": "", "visible": True})
        else:
            cell_data.append({"solution": t, "value": "", "status": "", "visible": True})

    # sanity tegen de live gemeten aantallen
    letter_vis = sum(1 for c in cell_data if c["solution"] and c["visible"])
    block_vis = sum(1 for c in cell_data if not c["solution"] and c["visible"])
    invisible = sum(1 for c in cell_data if not c["visible"])
    assert (letter_vis, block_vis, invisible) == (162, 90, 63), (letter_vis, block_vis, invisible)

    # elke clue-cel moet een witte lettercel zijn
    for group in (HORIZONTAL_CLUE_CELLS, VERTICAL_CLUE_CELLS):
        for cells in group:
            for idx in cells:
                assert cell_data[idx]["solution"] and cell_data[idx]["visible"], f"clue-cel {idx} klopt niet"

    return {
        "meta": {
            "gametype": "Cryptogram",
            "date": "2026-07-04",
            "puzzleid": "KNL-13577910",
            "customerid": "volkskrant",
            "puzzlevariation": "weekendPuzzlecrypto",
            "rows": ROWS,
            "columns": COLUMNS,
        },
        "cells": {"rows": ROWS, "columns": COLUMNS, "cellData": cell_data},
        "clues": {
            "horizontalClues": HORIZONTAL_CLUES,
            "horizontalClueCells": HORIZONTAL_CLUE_CELLS,
            "verticalClues": VERTICAL_CLUES,
            "verticalClueCells": VERTICAL_CLUE_CELLS,
        },
    }


if __name__ == "__main__":
    raw = build_raw()
    out = Path(__file__).with_name("sample_raw.json")
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {out} — {ROWS}x{COLUMNS}={len(raw['cells']['cellData'])} cellen "
        f"(162 letters / 90 blok / 63 onzichtbaar), "
        f"{len(HORIZONTAL_CLUES)}H + {len(VERTICAL_CLUES)}V clues"
    )
