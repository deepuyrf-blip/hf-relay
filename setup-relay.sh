#!/usr/bin/env bash
# Install the HF relay agent on this machine as a systemd service.
#   RELAY_REPO=you/vps-relay HF_TOKEN=hf_xxx ./setup-relay.sh
set -e
REPO="${RELAY_REPO:?set RELAY_REPO (e.g. yourname/vps-relay)}"
TOKEN="${HF_TOKEN:?set HF_TOKEN}"
DIR="${RELAY_DIR:-/opt/hf-relay}"
INTERVAL="${RELAY_INTERVAL:-20}"
ALLOW="${RELAY_ALLOW:-}"

echo "==> python deps"
python3 -c "import huggingface_hub" 2>/dev/null \
  || pip3 install --break-system-packages huggingface_hub 2>/dev/null \
  || pip3 install huggingface_hub

echo "==> fetching relay.py"
mkdir -p "$DIR"
curl -fsSL -m 60 https://raw.githubusercontent.com/deepuyrf-blip/hf-relay/main/relay.py -o "$DIR/relay.py"
chmod +x "$DIR/relay.py"

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
sleep 3
echo
echo "==> status"
systemctl --no-pager --lines=8 status hf-relay || true
echo
echo "Logs : journalctl -u hf-relay -f     (or tail -f /var/log/hf-relay.log)"
echo "Stop : systemctl stop hf-relay && systemctl disable hf-relay"
