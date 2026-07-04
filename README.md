# cryptogram2remarkable

Haalt wekelijks (zaterdagochtend) het **Volkskrant-cryptogram uit de krant** op,
rendert het als één landscape-PDF op reMarkable-2-maat (leeg rooster + clues om
zelf op te lossen) en uploadt het naar je reMarkable. Ontworpen om onbewaakt op
een Hetzner VPS te draaien.

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

## Installatie (VPS)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
playwright install chromium
playwright install-deps        # systeem-libs voor headless Chromium
cp .env.example .env           # en invullen
```

## Eenmalige setup

1. **Login-profiel (lokaal, met beeldscherm):**
   ```bash
   c2rm login          # opent een browser; log in bij de Volkskrant
   rsync -a profile/ vps:/opt/cryptogram2remarkable/profile/
   ```
   Headless VPS heeft geen scherm voor de interactieve login, daarom lokaal doen
   en de profielmap kopiëren.

2. **rmapi registreren (op de VPS):**
   ```bash
   rmapi        # voer de one-time code van my.remarkable.com in
   ```

3. **systemd:**
   ```bash
   sudo cp systemd/*.{service,timer} /etc/systemd/system/
   sudo cp .env /etc/c2rm.env && sudo chmod 600 /etc/c2rm.env
   sudo systemctl enable --now cryptogram2remarkable.timer
   ```

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

Niets gevoeligs in de repo: de VK-sessie leeft in `profile/` (git-ignored), het
reMarkable-token in `~/.config/rmapi/rmapi.conf`. `.env` staat in `.gitignore`.
