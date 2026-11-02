#!/usr/bin/env bash
# Install the HF relay agent as a systemd service. Needs no pip — only `requests`.
#   RELAY_REPO=you/vps-relay HF_TOKEN=hf_xxx ./setup-relay.sh
set -e
REPO="${RELAY_REPO:?set RELAY_REPO (e.g. yourname/vps-relay)}"
TOKEN="${HF_TOKEN:?set HF_TOKEN}"
DIR="${RELAY_DIR:-/opt/hf-relay}"
INTERVAL="${RELAY_INTERVAL:-20}"
ALLOW="${RELAY_ALLOW:-}"

if [ "$(id -u)" != "0" ]; then
  echo "run this as root (sudo -s), it writes to /opt and /etc"; exit 1
fi

echo "==> checking python deps"
python3 -c "import requests" 2>/dev/null || {
  echo "installing python3-requests"
  apt-get update -qq && apt-get install -y --no-install-recommends python3-requests
}

echo "==> fetching relay.py"
mkdir -p "$DIR"
curl -fsSL -m 60 https://raw.githubusercontent.com/deepuyrf-blip/hf-relay/main/relay.py -o "$DIR/relay.py"
chmod +x "$DIR/relay.py"
python3 -c "import ast,sys; ast.parse(open('$DIR/relay.py').read())" && echo "relay.py OK"

echo "==> writing env file (0600)"
umask 077
cat > /etc/hf-relay.env <<ENV
RELAY_REPO=$REPO
HF_TOKEN=$TOKEN
RELAY_INTERVAL=$INTERVAL
RELAY_TIMEOUT=600
RELAY_ALLOW=$ALLOW
ENV
chmod 600 /etc/hf-relay.env

echo "==> systemd unit"
cat > /etc/systemd/system/hf-relay.service <<UNIT
[Unit]
Description=HF relay agent (pull-based command channel)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/hf-relay.env
ExecStart=/usr/bin/python3 $DIR/relay.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/hf-relay.log
StandardError=append:/var/log/hf-relay.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now hf-relay
sleep 5
echo
echo "==> status"
systemctl --no-pager --lines=6 status hf-relay || true
echo
echo "Logs : tail -f /var/log/hf-relay.log"
echo "Stop : systemctl stop hf-relay && systemctl disable hf-relay"
