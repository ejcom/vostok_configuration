#!/usr/bin/env bash
# Генерация конфигов сборки Klipper/katapult для install_vostok.sh и update_klipper_mcu.sh.
# Параметры плат берутся из реестра boards/*.board (формат и поля - lib/boards.sh), Kconfig-строки строятся из полей.
# Конфиги лежат в configs/ (Klipper) и configs/katapult/ (katapult) и уже закоммичены в каталог;
# этот скрипт нужен, чтобы воспроизвести их после смены Kconfig (например, обновления Klipper)
# и чтобы создать конфиги для новой платы.
# Параметры исходных плат взяты из гайда https://k3d.tech/vostok/manual/electronics/firmware/.
# Octopus Pro F446: гайд её не описывает; значения (12 МГц, загрузчик 32KiB, USB PA11/PA12) по схеме платы.
# Katapult всегда пишется по DFU с 0x08000000, смещение приложения - стандартное для чипа (APP_OFFSET).
#
# Использование: tools/gen_configs.sh [--force] [--board ID] [--check] [--build]
#   (без опций)  создать недостающие конфиги (существующие не трогает)
#   --force      перезаписать существующие конфиги
#   --board ID   только эта плата (id или алиас)
#   --check      сгенерировать во временный каталог и сравнить с конфигами каталога по значимым ключам
#                (код 1 при расхождении или отсутствии файла); ничего в каталоге не меняет
#   --build      собрать каждый конфиг каталога во временном каталоге (Klipper/katapult не изменяются);
#                для katapult проверяется, что katapult.bin меньше смещения приложения

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
ROOT=$(dirname "$SCRIPT_DIR")
KLIPPER_DIR=${KLIPPER_DIR:-$HOME/klipper}
KATAPULT_DIR=${KATAPULT_DIR:-$HOME/katapult}
BOARDS_DIR=${BOARDS_DIR:-$ROOT/boards}
CONFIGS_DIR=$ROOT/configs
KATAPULT_CONFIGS=$CONFIGS_DIR/katapult
# shellcheck source=../lib/boards.sh
source "$ROOT/lib/boards.sh"

FORCE=0 CHECK=0 BUILD=0 ONLY=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE=1 ;;
        --check) CHECK=1 ;;
        --build) BUILD=1 ;;
        --board) shift; [[ $# -gt 0 ]] || { echo "--board: нужен id платы" >&2; exit 2; }
                 ONLY=$(board_resolve "$1") || { echo "неизвестная плата: $1" >&2; exit 2; } ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "неизвестный параметр: $1" >&2; exit 2 ;;
    esac
    shift
done

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Ключи, по которым --check сравнивает конфиги (остальное - версии, значения по умолчанию, шум olddefconfig)
SIGNIFICANT='^CONFIG_(MCU|CLOCK_REF_FREQ|FLASH_APPLICATION_ADDRESS|LAUNCH_APP_ADDRESS|STM32_[A-Z0-9_]*(CANBUS|USB|FLASH_START|APP_START|CLOCK_REF)[A-Z0-9_]*|USBSERIAL|CANBUS|USBCANBUS|CANBUS_FREQUENCY|INITIAL_PINS|ENABLE_DOUBLE_RESET|ENABLE_LED|STATUS_LED_PIN)='

# gen <каталог исходников> <файл> <ожидаемый CONFIG_MCU> <ожидаемый CONFIG_CLOCK_REF_FREQ> <ожидаемый FLASH_APPLICATION_ADDRESS> <строки CONFIG_...>
# Каждая заданная строка должна пережить olddefconfig: иначе Kconfig молча выбросил опцию (нет у чипа или зависимость не выполнена).
gen() {
    local src=$1 out=$2 mcu=$3 clk=$4 addr=$5 line; shift 5
    if [[ -f $out && $FORCE -eq 0 ]]; then echo "есть: $out"; return 0; fi
    mkdir -p "$(dirname "$out")"
    printf '%s\n' "$@" >"$TMP/.config"
    make -C "$src" "KCONFIG_CONFIG=$TMP/.config" "OUT=$TMP/out/" olddefconfig >"$TMP/make.log" 2>&1 \
        || { tail -n 20 "$TMP/make.log" >&2; echo "olddefconfig не удался: $out" >&2; exit 1; }
    grep -q "^CONFIG_MCU=\"$mcu\"$" "$TMP/.config" || { echo "$out: CONFIG_MCU != $mcu" >&2; exit 1; }
    grep -q "^CONFIG_CLOCK_REF_FREQ=$clk$" "$TMP/.config" || { echo "$out: CONFIG_CLOCK_REF_FREQ != $clk" >&2; exit 1; }
    grep -q "^CONFIG_FLASH_APPLICATION_ADDRESS=$addr$" "$TMP/.config" || { echo "$out: CONFIG_FLASH_APPLICATION_ADDRESS != $addr" >&2; exit 1; }
    for line in "$@"; do
        grep -qxF -- "$line" "$TMP/.config" \
            || { echo "$out: Kconfig отбросил или изменил заданную опцию после olddefconfig: $line" >&2; exit 1; }
    done
    cp "$TMP/.config" "$out"
    echo "создан: $out"
}

# Общие строки Klipper/katapult: чип, тактирование (B_CLOCK: 8M|12M|25M -> Гц)
clock_hz() { echo $(( ${1%M} * 1000000 )); }
hex_addr() { printf '0x%X' $(( 0x8000000 + 0x$1 )); }   # 0x8000000 + смещение (в hex без префикса)

# Строки CAN платы по CAN_KIND: cmenu (мост) | mmenu (меню G0B1/H7) | direct (отдельная опция)
can_lines() { # режим: bridge|head
    if [[ $1 == bridge ]]; then
        echo "CONFIG_STM32_USBCANBUS_$B_USB=y"; echo "CONFIG_STM32_CMENU_CANBUS_$B_CAN=y"
    else
        case $B_CAN_KIND in
            mmenu) echo "CONFIG_STM32_MMENU_CANBUS_$B_CAN=y" ;;
            direct) echo "CONFIG_STM32_CANBUS_$B_CAN=y" ;;
            *) echo "$B_ID: CAN_KIND=$B_CAN_KIND не подходит для платы головы" >&2; return 1 ;;
        esac
    fi
    echo "CONFIG_CANBUS_FREQUENCY=1000000"
}

