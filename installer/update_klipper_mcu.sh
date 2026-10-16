#!/usr/bin/env bash
# Обновление Klipper (KIAUH или git) и перепрошивка MCU через katapult (USB и CAN).
# Тонкая обёртка: вся логика в Python-пакете vostok (vostok/update.py).
# Запускать от обычного пользователя в терминале; без терминала (кнопка Fluidd, сервис mcu-update) см. --help.
# Подробности: README.md и ./update_klipper_mcu.sh --help
INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
command -v python3 >/dev/null 2>&1 || { echo "ОШИБКА: нужен python3" >&2; exit 1; }
PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok update "$@"
