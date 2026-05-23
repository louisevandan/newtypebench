#!/usr/bin/env python3
"""Send a PrototypeBench bruno top-100 progress report as a Slack DM.

Reads SLACK_BOT_TOKEN + SLACK_NOTIFY_EMAIL from `.env`, looks up the user by
email, opens (or reuses) the DM channel, and posts a one-shot status block.

Designed to be called periodically from a background loop (e.g. every 2h):
    while sleep 7200; do python3 scripts/notify_slack.py; done
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# --- env loading (no external deps) ----------------------------------------
ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"
env = {}
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip("'\"")

TOKEN = env.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
EMAIL = env.get("SLACK_NOTIFY_EMAIL") or os.environ.get("SLACK_NOTIFY_EMAIL")
if not TOKEN or not EMAIL:
    print("missing SLACK_BOT_TOKEN or SLACK_NOTIFY_EMAIL", file=sys.stderr)
    sys.exit(1)


def slack(endpoint: str, method: str = "GET", **params) -> dict:
    url = f"https://slack.com/api/{endpoint}"
    if method == "POST":
        data = json.dumps(params).encode()
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    else:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# --- progress snapshot -----------------------------------------------------
report_path = ROOT / "raw" / "bruno" / "extract_report.frontend.jsonl"
TARGET = 100
rows: list[dict] = []
if report_path.exists():
    for line in report_path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

done = len(rows)
status_counts: dict[str, int] = {}
total_f2p = 0
total_p2p = 0
durations = []
for r in rows:
    status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    if r["status"] == "exact":
        total_f2p += r.get("f2p", 0)
        total_p2p += r.get("p2p", 0)
    if r.get("duration_s", 0) > 5:
        durations.append(r["duration_s"])

avg_dur = sum(durations) / len(durations) if durations else 0.0
remaining = max(0, TARGET - done)
eta_sec = remaining * avg_dur if avg_dur else 0
eta_str = f"{int(eta_sec/3600)}h{int((eta_sec%3600)/60):02d}m" if eta_sec else "—"

# active container
try:
    active = subprocess.check_output(
        ["docker", "ps", "--filter", "name=pbench-fe-direct",
         "--format", "{{.Names}} ({{.RunningFor}})"],
        text=True, timeout=10,
    ).strip()
except Exception:
    active = ""

# corpus stats (instances.bruno.jsonl)
inst_path = ROOT / "tasks" / "instances.bruno.jsonl"
inst_count = 0
if inst_path.exists():
    inst_count = sum(1 for line in inst_path.read_text().splitlines() if line.strip())

status_line = " · ".join(f"{k}={v}" for k, v in sorted(status_counts.items()))
text = f"""*PrototypeBench — bruno top-100 progress*
:clock1: {datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")}

Progress: *{done}/{TARGET}* PR processed ({done*100//TARGET if TARGET else 0}%)
Status:   {status_line or '(none)'}
F2P 합 (exact only): {total_f2p}   ·   P2P 합: {total_p2p}
Avg dur (new PR):    {avg_dur:.0f}s
ETA (remaining {remaining} × avg): *{eta_str}*

Active container: `{active or '(idle / between tasks)'}`
Last built instance file: `tasks/instances.bruno.jsonl` — {inst_count} rows

Corpus (build-from-extract 적용 후 추정):
 backend_only 71  +  frontend_only {inst_count}  =  {71 + inst_count}
"""

# --- send DM ---------------------------------------------------------------
u = slack("users.lookupByEmail", email=EMAIL)
if not u.get("ok"):
    print(f"lookupByEmail failed: {u}", file=sys.stderr); sys.exit(1)
user_id = u["user"]["id"]

c = slack("conversations.open", method="POST", users=user_id)
if not c.get("ok"):
    print(f"conversations.open failed: {c}", file=sys.stderr); sys.exit(1)
channel = c["channel"]["id"]

m = slack("chat.postMessage", method="POST", channel=channel, text=text)
if not m.get("ok"):
    print(f"chat.postMessage failed: {m}", file=sys.stderr); sys.exit(1)

print(f"sent ts={m.get('ts')}  done={done}/{TARGET}  eta={eta_str}")
