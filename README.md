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

## Installatie

Zowel lokaal (voor de eenmalige login) als op de VPS:

```bash
python3 -m venv .venv
source .venv/bin/activate      # nodig; hierna is `c2rm` beschikbaar
pip install -e .               # maakt het `c2rm`-commando aan (entry point)
```

> Het `c2rm`-commando bestaat **pas na `pip install -e .`** en alleen met de venv
> geactiveerd. Zonder activeren kun je ook het volledige pad gebruiken:
> `.venv/bin/c2rm ...`.

### Browser: echte Google Chrome (verplicht)

De DPG-login zit achter **Akamai bot-detectie**, die een kale Playwright-browser
weigert (HTTP 406). We gebruiken daarom [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)
(gepatchte Playwright, meegeïnstalleerd via `pip install -e .`) met **echte Google
Chrome** (`C2RM_BROWSER_CHANNEL=chrome`).

- **Lokaal (Mac):** Google Chrome is er al — niets extra's nodig.
- **VPS:** installeer `google-chrome-stable`. Dat pakket zit achter Google's eigen
  apt-repo (de enige externe bron die je toevoegt):
  ```bash
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
  sudo apt-get update && sudo apt-get install -y google-chrome-stable
  cp .env.example .env          # en invullen
  ```

## Eenmalige setup

1. **Login-profiel aanmaken — doe dit LOKAAL (met beeldscherm):**
   ```bash
   source .venv/bin/activate
   c2rm login          # opent een browser; log in bij de Volkskrant
   rsync -a profile/ vps:/opt/cryptogram2remarkable/profile/
   ```
   Een headless VPS heeft geen scherm voor de interactieve login, dus dit gebeurt
   lokaal; daarna kopieer je de profielmap naar de VPS. (Lokaal moet dus ook
   `playwright install chromium` gedraaid zijn.)

2. **rmapi registreren (op de VPS):**
   ```bash
   rmapi        # voer de one-time code van my.remarkable.com in
   ```

3. **systemd (op de VPS):**
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
