Ты агент «configurator» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/configurator от py-migration (создай через git worktree; основной клон не трогай). Задача: Перенести настройку конфига (lib/vostok_config.sh: детект железа/меню/генерация/модули, configure_vostok.sh, gen_electronics.py) в vostok/configurator.py и vostok/electronics.py + обёртка configure_vostok.sh.
Исходники bash/Python: lib/vostok_config.sh, configure_vostok.sh, tools/gen_electronics.py
Владеешь файлами только: installer/vostok/{configurator,electronics}.py, installer/configure_vostok.sh, installer/tests/test_{configurator,electronics}.py
Особенности: Побайтовое совпадение выходных electronics_*.cfg и printer.cfg со старой версией на всей матрице (golden от A0). Убрать глобалы TABLE_OPTS/SVERIT/TABLE_SRC (класс Generator), разбить main() на 250 строк, зашитые BOARD_NAMES/BOARD_FILE h723/f446 взять из реестра плат. Функции detect_hardware и пр., общие с install, оформить так, чтобы A5 их переиспользовал (положить в configurator.py или hardware.py по CONTRACTS.md). Правило пользователя: свой electronics-конфиг всегда основа; cfg_state none|blank|foreign|vostok.

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/configurator.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
