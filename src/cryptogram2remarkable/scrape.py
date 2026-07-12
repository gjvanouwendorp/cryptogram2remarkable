"""Stap 1+2: puzzel-ID achterhalen en de Redux-data ophalen met Playwright.

Werkwijze (live bevestigd 2026-07-12, na de VK-site-redesign):
1. Open de overzichts-URL met het HERBRUIKBARE, ingelogde profiel
   (launch_persistent_context op C2RM_PROFILE_DIR). Deze redirect naar de
   dagelijkse cryptogrampagina met tabs (Mini / Normaal / Uit de krant).
2. Volg de "Uit de krant"-variantlink (`a[href*="/variant/uit-de-krant/"]`).
3. Volg op de variantpagina de "Speel"-link naar de speelpagina
   (`a[href*="/variant/uit-de-krant/"][href*="/speel/"]`); pas daar verschijnt
   de braintainment-widget als iframe.
4. Lees de iframe-src (selecteer op host `web.braintainment.com`; de class is
   nu een instabiele CSS-module-hash). Controleer dat het de krantenpuzzel is
   (customerid=volkskrant, puzzlevariation=weekendPuzzlecrypto).
5. Navigeer de pagina rechtstreeks naar die widget-URL (cross-origin; als iframe
   niet leesbaar). Klik "Starten" indien aanwezig.
6. Wacht tot de React/Redux-store gevuld is en lees `state.cells`/`state.clues`
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
from .config import (
    KRANT_CUSTOMERID,
    KRANT_PUZZLEVARIATION,
    OVERVIEW_URL,
    Settings,
    WIDGET_HOST,
)
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

            # Stap 2: volg de "Uit de krant"-variantlink. De overzichts-URL
            # redirect naar de dagelijkse cryptogrampagina met tabs; de
            # weekend-krantpuzzel zit achter deze variant (semantische slug,
            # geen instabiele hash). Klikken werkt niet betrouwbaar in headless,
            # de absolute href oplezen en direct navigeren wel.
            variant_href = _resolve_href(
                page, 'a[href*="/variant/uit-de-krant/"]',
                "'Uit de krant'-variantlink", debug_png,
            )
            page.goto(variant_href, wait_until="domcontentloaded", timeout=45_000)

            # De variant/speel-routes triggeren een silent OIDC-token-refresh
            # (prompt=none -> login2.volkskrant.nl/authorize). Laat die eerst
            # afronden; anders breekt de volgende navigatie af (ERR_ABORTED) of
            # blijft de pagina op de authorize-URL hangen.
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except PWTimeout:
                pass

            # Stap 3: klik de "Speel"-link. Dit is een Next.js/SPA-navigatie naar
            # de speelpagina (een harde `goto` wordt door de app afgebroken); pas
            # daar laadt de braintainment-widget als iframe.
            speel = page.locator(
                'a[href*="/variant/uit-de-krant/"][href*="/speel/"]').first
            try:
                speel.wait_for(state="attached", timeout=20_000)
                speel.click(timeout=15_000, no_wait_after=True)
            except PWTimeout as e:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    "'Speel'-link (uit de krant) niet gevonden/klikbaar. "
                    f"Screenshot: {debug_png}"
                ) from e

            # Stap 4: widget-iframe (selecteer op host; class is een instabiele
            # CSS-module-hash geworden).
            try:
                frame_el = page.wait_for_selector(
                    f'iframe[src*="{WIDGET_HOST}"]', state="attached", timeout=30_000)
            except PWTimeout as e:
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    f"Widget-iframe (host {WIDGET_HOST}) ontbreekt op de speelpagina. "
                    f"Screenshot: {debug_png}"
                ) from e

            src = frame_el.get_attribute("src") or ""
            qs = parse_qs(urlparse(src).query)
            host = urlparse(src).netloc
            if (host != WIDGET_HOST
                    or qs.get("customerid", [""])[0] != KRANT_CUSTOMERID
                    or qs.get("puzzlevariation", [""])[0] != KRANT_PUZZLEVARIATION):
                page.screenshot(path=str(debug_png))
                raise StructureChangedError(
                    f"Widget-URL wijkt af (host={host}, "
                    f"customerid={qs.get('customerid')}, "
                    f"puzzlevariation={qs.get('puzzlevariation')}). Screenshot: {debug_png}"
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


def _resolve_href(page, selector: str, wat: str, debug_png: Path) -> str:
    """Wacht op een <a>, geef de volledig-opgeloste (absolute) href terug.

    `el.href` levert altijd een absolute URL, ongeacht of het attribuut relatief
    is — zo hoeven we niet zelf te urljoinen.
    """
    from patchright.sync_api import TimeoutError as PWTimeout

    loc = page.locator(selector).first
    try:
        loc.wait_for(state="attached", timeout=20_000)
        href = loc.evaluate("el => el.href")
    except PWTimeout as e:
        page.screenshot(path=str(debug_png))
        raise StructureChangedError(
            f"{wat} niet gevonden ({selector}). Screenshot: {debug_png}"
        ) from e
    if not href:
        page.screenshot(path=str(debug_png))
        raise StructureChangedError(f"{wat} zonder href. Screenshot: {debug_png}")
    return href


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
