# cryptogram2remarkable

Haalt wekelijks (zaterdagochtend) het **Volkskrant-cryptogram uit de krant** op,
rendert het als één landscape-PDF op reMarkable-2-maat (leeg rooster + clues om
zelf op te lossen) en uploadt het naar je reMarkable. Ontworpen om zelfstandig op
een VPS te draaien.

Zie [PLAN.md](PLAN.md) voor het volledige ontwerp en de geverifieerde bevindingen
over de databron.

## Pijplijn

```
scrape  ->  normalize  ->  render  ->  upload
(Redux)     (schoon       (PDF        (rmapi ->
            model)         reMarkable)  reMarkable Cloud)
```

Elke stap is een los CLI-subcommando en schrijft naar `data/`, zodat je de render
kunt itereren op een fixture zonder live te scrapen.

## Installatie (lokaal)

Voor de eenmalige login op je Mac. (Op de VPS doet `deploy/bootstrap.sh` dit voor
je — zie [Deployment op de VPS](#deployment-op-de-vps).)

```bash
python3 -m venv .venv
source .venv/bin/activate      # nodig; hierna is `c2rm` beschikbaar
pip install -e .               # maakt het `c2rm`-commando aan (entry point)
```

> Het `c2rm`-commando bestaat **pas na `pip install -e .`** en alleen met de venv
> geactiveerd. Zonder activeren kun je ook het volledige pad gebruiken:
> `.venv/bin/c2rm ...`.

### Browser: echte Google Chrome (verplicht)

De DPG-login zit achter **Akamai bot-detectie** die een geautomatiseerde browser
weigert (HTTP 406) — óók met `channel="chrome"`, want de CDP-besturing is
detecteerbaar. We gebruiken daarom [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)
(gepatchte Playwright, meegeïnstalleerd via `pip install -e .`) met **echte Google
Chrome** (`C2RM_BROWSER_CHANNEL=chrome`). Lokaal (Mac) heb je Chrome al; op de VPS
installeert `deploy/bootstrap.sh` automatisch `google-chrome-stable`. De login zelf
wordt bewust **niet** geautomatiseerd (zie hieronder), anders blokkeert Akamai die
alsnog.

## Lokaal: inloggen en sessie exporteren

`c2rm login` opent een gewone, **mensgestuurde** Chrome (geen automation, geen CDP),
zodat Akamai je normaal binnenlaat, en exporteert daarna een **draagbare sessie**
`session.json`:

```bash
source .venv/bin/activate
c2rm login          # log in, LAAT Chrome open, druk dan op Enter
```

`login` leest de cookies live uit de draaiende Chrome via CDP (nodig op macOS: de
cookies op schijf zijn Keychain-versleuteld en alleen de live sessie geeft ze
ontsleuteld terug). Verloopt de sessie later, draai dan opnieuw `c2rm login`.

> **Waarom niet het hele profiel kopiëren?** Chrome versleutelt cookies met een
> OS-specifieke sleutel (macOS Keychain vs. Linux keyring), dus een macOS-profiel
> logt op een Linux-VPS níét in. `session.json` bevat de cookies als platte,
> OS-onafhankelijke JSON — dát kopieer je naar de VPS. De scraper injecteert 'm in
> een vers profiel. Verloopt de sessie ooit, draai dan opnieuw `c2rm login` en
> kopieer de nieuwe `session.json`.

## Deployment op de VPS

1. **Code naar de VPS** (git clone, of rsync vanaf je Mac), bijv. naar
   `/opt/cryptogram2remarkable`:
   ```bash
   sudo rsync -a --exclude .venv --exclude profile --exclude data ./ <vps>:/opt/cryptogram2remarkable/
   ```
2. **Bootstrap draaien** — installeert Chrome, Xvfb, venv + package, service-user,
   mappen en de systemd-units:
   ```bash
   cd /opt/cryptogram2remarkable && sudo bash deploy/bootstrap.sh
   ```
3. **Handmatige stappen** (de bootstrap somt ze aan het eind ook op):
   ```bash
   # a) draagbare sessie kopiëren vanaf je Mac (~15 KB) + eigendom
   rsync -a session.json <vps>:/opt/cryptogram2remarkable/session.json
   sudo chown c2rm:c2rm /opt/cryptogram2remarkable/session.json
   sudo -u c2rm /opt/cryptogram2remarkable/.venv/bin/c2rm debug-cookies   # verifieer: ingelogd: True

   # b) rmapi installeren (binary van github.com/ddvk/rmapi/releases -> /usr/local/bin)
   #    en registreren met de one-time code van my.remarkable.com:
   sudo -u c2rm RMAPI_CONFIG=/opt/cryptogram2remarkable/rmapi.conf rmapi

   # c) testen, dan de timer aanzetten
   sudo -u c2rm /opt/cryptogram2remarkable/.venv/bin/c2rm check-session
   sudo -u c2rm /opt/cryptogram2remarkable/.venv/bin/c2rm run --dry-run
   sudo systemctl enable --now cryptogram2remarkable.timer
   ```

De timer draait zaterdag 08:00 (`Persistent=true` haalt een gemiste run in). Logs:
`journalctl -u cryptogram2remarkable`. Geeft de headless scrape op de VPS toch een
406, zet dan `C2RM_HEADLESS=false` in `/etc/c2rm.env` en gebruik de Xvfb-ExecStart
uit het service-bestand.

## Gebruik

```bash
c2rm check-session                 # is het profiel nog ingelogd?
c2rm scrape                        # ruwe dump -> data/raw-YYYY-MM-DD.json
c2rm run --dry-run                 # volledige pijplijn zonder upload
c2rm run                           # scrape -> render -> upload

# render itereren zonder scrapen:
c2rm render --raw tests/fixtures/sample_raw.json --out data/out.pdf
c2rm render --raw tests/fixtures/sample_raw.json --out data/out.pdf --layout grid_first
```

## Testen

```bash
pip install -e ".[dev]"
pytest
```

De fixture `tests/fixtures/sample_raw.json` is een echte weekendpuzzel (2026-07-04,
21×15, onregelmatige vorm met "IJ"-vakjes), zodat normalize/render getest worden op
de lastige gevallen.

## Secrets

Niets gevoeligs in de repo: de VK-sessie leeft in `profile/` en de draagbare
`session.json` (beide git-ignored), het reMarkable-token in `rmapi.conf` (via
`RMAPI_CONFIG`, ook git-ignored). `.env` en `/etc/c2rm.env` staan buiten de repo.
