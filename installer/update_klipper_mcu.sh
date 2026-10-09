#!/usr/bin/env bash
# Обновление Klipper через KIAUH и прошивок MCU через katapult (только USB).
#
# Что делает: обновляет текущую ветку репозитория klipper (git pull внутри KIAUH),
# собирает прошивку под каждый найденный MCU и прошивает её через katapult,
# затем проверяет, что версии прошивок MCU совпадают с версией хоста.
#
# MCU находятся автоматически (секции [mcu*] из printer.cfg через Moonraker и
# все /dev/serial/by-id/usb-Klipper_*), конфиг сборки выбирается по типу чипа:
#   configs/<серийный_номер>.config  (для конкретной платы), иначе
#   configs/<чип>.config             (например stm32h723xx.config)
# MCU с canbus_uuid (платы голов H36/EBB, Octopus в режиме моста USB-CAN) прошиваются
# по CAN через flashtool.py -i can0 -u <uuid>; конфиг сборки для них берётся из devices.tsv
# (его создаёт install_vostok.sh) или configs/<uuid>.config. Без конфига такие MCU только показываются.
#
# Запускать от обычного пользователя в терминале (sudo спросит пароль).
# Без терминала (кнопка в Fluidd, сервис mcu-update) нужен -y; установка кнопки:
# ./install_fluidd_button.sh
# В терминале хост обновляет KIAUH, без терминала (или с --git-update) - git fast-forward
# и pip в klippy-env: KIAUH вызывает sudo (apt, systemctl), а пароль без терминала спросить некому.
# Подробности: README.md и ./update_klipper_mcu.sh --help

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4) )); then
    echo "Нужен bash 4.4 или новее (сейчас $BASH_VERSION)" >&2
    exit 1
fi

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
# Версия установщика (общая для всех скриптов): файл VERSION рядом со скриптом.
VOSTOK_INSTALLER_VERSION=$(head -n1 "$SCRIPT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || true)
VOSTOK_INSTALLER_VERSION=${VOSTOK_INSTALLER_VERSION:-неизвестна}

# Пути и адреса можно переопределить через окружение: KLIPPER_DIR=... ./update_klipper_mcu.sh
KLIPPER_DIR=${KLIPPER_DIR:-$HOME/klipper}
KLIPPY_ENV=${KLIPPY_ENV:-$HOME/klippy-env}
KATAPULT_DIR=${KATAPULT_DIR:-$HOME/katapult}
KIAUH_DIR=${KIAUH_DIR:-$HOME/kiauh}
PRINTER_DATA=${PRINTER_DATA:-$HOME/printer_data}
MOONRAKER_URL=${MOONRAKER_URL:-http://localhost:7125}
CONFIGS_DIR=${CONFIGS_DIR:-$SCRIPT_DIR/configs}
FIRMWARE_DIR=${FIRMWARE_DIR:-$SCRIPT_DIR/firmware}
BUILD_DIR=${BUILD_DIR:-$SCRIPT_DIR/build}
# Журнал версий, которые прошил этот скрипт: серийный_номер<TAB>версия.
# Нужен для MCU, которых нет в printer.cfg (Moonraker не знает их версию).
STATE_FILE=${STATE_FILE:-$FIRMWARE_DIR/flashed.tsv}
LOG_FILE=${LOG_FILE:-$PRINTER_DATA/logs/klipper_mcu_update.log}
# CAN: интерфейс и карта устройств (её пишет install_vostok.sh):
# ключ(uuid или серийный номер)<TAB>конфиг сборки (относительно configs/)<TAB>роль(bridge|can|usb)
CAN_IFACE=${CAN_IFACE:-can0}
DEVICES_FILE=${DEVICES_FILE:-$SCRIPT_DIR/devices.tsv}
GCODE_SHELL_ASSET=${GCODE_SHELL_ASSET:-$KIAUH_DIR/kiauh/extensions/gcode_shell_cmd/assets/gcode_shell_command.py}

DO_UPDATE=1
DO_FLASH=1
FORCE_FLASH=0
ASSUME_YES=0
LIST_ONLY=0
IGNORE_MOONRAKER=0
GIT_UPDATE=0
KLIPPER_STOPPED=0

# ---------------------------------------------------------------- вывод и лог

if [[ -t 1 ]]; then
    C_RED=$'\033[91m'; C_GREEN=$'\033[92m'; C_YELLOW=$'\033[93m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_OFF=""
fi

log_to_file() {
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || return 0
    printf '%s %s\n' "$(date '+%F %T')" "$1" >>"$LOG_FILE" 2>/dev/null || true
}
info() { printf '%s\n' "$*"; log_to_file "$*"; }
ok()   { printf '%s%s%s\n' "$C_GREEN" "$*" "$C_OFF"; log_to_file "OK: $*"; }
warn() { printf '%sВНИМАНИЕ: %s%s\n' "$C_YELLOW" "$*" "$C_OFF" >&2; log_to_file "ВНИМАНИЕ: $*"; }
die()  { printf '%sОШИБКА: %s%s\n' "$C_RED" "$*" "$C_OFF" >&2; log_to_file "ОШИБКА: $*"; exit 1; }
step() { printf '\n== %s ==\n' "$*"; log_to_file "== $* =="; }

usage() {
    cat <<'EOF'
Использование: update_klipper_mcu.sh [опции]

  --list              показать найденные MCU, конфиги сборки и версии, ничего не менять
  --no-update         не обновлять хост (KIAUH), только собрать и прошить MCU
  --no-flash          обновить только хост, прошивки MCU не трогать
  --force-flash       прошить все MCU, даже если версии уже совпадают с хостом
  --git-update        обновить хост без KIAUH (git fast-forward + pip, без sudo);
                      включается сам, если нет терминала (кнопка в Fluidd)
  -V, --version       показать версию установщика
  --ignore-moonraker  продолжить, если Moonraker недоступен (статус печати и
                      секции [mcu*] из printer.cfg не проверяются)
  -y, --yes           не задавать вопросов
  -h, --help          эта справка

Переменные окружения (значения по умолчанию в скобках):
  KLIPPER_DIR ($HOME/klipper)  KATAPULT_DIR ($HOME/katapult)  KIAUH_DIR ($HOME/kiauh)
  KLIPPY_ENV ($HOME/klippy-env)  PRINTER_DATA ($HOME/printer_data)
  MOONRAKER_URL (http://localhost:7125)  CONFIGS_DIR ($скрипт/configs)
EOF
}

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    [[ -r /dev/tty ]] || die "нет терминала для подтверждения, используйте -y"
    local answer
    read -r -p "$1 [y/N] " answer </dev/tty
    [[ $answer == [yYдД]* ]]
}

# ------------------------------------------------------------------ аргументы

while [[ $# -gt 0 ]]; do
    case $1 in
        --list) LIST_ONLY=1 ;;
        --no-update) DO_UPDATE=0 ;;
        --no-flash) DO_FLASH=0 ;;
        --force-flash) FORCE_FLASH=1 ;;
        --git-update) GIT_UPDATE=1 ;;
        --ignore-moonraker) IGNORE_MOONRAKER=1 ;;
        -y|--yes) ASSUME_YES=1 ;;
        -V|--version) echo "VOSTOK installer $VOSTOK_INSTALLER_VERSION"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "неизвестная опция: $1" ;;
    esac
    shift
