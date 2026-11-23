#!/usr/bin/env bash
# TST Trade: set a new panel password (and update the code). Run as root in the droplet console:
#   bash set-password.sh
# Removes a password saved earlier on the admin page, writes only a scrypt hash into .env, restarts the panel.
set -euo pipefail
APP_USER=tst
HOME_DIR=/opt/tst
APP_DIR=$HOME_DIR/repo/tst-trade
[[ $EUID -eq 0 ]] || { echo "root kimi işə salın"; exit 1; }
[[ -f $APP_DIR/.env ]] || { echo "TST Trade quraşdırılmayıb: əvvəlcə setup.sh"; exit 1; }

B=$(sudo -u $APP_USER git -C $HOME_DIR/repo rev-parse --abbrev-ref HEAD)
sudo -u $APP_USER git -C $HOME_DIR/repo fetch -q origin "$B"
sudo -u $APP_USER git -C $HOME_DIR/repo reset -q --hard "origin/$B"
sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -q -r $APP_DIR/requirements.txt

while true; do
  read -rsp "Yeni panel parolu (ən azı 8 simvol): " PW; echo
  read -rsp "Bir daha: " PW2; echo
  [[ ${#PW} -ge 8 && "$PW" == "$PW2" ]] && break
  echo "Parollar eyni deyil və ya 8 simvoldan qısadır, yenidən yazın."
done
HASH=$(printf '%s' "$PW" | python3 -c "import sys,os,hashlib;p=sys.stdin.read().encode();s=os.urandom(16);print('scrypt\$'+s.hex()+'\$'+hashlib.scrypt(p,salt=s,n=2**14,r=8,p=1,dklen=32).hex())")
unset PW PW2

grep -v -E '^(APP_PASSWORD|APP_PASSWORD_HASH)=' $APP_DIR/.env > $APP_DIR/.env.new || true
echo "APP_PASSWORD_HASH='$HASH'" >> $APP_DIR/.env.new
mv $APP_DIR/.env.new $APP_DIR/.env
chown $APP_USER:$APP_USER $APP_DIR/.env && chmod 600 $APP_DIR/.env

DB=$APP_DIR/data/lab.sqlite3
if [[ -f $DB ]]; then
  sudo -u $APP_USER python3 -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute(\"DELETE FROM kv WHERE k='auth:password_hash'\");c.commit()" "$DB"
fi
systemctl restart tst-trade
sleep 3
curl -fsS http://127.0.0.1:8100/healthz >/dev/null && echo "Parol dəyişdi, TST Trade işləyir. Brauzerdə yeni parolla daxil olun."
