# cryptogram2remarkable — technisch plan

Een service die wekelijks (zaterdagochtend) het Volkskrant-cryptogram ophaalt,
omzet naar een reMarkable-2-vriendelijke PDF (leeg rooster + omschrijvingen om
zelf op te lossen) en naar het apparaat uploadt. Draait onbewaakt op een Hetzner
VPS.

## Vastgestelde keuzes

| Onderwerp | Keuze |
|---|---|
| VK-authenticatie | **Herbruikbaar browserprofiel**: eenmalig ingelogd Playwright-profiel dat headless wordt hergebruikt. Geen wachtwoord op de VPS. |
| PDF-inhoud | **Alleen de lege puzzel**: leeg rooster + omschrijvingen om zelf op te lossen. `solution` wordt genegeerd. |
| Omschrijvingen | **Eén kolom**, twee secties onder elkaar: **"Horizontaal"** en **"Verticaal"**. |
| reMarkable-upload | **rmapi** (reMarkable Cloud), account beschikbaar. |
| Taal / stack | Python 3.11+, Playwright (Chromium), ReportLab, rmapi. |
| Scheduling | **systemd timer** (journald-logging, `Persistent=true` vangt gemiste runs op). |

### Layout: oriëntatie volgt de inhoud

Een cryptogram heeft in de praktijk zo'n ~22 clues, dus **rooster + clues passen
op één landscape-pagina**:

- **Rooster links** (ca. 55–60% breedte), zo groot mogelijk binnen de hoogte,
  celnummers linksboven in de startvakjes.
- **Omschrijvingen rechts**, één kolom, secties "Horizontaal" dan "Verticaal".

**Twee-pagina-vangnet → portrait.** Past het niet op één pagina (uitzonderlijk
veel/lange clues), dan schakelt de renderer automatisch over op **portrait**:
rooster groot op pagina 1, omschrijvingen (één kolom) op pagina 2. Zo blijft de
tekst leesbaar i.p.v. onleesbaar klein geschaald, en sluit de oriëntatie aan op de
native portrait-stand van de reMarkable. `LAYOUT=grid_first` forceert deze
portrait-twee-pagina-variant altijd; `LAYOUT=single_page` (default) probeert eerst
de ene landscape-pagina en valt alleen bij overloop terug op portrait.

---

## Geverifieerde bevindingen (live scrape 2026-07-04)

Deze zijn empirisch vastgesteld door de echte puzzel via Chrome uit te lezen en
zitten verwerkt in de fixture `tests/fixtures/sample_raw.json`.

**Twee cryptogrammen per dag — pak de juiste.** Er is een losse *dagelijkse*
cryptogram (widget `customerid=aldagpremium`, 11×11, volle rechthoek) én de
*krantenpuzzel* "Cryptogram - Puzzel uit de krant". De service moet de
**krantenpuzzel** hebben: tegel met ondertitel "Cryptogram - Puzzel uit de krant".

**URL-/parameterpatroon (bevestigd):**
- Overzicht: `volkskrant.nl/puzzels/ontdekken/cryptogram~genre23`
- Puzzelpagina: `.../puzzels/puzzels/cryptogram-YYYY-MM-DD~gXXXXXXXX`
- Widget (in `iframe.mychannels-fun-player__frame`, cross-origin):
  `web.braintainment.com/pub/puzzle/volkskrant/?gametype=Cryptogram&puzzleid=KNL-XXXXXXXX&customerid=volkskrant&puzzlevariation=weekendPuzzlecrypto&env=browser`
- De widget is cross-origin t.o.v. volkskrant.nl → de store is niet vanuit de
  parent te lezen. **Navigeer de scraper rechtstreeks naar de widget-URL** (zoals
  in het plan), dan is de React-app het topdocument.

**Auth (bevestigd):** DPG Media-login (e-mail + wachtwoord) op `login.dpgmedia.nl`
(`client_id=vk-selectives-web`, `dpg_medium=fun`). Zowel de dagelijkse als de
krantenpuzzel vereisen login → scraper draait altijd met ingelogd profiel.