# gen_klipper_cfg ID вид(usb|bridge|can): строит строки и вызывает gen для файла из реестра
gen_klipper_cfg() {
    local kind=$1 out lines pins
    out=$(board_cfg "$B_ID" "$kind") || return 0
    lines=(CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y "CONFIG_MACH_$B_MACH=y"
        "CONFIG_STM32_FLASH_START_$B_APP_OFFSET=y" "CONFIG_STM32_CLOCK_REF_$B_CLOCK=y")
    pins=$B_INITIAL_PINS
    case $kind in
        usb) lines+=("CONFIG_STM32_USB_$B_USB=y") ;;
        bridge) mapfile -t -O "${#lines[@]}" lines < <(can_lines bridge); pins=$B_BRIDGE_INITIAL_PINS ;;
        can) mapfile -t -O "${#lines[@]}" lines < <(can_lines head) ;;
    esac
    lines+=("CONFIG_INITIAL_PINS=\"$pins\"")
    gen "$KLIPPER_DIR" "$out" "$B_CHIP" "$(clock_hz "$B_CLOCK")" "$(hex_addr "$B_APP_OFFSET")" "${lines[@]}"
}

# gen_katapult_cfg: katapult пишется с 0x08000000, приложение с APP_OFFSET
gen_katapult_cfg() {
    local out lines
    out=$(board_cfg "$B_ID" katapult)
    lines=(CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y "CONFIG_MACH_$B_MACH=y"
        CONFIG_STM32_FLASH_START_0000=y "CONFIG_STM32_CLOCK_REF_$B_CLOCK=y")
    if [[ $B_ROLE == head ]]; then
        mapfile -t -O "${#lines[@]}" lines < <(can_lines head)
    else
        lines+=("CONFIG_STM32_USB_$B_USB=y")
    fi
    lines+=("CONFIG_STM32_APP_START_$B_APP_OFFSET=y" "CONFIG_INITIAL_PINS=\"$B_KATAPULT_INITIAL_PINS\"")
    [[ $B_KATAPULT_DOUBLE_RESET == y ]] && lines+=(CONFIG_ENABLE_DOUBLE_RESET=y)
    [[ -n $B_KATAPULT_LED ]] && lines+=(CONFIG_ENABLE_LED=y "CONFIG_STATUS_LED_PIN=\"$B_KATAPULT_LED\"")
    gen "$KATAPULT_DIR" "$out" "$B_CHIP" "$(clock_hz "$B_CLOCK")" 0x8000000 "${lines[@]}"
}

ids=()
if [[ -n $ONLY ]]; then ids=("$ONLY"); else mapfile -t ids < <(boards_list); fi

gen_all() {
    local id kind
    for id in "${ids[@]}"; do
        board_load "$id"
        for kind in usb bridge can; do gen_klipper_cfg "$kind"; done
        gen_katapult_cfg
    done
}

# ------------------------------------------------------------------ --check
sig() { grep -E "$SIGNIFICANT" "$1" | sort; }

