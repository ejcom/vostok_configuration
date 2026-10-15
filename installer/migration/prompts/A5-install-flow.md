Ты агент «install-flow» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/install-flow от py-migration (создай через git worktree; основной клон не трогай). Задача: Перенести install_vostok.sh: vostok/{install,host,flashing}.py, расширения hardware.py/firmware.py; install_vostok.sh становится загрузчиком (ставит python3 при отсутствии, exec python3 -m vostok).
Исходники bash/Python: install_vostok.sh
Владеешь файлами только: installer/vostok/{install,host,flashing}.py, расширения hardware.py/firmware.py, installer/install_vostok.sh, installer/tests/test_{install,flashing,host}.py
Особенности: InstallContext (Options/Hardware/Results) вместо ~45 глобалов; FlashJob + стратегии (DfuAll, KatapultThenKlipper, DfuKlipperOnly, CanKlipper), исключения вместо кодов возврата, один flash_with_retry вместо flash_board+flash_menu+BOARD_PHASE. Покрыть тестами все пути меню (retry/dfu/dfuall/dfuk/skip/abort), --skip-board, --reflash, автопропуск по версии, -y без tty, --check-can, --heads-flash dfu|can, --main-flash dfu|katapult. Загрузчик: поведение без python3 проверить в контейнере/по заглушке PATH. Если слишком большой — делить A5a (host.py) и A5b (flashing.py+install.py), запись в STATUS.

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/install-flow.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
