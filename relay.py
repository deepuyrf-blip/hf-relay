#!/usr/bin/env python3
"""
HF Relay agent — a pull-based command channel over a private Hugging Face dataset.

The VPS polls the dataset for `inbox/cmd.json`, runs the command, and uploads the
result to `outbox/<id>.json`. Nothing inbound is exposed: no ports, no tunnels,
no SSH.

Env:
  RELAY_REPO      e.g. factblink514/vps-relay      (required)
  HF_TOKEN        HF token with write access        (required)
  RELAY_INTERVAL  seconds between polls             (default 20)
  RELAY_TIMEOUT   per-command timeout in seconds    (default 600)
  RELAY_SHELL     shell to use                      (default /bin/bash)
  RELAY_ALLOW     optional: comma-separated command prefixes that are allowed
                  (empty = allow everything)

Stop anytime:  systemctl stop hf-relay
"""
import json
import os
import subprocess
import sys
import time

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import EntryNotFoundError

REPO = os.environ.get("RELAY_REPO", "").strip()
TOKEN = os.environ.get("HF_TOKEN", "").strip()
INTERVAL = int(os.environ.get("RELAY_INTERVAL", "20"))
TIMEOUT = int(os.environ.get("RELAY_TIMEOUT", "600"))
SHELL = os.environ.get("RELAY_SHELL", "/bin/bash")
ALLOW = [a.strip() for a in os.environ.get("RELAY_ALLOW", "").split(",") if a.strip()]

HOME = os.path.expanduser("~")
STATE = os.path.join(HOME, ".hf-relay-state.json")
LOG = os.path.join(HOME, "hf-relay.log")

if not REPO or not TOKEN:
    sys.exit("RELAY_REPO and HF_TOKEN are required")

api = HfApi(token=TOKEN)


def log(msg: str) -> None:
    line = f"[{time.strftime('%F %T')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"last": ""}


def save_state(s: dict) -> None:
    try:
        json.dump(s, open(STATE, "w", encoding="utf-8"))
    except Exception:
        pass


def fetch_cmd():
    try:
        p = hf_hub_download(repo_id=REPO, filename="inbox/cmd.json",
                            repo_type="dataset", token=TOKEN)
        return json.load(open(p, encoding="utf-8"))
    except EntryNotFoundError:
        return None
    except Exception as e:
        log(f"fetch error: {type(e).__name__}: {e}")
        return None


def upload(name: str, obj: dict) -> None:
    api.upload_file(
        path_or_fileobj=json.dumps(obj, indent=2).encode(),
        path_in_repo=name,
        repo_id=REPO,
        repo_type="dataset",
        commit_message=f"relay: {name}",
    )


def run(cmd: str, cwd: str | None, timeout: int) -> dict:
    log(f"RUN (cwd={cwd or HOME}): {cmd[:400]}")
    t0 = time.time()
    try:
        p = subprocess.run(cmd, shell=True, executable=SHELL, cwd=cwd or HOME,
                           capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode,
                "stdout": p.stdout[-20000:],
                "stderr": p.stderr[-8000:],
                "ms": int((time.time() - t0) * 1000)}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "stdout": "", "stderr": f"timeout after {timeout}s",
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"rc": 1, "stdout": "", "stderr": f"{type(e).__name__}: {e}",
                "ms": int((time.time() - t0) * 1000)}


def main() -> None:
    log(f"relay up · repo={REPO} · interval={INTERVAL}s · timeout={TIMEOUT}s "
        f"· allow={'ALL' if not ALLOW else ALLOW}")
    st = load_state()
    last_hb = 0.0

    while True:
        now = time.time()

        # heartbeat so the other side can see the box is alive
        if now - last_hb > 60:
            last_hb = now
            try:
                upload("status.json", {"ts": int(now), "host": os.uname().nodename,
                                       "user": os.environ.get("USER", ""),
                                       "last_id": st.get("last", "")})
            except Exception as e:
                log(f"heartbeat failed: {e}")

        job = fetch_cmd()
        if job and job.get("id") and job["id"] != st.get("last"):
            cid = str(job["id"])
            cmd = job.get("cmd", "")
            if ALLOW and not any(cmd.strip().startswith(a) for a in ALLOW):
                res = {"rc": 403, "stdout": "", "stderr": "command not in RELAY_ALLOW list"}
            else:
                res = run(cmd, job.get("cwd"), int(job.get("timeout") or TIMEOUT))
            res.update({"id": cid, "ts": int(time.time()),
                        "host": os.uname().nodename, "cmd": cmd})
            try:
                upload(f"outbox/{cid}.json", res)
                log(f"DONE {cid} rc={res['rc']}")
            except Exception as e:
                log(f"upload result failed: {e}")
            st["last"] = cid
            save_state(st)

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("relay stopped")
