Ты агент «harness» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/harness от py-migration (создай через git worktree; основной клон не трогай). Задача: Страховочная сетка: снять эталоны (golden) со СТАРЫХ скриптов до любых правок и написать tests/run_golden.sh.
Исходники bash/Python: все *.sh в installer/ (только запуск, не правка)
Владеешь файлами только: installer/tests/** (golden/, fixtures/, run_golden.sh)
Особенности: Эталоны: --help каждого скрипта; --list-boards; --only-detect и --dry-run по матрице плат (14 из boards/, роль main) × режимы usb/bridge × heads none/v1.3/v2/ebb42 с заглушкой BYID_DIR; update_klipper_mcu.sh --list на фикстуре (BYID_DIR + мок Moonraker на http.server); configure_vostok.sh --dry-run и реальная запись на КОПИИ printer_data (PRINTER_DATA=<scratchpad>/pd) для сценариев A–H из CONFIGURATOR.md; результат gen_electronics на матрице. run_golden.sh нормализует пути/время и сравнивает. Для --dry-run install_vostok.sh отключи sudo-запросы (проверь, что dry-run не требует пароля; иначе зафиксируй в STATUS).

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/harness.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