done
[[ -t 0 ]] || GIT_UPDATE=1

# ------------------------------------------------------------------- Moonraker

MOONRAKER_OK=0

# mr_get <путь>: JSON из Moonraker или ненулевой код
mr_get() { curl -sf --max-time 5 "${MOONRAKER_URL}$1"; }

# json_get <python-выражение над r>: вычисляет выражение над JSON со stdin
json_get() {
    python3 -c '
import sys, json
r = json.load(sys.stdin)
expr = sys.argv[1]
print(eval(expr))
' "$1"
}

check_moonraker() {
    if mr_get /server/info >/dev/null 2>&1; then
        MOONRAKER_OK=1
        return
    fi
    if [[ $IGNORE_MOONRAKER -eq 1 ]]; then
        warn "Moonraker недоступен ($MOONRAKER_URL): статус печати и секции [mcu*] не проверяются"
        return
    fi
    die "Moonraker недоступен ($MOONRAKER_URL). Проверьте MOONRAKER_URL или запустите с --ignore-moonraker"
}

check_not_printing() {
    [[ $MOONRAKER_OK -eq 1 ]] || return 0
    local state
    state=$(mr_get '/printer/objects/query?print_stats' 2>/dev/null \
        | json_get "r['result']['status']['print_stats']['state']" 2>/dev/null || echo "")
    case $state in
        printing|paused) die "идёт печать (state=$state). Обновление остановит Klipper и сорвёт печать" ;;
    esac
}

# ------------------------------------------------------------------- проверки