**Tegel-resolutie (live geverifieerd):** de krantenpuzzel-tegel is geen `<a>` maar
een `div.mychannels-fun-tile` met een verborgen link
`a.js-link--puzzle[href=".../cryptogram-YYYY-MM-DD~gXXXXX"]`. Klikken werkt niet
betrouwbaar headless; lees de `href` uit en navigeer er direct heen. Kies de tegel
in de **featured** grid (`.mychannels-fun-tiles-grid--featured`, = "Vandaag") met
tekst "Puzzel uit de krant" — niet de Sudoku-krant-tegel of oudere datums.
**Vensterbreedte forceren** (`--window-size=1400,940`): anders toont volkskrant.nl
de mobiele layout zonder deze tegel.

**Widget-flow:** na openen verschijnt een modal **"Nieuwe puzzel → Starten"**;
klik "Starten" (of wacht tot de store gevuld is) voordat je uitleest.

**Redux-store uitlezen (bevestigd werkend):** loop vanaf een DOM-node omhoog via
`__reactFiber$…` tot een fiber met `memoizedProps.store.getState`. `getState()`
geeft o.a. `state.cells` en `state.clues`.

**Datamodel (bevestigd, weekendpuzzel 2026-07-04 = 21×15, 315 cellen):**
- `cells.rows`, `cells.columns`, `cells.cellData` = **platte array**, index =
  `rij * columns + kolom`.
- Cel = `{solution, value:"", status:"", visible}` (soms key `animation`, undefined).
- **Drie celtypes** (de renderer/normalizer MOET `visible` respecteren):
  | type | conditie | render |
  |---|---|---|
  | lettercel | `visible=true` & `solution!=""` | witte, invulbare cel |
  | blok | `visible=true` & `solution==""` | zwart vakje |
  | onzichtbaar | `visible=false` | **niets tekenen** (buiten de vorm) |
  Meetwaarden: 162 letters / 90 blok / 63 onzichtbaar. De krantenpuzzel is dus
  **onregelmatig van vorm** (geen volle rechthoek). De dagelijkse 11×11 had 0
  onzichtbare cellen — vandaar dat testen op de weekendpuzzel cruciaal is.
- **Meerletterige cellen bestaan**: Nederlandse **"IJ"** zit als één vakje in één
  cel (`solution` kan 2 tekens zijn). Reken nooit op 1 teken per cel.
- Clues: `horizontalClues`/`verticalClues` = `[{text, label}]`;
  `horizontalClueCells`/`verticalClueCells` = arrays van platte celindexen. De
  `label` (nummer) hoort bij `cells[0]` van dat woord. Nummering 1..N is **gedeeld**
  over H en V (standaard kruiswoordnummering).
- **Rooster-oriëntatie varieert**: de weekendpuzzel is 21×15 (portret-achtig, hoger
  dan breed). Op een landscape-pagina met rooster links betekent dat kleine cellen
  (~19 pt bij paginahoogte); houd de celgrootte dynamisch en pas 'm aan de
  paginahoogte aan, niet aan een vaste maat.

## Architectuur

Strikte scheiding tussen **scrape** en **render**, zodat je de PDF-layout kunt
itereren op een opgeslagen JSON-dump zonder telkens live te scrapen (de puzzel
verandert maar 1x per week).

```
resolve  →  scrape  →  normalize  →  render  →  upload
 (id)      (redux)     (schoon      (PDF)      (rmapi)
                        model)
```

Elke stap is een los CLI-subcommando en schrijft/leest een bestand op schijf, zodat
elke stap afzonderlijk draaibaar en testbaar is.

### Projectstructuur

