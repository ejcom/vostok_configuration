#!/usr/bin/env bash
# Генерация конфигов сборки Klipper/katapult для install_vostok.sh и update_klipper_mcu.sh.
# Конфиги лежат в configs/ (Klipper) и configs/katapult/ (katapult) и уже закоммичены в каталог;
# этот скрипт нужен, чтобы воспроизвести их после смены Kconfig (например, обновления Klipper).
# Параметры взяты из гайда https://k3d.tech/vostok/manual/electronics/firmware/.
# Octopus Pro F446: гайд её не описывает; значения (12 МГц, загрузчик 32KiB, USB PA11/PA12) по схеме платы.
#
# Использование: tools/gen_configs.sh [--force]   (существующие файлы без --force не трогает)

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
ROOT=$(dirname "$SCRIPT_DIR")
KLIPPER_DIR=${KLIPPER_DIR:-$HOME/klipper}
KATAPULT_DIR=${KATAPULT_DIR:-$HOME/katapult}
FORCE=0
[[ ${1:-} == --force ]] && FORCE=1

mkdir -p "$ROOT/configs/katapult"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# gen <каталог исходников> <файл> <ожидаемый CONFIG_MCU> <строки CONFIG_...>
gen() {
    local src=$1 out=$2 mcu=$3; shift 3
    if [[ -f $out && $FORCE -eq 0 ]]; then echo "есть: $out"; return; fi
    printf '%s\n' "$@" >"$TMP/.config"
    make -C "$src" "KCONFIG_CONFIG=$TMP/.config" "OUT=$TMP/out/" olddefconfig >"$TMP/make.log" 2>&1 \
        || { tail -n 20 "$TMP/make.log" >&2; echo "olddefconfig не удался: $out" >&2; exit 1; }
    grep -q "^CONFIG_MCU=\"$mcu\"$" "$TMP/.config" || { echo "$out: CONFIG_MCU != $mcu" >&2; exit 1; }
    cp "$TMP/.config" "$out"
    echo "создан: $out"
}

# ------------------------------------------------------------------ Klipper
K=$ROOT/configs
# Octopus Pro H723: USB (как у пользователя уже есть в stm32h723xx.config) и мост USB->CAN
gen "$KLIPPER_DIR" "$K/stm32h723xx-canbridge.config" stm32h723xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32H723=y \
    CONFIG_STM32_FLASH_START_20000=y CONFIG_STM32_CLOCK_REF_25M=y \
    CONFIG_STM32_USBCANBUS_PA11_PA12=y CONFIG_STM32_CMENU_CANBUS_PD0_PD1=y \
    CONFIG_CANBUS_FREQUENCY=1000000 'CONFIG_INITIAL_PINS="PD12"'
# Octopus Pro F446
gen "$KLIPPER_DIR" "$K/stm32f446xx.config" stm32f446xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32F446=y \
    CONFIG_STM32_FLASH_START_8000=y CONFIG_STM32_CLOCK_REF_12M=y \
    CONFIG_STM32_USB_PA11_PA12=y 'CONFIG_INITIAL_PINS=""'
gen "$KLIPPER_DIR" "$K/stm32f446xx-canbridge.config" stm32f446xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32F446=y \
    CONFIG_STM32_FLASH_START_8000=y CONFIG_STM32_CLOCK_REF_12M=y \
    CONFIG_STM32_USBCANBUS_PA11_PA12=y CONFIG_STM32_CMENU_CANBUS_PD0_PD1=y \
    CONFIG_CANBUS_FREQUENCY=1000000 'CONFIG_INITIAL_PINS="PD12"'
# Fysetc H36: v2 = STM32G431, CAN PA11/PA12; v1.3 = STM32G0B1, CAN PD0/PD1
gen "$KLIPPER_DIR" "$K/stm32g431xx-can.config" stm32g431xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32G431=y \
    CONFIG_STM32_FLASH_START_2000=y CONFIG_STM32_CLOCK_REF_12M=y \
    CONFIG_STM32_CANBUS_PA11_PA12=y CONFIG_CANBUS_FREQUENCY=1000000 'CONFIG_INITIAL_PINS="!PA2"'
gen "$KLIPPER_DIR" "$K/stm32g0b1xx-can.config" stm32g0b1xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32G0B1=y \
    CONFIG_STM32_FLASH_START_2000=y CONFIG_STM32_CLOCK_REF_12M=y \
    CONFIG_STM32_MMENU_CANBUS_PD0_PD1=y CONFIG_CANBUS_FREQUENCY=1000000 'CONFIG_INITIAL_PINS="!PA2"'