preflight() {
    step "Проверки"
    [[ $EUID -ne 0 ]] || die "не запускайте от root (KIAUH это запрещает), sudo спросит пароль сам"
    command -v python3 >/dev/null || die "нет python3"
    command -v curl >/dev/null || die "нет curl"
    command -v git >/dev/null || die "нет git"
    [[ -d $KLIPPER_DIR/.git ]] || die "$KLIPPER_DIR не git-репозиторий (KLIPPER_DIR)"

    if [[ $DO_UPDATE -eq 1 ]]; then
        if [[ $GIT_UPDATE -eq 1 ]]; then
            [[ -x $KLIPPY_ENV/bin/pip ]] || die "нет $KLIPPY_ENV/bin/pip (KLIPPY_ENV)"
        else
            [[ -x $KIAUH_DIR/kiauh.sh ]] || die "нет $KIAUH_DIR/kiauh.sh (KIAUH_DIR)"
        fi
        git -C "$KLIPPER_DIR" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1 \
            || die "у текущей ветки klipper не задан upstream, git pull не сработает"
    fi
    if [[ $DO_FLASH -eq 1 ]]; then
        [[ -f $KATAPULT_DIR/scripts/flashtool.py ]] || die "нет $KATAPULT_DIR/scripts/flashtool.py (KATAPULT_DIR)"
        python3 -c 'import serial' 2>/dev/null || die "для flashtool.py нужен pyserial (python3 -m pip install pyserial)"
        command -v arm-none-eabi-gcc >/dev/null || die "нет arm-none-eabi-gcc (sudo apt install gcc-arm-none-eabi)"
        command -v make >/dev/null || die "нет make"
        command -v ip >/dev/null || warn "нет ip (пакет iproute2): MCU на CAN не будут найдены"
        if [[ ! -t 0 && $LIST_ONLY -eq 0 ]]; then
            can_manage_services \
                || die "без терминала нет прав останавливать klipper (нужен polkit Moonraker или sudo NOPASSWD, см. install_fluidd_button.sh)"
        fi
    fi

    # tracked-изменения ломают git pull и дают -dirty в версии прошивки; untracked не мешают
    if [[ -n $(git -C "$KLIPPER_DIR" status --porcelain --untracked-files=no) ]]; then
        git -C "$KLIPPER_DIR" status --short --untracked-files=no >&2
        die "в $KLIPPER_DIR есть изменённые отслеживаемые файлы, зафиксируйте или откатите их"
    fi

    check_moonraker
    check_not_printing
    ok "проверки пройдены"
}

# ----------------------------------------------------------- обнаружение MCU

# Параллельные массивы по найденным MCU
MCU_NAME=(); MCU_PATH=(); MCU_CHIP=(); MCU_SERIAL=(); MCU_CFG=(); MCU_VER=(); MCU_ORDER=()
MCU_UUID=(); MCU_BRIDGE=()   # для MCU на CAN: uuid и признак «главная плата - мост USB-CAN»
SKIPPED=()

# Из имени usb-Klipper_<чип>_<серийный>-if00 вытаскивает чип/серийный номер
by_id_chip()   { sed -n 's/^usb-Klipper_\(.*\)_[^_]*-if[0-9]*$/\1/p' <<<"$(basename "$1")"; }
by_id_serial() { sed -n 's/^usb-Klipper_.*_\([^_]*\)-if[0-9]*$/\1/p' <<<"$(basename "$1")"; }

# Секции [mcu*] из printer.cfg: строки "имя<TAB>serial<TAB>canbus_uuid"
cfg_mcus() {
    [[ $MOONRAKER_OK -eq 1 ]] || return 0
    mr_get '/printer/objects/query?configfile=settings' 2>/dev/null | python3 -c '
import sys, json
try:
    s = json.load(sys.stdin)["result"]["status"]["configfile"]["settings"]
except Exception:
    sys.exit(0)
for name, sect in s.items():
    if name == "mcu" or name.startswith("mcu "):
        # "-" вместо пустого поля: read с IFS=таб схлопывает пустые значения
        print("%s\t%s\t%s" % (name, sect.get("serial") or "-", sect.get("canbus_uuid") or "-"))
' || true
}

# Версии прошивок: строки "имя<TAB>версия" для объектов mcu*
cfg_mcu_versions() {
    [[ $MOONRAKER_OK -eq 1 ]] || return 0
    local names="$1" query=""
    [[ -n $names ]] || return 0
    while IFS= read -r n; do
        query+="&$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$n")"
    done <<<"$names"
    mr_get "/printer/objects/query?${query#&}" 2>/dev/null | python3 -c '
import sys, json
try:
    s = json.load(sys.stdin)["result"]["status"]
except Exception:
    sys.exit(0)
for name, o in s.items():
    if isinstance(o, dict) and "mcu_version" in o:
        print("%s\t%s" % (name, o["mcu_version"]))
' || true
}

add_mcu() { # имя путь происхождение(cfg|usb)
    local name=$1 path=$2 origin=$3 chip serial cfg order real i
    real=$(readlink -f "$path" 2>/dev/null || echo "$path")
    for i in "${!MCU_PATH[@]}"; do
        [[ $(readlink -f "${MCU_PATH[$i]}" 2>/dev/null || echo "${MCU_PATH[$i]}") == "$real" ]] && return 0
    done
    chip=$(by_id_chip "$path"); serial=$(by_id_serial "$path")
    if [[ -z $chip ]]; then
        SKIPPED+=("$name ($path): не /dev/serial/by-id/usb-Klipper_*, тип чипа неизвестен")
        return 0
    fi
    cfg=""
    if [[ -f $CONFIGS_DIR/$serial.config ]]; then
        cfg=$CONFIGS_DIR/$serial.config
    elif [[ -f $CONFIGS_DIR/$chip.config ]]; then
        cfg=$CONFIGS_DIR/$chip.config
    fi
    # Порядок прошивки: сначала MCU вне printer.cfg, потом дополнительные, главный [mcu] последним
    if [[ $origin == usb ]]; then order=1; elif [[ $name == mcu ]]; then order=3; else order=2; fi
    MCU_NAME+=("$name"); MCU_PATH+=("$path"); MCU_CHIP+=("$chip"); MCU_SERIAL+=("$serial")
    MCU_CFG+=("$cfg"); MCU_VER+=("?"); MCU_ORDER+=("$order"); MCU_UUID+=(""); MCU_BRIDGE+=(0)
}

