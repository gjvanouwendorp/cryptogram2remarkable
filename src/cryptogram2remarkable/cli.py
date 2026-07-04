"""Command-line interface.

Elke stap is een los subcommando en leest/schrijft naar schijf, zodat je de
render kunt itereren op een fixture zonder live te scrapen.

Voorbeelden:
    c2rm normalize --raw tests/fixtures/sample_raw.json --out data/puzzle.json
    c2rm render    --raw tests/fixtures/sample_raw.json --out data/cryptogram.pdf
    c2rm render    --puzzle data/puzzle.json --out data/cryptogram.pdf --layout grid_first

Scrape/upload/pipeline volgen later.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from .model import Puzzle
from .normalize import normalize
from .render_pdf import render_pdf


def _load_raw(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_puzzle(args) -> Puzzle:
    if getattr(args, "raw", None):
        return normalize(_load_raw(args.raw))
    if getattr(args, "puzzle", None):
        return Puzzle.from_dict(json.loads(Path(args.puzzle).read_text(encoding="utf-8")))
    raise SystemExit("Geef --raw of --puzzle op.")


def cmd_normalize(args) -> int:
    puzzle = normalize(_load_raw(args.raw))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(puzzle.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Genormaliseerd: {out} — {puzzle.rows}x{puzzle.cols}, "
          f"{len(puzzle.horizontal)}H + {len(puzzle.vertical)}V clues")
    return 0


def cmd_render(args) -> int:
    puzzle = _load_puzzle(args)
    out = render_pdf(puzzle, args.out, layout=args.layout)
    print(f"PDF geschreven: {out} (layout={args.layout})")
    return 0


def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def cmd_login(_args) -> int:
    from .config import load_settings
    from .session import login
    login(load_settings())
    return 0


def cmd_check_session(_args) -> int:
    from .config import load_settings
    from .session import check_session
    ok = check_session(load_settings())
    print("Ingelogd." if ok else "NIET ingelogd — opnieuw inloggen en profiel syncen.")
    return 0 if ok else 1


def cmd_export_session(_args) -> int:
    from .config import load_settings
    from .session import export_session
    s = load_settings()
    export_session(s)
    print(f"Sessie geëxporteerd naar {s.session_file}")
    return 0


def cmd_debug_cookies(_args) -> int:
    """Diagnose: laadt profiel + sessie en rapporteert cookies (draai op de VPS)."""
    from collections import Counter
    from patchright.sync_api import sync_playwright
    from .config import load_settings, OVERVIEW_URL
    from .browser import launch_persistent
    s = load_settings()
    print(f"profile_dir : {s.profile_dir.resolve()} (exists={s.profile_dir.exists()})")
    print(f"session_file: {s.session_file.resolve()} (exists={s.session_file.exists()})")
    with sync_playwright() as pw:
        ctx = launch_persistent(pw, s, headless=s.headless)
        try:
            cks = ctx.cookies()
            vk = [c for c in cks if "volkskrant" in c["domain"] or "dpg" in c["domain"]]
            empty = sum(1 for c in cks if not c.get("value"))
            print(f"cookies totaal: {len(cks)} | volkskrant/dpg: {len(vk)} | lege waarde: {empty}")
            print("top domeinen:", Counter(c["domain"] for c in cks).most_common(6))
            page = ctx.new_page()
            resp = page.goto(OVERVIEW_URL, wait_until="domcontentloaded", timeout=45_000)
            print(f"overzicht status: {resp.status if resp else '?'} | url: {page.url[:60]}")
            print("ingelogd:" , "login.dpgmedia.nl" not in page.url and len(vk) > 0)
        finally:
            ctx.close()
    return 0


def cmd_debug_overview(_args) -> int:
    """Diagnose: laadt het overzicht en rapporteert tegels + gefaalde requests."""
    from patchright.sync_api import sync_playwright
    from .config import load_settings, OVERVIEW_URL
    from .browser import launch_persistent
    s = load_settings()
    s.ensure_dirs()
    failures: list[tuple[int, str]] = []
    with sync_playwright() as pw:
        ctx = launch_persistent(pw, s, headless=s.headless)
        page = ctx.new_page()
        page.on("response", lambda r: failures.append((r.status, r.url)) if r.status >= 400 else None)
        try:
            page.goto(OVERVIEW_URL, wait_until="networkidle", timeout=60_000)
        except Exception as e:  # networkidle kan timen; ga door met wat er is
            print("waarschuwing bij laden:", repr(e)[:100])
        info = page.evaluate(
            r"""() => {
              const tiles = document.querySelectorAll('.mychannels-fun-tile');
              const featured = document.querySelectorAll('.mychannels-fun-tiles-grid--featured .mychannels-fun-tile');
              const krant = [...tiles].filter(t => (t.innerText||'').toLowerCase().includes('puzzel uit de krant'));
              let krantHref = null;
              for (const t of krant) { const a = t.querySelector('a.js-link--puzzle'); if (a) { krantHref = a.getAttribute('href'); break; } }
              const body = document.body.innerText || '';
              return { tiles: tiles.length, featured: featured.length, krant: krant.length,
                       krantHref, loginModal: body.includes('Exclusief voor ingelogde'),
                       recent: body.includes('Recent gespeeld') };
            }"""
        )
        print("overzicht:", info)
        png = s.data_dir / "debug-overview.png"
        page.screenshot(path=str(png))
        print("screenshot:", png)
        api_fail = [(st, u) for st, u in failures if any(k in u for k in ("mychannels", "braintainment", "volkskrant", "dpg"))]
        print(f"gefaalde requests (>=400): {len(failures)} totaal, relevante:")
        for st, u in api_fail[:20]:
            print(f"  {st}  {u[:110]}")
        ctx.close()
    return 0


def cmd_scrape(args) -> int:
    from .config import load_settings
    from .scrape import scrape_to_file
    out = scrape_to_file(load_settings(), _parse_date(args.date))
    print(f"Ruwe dump geschreven: {out}")
    return 0


def cmd_run(args) -> int:
    from .config import load_settings
    from .pipeline import run
    settings = load_settings()
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run(settings, _parse_date(args.date), dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c2rm", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_norm = sub.add_parser("normalize", help="ruwe scrape -> schoon model (JSON)")
    p_norm.add_argument("--raw", required=True)
    p_norm.add_argument("--out", required=True)
    p_norm.set_defaults(func=cmd_normalize)

    p_render = sub.add_parser("render", help="model -> PDF voor reMarkable 2")
    src = p_render.add_mutually_exclusive_group(required=True)
    src.add_argument("--raw", help="ruwe scrape-JSON (wordt eerst genormaliseerd)")
    src.add_argument("--puzzle", help="genormaliseerd model-JSON")
    p_render.add_argument("--out", required=True)
    p_render.add_argument("--layout", default="single_page",
                          choices=["single_page", "grid_first"])
    p_render.set_defaults(func=cmd_render)

    p_login = sub.add_parser("login", help="eenmalig inloggen (lokaal, headed) -> profielmap")
    p_login.set_defaults(func=cmd_login)

    p_check = sub.add_parser("check-session", help="controleer of het profiel nog ingelogd is")
    p_check.set_defaults(func=cmd_check_session)

    p_export = sub.add_parser("export-session", help="exporteer draagbare sessie (session.json) uit het profiel")
    p_export.set_defaults(func=cmd_export_session)

    p_dbg = sub.add_parser("debug-cookies", help="diagnose: toon geladen cookies (draai op de VPS)")
    p_dbg.set_defaults(func=cmd_debug_cookies)

    p_dbg2 = sub.add_parser("debug-overview", help="diagnose: tegels + gefaalde requests op het overzicht")
    p_dbg2.set_defaults(func=cmd_debug_overview)

    p_scrape = sub.add_parser("scrape", help="scrape de krantenpuzzel -> ruwe JSON")
    p_scrape.add_argument("--date", help="ISO-datum (default: vandaag)")
    p_scrape.set_defaults(func=cmd_scrape)

    p_run = sub.add_parser("run", help="volledige pipeline: scrape -> render -> upload")
    p_run.add_argument("--date", help="ISO-datum (default: vandaag)")
    p_run.add_argument("--dry-run", action="store_true", help="niet uploaden")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
