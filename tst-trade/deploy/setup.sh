#!/usr/bin/env bash
# TST Trade: one-time install on a fresh Ubuntu 24.04 server (DigitalOcean droplet), run as root:
#   bash setup.sh panel.example.com      # with a domain: HTTPS by Caddy (the domain's A record must point here)
#   bash setup.sh                        # no domain: plain HTTP on port 80 (only for a first look)
# Re-running it updates the code and restarts the service; .env and the database are kept.
set -euo pipefail
DOMAIN="${1:-}"
REPO="https://github.com/Parviz1987/Parviz1987.git"
BRANCH="${BRANCH:-}"          # empty: the repository's default branch
APP_USER=tst
HOME_DIR=/opt/tst
APP_DIR=$HOME_DIR/repo/tst-trade

[[ $EUID -eq 0 ]] || { echo "root kimi işə salın"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3-venv git debian-keyring debian-archive-keyring apt-transport-https curl gnupg

if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -y -q caddy
fi

id $APP_USER >/dev/null 2>&1 || useradd --system --home $HOME_DIR --create-home --shell /usr/sbin/nologin $APP_USER
if [[ -d $HOME_DIR/repo/.git ]]; then
  B="${BRANCH:-$(sudo -u $APP_USER git -C $HOME_DIR/repo rev-parse --abbrev-ref HEAD)}"
  sudo -u $APP_USER git -C $HOME_DIR/repo fetch -q origin "$B"
  sudo -u $APP_USER git -C $HOME_DIR/repo checkout -q "$B"
  sudo -u $APP_USER git -C $HOME_DIR/repo reset -q --hard "origin/$B"
else
  sudo -u $APP_USER git clone -q ${BRANCH:+--branch "$BRANCH"} "$REPO" $HOME_DIR/repo
fi
sudo -u $APP_USER python3 -m venv $APP_DIR/.venv
sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -q -r $APP_DIR/requirements.txt

if [[ ! -f $APP_DIR/.env ]]; then
  while true; do
    read -rsp "Panel üçün parol yazın (ən azı 8 simvol): " PW; echo
    read -rsp "Parolu bir daha yazın: " PW2; echo
    [[ ${#PW} -ge 8 && "$PW" == "$PW2" ]] && break
    echo "Parollar eyni deyil və ya 8 simvoldan qısadır, yenidən yazın."
  done
  # Only a scrypt hash goes into .env (read from stdin: the password never appears in a command line).
  HASH=$(printf '%s' "$PW" | python3 -c "import sys,os,hashlib;p=sys.stdin.read().encode();s=os.urandom(16);print('scrypt\$'+s.hex()+'\$'+hashlib.scrypt(p,salt=s,n=2**14,r=8,p=1,dklen=32).hex())")
  unset PW PW2
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  SECURE=1; [[ -z $DOMAIN ]] && SECURE=0
  cat > $APP_DIR/.env <<ENV
APP_PASSWORD_HASH='$HASH'
SESSION_SECRET=$SECRET
PRICE_PROVIDER=goldapi
PRICE_POLL_SECONDS=15
COOKIE_SECURE=$SECURE
DB_PATH=data/lab.sqlite3
ENV
  chown $APP_USER:$APP_USER $APP_DIR/.env && chmod 600 $APP_DIR/.env
fi

cat > /etc/systemd/system/tst-trade.service <<UNIT
[Unit]
Description=TST Trade forecast lab
After=network-online.target
[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8100 --workers 1
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$APP_DIR/data
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
sudo -u $APP_USER mkdir -p $APP_DIR/data

SITE="${DOMAIN:-:80}"
cat > /etc/caddy/Caddyfile <<CADDY
$SITE {
  encode gzip
  reverse_proxy 127.0.0.1:8100
}
CADDY

systemctl daemon-reload
systemctl enable --now tst-trade
systemctl restart tst-trade
systemctl reload caddy || systemctl restart caddy
sleep 3
curl -fsS http://127.0.0.1:8100/healthz && echo " — TST Trade işləyir"
echo "Açın: ${DOMAIN:+https://$DOMAIN}${DOMAIN:-http://<server IP>}"
