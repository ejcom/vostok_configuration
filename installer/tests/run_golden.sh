#!/usr/bin/env bash
# Сравнение вывода скриптов установщика с эталонами tests/golden (страховочная сетка переноса на Python).
# Подробности и опции: ./run_golden.sh --help
set -euo pipefail
HERE=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
command -v python3 >/dev/null || { echo "нужен python3" >&2; exit 2; }
exec python3 "$HERE/golden_runner.py" "$@"
