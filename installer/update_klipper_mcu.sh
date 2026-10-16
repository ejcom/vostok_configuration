#!/usr/bin/env bash
# Обновление Klipper (KIAUH или git) и перепрошивка MCU через katapult (USB и CAN).
# Тонкая обёртка: вся логика в Python-пакете vostok (vostok/update.py).
# Запускать от обычного пользователя в терминале; без терминала (кнопка Fluidd, сервис mcu-update) см. --help.
# Подробности: README.md и ./update_klipper_mcu.sh --help
# ВРЕМЕННО: install_vostok.sh (пока на bash) подключает этот файл через source ради функций.
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
    # shellcheck source=lib/update_legacy.sh
    source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/update_legacy.sh"
    return 0
fi
INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
command -v python3 >/dev/null 2>&1 || { echo "ОШИБКА: нужен python3" >&2; exit 1; }
PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok update "$@"
