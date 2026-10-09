#!/usr/bin/env bash
# Установка «кнопки» прошивки MCU в Fluidd: systemd-сервис mcu-update, который
# запускает update_klipper_mcu.sh (обновляет ветку klipper без KIAUH и прошивает MCU). Moonraker показывает его в меню питания Fluidd
# (⏻ вверху справа -> mcu-update -> Start), лог: <printer_data>/logs/klipper_mcu_update.log.
#
# Что делает (повторный запуск безопасен):
#   1. проверяет окружение (klipper, katapult, Moonraker, компилятор, pyserial);
#   2. проверяет права на остановку klipper без пароля, при необходимости ставит
#      /etc/sudoers.d/mcu-update (только start/stop klipper*.service);
#   3. ставит /etc/systemd/system/mcu-update.service из mcu-update.service.in;
#   4. добавляет mcu-update в <printer_data>/moonraker.asvc и перезапускает Moonraker;
#   5. с --with-macro создаёт mcu_update.cfg с макросом MCU_UPDATE.
#
# Запускать от обычного пользователя (не root), sudo спросит пароль.

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
VOSTOK_INSTALLER_VERSION=$(head -n1 "$SCRIPT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || true)
VOSTOK_INSTALLER_VERSION=${VOSTOK_INSTALLER_VERSION:-неизвестна}
UPDATE_SCRIPT=$SCRIPT_DIR/update_klipper_mcu.sh
UNIT_TEMPLATE=$SCRIPT_DIR/mcu-update.service.in
SERVICE=mcu-update
UNIT_PATH=/etc/systemd/system/$SERVICE.service
SUDOERS_PATH=/etc/sudoers.d/$SERVICE

PRINTER_DATA=${PRINTER_DATA:-$HOME/printer_data}
KLIPPER_DIR=${KLIPPER_DIR:-$HOME/klipper}
KATAPULT_DIR=${KATAPULT_DIR:-$HOME/katapult}
MOONRAKER_URL=${MOONRAKER_URL:-http://localhost:7125}
FLASH_ARGS=""
WITH_MACRO=0
UNINSTALL=0
DRY_RUN=0
ASSUME_YES=0

if [[ -t 1 ]]; then
    C_RED=$'\033[91m'; C_GREEN=$'\033[92m'; C_YELLOW=$'\033[93m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_OFF=""
fi
info() { printf '%s\n' "$*"; }
ok()   { printf '%s%s%s\n' "$C_GREEN" "$*" "$C_OFF"; }
warn() { printf '%sВНИМАНИЕ: %s%s\n' "$C_YELLOW" "$*" "$C_OFF" >&2; }
die()  { printf '%sОШИБКА: %s%s\n' "$C_RED" "$*" "$C_OFF" >&2; exit 1; }
step() { printf '\n== %s ==\n' "$*"; }

usage() {
    cat <<'EOF'
Использование: install_fluidd_button.sh [опции]

  --printer-data DIR  каталог printer_data (по умолчанию ~/printer_data)
  --flash-args "..."  аргументы update_klipper_mcu.sh для кнопки (по умолчанию пусто:
                      обновить ветку klipper через git и прошить MCU; например
                      "--no-update --force-flash" = только перепрошить все MCU)
  --with-macro        создать mcu_update.cfg с макросом MCU_UPDATE
  --uninstall         удалить сервис, строку в moonraker.asvc и sudoers-файл
  --dry-run           ничего не менять, показать unit и план действий
  -y, --yes           не задавать вопросов
  -V, --version       показать версию установщика
  -h, --help          эта справка

Переменные окружения: PRINTER_DATA, KLIPPER_DIR, KATAPULT_DIR, MOONRAKER_URL.
EOF
}

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    [[ -r /dev/tty ]] || die "нет терминала для подтверждения, используйте -y"
    local answer
    read -r -p "$1 [y/N] " answer </dev/tty
    [[ $answer == [yYдД]* ]]
}

# run <команда...>: выполняет или только печатает при --dry-run
run() {
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] $*"; else "$@"; fi
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --printer-data) [[ $# -ge 2 ]] || die "--printer-data требует аргумент"; PRINTER_DATA=$2; shift ;;
        --flash-args) [[ $# -ge 2 ]] || die "--flash-args требует аргумент"; FLASH_ARGS=$2; shift ;;
        --with-macro) WITH_MACRO=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -y|--yes) ASSUME_YES=1 ;;
        -V|--version) echo "VOSTOK installer $VOSTOK_INSTALLER_VERSION"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "неизвестная опция: $1" ;;
    esac
    shift
done

ASVC=$PRINTER_DATA/moonraker.asvc
MACRO_CFG=$PRINTER_DATA/config/mcu_update.cfg