if [[ $CHECK -eq 1 ]]; then
    REAL_CONFIGS=$CONFIGS_DIR REAL_KATAPULT=$KATAPULT_CONFIGS
    CONFIGS_DIR=$TMP/gen/configs KATAPULT_CONFIGS=$TMP/gen/configs/katapult
    FORCE=1
    gen_all >/dev/null
    CONFIGS_DIR=$REAL_CONFIGS KATAPULT_CONFIGS=$REAL_KATAPULT
    bad=0 n=0
    while IFS= read -r new; do
        rel=${new#"$TMP/gen/configs/"}
        old=$CONFIGS_DIR/$rel
        n=$((n + 1))
        if [[ ! -f $old ]]; then echo "НЕТ ФАЙЛА: configs/$rel"; bad=$((bad + 1)); continue; fi
        if d=$(diff <(sig "$old") <(sig "$new")); then echo "совпадает: configs/$rel"
        else echo "РАСХОЖДЕНИЕ: configs/$rel (< каталог, > сгенерировано)"; echo "$d" | sed 's/^/    /'; bad=$((bad + 1)); fi
    done < <(find "$TMP/gen/configs" -name '*.config' | sort)
    # пресет пинов главной платы (TEMPLATE) должен существовать: octopus_pro - встроенный, прочие - templates/boards/main/<имя>.cfg
    for id in "${ids[@]}"; do
        board_load "$id"
        t=$B_TEMPLATE
        [[ -z $t || $t == octopus_pro ]] && continue
        n=$((n + 1))
        if [[ -f $ROOT/templates/boards/main/$t.cfg ]]; then echo "совпадает: пресет пинов $id -> $t"
        else echo "НЕТ ФАЙЛА: templates/boards/main/$t.cfg (TEMPLATE платы $id)"; bad=$((bad + 1)); fi
    done
    echo "проверено: $n, расхождений: $bad"
    [[ $bad -eq 0 ]]
    exit
fi

# ------------------------------------------------------------------ --build
if [[ $BUILD -eq 1 ]]; then
    fail=0
    printf '%-20s %-9s %-13s %-9s %-11s %-11s %s\n' плата вид CONFIG_MCU CLOCK APP_ADDR CAN-пины "bin (байт)"
    for id in "${ids[@]}"; do
        board_load "$id"
        for kind in usb bridge can katapult; do
            cfg=$(board_cfg "$id" "$kind" 2>/dev/null) || continue
            [[ -f $cfg ]] || { echo "$id $kind: нет файла $cfg" >&2; fail=1; continue; }
            if [[ $kind == katapult ]]; then src=$KATAPULT_DIR bin=katapult.bin; else src=$KLIPPER_DIR bin=klipper.bin; fi
            rm -rf "$TMP/b"; mkdir -p "$TMP/b"
            cp "$cfg" "$TMP/b/.config"
            if ! make -C "$src" "KCONFIG_CONFIG=$TMP/b/.config" "OUT=$TMP/b/out/" olddefconfig >"$TMP/b/log" 2>&1 \
               || ! make -C "$src" "KCONFIG_CONFIG=$TMP/b/.config" "OUT=$TMP/b/out/" -j"$(nproc)" >>"$TMP/b/log" 2>&1; then
                tail -n 25 "$TMP/b/log" >&2; echo "$id $kind: сборка не удалась" >&2; fail=1; continue
            fi
            size=$(stat -c %s "$TMP/b/out/$bin")
            mcu=$(sed -n 's/^CONFIG_MCU="\(.*\)"$/\1/p' "$TMP/b/.config")
            clk=$(sed -n 's/^CONFIG_CLOCK_REF_FREQ=//p' "$TMP/b/.config")
            addr=$(sed -n 's/^CONFIG_FLASH_APPLICATION_ADDRESS=//p' "$TMP/b/.config")
            canpins=$(grep -oE '^CONFIG_STM32_(MMENU_|CMENU_)?CANBUS_P[A-Z0-9]+_P[A-Z0-9]+=y' "$TMP/b/.config" | sed -n 's/^CONFIG_STM32_\(MMENU_\|CMENU_\)\?CANBUS_\(.*\)=y/\2/p' | head -1) || true
            note=""
            if [[ $kind == katapult ]]; then
                lim=$((0x$B_APP_OFFSET))
                (( size < lim )) || { note=" ОШИБКА: katapult.bin >= смещения приложения $lim"; fail=1; }
            else
                flash=$(sed -n 's/^CONFIG_FLASH_SIZE=//p' "$TMP/b/.config")
                (( size <= flash - 0x$B_APP_OFFSET )) || { note=" ОШИБКА: klipper.bin не помещается во флеш"; fail=1; }
            fi
            printf '%-20s %-9s %-13s %-9s %-11s %-11s %s%s\n' "$id" "$kind" "$mcu" "$clk" "$addr" "${canpins:--}" "$size" "$note"
        done
    done
    [[ $fail -eq 0 ]]
    exit
fi

gen_all
