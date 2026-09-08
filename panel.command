#!/bin/bash
# Launcher for the pipeline control panel (macOS and Linux).
#
# Double-click opens the panel in a browser. On macOS a .command file is
# executable from Finder; on Linux run it from a terminal or a desktop entry.
#
# Finds the project venv on its own: a human should not have to remember that
# dependencies live in .venv, while the system python dies on "import yaml"
# with a traceback that never mentions the interpreter.
#
# ASCII only, mirroring panel.cmd: the two launchers say the same things, and a
# difference between them would be a difference nobody notices until it breaks.

cd "$(dirname "$0")" || exit 1

PY="./.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo
    echo "Project environment not found: $PY"
    echo
    echo "Create it once:"
    echo "    python3 -m venv .venv"
    echo "    ./.venv/bin/python -m pip install -r requirements.txt"
    echo
    read -r -p "Press Enter to close." _
    exit 1
fi

# Missing tools (ffmpeg, node, montage deps) are reported by the server itself:
# the list of what is needed lives in scripts/factory/environment.py, and a copy
# of it here would drift the day a fourth dependency appears.

echo "Starting the panel; the browser will open by itself."
echo "Keep this window open - it IS the server. Ctrl+C stops it."
echo

"$PY" scripts/serve.py "$@"

# Pause only on failure: a normal Ctrl+C should just close the window, while a
# crashed start is something the human must have time to read.
status=$?
if [ $status -ne 0 ] && [ $status -ne 130 ]; then
    read -r -p "Press Enter to close." _
fi