# BTT EBB42 (платы голов по CAN): STM32G0B1, 8 МГц, CAN PB0/PB1, загрузчик 8KiB (по документации BTT, не проверено на железе)
gen "$KLIPPER_DIR" "$K/stm32g0b1xx-ebb42-can.config" stm32g0b1xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32G0B1=y \
    CONFIG_STM32_FLASH_START_2000=y CONFIG_STM32_CLOCK_REF_8M=y \
    CONFIG_STM32_MMENU_CANBUS_PB0_PB1=y CONFIG_CANBUS_FREQUENCY=1000000 'CONFIG_INITIAL_PINS=""'

# ----------------------------------------------------------------- katapult
C=$ROOT/configs/katapult
# Octopus Pro H723: 25 МГц, USB PA11/PA12, приложение с 128KiB, PD12 на входе, двойной reset, LED PA13
gen "$KATAPULT_DIR" "$C/stm32h723xx.config" stm32h723xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32H723=y \
    CONFIG_STM32_FLASH_START_0000=y CONFIG_STM32_CLOCK_REF_25M=y CONFIG_STM32_USB_PA11_PA12=y \
    CONFIG_STM32_APP_START_20000=y 'CONFIG_INITIAL_PINS="PD12"' \
    CONFIG_ENABLE_DOUBLE_RESET=y CONFIG_ENABLE_LED=y 'CONFIG_STATUS_LED_PIN="PA13"'
# Octopus Pro F446: 12 МГц, USB PA11/PA12, приложение с 32KiB
gen "$KATAPULT_DIR" "$C/stm32f446xx.config" stm32f446xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32F446=y \
    CONFIG_STM32_FLASH_START_0000=y CONFIG_STM32_CLOCK_REF_12M=y CONFIG_STM32_USB_PA11_PA12=y \
    CONFIG_STM32_APP_START_8000=y 'CONFIG_INITIAL_PINS="PD12"' \
    CONFIG_ENABLE_DOUBLE_RESET=y CONFIG_ENABLE_LED=y 'CONFIG_STATUS_LED_PIN="PA13"'
# ALPS (как у пользователя): F072, 8 МГц, USB PA11/PA12, приложение с 8KiB, двойной reset
gen "$KATAPULT_DIR" "$C/stm32f072xb.config" stm32f072xb \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32F072=y \
    CONFIG_STM32_FLASH_START_0000=y CONFIG_STM32_CLOCK_REF_8M=y CONFIG_STM32_USB_PA11_PA12=y \
    CONFIG_STM32_APP_START_2000=y 'CONFIG_INITIAL_PINS=""' CONFIG_ENABLE_DOUBLE_RESET=y
# Fysetc H36 по гайду: CAN 1 Мбит, приложение с 8KiB, !PA2 на входе, двойной reset, LED включён
# (пин LED гайд не указывает: LED включается, пин не задан - выключаем, чтобы не гадать)
gen "$KATAPULT_DIR" "$C/stm32g431xx-can.config" stm32g431xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32G431=y \
    CONFIG_STM32_FLASH_START_0000=y CONFIG_STM32_CLOCK_REF_12M=y CONFIG_STM32_CANBUS_PA11_PA12=y \
    CONFIG_CANBUS_FREQUENCY=1000000 CONFIG_STM32_APP_START_2000=y 'CONFIG_INITIAL_PINS="!PA2"' \
    CONFIG_ENABLE_DOUBLE_RESET=y
gen "$KATAPULT_DIR" "$C/stm32g0b1xx-can.config" stm32g0b1xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32G0B1=y \
    CONFIG_STM32_FLASH_START_0000=y CONFIG_STM32_CLOCK_REF_12M=y CONFIG_STM32_MMENU_CANBUS_PD0_PD1=y \
    CONFIG_CANBUS_FREQUENCY=1000000 CONFIG_STM32_APP_START_2000=y 'CONFIG_INITIAL_PINS="!PA2"' \
    CONFIG_ENABLE_DOUBLE_RESET=y
# BTT EBB42: G0B1, 8 МГц, CAN PB0/PB1 1 Мбит, приложение с 8KiB, двойной reset (LED/пины гайд не задаёт)
gen "$KATAPULT_DIR" "$C/stm32g0b1xx-ebb42-can.config" stm32g0b1xx \
    CONFIG_LOW_LEVEL_OPTIONS=y CONFIG_MACH_STM32=y CONFIG_MACH_STM32G0B1=y \
    CONFIG_STM32_FLASH_START_0000=y CONFIG_STM32_CLOCK_REF_8M=y CONFIG_STM32_MMENU_CANBUS_PB0_PB1=y \
    CONFIG_CANBUS_FREQUENCY=1000000 CONFIG_STM32_APP_START_2000=y 'CONFIG_INITIAL_PINS=""' \
    CONFIG_ENABLE_DOUBLE_RESET=y