```
cryptogram2remarkable/
├── pyproject.toml              # deps + console-script entrypoint
├── .env.example                # documenteert verwachte env-vars (geen secrets)
├── .gitignore                  # sluit data/, profile/, .env uit
├── README.md                   # setup + runbook
├── PLAN.md                     # dit document
├── src/cryptogram2remarkable/
│   ├── __init__.py
│   ├── config.py               # env-vars → typed Settings (pydantic-settings)
│   ├── model.py                # dataclasses: Puzzle, Cell, Clue
│   ├── resolve_puzzle.py       # stap 1: puzzle-id / widget-URL vinden
│   ├── scrape.py               # stap 2: Redux-state uitlezen
│   ├── normalize.py            # stap 3: ruwe data → schoon model
│   ├── render_pdf.py           # stap 4: PDF voor reMarkable 2
│   ├── upload.py               # stap 5: rmapi-wrapper
│   ├── notify.py               # optioneel: alert bij sessie-expiry/fout
│   ├── pipeline.py             # orkestratie + idempotentie + state
│   └── cli.py                  # argparse/typer entrypoints
├── data/                       # runtime output (git-ignored)
│   ├── raw-YYYY-MM-DD.json      # ruwe redux-dump
│   ├── puzzle-YYYY-MM-DD.json   # genormaliseerd model
│   ├── cryptogram-YYYY-MM-DD.pdf
│   ├── debug-YYYY-MM-DD.png     # screenshot bij scrape-fout
│   └── state.json              # laatst verwerkte puzzleid + upload-status
├── profile/                    # Playwright persistent context (git-ignored)
├── tests/
│   ├── fixtures/sample_raw.json     # bevroren redux-dump
│   ├── fixtures/sample_puzzle.json  # bevroren genormaliseerd model
│   ├── test_normalize.py
│   └── test_render.py
└── systemd/
    ├── cryptogram2remarkable.service
    └── cryptogram2remarkable.timer
```

---

## Stap 1 — Puzzle-ID achterhalen (`resolve_puzzle.py`)

- Open met de **persistente Playwright-context** de cryptogram-overzichtspagina
  (`volkskrant.nl/puzzels/ontdekken/cryptogram~genre23`) of de dag-URL
  (`cryptogram-YYYY-MM-DD~gXXXXXXXX`).
- Wacht op `iframe.mychannels-fun-player__frame`, lees de `src` en parse de
  querystring: `gametype`, `puzzleid`, `customerid`, `puzzlevariation`.
- Output: een dict met deze parameters + de volledige widget-URL.
- **Robuustheid**: als het iframe niet binnen een timeout verschijnt → controleer
  of we nog zijn ingelogd (paywall/consent-wall gedetecteerd?) en gooi een
  duidelijke, getypeerde fout (`SessionExpiredError` vs `StructureChangedError`),
  met een screenshot-dump naar `data/debug-*.png`.

## Stap 2 — Puzzeldata ophalen (`scrape.py`)

- Open de widget-URL in dezelfde persistente context (headless).
- Wacht tot de React-app gerenderd is (`button.carousel-bar__text` in de DOM).
- Via `page.evaluate()`: loop over het React-fiber-attribuut omhoog tot een
  component met een `store`-prop, roep `store.getState()` aan en retourneer
  `state.cells` en `state.clues` (+ `horizontalClueCells` / `verticalClueCells`).
- Schrijf de ruwe dump naar `data/raw-YYYY-MM-DD.json`. **Dit is het testanker**:
  alle latere stappen draaien hierop, live scrapen is daarna niet meer nodig.
- Retry met exponentiële backoff (tenacity) op transiente netwerk-/timeout-fouten.

## Stap 3 — Datamodel normaliseren (`normalize.py`, `model.py`)

Zet de ruwe Braintainment/Redux-structuur om naar een eigen, stabiel model:

```python
@dataclass
class Cell:
    row: int
    col: int
    is_block: bool          # zwart vakje?
    number: int | None      # clue-nummer als dit een startvakje is

@dataclass
class Clue:
    direction: Literal["H", "V"]
    number: int
    text: str
    cells: list[tuple[int, int]]   # celcoördinaten

@dataclass
class Puzzle:
    date: str
    rows: int
    cols: int
    grid: list[list[Cell]]
    clues: list[Clue]
```

- Celnummers worden hier **afgeleid** uit de clue→cel-koppeling (`label` van de
  clue op de eerste cel van het woord), zodat rooster en omschrijvingen
  gegarandeerd matchen — onafhankelijk van eigenaardigheden in de brondata.
- `solution` en `visible` worden bewust genegeerd (we willen een lege puzzel).
- Schrijf naar `data/puzzle-YYYY-MM-DD.json`. Dit bestand is de contract-input
  voor de renderer en voor de fixtures in `tests/`.

## Stap 4 — PDF-rendering (`render_pdf.py`)

**Library: ReportLab.** Dependency-licht (geen cairo/pango zoals WeasyPrint),
pixel-precieze controle over het rooster, en `Platypus` (Frames/Paragraphs) doet
automatische tekst-wrapping én paginering van de clue-lijst gratis.