# Строка devices.tsv по ключу (uuid или серийный номер): "конфиг<TAB>роль"
devices_lookup() {
    [[ -f $DEVICES_FILE ]] || return 0
    awk -F'\t' -v k="$1" '$1 == k {print $2 "\t" $3; exit}' "$DEVICES_FILE"
}

can_iface_up() { ip link show "$CAN_IFACE" 2>/dev/null | grep -q 'UP'; }

add_can_mcu() { # имя uuid
    local name=$1 uuid=$2 rel role cfg="" chip order=2 bridge=0
    IFS=$'\t' read -r rel role < <(devices_lookup "$uuid") || true
    if [[ -n ${rel:-} && -f $CONFIGS_DIR/$rel ]]; then
        cfg=$CONFIGS_DIR/$rel
    elif [[ -f $CONFIGS_DIR/$uuid.config ]]; then
        cfg=$CONFIGS_DIR/$uuid.config
    fi
    if [[ -z $cfg ]]; then
        SKIPPED+=("$name: CAN (canbus_uuid $uuid), нет конфига сборки (devices.tsv или configs/$uuid.config), прошивается вручную: flashtool.py -i $CAN_IFACE -u $uuid -f <bin>")
        return 0
    fi
    if ! can_iface_up; then
        SKIPPED+=("$name: CAN (canbus_uuid $uuid), интерфейс $CAN_IFACE не поднят (ip link show $CAN_IFACE)")
        return 0
    fi
    chip=$(sed -n 's/^CONFIG_MCU="\(.*\)"$/\1/p' "$cfg")
    if [[ ${role:-} == bridge ]]; then bridge=1; order=3; fi
    [[ $name == mcu ]] && order=3
    MCU_NAME+=("$name"); MCU_PATH+=("CAN $CAN_IFACE $uuid"); MCU_CHIP+=("$chip"); MCU_SERIAL+=("$uuid")
    MCU_CFG+=("$cfg"); MCU_VER+=("?"); MCU_ORDER+=("$order"); MCU_UUID+=("$uuid"); MCU_BRIDGE+=("$bridge")
}

discover_mcus() {
    MCU_NAME=(); MCU_PATH=(); MCU_CHIP=(); MCU_SERIAL=(); MCU_CFG=(); MCU_VER=(); MCU_ORDER=(); SKIPPED=()
    MCU_UUID=(); MCU_BRIDGE=()
    local name serial uuid dev names="" n v i

    while IFS=$'\t' read -r name serial uuid; do
        [[ -n $name ]] || continue
        names+="$name"$'\n'
        [[ $serial == "-" ]] && serial=""
        [[ $uuid == "-" ]] && uuid=""
        if [[ -n $uuid ]]; then
            add_can_mcu "$name" "$uuid"
        elif [[ -n $serial ]]; then
            if [[ -e $serial ]]; then
                add_mcu "$name" "$serial" cfg
            else
                SKIPPED+=("$name: устройство $serial не найдено (не подключено или в режиме загрузчика?)")
            fi
        fi
    done < <(cfg_mcus)

    for dev in /dev/serial/by-id/usb-Klipper_*; do
        [[ -e $dev ]] || continue
        add_mcu "(не в printer.cfg)" "$dev" usb
    done
    for dev in /dev/serial/by-id/usb-katapult_*; do
        [[ -e $dev ]] || continue
        SKIPPED+=("$(basename "$dev"): устройство в режиме загрузчика katapult, прошейте вручную: flashtool.py -d $dev -f <bin>")
    done

    # Текущие версии прошивок
    while IFS=$'\t' read -r n v; do
        [[ -n $n ]] || continue
        for i in "${!MCU_NAME[@]}"; do
            [[ ${MCU_NAME[$i]} == "$n" ]] && MCU_VER[$i]=$v
        done
    done < <(cfg_mcu_versions "$names")

    # Версия неизвестна (нет в printer.cfg или Klipper не дошёл до MCU): берём из журнала, помечаем "*"
    for i in "${!MCU_NAME[@]}"; do
        if [[ ${MCU_VER[$i]} == "?" ]]; then
            v=$(state_get "${MCU_SERIAL[$i]}")
            [[ -z $v ]] || MCU_VER[$i]="$v*"
        fi
    done
}

host_version() { git -C "$KLIPPER_DIR" describe --always --tags --long; }
# Убирает "*" (версия взята из журнала) и "-dirty"
norm_version() { local v=${1%\*}; printf '%s' "${v%-dirty}"; }

state_get() { [[ -f $STATE_FILE ]] && awk -F'\t' -v s="$1" '$1 == s {v = $2} END {if (v != "") print v}' "$STATE_FILE" || true; }
state_set() {
    local tmp
    mkdir -p "$(dirname "$STATE_FILE")"
    tmp=$(mktemp "$STATE_FILE.XXXXXX")
    { [[ -f $STATE_FILE ]] && awk -F'\t' -v s="$1" '$1 != s' "$STATE_FILE" || true; printf '%s\t%s\n' "$1" "$2"; } >"$tmp"
    mv "$tmp" "$STATE_FILE"
}

