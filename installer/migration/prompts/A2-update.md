Ты агент «update» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/update от py-migration (создай через git worktree; основной клон не трогай). Задача: Перенести update_klipper_mcu.sh на vostok/update.py (+ firmware.py, hardware.py: сборка, host_version, by-id, CAN-состояние, flashtool-обёртки), обёртка update_klipper_mcu.sh.
Исходники bash/Python: update_klipper_mcu.sh
Владеешь файлами только: installer/vostok/{update,firmware,hardware}.py, installer/update_klipper_mcu.sh, installer/tests/test_update.py
Особенности: Mcu — dataclass вместо 9 параллельных массивов. Moonraker через urllib, json_get(eval) убрать. Режимы: --list, --no-update, --no-flash, --force-flash, --git-update (авто при отсутствии tty), --ignore-moonraker, -y. Кнопка Fluidd запускает без tty: polkit/sudo -n 1:1. Исправить flash_can: брать BYID_DIR вместо жёсткого /dev/serial/by-id. Порядок прошивки 1→2→3 и мост последним. Обёртка сама определяет INSTALL_DIR через readlink -f; --help идентичен.

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/update.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