**Canvas / maat reMarkable 2**: scherm 1872×1404 px @ 226 dpi. Zet de PDF op de
fysieke maat in points zodat lettergroottes echte points blijven:

```
breedte = 1872 / 226 * 72 ≈ 596.6 pt   (landscape)
hoogte  = 1404 / 226 * 72 ≈ 447.4 pt
```

- **Marges** ~24–32 pt rondom (veilige zone; reMarkable-UI-balk hapt niets weg).
- **Rooster (links, ~55–60% breedte)**: vierkante cellen zo groot mogelijk binnen
  de hoogte, zwarte blokken gevuld, witte cellen met dunne rand, clue-nummer klein
  linksboven in startvakjes. Grote cellen = fijn schrijven met de stylus.
- **Omschrijvingen (rechts, één kolom via Platypus-`Frame`)**: kop "Horizontaal",
  dan de H-clues (`<b>{nr}</b> {tekst}`), kop "Verticaal", dan de V-clues.
- **Oriëntatie volgt de inhoud**: past alles op één pagina → landscape; is er een
  tweede pagina nodig → de renderer bouwt opnieuw in **portrait** (rooster groot op
  pagina 1, clues op pagina 2). Zie de layout-sectie hierboven.
- **Lettergrootte** afgestemd op e-ink (rooster-nummers ~7–8 pt, clue-tekst
  ~10–11 pt met ruime leading). Config-overrides via env als je wilt bijstellen.
- Output: `data/cryptogram-YYYY-MM-DD.pdf`.

## Stap 5 — Upload naar reMarkable (`upload.py`)

- Wrapper om de **rmapi**-CLI (ddvk-fork). Eenmalige registratie buiten de code:
  `rmapi` vraagt om een one-time code van my.remarkable.com en bewaart het
  device-token in `~/.config/rmapi/rmapi.conf` — **niet** in de repo of logs.
- Upload naar een vaste map, bijv. `/Cryptogrammen`, met bestandsnaam
  `cryptogram-YYYY-MM-DD.pdf`.
- **Idempotentie**: vóór upload `rmapi ls /Cryptogrammen` checken; bestaat de naam
  al → skippen. Plus `state.json` met laatst geüploade puzzleid.

## Stap 6 — Orkestratie, scheduling & betrouwbaarheid (`pipeline.py`)

- `pipeline.run()` ketent de stappen, logt per stap gestructureerd
  (puzzel gevonden? data compleet? PDF gegenereerd? upload gelukt?).
- **Idempotentie & lock**: `state.json` (laatst verwerkte puzzleid + datum +
  upload-status) + een file-lock (`fcntl.flock`), zodat een dubbele run niet twee
  keer dezelfde pagina uploadt.
- **Sessie-check vooraf**: bezoek een abonnee-only element; bij expiry → stop met
  duidelijke `SessionExpiredError`, non-zero exit, en (optioneel) een alert via
  `notify.py` (e-mail/ntfy) met de melding "log opnieuw in en sync het profiel".
- **Foutdiagnose**: bij gewijzigde class-namen/structuur een `StructureChangedError`
  + screenshot, zodat je snel ziet wat de Volkskrant heeft veranderd.

### systemd (aanbevolen boven cron)

`cryptogram2remarkable.timer` — `OnCalendar=Sat 08:00`, `Persistent=true`,
`Europe/Amsterdam`. `cryptogram2remarkable.service` (Type=oneshot) draait
`c2rm run` als een dedicated user, met `EnvironmentFile=/etc/c2rm.env`
(chmod 600). Logs via `journalctl -u cryptogram2remarkable`.

---

## Configuratie & secrets

Alles via env-vars; `.env.example` documenteert ze (nooit echte waarden in de repo):

```
# .env.example
PROFILE_DIR=./profile              # Playwright persistent context
DATA_DIR=./data
RM_FOLDER=/Cryptogrammen           # doelmap op reMarkable
LAYOUT=single_page                 # of: grid_first
TIMEZONE=Europe/Amsterdam
LOG_LEVEL=INFO
# optioneel voor alerts:
NOTIFY_EMAIL=
SMTP_URL=
```

- **VK-sessie**: zit in `PROFILE_DIR` (het browserprofiel), niet als cookies in
  env. Wordt lokaal aangemaakt en naar de VPS gekopieerd (zie onder).