print_mcus() {
    local i host
    host=$(host_version)
    info "Версия хоста: $host"
    if [[ ${#MCU_NAME[@]} -eq 0 ]]; then
        info "MCU по USB не найдены"
    else
        printf '%-20s %-13s %-26s %-24s %s\n' "MCU" "чип" "версия" "конфиг сборки" "устройство"
        for i in "${!MCU_NAME[@]}"; do
            printf '%-20s %-13s %-26s %-24s %s\n' "${MCU_NAME[$i]}" "${MCU_CHIP[$i]}" "${MCU_VER[$i]}" \
                "$( [[ -n ${MCU_CFG[$i]} ]] && basename "${MCU_CFG[$i]}" || echo '-- нет --' )" "${MCU_PATH[$i]}"
        done
    fi
    for i in "${!SKIPPED[@]}"; do
        info "Пропущено: ${SKIPPED[$i]}"
    done
    for i in "${!MCU_NAME[@]}"; do
        if [[ -z ${MCU_CFG[$i]} ]]; then
            warn "для ${MCU_NAME[$i]} (${MCU_CHIP[$i]}) нет конфига сборки; создайте его: cd $KLIPPER_DIR && make menuconfig KCONFIG_CONFIG=$CONFIGS_DIR/${MCU_CHIP[$i]}.config"
        fi
    done
}

# ------------------------------------------------------------ обновление хоста

pending_commits() {
    git -C "$KLIPPER_DIR" fetch -q || die "git fetch не удался"
    git -C "$KLIPPER_DIR" rev-list --count 'HEAD..@{u}'
}

# Расширение KIAUH пропадает при смене/переустановке репозитория; затем проверка импорта
post_update_checks() {
    local extras=$KLIPPER_DIR/klippy/extras
    if grep -qs '^\[gcode_shell_command' "$PRINTER_DATA"/config/*.cfg 2>/dev/null \
        && [[ ! -f $extras/gcode_shell_command.py ]]; then
        if [[ -f $GCODE_SHELL_ASSET ]]; then
            cp -n "$GCODE_SHELL_ASSET" "$extras/" && info "восстановлен gcode_shell_command.py"
        else
            warn "в конфигах есть [gcode_shell_command], но $GCODE_SHELL_ASSET не найден"
        fi
    fi
    if [[ -x $KLIPPY_ENV/bin/python ]]; then
        "$KLIPPY_ENV/bin/python" "$KLIPPER_DIR/klippy/klippy.py" --import-test >/dev/null \
            || die "klippy --import-test не прошёл после обновления"
    fi
}

# Обновление без KIAUH и без sudo: fast-forward ветки, зависимости в klippy-env.
# Klipper останавливается на время обновления (services вызывается в main).
update_host_git() {
    step "Обновление Klipper через git"
    local before after upstream
    before=$(git -C "$KLIPPER_DIR" rev-parse HEAD)
    upstream=$(git -C "$KLIPPER_DIR" rev-parse '@{u}')
    if git -C "$KLIPPER_DIR" merge-base --is-ancestor HEAD "$upstream"; then
        git -C "$KLIPPER_DIR" merge --ff-only -q "$upstream" || die "git merge --ff-only не удался"
    elif [[ -z $(git -C "$KLIPPER_DIR" rev-list HEAD --not --remotes) ]]; then
        # upstream переписан (force-push), локальных коммитов, которых нет на сервере, нет
        warn "история upstream переписана, перехожу на ${upstream:0:8}"
        git -C "$KLIPPER_DIR" reset -q --hard "$upstream" || die "git reset не удался"
    else
        die "в $KLIPPER_DIR есть локальные коммиты, которых нет на сервере; обновите вручную"
    fi
    after=$(git -C "$KLIPPER_DIR" rev-parse HEAD)
    [[ $after == "$upstream" ]] || die "репозиторий не на upstream после обновления"
    info "обновлено: ${before:0:8} -> ${after:0:8}"

    log_to_file "pip install -r klippy-requirements.txt"
    "$KLIPPY_ENV/bin/pip" install -q -r "$KLIPPER_DIR/scripts/klippy-requirements.txt" \
        || die "pip install зависимостей klippy не удался"
    if ! git -C "$KLIPPER_DIR" diff --quiet "$before" "$after" -- scripts/install-debian.sh; then
        warn "изменился scripts/install-debian.sh: возможно нужны новые системные пакеты; запустите ./update_klipper_mcu.sh из терминала (KIAUH)"
    fi
    post_update_checks
    ok "хост обновлён: $(host_version)"
}

update_host() {
    step "Обновление Klipper через KIAUH"
    local before after upstream
    before=$(git -C "$KLIPPER_DIR" rev-parse HEAD)
    log_to_file "запуск KIAUH: kiauh.sh update klipper"
    "$KIAUH_DIR/kiauh.sh" update klipper || die "KIAUH завершился с ошибкой"
    # git_pull_wrapper в KIAUH глотает ошибки git pull, поэтому проверяем результат сами
    after=$(git -C "$KLIPPER_DIR" rev-parse HEAD)
    upstream=$(git -C "$KLIPPER_DIR" rev-parse '@{u}')
    [[ $after == "$upstream" ]] || die "после KIAUH репозиторий не на upstream (HEAD=${after:0:8}, upstream=${upstream:0:8}); смотрите вывод git pull выше"
    [[ $before == "$after" ]] && info "репозиторий не изменился" || info "обновлено: ${before:0:8} -> ${after:0:8}"

    post_update_checks
    ok "хост обновлён: $(host_version)"
}

# --------------------------------------------------------------------- сборка

declare -A BUILT_BIN=()   # путь конфига -> путь собранного bin

build_firmware() { # конфиг чип
    local cfg=$1 chip=$2 key work out cfg_mcu ver
    key=$(basename "$cfg" .config)
    [[ -n ${BUILT_BIN[$cfg]:-} ]] && return 0
    work=$BUILD_DIR/$key
    out=$work/out/
    rm -rf "$work"; mkdir -p "$work" "$FIRMWARE_DIR"
    cp "$cfg" "$work/.config"
    info "сборка $key ..."
    # Сборка вне репозитория: KCONFIG_CONFIG и OUT указывают в BUILD_DIR
    local mk=(make -C "$KLIPPER_DIR" "KCONFIG_CONFIG=$work/.config" "OUT=$out")
    "${mk[@]}" olddefconfig >"$work/make.log" 2>&1 || { tail -n 20 "$work/make.log" >&2; die "make olddefconfig ($key) не удался"; }
    cfg_mcu=$(sed -n 's/^CONFIG_MCU="\(.*\)"$/\1/p' "$work/.config")
    [[ $cfg_mcu == "$chip" ]] || die "конфиг $cfg собирает CONFIG_MCU=$cfg_mcu, а устройству нужен $chip"
    "${mk[@]}" -j"$(nproc)" >>"$work/make.log" 2>&1 || { tail -n 30 "$work/make.log" >&2; die "сборка $key не удалась, лог: $work/make.log"; }
    [[ -f $out/klipper.bin ]] || die "сборка $key не создала klipper.bin"
    ver=$(host_version)
    cp "$out/klipper.bin" "$FIRMWARE_DIR/$key-$ver.bin"
    cp "$work/.config" "$cfg"   # olddefconfig мог добавить новые опции
    BUILT_BIN[$cfg]=$FIRMWARE_DIR/$key-$ver.bin
    ok "собрано: $FIRMWARE_DIR/$key-$ver.bin ($(stat -c %s "$out/klipper.bin") байт)"
}

# ------------------------------------------------------------------- сервисы

klipper_units() {
    systemctl list-unit-files 'klipper*.service' --no-legend 2>/dev/null | awk '{print $1}' \
        | grep -E '^klipper(-[A-Za-z0-9_]+)?\.service$' | grep -v '^klipper-mcu\.service$' || true
}

# systemctl без пароля: сначала через polkit (права от Moonraker), затем sudo
sctl() {
    systemctl --no-ask-password "$@" 2>/dev/null && return 0
    if [[ -t 0 ]]; then sudo systemctl "$@"; else sudo -n systemctl "$@"; fi
}

# Можно ли управлять сервисами klipper без терминала (запуск из Fluidd)
can_manage_services() {
    pkcheck --action-id org.freedesktop.systemd1.manage-units --process $$ >/dev/null 2>&1 \
        || sudo -n true 2>/dev/null
}

services() { # stop|start
    local action=$1 u units
    units=$(klipper_units)
    [[ -n $units ]] || die "не найдены сервисы klipper*.service"
    for u in $units; do
        info "systemctl $action $u"
        sctl "$action" "$u" || die "systemctl $action $u не удалось"
    done
}

# -------------------------------------------------------------------- прошивка

wait_for_device() { # путь, секунд
    local i
    for ((i = 0; i < $2 * 2; i++)); do
        [[ -e $1 ]] && return 0
        sleep 0.5
    done
    return 1
}

# Прошивка одного MCU по CAN. Обычная плата (H36/EBB): flashtool сам просит загрузчик по uuid.
# Octopus в режиме моста USB-CAN: загрузчик запрашивается по CAN, мост перезагружается в
# usb-katapult_* (шина can0 на это время пропадает), затем прошивка по USB.
flash_can() { # индекс MCU, bin
    local i=$1 bin=$2 uuid dev="" n
    uuid=${MCU_UUID[$i]}
    if [[ ${MCU_BRIDGE[$i]} -eq 1 ]]; then
        log_to_file "flashtool -i $CAN_IFACE -u $uuid -r (мост)"
        python3 "$KATAPULT_DIR/scripts/flashtool.py" -i "$CAN_IFACE" -u "$uuid" -r || return 1
        for ((n = 0; n < 40; n++)); do
            dev=$(ls /dev/serial/by-id/usb-katapult_"${MCU_CHIP[$i]}"_* 2>/dev/null | head -n 1 || true)
            [[ -n $dev ]] && break
            sleep 0.5
        done
        [[ -n $dev ]] || { warn "мост не перешёл в katapult за 20 с (usb-katapult_${MCU_CHIP[$i]}_*)"; return 1; }
        log_to_file "flashtool -d $dev -f $bin (мост)"
        python3 "$KATAPULT_DIR/scripts/flashtool.py" -d "$dev" -f "$bin" || return 1
        # мост вернулся: поднимается gs_usb и интерфейс CAN
        for ((n = 0; n < 40; n++)); do
            ip link show "$CAN_IFACE" >/dev/null 2>&1 && break
            sleep 0.5
        done
        ip link show "$CAN_IFACE" >/dev/null 2>&1 || { warn "интерфейс $CAN_IFACE не появился после прошивки моста"; return 1; }
        can_iface_up || sudo -n ifup "$CAN_IFACE" >/dev/null 2>&1 || true
        sleep 2
    else
        log_to_file "flashtool -i $CAN_IFACE -u $uuid -f $bin"
        python3 "$KATAPULT_DIR/scripts/flashtool.py" -i "$CAN_IFACE" -u "$uuid" -f "$bin" || return 1
        sleep 2
    fi
}

flash_all() { # индексы MCU через пробел
    local i bin ok_flash
    for i in "$@"; do
        bin=${BUILT_BIN[${MCU_CFG[$i]}]}
        step "Прошивка ${MCU_NAME[$i]} (${MCU_CHIP[$i]})"
        ok_flash=1
        if [[ -n ${MCU_UUID[$i]} ]]; then
            flash_can "$i" "$bin" || ok_flash=0
        else
            log_to_file "flashtool -d ${MCU_PATH[$i]} -f $bin"
            python3 "$KATAPULT_DIR/scripts/flashtool.py" -d "${MCU_PATH[$i]}" -f "$bin" || ok_flash=0
        fi
        if [[ $ok_flash -eq 0 ]]; then
            if [[ -n ${MCU_UUID[$i]} ]]; then
                cat >&2 <<EOF

Прошивка ${MCU_NAME[$i]} по CAN не удалась. Klipper НЕ запущен.
Что делать: katapult остаётся в MCU, прошивку можно повторить.
  - проверьте шину: ip -s -d link show $CAN_IFACE (state UP, bitrate 1000000, errors 0; BUS-OFF: перезапустите интерфейс);
  - терминаторы 120 Ом: на шине должно быть около 60 Ом (питание выключено);
  - python3 $KATAPULT_DIR/scripts/flashtool.py -i $CAN_IFACE -q покажет uuid плат, находящихся в katapult (двойной RESET);
  - повтор: python3 $KATAPULT_DIR/scripts/flashtool.py -i $CAN_IFACE -u ${MCU_UUID[$i]} -f $bin
EOF
            else
                cat >&2 <<EOF

Прошивка ${MCU_NAME[$i]} не удалась. Klipper НЕ запущен.
Что делать: katapult остаётся в MCU, прошивку можно повторить.
  - посмотрите ls /dev/serial/by-id/ (устройство может быть usb-katapult_*);
  - если есть usb-katapult_*: python3 $KATAPULT_DIR/scripts/flashtool.py -d /dev/serial/by-id/usb-katapult_... -f $bin
  - иначе дважды быстро нажмите RESET на плате (двойной сброс входит в katapult).
EOF
            fi
            die "прошивка ${MCU_NAME[$i]} не удалась"
        fi
        if [[ -z ${MCU_UUID[$i]} ]]; then
            wait_for_device "${MCU_PATH[$i]}" 20 \
                || die "после прошивки ${MCU_NAME[$i]} не вернулось устройство ${MCU_PATH[$i]}; проверьте ls /dev/serial/by-id/"
        fi
        state_set "${MCU_SERIAL[$i]}" "$(host_version)"
        ok "${MCU_NAME[$i]} прошит"
    done
}

# ---------------------------------------------------------- проверка итогов

wait_for_klipper() {
    local i state="" msg=""
    for ((i = 0; i < 60; i++)); do
        state=$(mr_get /printer/info 2>/dev/null | json_get "r['result']['state']" 2>/dev/null || echo "")
        case $state in ready|shutdown|error) break ;; esac
        sleep 1
    done
    if [[ -z $state ]]; then
        warn "Moonraker не ответил за 60 с; проверьте systemctl status klipper moonraker"
        return 1
    fi
    if [[ $state != ready ]]; then
        msg=$(mr_get /printer/info 2>/dev/null | json_get "r['result']['state_message']" 2>/dev/null || echo "")
        warn "состояние Klipper: $state"
        printf '%s\n' "$msg" >&2
        return 1
    fi
    ok "Klipper: ready"
}

verify_versions() {
    local host mismatch=0 i
    host=$(norm_version "$(host_version)")
    discover_mcus
    for i in "${!MCU_NAME[@]}"; do
        if [[ ${MCU_VER[$i]} == "?" ]]; then
            info "${MCU_NAME[$i]}: версию получить не удалось"
        elif [[ ${MCU_VER[$i]} == *'*' ]]; then
            # Версия из журнала: MCU вне printer.cfg, сам Klipper её не видит
            if [[ $(norm_version "${MCU_VER[$i]}") == "$host" ]]; then
                ok "${MCU_NAME[$i]}: ${MCU_VER[$i]%\*} (по журналу прошивок)"
            else
                warn "${MCU_NAME[$i]}: ${MCU_VER[$i]%\*} по журналу, хост $host"
                mismatch=1
            fi
        elif [[ $(norm_version "${MCU_VER[$i]}") == "$host" ]]; then
            ok "${MCU_NAME[$i]}: ${MCU_VER[$i]}"
        else
            warn "${MCU_NAME[$i]}: ${MCU_VER[$i]} (хост $host)"
            mismatch=1
        fi
    done
    return $mismatch
}

# ---------------------------------------------------------------------- main

main() {
    log_to_file "=== запуск (VOSTOK installer $VOSTOK_INSTALLER_VERSION): $* ==="
    preflight

    step "Найденные MCU"
    discover_mcus
    print_mcus
    [[ $LIST_ONLY -eq 1 ]] && exit 0

    local pending=0 host_before
    host_before=$(host_version)
    if [[ $DO_UPDATE -eq 1 ]]; then
        pending=$(pending_commits)
        step "Обновления в ветке klipper"
        if [[ $pending -gt 0 ]]; then
            git -C "$KLIPPER_DIR" log --oneline 'HEAD..@{u}' | head -n 20
            [[ $pending -gt 20 ]] && info "... и ещё $((pending - 20))"
            info "Новых коммитов: $pending"
        else
            info "Новых коммитов нет (версия $host_before)"
        fi
    fi

    # Какие MCU нужно прошить: все, если хост обновится или --force-flash, иначе только отстающие
    local targets=() i host_norm
    host_norm=$(norm_version "$host_before")
    if [[ $DO_FLASH -eq 1 ]]; then
        for i in "${!MCU_NAME[@]}"; do
            [[ -n ${MCU_CFG[$i]} ]] || continue
            if [[ $pending -gt 0 || $FORCE_FLASH -eq 1 || $(norm_version "${MCU_VER[$i]}") != "$host_norm" ]]; then
                targets+=("$i")
            fi
        done
    fi

    if [[ $pending -eq 0 && ${#targets[@]} -eq 0 ]]; then
        ok "всё актуально: хост $host_before, прошивки MCU совпадают"
        exit 0
    fi

    info ""
    if [[ $pending -gt 0 ]]; then
        if [[ $GIT_UPDATE -eq 1 ]]; then
            info "Будет обновлён хост Klipper (git fast-forward, Klipper будет остановлен)."
        else
            info "Будет обновлён хост Klipper через KIAUH."
        fi
    fi
    if [[ ${#targets[@]} -gt 0 ]]; then
        info "Будут собраны и прошиты:"
        for i in "${targets[@]}"; do info "  ${MCU_NAME[$i]} (${MCU_CHIP[$i]}) <- $(basename "${MCU_CFG[$i]}")"; done
        info "Klipper будет остановлен на время прошивки."
    fi
    confirm "Продолжить?" || { info "отменено"; exit 0; }

    if [[ $pending -gt 0 ]]; then
        if [[ $GIT_UPDATE -eq 1 ]]; then
            step "Остановка Klipper"
            services stop
            KLIPPER_STOPPED=1
            update_host_git
        else
            update_host
        fi
    fi

    if [[ ${#targets[@]} -gt 0 ]]; then
        step "Сборка прошивок"
        for i in "${targets[@]}"; do build_firmware "${MCU_CFG[$i]}" "${MCU_CHIP[$i]}"; done

        # Порядок: MCU вне printer.cfg, затем дополнительные, главный [mcu] последним
        local ordered=() o
        for o in 1 2 3; do
            for i in "${targets[@]}"; do [[ ${MCU_ORDER[$i]} == "$o" ]] && ordered+=("$i"); done
        done

        if [[ $KLIPPER_STOPPED -eq 0 ]]; then
            step "Остановка Klipper"
            services stop
            KLIPPER_STOPPED=1
        fi
        flash_all "${ordered[@]}"
    fi
    if [[ $KLIPPER_STOPPED -eq 1 ]]; then
        step "Запуск Klipper"
        services start
        KLIPPER_STOPPED=0
    fi

    step "Проверка"
    local rc=0
    wait_for_klipper || rc=1
    verify_versions || rc=1
    if [[ $rc -eq 0 ]]; then
        ok "готово"
    else
        warn "завершено с замечаниями, смотрите вывод выше (лог: $LOG_FILE)"
    fi
    exit $rc
}

# При запуске через source (для тестов функций) main не вызывается
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    main "$@"
fi