[[ $EUID -ne 0 ]] || die "не запускайте от root: сервис должен работать от обычного пользователя"
[[ -f $UPDATE_SCRIPT ]] || die "нет $UPDATE_SCRIPT"
[[ -f $UNIT_TEMPLATE ]] || die "нет $UNIT_TEMPLATE"

render_unit() {
    local content
    content=$(<"$UNIT_TEMPLATE")
    content=${content//@USER@/$(id -un)}
    content=${content//@HOME@/$HOME}
    content=${content//@PRINTER_DATA@/$PRINTER_DATA}
    content=${content//@SCRIPT@/$UPDATE_SCRIPT}
    content=${content//@FLASH_ARGS@/$FLASH_ARGS}
    printf '%s\n' "$content"
}

# Без терминала sudo спрашивать пароль не сможет, поэтому нужны права заранее
can_manage_services() {
    pkcheck --action-id org.freedesktop.systemd1.manage-units --process $$ >/dev/null 2>&1
}

restart_moonraker() {
    systemctl --no-ask-password restart moonraker 2>/dev/null \
        || sudo systemctl restart moonraker \
        || warn "не удалось перезапустить Moonraker, сделайте это вручную"
}

# ------------------------------------------------------------------ удаление

if [[ $UNINSTALL -eq 1 ]]; then
    step "Удаление"
    if [[ -f $UNIT_PATH ]]; then
        run sudo systemctl stop "$SERVICE" || true
        run sudo rm -f "$UNIT_PATH"
        run sudo systemctl daemon-reload
        ok "удалён $UNIT_PATH"
    fi
    for dropin in /etc/systemd/system/moonraker*.service.d/$SERVICE.conf; do
        [[ -f $dropin ]] || continue
        run sudo rm -f "$dropin"
        run sudo rmdir --ignore-fail-on-non-empty "$(dirname "$dropin")"
        run sudo systemctl daemon-reload
        ok "удалён $dropin"
    done
    if [[ -f $SUDOERS_PATH ]]; then
        run sudo rm -f "$SUDOERS_PATH"
        ok "удалён $SUDOERS_PATH"
    fi
    if [[ -f $ASVC ]] && grep -qx "$SERVICE" "$ASVC"; then
        if [[ $DRY_RUN -eq 0 ]]; then
            tmp=$(mktemp)
            grep -vx "$SERVICE" "$ASVC" >"$tmp" || true
            cat "$tmp" >"$ASVC"; rm -f "$tmp"
        else
            info "[dry-run] удалить строку $SERVICE из $ASVC"
        fi
        ok "строка $SERVICE удалена из $ASVC"
        [[ $DRY_RUN -eq 1 ]] || restart_moonraker
    fi
    if [[ -f $MACRO_CFG ]]; then
        warn "$MACRO_CFG не удалён; уберите [include mcu_update.cfg] из printer.cfg и удалите файл сами"
    fi
    exit 0
fi

# ------------------------------------------------------------------ проверки

step "Проверки"
[[ -d $KLIPPER_DIR/.git ]] || die "$KLIPPER_DIR не git-репозиторий (KLIPPER_DIR)"
[[ -f $KATAPULT_DIR/scripts/flashtool.py ]] || die "нет $KATAPULT_DIR/scripts/flashtool.py (KATAPULT_DIR)"
[[ -d $PRINTER_DATA ]] || die "нет каталога $PRINTER_DATA (--printer-data)"
command -v systemctl >/dev/null || die "нет systemctl"
curl -sf --max-time 5 "$MOONRAKER_URL/server/info" >/dev/null 2>&1 \
    || die "Moonraker недоступен ($MOONRAKER_URL)"

missing=()
command -v arm-none-eabi-gcc >/dev/null || missing+=(gcc-arm-none-eabi)
command -v make >/dev/null || missing+=(make)
python3 -c 'import serial' 2>/dev/null || missing+=(python3-serial)
if [[ ${#missing[@]} -gt 0 ]]; then
    warn "не хватает пакетов: ${missing[*]}"
    if [[ $DRY_RUN -eq 0 ]] && confirm "Установить: sudo apt install ${missing[*]}?"; then
        sudo apt install -y "${missing[@]}"
    else
        warn "поставьте вручную: sudo apt install ${missing[*]}"
    fi
fi

info "Найденные MCU и конфиги сборки:"
"$UPDATE_SCRIPT" --list || warn "--list завершился с ошибкой, посмотрите вывод выше"
info "Напоминание: на каждом MCU должен стоять загрузчик katapult, иначе прошивка не сработает."
ok "проверки закончены"

# ---------------------------------------------------------------------- права

step "Права на остановку klipper без пароля"
if can_manage_services; then
    ok "достаточно polkit (права выданы Moonraker), sudoers не нужен"
else
    warn "polkit не разрешает управлять сервисами, потребуется sudoers-правило"
    rule="$(id -un) ALL=(root) NOPASSWD: /usr/bin/systemctl start klipper*.service, /usr/bin/systemctl stop klipper*.service, /bin/systemctl start klipper*.service, /bin/systemctl stop klipper*.service"
    if [[ $DRY_RUN -eq 1 ]]; then
        info "[dry-run] $SUDOERS_PATH: $rule"
    else
        tmp=$(mktemp)
        printf '%s\n' "$rule" >"$tmp"
        sudo visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; die "sudoers-правило не прошло visudo"; }
        sudo install -m 0440 -o root -g root "$tmp" "$SUDOERS_PATH"
        rm -f "$tmp"
        ok "создан $SUDOERS_PATH"
    fi
fi

# ----------------------------------------------------------------------- unit

step "Сервис $SERVICE"
if [[ $DRY_RUN -eq 1 ]]; then
    info "[dry-run] $UNIT_PATH:"
    render_unit
else
    tmp=$(mktemp)
    render_unit >"$tmp"
    sudo install -m 0644 -o root -g root "$tmp" "$UNIT_PATH"
    rm -f "$tmp"
    sudo systemctl daemon-reload
    ok "установлен $UNIT_PATH"
fi

step "Moonraker: список разрешённых сервисов"
NEED_RESTART=0
if [[ -f $ASVC ]] && grep -qx "$SERVICE" "$ASVC"; then
    info "$SERVICE уже есть в $ASVC"
elif [[ $DRY_RUN -eq 1 ]]; then
    info "[dry-run] добавить $SERVICE в $ASVC"
else
    # файл может не заканчиваться переводом строки
    if [[ -s $ASVC && -n $(tail -c1 "$ASVC") ]]; then printf '\n' >>"$ASVC"; fi
    printf '%s\n' "$SERVICE" >>"$ASVC"
    ok "добавлено в $ASVC"
    NEED_RESTART=1
fi

# Moonraker показывает в Fluidd только загруженные в systemd сервисы, а неактивный oneshot
# systemd выгружает. Ссылка After= из moonraker.service держит юнит загруженным, не запуская его.
step "Moonraker: загрузка юнита $SERVICE в systemd"
for mu in $(systemctl list-unit-files 'moonraker*.service' --no-legend 2>/dev/null | awk '{print $1}'); do
    dropin=/etc/systemd/system/$mu.d/$SERVICE.conf
    want=$'[Unit]\n'"After=$SERVICE.service"
    if [[ -f $dropin && $(<"$dropin") == "$want" ]]; then
        info "$dropin уже есть"
    elif [[ $DRY_RUN -eq 1 ]]; then
        info "[dry-run] $dropin: After=$SERVICE.service"
    else
        tmp=$(mktemp)
        printf '%s\n' "$want" >"$tmp"
        sudo install -d -m 0755 "/etc/systemd/system/$mu.d"
        sudo install -m 0644 -o root -g root "$tmp" "$dropin"
        rm -f "$tmp"
        sudo systemctl daemon-reload
        ok "создан $dropin"
        NEED_RESTART=1
    fi
done
[[ $NEED_RESTART -eq 0 || $DRY_RUN -eq 1 ]] || restart_moonraker

# --------------------------------------------------------------------- макрос

if [[ $WITH_MACRO -eq 1 ]]; then
    step "Макрос MCU_UPDATE"
    if [[ ! -f $KLIPPER_DIR/klippy/extras/gcode_shell_command.py ]]; then
        warn "нет gcode_shell_command.py: установите расширение через KIAUH (Extensions), иначе макрос не загрузится"
    fi
    if [[ -f $MACRO_CFG ]]; then
        info "$MACRO_CFG уже существует, не трогаю"
    elif [[ $DRY_RUN -eq 1 ]]; then
        info "[dry-run] создать $MACRO_CFG"
    else
        cat >"$MACRO_CFG" <<EOF
# Запуск сборки и прошивки MCU (сервис $SERVICE). Работает, когда Klipper в состоянии ready;
# если Klipper не стартует из-за версии MCU, запускайте из меню питания Fluidd.
[gcode_shell_command mcu_update]
command: systemctl --no-ask-password start --no-block $SERVICE
timeout: 10.
verbose: True

[gcode_macro MCU_UPDATE]
description: Собрать и прошить MCU (Klipper будет остановлен)
gcode:
    RESPOND MSG="Запуск обновления прошивок MCU, Klipper будет остановлен"
    RUN_SHELL_COMMAND CMD=mcu_update
EOF
        ok "создан $MACRO_CFG"
    fi
    info "Добавьте в printer.cfg после остальных [include]: [include mcu_update.cfg]"
fi

step "Готово"
info "В Fluidd: меню питания ⏻ вверху справа -> $SERVICE -> Start."
info "Лог: $PRINTER_DATA/logs/klipper_mcu_update.log (Fluidd: Файлы -> logs), journalctl -u $SERVICE"
