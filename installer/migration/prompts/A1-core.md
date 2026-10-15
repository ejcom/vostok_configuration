Ты агент «core» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/core от py-migration (создай через git worktree; основной клон не трогай). Задача: Фундамент: ui, system (Runner), boards, state, cfgfile, cli/__main__ + can_uuid. Сначала отдельным коммитом опубликуй сигнатуры с докстрингами по CONTRACTS.md, потом реализация и юнит-тесты.
Исходники bash/Python: lib/boards.sh, tools/mcu_merge.py, tools/pin_conflicts.py, tools/can_uuid.py, heredoc правки printer.cfg и module_add_include/cfg_state/module_state из lib/vostok_config.sh, ask_yn/ask_choice/pause_hw/info/ok/warn/die/step из update_klipper_mcu.sh и lib/vostok_config.sh
Владеешь файлами только: installer/vostok/{__init__,__main__,cli,ui,system,boards,state,cfgfile}.py, installer/vostok/can_uuid.py, installer/tests/test_{boards,state,cfgfile,can_uuid,ui}.py
Особенности: Парсер .board без исполнения кода, формат и сообщения об ошибках прежние. cfgfile: один read_with_includes и один разбор секций вместо трёх; atomic_write с .bak. can_uuid проверить векторами из C-реализации (tools/can_uuid.py уже сверен). Runner — единственное место subprocess, dry-run реализован один раз. cli.py: COMMANDS = {} реестр, остальные агенты добавляют по строке.

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/core.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