- **reMarkable-token**: in rmapi's eigen config, buiten de repo.

---

## Eenmalige setup (runbook)

1. **VPS voorbereiden**: Python 3.11+, `pip install -e .`,
   `playwright install chromium` + `playwright install-deps`.
2. **Browserprofiel aanmaken (lokaal, met beeldscherm)**: draai `c2rm login`
   headed op je eigen machine, log in bij de Volkskrant, accepteer de
   consent/cookie-wall. Kopieer daarna de map `profile/` met `scp`/`rsync` naar de
   VPS. (Headless VPS heeft geen display voor de interactieve login.)
3. **rmapi registreren** op de VPS: `rmapi` → one-time code van
   my.remarkable.com invoeren.
4. **systemd installeren**: units naar `/etc/systemd/system/`, `.env` naar
   `/etc/c2rm.env` (chmod 600), `systemctl enable --now cryptogram2remarkable.timer`.
5. **Droogtest**: `c2rm run --dry-run` (scrape→render, geen upload) en controleer
   de PDF.

---

## Testbaarheid

- CLI-subcommando's: `resolve`, `scrape`, `normalize`, `render`, `upload`, `run`,
  `login`, `check-session`.
- `render` draait op een fixture (`tests/fixtures/sample_puzzle.json`), dus je
  itereert de layout zonder te scrapen.
- `test_normalize.py`: bevroren `sample_raw.json` → verwacht model.
- `test_render.py`: rendert de fixture en assert dat er een niet-lege PDF met het
  verwachte aantal pagina's uitkomt (grid-pagina aanwezig, clue-pagina's aanwezig).

---

## Bekende risico's

- **Akamai bot-detectie (opgelost).** De DPG-login (`login.dpgmedia.nl`) zit achter
  Akamai Bot Manager en weigert een geautomatiseerde browser met HTTP 406 — óók met
  `channel="chrome"`, want Akamai detecteert de CDP-automation (`Runtime.enable`).
  Opgelost met **patchright** (gepatchte Playwright) + **echte Google Chrome**.
  Empirisch (2026-07): login werkt headed, scrape werkt headless. Vereist dus
  `google-chrome-stable` op de VPS. Als de headless scrape ooit alsnog 406 geeft:
  `C2RM_HEADLESS=false` + `xvfb-run`. Merk op: `login.dpgmedia.nl` is strenger dan
  `volkskrant.nl`; de weekrun raakt dat domein alleen als de sessie is verlopen —
  dat wordt afgevangen als `SessionExpiredError` (schone melding, geen stille 406).
- **Cross-OS cookie-versleuteling (opgelost).** Chrome versleutelt cookies met een
  OS-specifieke sleutel (macOS Keychain vs. Linux keyring), dus een macOS-profiel
  naar Linux kopiëren logt niet in — de cookiewaarden zijn onleesbaar. Opgelost met
  een **draagbare `session.json`** (Playwright `storage_state`: platte cookies):
  `c2rm login` leest die **live via CDP** uit de nog draaiende, ingelogde Chrome
  (cruciaal op macOS: cookies op schijf zijn Keychain-versleuteld en een los
  heropend profiel geeft 0 cookies terug). De scraper injecteert de cookies
  (`add_cookies`) in een vers profiel op de VPS. Diagnose met `c2rm debug-cookies`.
  Je kopieert dus alleen `session.json`, niet het profiel. Bewezen: de VPS scrapet
  hiermee prima vanaf zijn datacenter-IP (geen IP-blok).
- **Selector-drift**: Volkskrant/Braintainment kan class-namen of de
  Redux-structuur wijzigen. Afgevangen met getypeerde fouten + screenshot; fix is
  dan een kleine, geïsoleerde aanpassing in `resolve_puzzle.py`/`scrape.py`.
- **Sessie-expiry**: het profiel verloopt periodiek → handmatig opnieuw inloggen
  en profiel opnieuw kopiëren. `check-session` + alert maken dit zichtbaar i.p.v.
  een stille mislukking.
- **Uitschieter in clue-aantal**: normaal past alles op één pagina; bij een
  uitzonderlijk grote puzzel loopt de clue-lijst door naar een tweede pagina —
  bewust toegestaan (paginering is automatisch).
```

