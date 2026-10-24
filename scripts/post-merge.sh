#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset PYTHONNOUSERSITE
export PYTHONUSERBASE="$PWD/.pythonlibs"
python -m pip install --prefix "$PYTHONUSERBASE" --no-input -r requirements.txt
