# HF Relay — a pull-based command channel over Hugging Face

Your VPS has no reachable inbound port (firewalled / tunnel-only), so an outside
agent cannot SSH in. This flips the direction: the VPS **pulls** work from a
private Hugging Face dataset and pushes results back.

```
writer  ──push──►  HF dataset (inbox/cmd.json)
                          │
                  relay agent on the VPS (polls every 20s)
                          │
                    runs the command
                          │
                  push ──►  HF dataset (outbox/<id>.json)
                          │
writer  ◄──read───────────┘
```

No ports opened, no tunnels, no SSH. Only outbound HTTPS to `huggingface.co`.

## Setup (on the VPS)

```bash
RELAY_REPO=yourname/vps-relay HF_TOKEN=hf_xxx \
  bash <(curl -fsSL https://raw.githubusercontent.com/deepuyrf-blip/hf-relay/main/setup-relay.sh)
```

That installs `huggingface_hub`, drops `relay.py` in `/opt/hf-relay`, writes
`/etc/hf-relay.env` (mode 600) and starts a systemd service.

## Protocol

**`inbox/cmd.json`**
```json
{"id": "2026-11-02-001", "cmd": "docker ps", "cwd": "/home/ubuntu", "timeout": 300}
```

**`outbox/<id>.json`** (written by the agent)
```json
{"id": "2026-11-02-001", "rc": 0, "stdout": "...", "stderr": "", "ms": 412,
 "host": "deepak", "ts": 1762000000, "cmd": "docker ps"}
```

**`status.json`** — heartbeat every 60s (`ts`, `host`, `user`, `last_id`).

Each `id` runs **once** — the agent remembers the last id in `~/.hf-relay-state.json`.

## Safety

- Use a **private** dataset and a **write-scoped** token.
- `RELAY_ALLOW` optionally restricts commands by prefix, e.g.
  `RELAY_ALLOW="docker,systemctl,ls,cat"`.
- Everything is logged to `/var/log/hf-relay.log`.
- Kill switch: `systemctl stop hf-relay && systemctl disable hf-relay`.

## Files

| File | Purpose |
|---|---|
| `relay.py` | the agent |
| `setup-relay.sh` | installer (systemd) |

MIT
