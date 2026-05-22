#!/bin/bash
# Wrapper used as the ENTRYPOINT of prototypebench/playwright-electron.
# Starts Xvfb on :99 so Electron's renderer has a display, then exec's the
# given command (typically `bash -c "<install + tests pipeline>"`).
set -e
Xvfb :99 -screen 0 1280x1024x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99
# Give Xvfb a moment to come up before launching anything that needs DISPLAY.
sleep 0.5
exec "$@"
