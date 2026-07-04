#!/usr/bin/env bash
#
# VPS-bootstrap voor cryptogram2remarkable (Debian/Ubuntu).
# Idempotent: veilig meerdere keren te draaien.
#
# Draai vanuit de projectmap op de VPS, als root of met sudo:
#   sudo bash deploy/bootstrap.sh
#
# Installeert: systeem-deps, Google Chrome, (optioneel) Xvfb, een venv met de
# package, en maakt de service-user + mappen. rmapi installeren/registreren en
# het profiel kopiëren blijven handmatige stappen (zie de uitvoer aan het eind).

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="c2rm"
ENV_FILE="/etc/c2rm.env"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
require_root() { [ "$(id -u)" -eq 0 ] || { echo "Draai als root of met sudo."; exit 1; }; }

require_root

ARCH="$(dpkg --print-architecture)"
log "Projectmap: $APP_DIR   architectuur: $ARCH"

log "APT-pakketten (python, venv, tools, fonts, Xvfb)"
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    curl ca-certificates gnupg rsync \
    xvfb fonts-liberation

log "Google Chrome"
if command -v google-chrome >/dev/null 2>&1; then
    echo "Chrome is al aanwezig: $(google-chrome --version)"
elif [ "$ARCH" = "amd64" ]; then
    install -d -m 0755 /usr/share/keyrings
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list
    apt-get update -qq
    apt-get install -y google-chrome-stable
    echo "Geïnstalleerd: $(google-chrome --version)"
else
    echo "LET OP: geen amd64 ($ARCH) — Google Chrome heeft geen Linux-build hiervoor."
    echo "Installeer 'chromium' en zet C2RM_BROWSER_CHANNEL=chromium in $ENV_FILE."
    apt-get install -y chromium || apt-get install -y chromium-browser || true
fi

log "Service-user '$SERVICE_USER'"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "/home/$SERVICE_USER" --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "Aangemaakt."
else
    echo "Bestaat al."
fi

log "Python-venv + package (editable)"
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -e "$APP_DIR"
echo "c2rm: $("$APP_DIR/.venv/bin/c2rm" --help >/dev/null 2>&1 && echo OK)"

log "Mappen + eigendom"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$APP_DIR/data" "$APP_DIR/profile"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.venv" "$APP_DIR/data" "$APP_DIR/profile"

log "Env-bestand $ENV_FILE"
if [ ! -f "$ENV_FILE" ]; then
    cp "$APP_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Aangemaakt uit .env.example (controleer de waarden)."
else
    echo "Bestaat al — niet overschreven."
fi

log "systemd-units"
sed "s#/opt/cryptogram2remarkable#${APP_DIR}#g" "$APP_DIR/systemd/cryptogram2remarkable.service" \
    > /etc/systemd/system/cryptogram2remarkable.service
cp "$APP_DIR/systemd/cryptogram2remarkable.timer" /etc/systemd/system/cryptogram2remarkable.timer
systemctl daemon-reload
echo "Geïnstalleerd (nog niet ingeschakeld)."

cat <<EOF

Bootstrap klaar. Resterende HANDMATIGE stappen:

1) Profiel kopiëren (vanaf je Mac, na 'c2rm login'):
     rsync -a profile/ <deze-vps>:${APP_DIR}/profile/
     # daarna op de VPS:
     chown -R ${SERVICE_USER}:${SERVICE_USER} ${APP_DIR}/profile

2) rmapi installeren en registreren (als ${SERVICE_USER}):
     # download de juiste binary van https://github.com/ddvk/rmapi/releases
     # naar /usr/local/bin/rmapi (chmod +x), daarna:
     sudo -u ${SERVICE_USER} RMAPI_CONFIG=${APP_DIR}/rmapi.conf rmapi
     # voer de one-time code van my.remarkable.com in

3) Testrun (zonder upload), daarna echt:
     sudo -u ${SERVICE_USER} ${APP_DIR}/.venv/bin/c2rm check-session
     sudo -u ${SERVICE_USER} ${APP_DIR}/.venv/bin/c2rm run --dry-run
     sudo systemctl start cryptogram2remarkable.service    # echte run
     journalctl -u cryptogram2remarkable -n 50

4) Wekelijkse timer aanzetten:
     sudo systemctl enable --now cryptogram2remarkable.timer
     systemctl list-timers cryptogram2remarkable.timer

Bot-detectie-fallback: als de headless scrape op de VPS 406 geeft, zet in
${ENV_FILE} 'C2RM_HEADLESS=false' en gebruik de Xvfb-ExecStart in de service
(zie de commentaarregel in het unit-bestand).
EOF
