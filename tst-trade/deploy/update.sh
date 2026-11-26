#!/usr/bin/env bash
# TST Trade auto-update (run by the tst-trade-update timer every 5 minutes, as root):
# fetches the branch the server runs; when GitHub has a newer commit it installs it, restarts the panel and checks
# /healthz; if the new version does not answer, it goes back to the previous commit. .env and data/ are never touched.
set -euo pipefail
# The whole script is one function: bash reads it fully before running, so the reset below can rewrite this file safely.
apply_site() {
  # Caddy and the cookie setting follow deploy/site.env (applied on every run; nothing happens when already right).
  local SITE_FILE=/opt/tst/repo/tst-trade/deploy/site.env ENVF=/opt/tst/repo/tst-trade/.env DOMAIN="" SERVER_IP=""
  [[ -f $SITE_FILE ]] || return 0
  DOMAIN=$(grep -E '^DOMAIN=' "$SITE_FILE" | cut -d= -f2- | tr -d '[:space:]')
  SERVER_IP=$(grep -E '^SERVER_IP=' "$SITE_FILE" | cut -d= -f2- | tr -d '[:space:]')
  [[ "$DOMAIN" =~ ^[a-z0-9.-]+$ ]] || return 0
  local WANT
  WANT=$(printf '%s {\n\tencode gzip\n\treverse_proxy 127.0.0.1:8100\n}\n' "$DOMAIN")
  if [[ "$SERVER_IP" =~ ^[0-9.]+$ ]]; then
    WANT+=$(printf '\nhttp://%s {\n\tredir https://%s{uri} permanent\n}\n' "$SERVER_IP" "$DOMAIN")
  fi
  if [[ "$(cat /etc/caddy/Caddyfile 2>/dev/null)" != "$WANT" ]]; then
    cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak 2>/dev/null || true
    printf '%s\n' "$WANT" > /etc/caddy/Caddyfile
    if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
      systemctl reload caddy || systemctl restart caddy
      echo "caddy: HTTPS for $DOMAIN"
    else
      cp /etc/caddy/Caddyfile.bak /etc/caddy/Caddyfile && echo "caddy: new config invalid, kept the old one"
      return 0
    fi
  fi
  if grep -qE '^COOKIE_SECURE=0' "$ENVF"; then
    sed -i 's/^COOKIE_SECURE=0/COOKIE_SECURE=1/' "$ENVF" && systemctl restart tst-trade && echo "cookies: secure"
  fi
}

# Qorunan fayllar (owner 2026-11-26): a change to a file in deploy/protected.txt (read from the version that runs NOW,
# so a commit cannot loosen its own guard) goes live only if one of the new commits has a line «Sahib-təsdiqi: ...».
# Otherwise nothing is installed, the server keeps the running version, and data/update.log says why (once).
guard_protected() {
  local OLD=$1 NEW=$2 LOG=$3 list changed hit line msgs
  list=$(sudo -u $APP_USER git -C $REPO show "$OLD:tst-trade/deploy/protected.txt" 2>/dev/null) || return 0
  changed=$(sudo -u $APP_USER git -C $REPO diff --name-only "$OLD" "$NEW")
  hit=$(grep -Fxf <(printf '%s\n' "$list" | sed '/^#/d;/^[[:space:]]*$/d') <<<"$changed" || true)
  [[ -z "$hit" ]] && return 0
  msgs=$(sudo -u $APP_USER git -C $REPO log --format=%B "$OLD..$NEW")
  if grep -q '^Sahib-təsdiqi:' <<<"$msgs"; then
    return 0
  fi
  line="held ${NEW:0:7}: protected files changed without owner approval: $(printf '%s ' $hit)"
  if [[ "$(tail -n 1 "$LOG" 2>/dev/null | cut -d' ' -f2-)" != "$line" ]]; then
    echo "$(date -u +%FT%TZ) $line" >> "$LOG"; chmod 644 "$LOG"
  fi
  echo "$line"
  return 1
}

main() {
  APP_USER=tst
  REPO=/opt/tst/repo
  APP_DIR=$REPO/tst-trade
  B=$(sudo -u $APP_USER git -C $REPO rev-parse --abbrev-ref HEAD)
  sudo -u $APP_USER git -C $REPO fetch -q origin "$B"
  OLD=$(sudo -u $APP_USER git -C $REPO rev-parse HEAD)
  NEW=$(sudo -u $APP_USER git -C $REPO rev-parse "origin/$B")
  apply_site || true
  [[ "$OLD" == "$NEW" ]] && return 0
  guard_protected "$OLD" "$NEW" "$APP_DIR/data/update.log" || return 0
  echo "updating ${OLD:0:7} -> ${NEW:0:7}"
  sudo -u $APP_USER git -C $REPO reset -q --hard "$NEW"
  sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -q -r $APP_DIR/requirements.txt
  systemctl restart tst-trade
  # up to 2 minutes for the first answer (2026-11-26: a 1 GB database can make the start slower than the old 30 s,
  # which rolled a good version back and restarted the panel twice); every outcome goes to data/update.log
  local LOG=$APP_DIR/data/update.log
  for i in $(seq 1 24); do
    sleep 5
    if curl -fsS http://127.0.0.1:8100/healthz >/dev/null; then
      echo "updated to ${NEW:0:7}"
      echo "$(date -u +%FT%TZ) updated ${OLD:0:7} -> ${NEW:0:7}, answered after $((i * 5)) s" >> "$LOG"
      tail -n 50 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; chmod 644 "$LOG"
      return 0
    fi
  done
  echo "new version did not answer: rolling back to ${OLD:0:7}"
  echo "$(date -u +%FT%TZ) ${NEW:0:7} did not answer in 120 s: rolled back to ${OLD:0:7}" >> "$LOG"; chmod 644 "$LOG"
  sudo -u $APP_USER git -C $REPO reset -q --hard "$OLD"
  systemctl restart tst-trade
  return 1
}
main "$@"
