#!/bin/bash
# Phase 3 multi-instance smoke: 10 backend (mcp-context-forge) instances via
# Claude CLI agent loop. Results streamed to JSONL + Slack DM at start/end.
set -u
cd "$(dirname "$0")/.."

PRS_FILE="/tmp/smoke10.prs"
RESULTS="/tmp/agent_smoke10_results.jsonl"
LOG="/tmp/agent_smoke10.log"
MODEL="${1:-claude-opus-4-7}"
SOURCE="mcp-context-forge"

: > "$RESULTS"
: > "$LOG"

# --- Slack helper -----------------------------------------------------------
notify() {
    local text="$1"
    python3 - "$text" << 'EOF' || true
import json, os, sys, urllib.request, urllib.parse
from pathlib import Path
text = sys.argv[1]
env = {}
for line in Path('.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, _, v = line.partition('=')
        env[k.strip()] = v.strip().strip("'\"")
T = env.get('SLACK_BOT_TOKEN'); E = env.get('SLACK_NOTIFY_EMAIL')
def call(ep, method='GET', **p):
    url = f'https://slack.com/api/{ep}'
    h = {'Authorization': f'Bearer {T}'}
    if method == 'POST':
        h['Content-Type'] = 'application/json; charset=utf-8'
        req = urllib.request.Request(url, data=json.dumps(p).encode(), headers=h, method='POST')
    else:
        if p: url += '?' + urllib.parse.urlencode(p)
        req = urllib.request.Request(url, headers=h)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())
u = call('users.lookupByEmail', email=E)
c = call('conversations.open', method='POST', users=u['user']['id'])
call('chat.postMessage', method='POST', channel=c['channel']['id'], text=text)
EOF
}

START=$(date '+%Y-%m-%d %H:%M:%S')
COUNT=$(wc -l < "$PRS_FILE" | tr -d ' ')
notify ":rocket: *Phase 3 agent-loop smoke (10 backend)* — started ${START}
Source: ${SOURCE}   Model: \`${MODEL}\`
PRs: $(tr '\n' ' ' < "$PRS_FILE")"

t_total_start=$(date +%s)

while IFS= read -r PR; do
    [ -z "$PR" ] && continue
    t_inst_start=$(date +%s)
    echo "=========================" >> "$LOG"
    echo "PR #$PR  start $(date '+%H:%M:%S')" >> "$LOG"

    # 1. extract (work_dir + summary.json)
    uv run pbench extract --source "$SOURCE" --pr "$PR" \
        --prs "raw/${SOURCE}/prs.jsonl" >> "$LOG" 2>&1
    EXTRACT_RC=$?
    if [ $EXTRACT_RC -ne 0 ]; then
        python3 -c "
import json, time
print(json.dumps({'pr': $PR, 'stage': 'extract', 'rc': $EXTRACT_RC, 'duration_s': $(( $(date +%s) - t_inst_start )), 'score': None, 'error': 'extract failed'}))
" >> "$RESULTS"
        continue
    fi

    # 2. agent-score
    AGENT_LOG="$LOG.pr${PR}.agent"
    uv run pbench agent-score --source "$SOURCE" --pr "$PR" \
        --model "$MODEL" --timeout 600 > "$AGENT_LOG" 2>&1
    AGENT_RC=$?

    # Parse score from final lines
    SCORE=$(grep -oE 'score = [01]' "$AGENT_LOG" | tail -1 | awk '{print $3}')
    [ -z "$SCORE" ] && SCORE="null"
    DIFF_SIZE=$(grep -oE 'diff=[0-9]+B' "$AGENT_LOG" | tail -1 | sed 's/diff=//;s/B//')
    [ -z "$DIFF_SIZE" ] && DIFF_SIZE="null"
    AGENT_DUR=$(grep -oE 'dur=[0-9]+s' "$AGENT_LOG" | tail -1 | sed 's/dur=//;s/s//')
    [ -z "$AGENT_DUR" ] && AGENT_DUR="null"
    F2P_LINE=$(grep -oE 'FAIL_TO_PASS: [0-9]+/[0-9]+ passing' "$AGENT_LOG" | tail -1)
    P2P_LINE=$(grep -oE 'PASS_TO_PASS: [0-9]+/[0-9]+ passing' "$AGENT_LOG" | tail -1)

    t_inst_dur=$(( $(date +%s) - t_inst_start ))

    python3 -c "
import json
print(json.dumps({
    'pr': $PR,
    'stage': 'done',
    'rc': $AGENT_RC,
    'score': $SCORE,
    'agent_dur_s': $AGENT_DUR,
    'diff_bytes': $DIFF_SIZE,
    'total_dur_s': $t_inst_dur,
    'f2p': '$F2P_LINE',
    'p2p': '$P2P_LINE',
}))
" >> "$RESULTS"
    echo "PR #$PR  done score=$SCORE  total=${t_inst_dur}s" >> "$LOG"
done < "$PRS_FILE"

t_total=$(( $(date +%s) - t_total_start ))

# --- summary + Slack -------------------------------------------------------
END=$(date '+%Y-%m-%d %H:%M:%S')
SUMMARY=$(python3 - << EOF
import json
rows = [json.loads(l) for l in open('$RESULTS').read().splitlines() if l.strip()]
n = len(rows)
ok = sum(1 for r in rows if r.get('score') == 1)
miss = sum(1 for r in rows if r.get('score') == 0)
err = sum(1 for r in rows if r.get('stage') != 'done' or r.get('score') is None)
total_agent_dur = sum((r.get('agent_dur_s') or 0) for r in rows)
total_inst_dur = sum((r.get('total_dur_s') or 0) for r in rows)
lines = [
    f"Total: {n}   score=1: *{ok}*   score=0: {miss}   error: {err}",
    f"Avg total dur: {total_inst_dur//n if n else 0}s   Avg agent dur: {total_agent_dur//n if n else 0}s",
    "",
    "Per-PR:",
]
for r in rows:
    pr = r.get('pr','?')
    s = r.get('score')
    s_str = ':white_check_mark:' if s == 1 else (':x:' if s == 0 else ':warning:')
    f2p = r.get('f2p','')
    dur = r.get('total_dur_s', 0)
    lines.append(f"  PR #{pr}  {s_str}  dur={dur}s  {f2p}")
print("\n".join(lines))
EOF
)

notify ":checkered_flag: *Phase 3 agent-loop smoke (10 backend)* — finished ${END}
Total wall-time: ${t_total}s
${SUMMARY}

Results JSONL: \`${RESULTS}\`
Log: \`${LOG}\`"

echo "DONE  total=${t_total}s" >> "$LOG"
