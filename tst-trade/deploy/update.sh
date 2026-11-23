#!/usr/bin/env bash
# TST Trade auto-update (run by the tst-trade-update timer every 5 minutes, as root):
# fetches the branch the server runs; when GitHub has a newer commit it installs it, restarts the panel and checks
# /healthz; if the new version does not answer, it goes back to the previous commit. .env and data/ are never touched.
set -euo pipefail
# The whole script is one function: bash reads it fully before running, so the reset below can rewrite this file safely.
main() {
  APP_USER=tst
  REPO=/opt/tst/repo
  APP_DIR=$REPO/tst-trade
  B=$(sudo -u $APP_USER git -C $REPO rev-parse --abbrev-ref HEAD)
  sudo -u $APP_USER git -C $REPO fetch -q origin "$B"
  OLD=$(sudo -u $APP_USER git -C $REPO rev-parse HEAD)
  NEW=$(sudo -u $APP_USER git -C $REPO rev-parse "origin/$B")
  [[ "$OLD" == "$NEW" ]] && return 0
  echo "updating ${OLD:0:7} -> ${NEW:0:7}"
  sudo -u $APP_USER git -C $REPO reset -q --hard "$NEW"
  sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -q -r $APP_DIR/requirements.txt
  systemctl restart tst-trade
  for i in 1 2 3 4 5 6; do
    sleep 5
    if curl -fsS http://127.0.0.1:8100/healthz >/dev/null; then echo "updated to ${NEW:0:7}"; return 0; fi
  done
  echo "new version did not answer: rolling back to ${OLD:0:7}"
  sudo -u $APP_USER git -C $REPO reset -q --hard "$OLD"
  systemctl restart tst-trade
  return 1
}
main "$@"
