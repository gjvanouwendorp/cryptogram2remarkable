"""Stap 1+2: puzzel-ID achterhalen en de Redux-data ophalen met Playwright.

Werkwijze (live bevestigd 2026-07-04):
1. Open de overzichtspagina met het HERBRUIKBARE, ingelogde profiel
   (launch_persistent_context op C2RM_PROFILE_DIR).
2. Klik de tegel "Cryptogram - Puzzel uit de krant" -> puzzelpagina met
   `iframe.mychannels-fun-player__frame`.
3. Lees de iframe-src; controleer dat het de krantenpuzzel is
   (customerid=volkskrant, gametype=Cryptogram).
4. Navigeer de pagina rechtstreeks naar die widget-URL (cross-origin; als iframe
   niet leesbaar). Klik "Starten" indien aanwezig.
5. Wacht tot de React/Redux-store gevuld is en lees `state.cells`/`state.clues`
   uit via het React-fiber.

Levert een ruwe dict op in exact dezelfde vorm als tests/fixtures/sample_raw.json,
zodat normalize/render er identiek op werken.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .browser import launch_persistent
from .config import KRANT_CUSTOMERID, OVERVIEW_URL, Settings, WIDGET_HOST
from .errors import SessionExpiredError, StructureChangedError

# JS dat via het React-fiber de store vindt en de puzzeldata teruggeeft.
_EXTRACT_JS = r"""
() => {
  function findStore(root){
    if(!root) return null;
    const key = Object.keys(root).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
    if(!key) return null;
    let fiber = root[key];
    while(fiber){
      const p = fiber.memoizedProps;
      if(p && p.store && typeof p.store.getState === 'function') return p.store;
      if(p && p.value && typeof p.value.getState === 'function') return p.value;
      fiber = fiber.return;
    }
    return null;
  }
  const candidates = [document.querySelector('#root'), document.body, ...document.body.querySelectorAll('div')];
  let store = null;
  for(const c of candidates){ store = findStore(c); if(store) break; }
  if(!store) return null;
  const s = store.getState();
  if(!s || !s.cells || !s.clues) return null;
  if(!Array.isArray(s.cells.cellData) || s.cells.cellData.length === 0) return null;
  return {
    cells: { rows: s.cells.rows, columns: s.cells.columns, cellData: s.cells.cellData },
    clues: {
      horizontalClues: s.clues.horizontalClues,
      horizontalClueCells: s.clues.horizontalClueCells,
      verticalClues: s.clues.verticalClues,
      verticalClueCells: s.clues.verticalClueCells
    }
  };
}
"""


@retry(retry=retry_if_exception_type(StructureChangedError),
       stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20),
       reraise=True)
def scrape(settings: Settings, on_date: date | None = None) -> dict:
    """Scrape de krantenpuzzel; retourneert de ruwe dict (raw)."""
    from patchright.sync_api import TimeoutError as PWTimeout, sync_playwright

    on_date = on_date or date.today()
    debug_png = settings.data_dir / f"debug-{on_date.isoformat()}.png"

    with sync_playwright() as pw:
        ctx = launch_persistent(pw, settings, headless=settings.headless)
        page = ctx.new_page()
        try:
            page.goto(OVERVIEW_URL, wait_until="domcontentloaded", timeout=45_000)
            _assert_logged_in(page)

            # Vind de krantenpuzzel-tegel (featured grid, "Vandaag") en lees de
            # verborgen navigatielink eruit; klikken werkt niet betrouwbaar in
            # headless, direct navigeren wel.
            try:
                tile = page.locator(
                    ".mychannels-fun-tiles-grid--featured .mychannels-fun-tile",
                    has_text="Puzzel uit de krant",
                ).first
                href = tile.locator("a.js-link--puzzle").first.get_attribute("href", timeout=20_000)
            except PWTimeout as e:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    "Tegel 'Cryptogram - Puzzel uit de krant' (featured) niet gevonden. "
                    f"Screenshot: {debug_png}"
                ) from e
            if not href:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(f"Krantenpuzzel-tegel zonder link. Screenshot: {debug_png}")

            # Puzzelpagina -> widget-iframe.
            page.goto(href, wait_until="domcontentloaded", timeout=45_000)
            try:
                frame_el = page.wait_for_selector(
                    "iframe.mychannels-fun-player__frame", state="attached", timeout=30_000)
            except PWTimeout as e:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    f"iframe.mychannels-fun-player__frame ontbreekt. Screenshot: {debug_png}"
                ) from e

            src = frame_el.get_attribute("src") or ""
            qs = parse_qs(urlparse(src).query)
            host = urlparse(src).netloc
            if host != WIDGET_HOST or qs.get("customerid", [""])[0] != KRANT_CUSTOMERID:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    f"Widget-URL wijkt af (host={host}, customerid={qs.get('customerid')}). "
                    f"Screenshot: {debug_png}"
                )

            # Navigeer rechtstreeks naar de widget (wordt topdocument).
            page.goto(src, wait_until="domcontentloaded", timeout=45_000)

            # "Nieuwe puzzel -> Starten" wegklikken indien aanwezig.
            try:
                page.get_by_role("button", name="Starten").click(timeout=8_000)
            except PWTimeout:
                pass  # geen modal; puzzel was al gestart

            # Wacht tot de store gevuld is.
            try:
                page.wait_for_function(f"({_EXTRACT_JS})() !== null", timeout=30_000)
            except PWTimeout as e:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    f"Redux-store niet gevonden/gevuld. Screenshot: {debug_png}"
                ) from e

            data = page.evaluate(_EXTRACT_JS)
            if not data:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(f"Lege puzzeldata. Screenshot: {debug_png}")

            data["meta"] = {
                "gametype": qs.get("gametype", ["Cryptogram"])[0],
                "date": on_date.isoformat(),
                "puzzleid": qs.get("puzzleid", [""])[0],
                "customerid": qs.get("customerid", [""])[0],
                "puzzlevariation": qs.get("puzzlevariation", [""])[0],
                "rows": data["cells"]["rows"],
                "columns": data["cells"]["columns"],
            }
            return data
        finally:
            ctx.close()


def _assert_logged_in(page) -> None:
    """Faal snel en duidelijk als het profiel niet (meer) is ingelogd."""
    if "login.dpgmedia.nl" in page.url:
        raise SessionExpiredError(
            "Profiel is niet ingelogd (redirect naar login.dpgmedia.nl). "
            "Log lokaal opnieuw in en synchroniseer de profielmap naar de VPS."
        )


def scrape_to_file(settings: Settings, on_date: date | None = None) -> Path:
    on_date = on_date or date.today()
    settings.ensure_dirs()
    raw = scrape(settings, on_date)
    out = settings.data_dir / f"raw-{on_date.isoformat()}.json"
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
