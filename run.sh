#!/bin/bash
cd "$(dirname "$0")"

PYTHON_EXE=""

if [ -n "$MEETSCRIBE_VENV" ] && [ -x "$MEETSCRIBE_VENV/bin/python" ]; then
    PYTHON_EXE="$MEETSCRIBE_VENV/bin/python"
elif [ -n "$TRANSCRIPTOR_VENV" ] && [ -x "$TRANSCRIPTOR_VENV/bin/python" ]; then
    PYTHON_EXE="$TRANSCRIPTOR_VENV/bin/python"
elif [ -x ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="python3"
else
    PYTHON_EXE="python"
fi

"$PYTHON_EXE" main.py

if [ $? -ne 0 ]; then
    echo ""
    echo "Startup failed. Check that Python and dependencies are installed."
    echo "See README.md — Installation section."
    read -p "Press Enter to exit..."
fi
