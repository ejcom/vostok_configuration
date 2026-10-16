#!/usr/bin/env bash
# Обёртка: вся логика в пакете vostok (vostok/integrations.py), путь и флаги скрипта прежние.
INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
PYTHONPATH="$INSTALL_DIR" PYTHONDONTWRITEBYTECODE=1 VOSTOK_PROG="$0" exec python3 -m vostok theme "$@"
