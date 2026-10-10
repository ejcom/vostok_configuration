# Если прошивка не удалась

🇷🇺 Русский | [🇬🇧 English](troubleshooting.en.md)

[← К оглавлению](../README.md)

Ошибка прошивки одной платы не останавливает установку: после неё предлагается меню — повторить (с того шага, на котором остановились), прошить katapult и Klipper сразу по DFU, прошить заново через DFU (katapult) и Klipper через katapult, прошить только Klipper напрямую по DFU, пропустить плату или прервать установку. Без терминала или с `-y` плата пропускается. Пропущенные платы попадают в итоговый список, а в `printer.cfg` вместо их serial/`canbus_uuid` пишется `ЗАПОЛНИТЕ`.

Если `flashtool.py` не может записать Klipper через katapult, в меню выберите «Прошить Klipper напрямую по DFU»: плата переводится в DFU, Klipper пишется по смещению приложения, katapult не затрагивается.

**RESET после DFU.** После прошивки katapult по DFU одиночный RESET может запустить прежнюю прошивку, а не katapult. Нажимайте RESET **дважды подряд, быстро** (katapult мигает светодиодом медленно). Если katapult уже на плате (например, после прошлой попытки), на запрос DFU ответьте `s`.

**Повторный запуск.** Установщик находит платы с Klipper текущей версии (по `firmware/flashed.tsv` и `devices.tsv`) и предлагает их пропустить, поэтому уже прошитые ALPS, платы голов и Octopus повторно не прошиваются. Явно: `--skip-board alps --skip-board heads`; прошить всё заново: `--reflash`.

Ручной повтор: katapult остаётся в плате, Klipper на это время остановлен.
1. `ls /dev/serial/by-id/` — плата может быть `usb-katapult_…`. Нет — дважды быстро нажмите RESET.
2. `python3 ~/katapult/scripts/flashtool.py -d /dev/serial/by-id/usb-katapult_… -f installer/firmware/<файл>.bin`
3. CAN: `ip -s -d link show can0` (`state UP`, `bitrate 1000000`, ошибок нет). На шине должно быть около 60 Ом (два терминатора по 120 Ом), состояние BUS-OFF лечится перезапуском интерфейса: `sudo ip link set can0 down type can && sudo ip link set can0 up type can bitrate 1000000`.
4. `sudo systemctl start klipper`.

Скрипты сами печатают эти подсказки при ошибках.
