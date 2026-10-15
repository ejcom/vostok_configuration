# План: перевод установщика VOSTOK с bash на Python

## Context

`~/vostok_configuration/installer/` (v1.3a) на **~5 400 строк bash**: `install_vostok.sh` 1809, `lib/vostok_config.sh` 965, `update_klipper_mcu.sh` 785, `install_*.sh` ×3 (~800), `configure_vostok.sh` 200, `lib/boards.sh` 176, `tools/gen_configs.sh` 203. Плюс ~1 100 строк Python (`gen_electronics.py` 610, `mcu_merge.py`, `pin_conflicts.py`, `can_uuid.py`).
Поддерживать это трудно, а python3 установщик и так ставит на первом шаге. Цель: вынести логику в Python-пакет (только stdlib, как требует `AGENTS.md`), bash оставить тонкой загрузочной оболочкой.

## Что нашёл при проверке кода (причины переписывать)

1. **~45 глобальных переменных** в `install_vostok.sh` (`MAIN`, `MODE`, `HEADS`, `RES_*`, `FLASH_FAILED`, `BOARD_PHASE`, `BOARD_DEV`, `BOARD_START_PHASE`, `HEAD_DFU_DONE`, `HEAD_UUID_SRC`…). Из функций bash нельзя вернуть значение, поэтому результаты идут через глобалы (`FLASHED_SERIAL`, `FLASHED_UUID`, `NEW_KATAPULT_DEV`, `DFU_UID_UUID`, `TMP_ANS`-файл для ответа пользователя).
2. **Автомат повторов прошивки неявный**: `flash_board` + `BOARD_PHASE` + `dfuall|dfuk|klipper|full` + `flash_menu` в строковых кодах. `try_main`/`try_alps`/`try_head_dfu`/`try_head_klipper` повторяют одну схему.
3. **Параллельные массивы** в `update_klipper_mcu.sh`: `MCU_NAME/PATH/CHIP/SERIAL/CFG/VER/ORDER/UUID/BRIDGE` (9 штук), индексирование через `${!MCU_NAME[@]}`.
4. **Python внутри bash**: heredoc `kiauh_set_fork_repo`, 40-строчная правка `printer.cfg` в `stage_config`, `json_get` с `eval(expr)`, `py -c` в обеих темах, `can_uuids` парсит вывод утилит через `sed`.
5. **Дублирование**: цвета/`info/ok/warn/die/step`, `confirm`, разбор `VERSION`, парсинг аргументов в 5 скриптах; `read_with_includes` + `HDR` в `mcu_merge.py` и `pin_conflicts.py`; `can_manage_services` в двух местах (и с разной логикой); парсинг секций cfg в трёх местах (py, `sed`, `grep`).
6. **`gen_electronics.py`**: глобальное изменяемое состояние (`TABLE_OPTS`, `SVERIT`, `TABLE_SRC` через `global`), `main()` на 250 строк, старые значения `h723/f446` зашиты в словари рядом с реестром плат.
7. Мелкие дефекты: `flash_can` ищет в `/dev/serial/by-id` вместо `$BYID_DIR`; парсинг `ls`; `mcu_merge --set` пишет файл не атомарно и без бэкапа; `check_can_uuids` держит `rc=0`, который никогда не меняется; `set_head_names`/`HEAD_MCU` повторены в `configure_vostok.sh`; `stage_config` копирует файлы без атомарной записи.

## Целевая архитектура

Пакет `installer/vostok/` (Python ≥ 3.8: на хосте 3.9.2, Debian 11; без `match`, `from __future__ import annotations`). Запуск: `python3 -m vostok <команда>`.

```
installer/
  install_vostok.sh        # ~40 строк: проверка bash/apt, при отсутствии ставит python3 (+venv), exec python3 -m vostok install "$@"
  update_klipper_mcu.sh    # однострочная обёртка: exec python3 -m vostok update "$@"   (путь зашит в unit кнопки и в документацию)
  configure_vostok.sh, install_fluidd_button.sh,
  install_fluidd_theme.sh, install_klipperscreen_theme.sh   # такие же обёртки
  vostok/
    cli.py           # внутренняя диспетчеризация обёрток (install|update|configure|button|theme|ks-theme), argparse с теми же флагами, что и сейчас; --check-can остаётся флагом install_vostok.sh
    ui.py            # вывод/цвета/лог-файл, ask_yn, ask_choice, pause_hw; флаги --yes/--dry-run
    system.py        # Runner: run()/sudo()/capture(), dry-run, systemctl/polkit, apt, git (единственное место subprocess)
    boards.py        # dataclass Board + парсер boards/*.board (формат не меняется) + Registry (resolve, for_chip, by_cfg, cfg_path)
    state.py         # DevicesFile (devices.tsv), FlashedLog (flashed.tsv): форматы прежние
    hardware.py      # поиск by-id, lsusb/dfu-util (family, UID), состояние CAN, can_uuids (canbus_query/flashtool), мост
    firmware.py      # сборка Klipper/katapult (make), host_version, обёртки flashtool.py/dfu-util
    flashing.py      # FlashJob, стратегии прошивки, retry-меню
    host.py          # пакеты apt, KIAUH, форк Klipper, Moonraker-клиент (urllib), службы, проверки окружения
    cfgfile.py       # чтение секций/include, mcu_merge, pin_conflicts, правка printer.cfg, модули, cfg_state, атомарная запись+.bak
    electronics.py   # бывший gen_electronics.py (класс Generator вместо глобалов) + can_uuid.py
    configurator.py  # меню источника конфига, выбор electronics, драйверы, stage_config
    install.py       # InstallContext + конвейер этапов
    update.py        # бывший update_klipper_mcu.sh
    integrations.py  # кнопка Fluidd (unit, asvc, sudoers), тема Fluidd, тема KlipperScreen
  tests/             # unittest (stdlib), без pytest
```
~16 модулей. Данные не трогаем: `boards/*.board`, `templates/`, `configs/`, `fluidd-theme/`, `klipperscreen-theme/`, `mcu-update.service.in`.

### Паттерны (по делу, без лишнего)

- **Dataclass-модели вместо глобалов/параллельных массивов**: `Board`, `Mcu` (name, path, chip, serial, cfg, version, order, uuid, is_bridge), `Device` (key, cfg, role), `Options` (из argparse), `Hardware` (main_board, heads, alps_count, mode), `Results` (serial/uuid плат, failed, skipped), всё собирается в один `InstallContext`.
- **Adapter/Facade `Runner`** (`system.py`): единственная точка запуска команд, знает `dry_run`, пишет в лог. Благодаря этому тесты подменяют его заглушкой, а `[dry-run]` реализован один раз (сейчас — в десятках `if [[ $DRY_RUN -eq 1 ]]`).
- **Strategy для способов прошивки** (`flashing.py`): функции/небольшие классы `DfuAll` (katapult+Klipper за сеанс DFU), `KatapultThenKlipper`, `DfuKlipperOnly`, `CanKlipper`; общий интерфейс `run(job) -> FlashResult`, ошибки через `FlashError`, а не коды возврата. Один `flash_with_retry(job, menu)` заменяет `flash_board`+`flash_menu`+`BOARD_PHASE`.
- **Pipeline этапов** (`install.py`): список обычных функций `stage_preflight, stage_packages, stage_software, stage_can, stage_flash, stage_config, stage_start_klipper, stage_button, stage_theme`, каждая принимает `ctx`. Без классов-этапов и реестров плагинов.
- **Repository** только для двух tsv-файлов и реестра плат (чтение/запись в одном месте).
- **Исключения**: `UserAbort`, `FlashError`, `InstallError` вместо `die` (exit) посреди кода; обработка в `cli.main()`.

### Защита от чрезмерной декомпозиции
- Не более ~16 модулей; один класс = одна ответственность, но функции остаются функциями.
- ABC только если реально две реализации; DI-контейнеров, фабрик, плагинов нет.
- Вывод/ввод пользователя через модуль `ui`, а не объект-интерфейс.
- Логика `electronics.py` разбивается на 4–5 функций/небольшой класс `Generator`, но не на пакет.

### Что остаётся в bash и почему
- Только загрузчик `install_vostok.sh` (python3 может быть не установлен) и обёртки для обратной совместимости путей (unit `mcu-update.service`, документация, привычки пользователей).
- Внешние программы остаются внешними: `make` (Kconfig/сборка), `dfu-util`, `katapult/scripts/flashtool.py`, `canbus_query.py`, `kiauh.sh`, `git`, `apt-get`, `systemctl`.
- `tools/gen_configs.sh` → `tools/gen_configs.py` на последнем шаге (низкий приоритет, это dev-инструмент).

## Механизм запуска не меняется (решение пользователя)
- Публичные команды остаются ровно прежними: `./install_vostok.sh`, `./update_klipper_mcu.sh`, `./configure_vostok.sh`, `./install_fluidd_button.sh`, `./install_fluidd_theme.sh`, `./install_klipperscreen_theme.sh` — те же имена, пути, флаги, переменные окружения, коды возврата. Документация и привычки пользователей не меняются.
- `python3 -m vostok …` — внутренняя деталь обёрток, в документации и справке (`--help`) не упоминается; `--help` каждого скрипта выводит тот же текст.
- Каждый `.sh` остаётся исполняемым файлом на тех же местах и сам определяет `INSTALL_DIR` (через `readlink -f`), поэтому запуск по абсолютному пути, из systemd (`mcu-update.service`), из Fluidd-кнопки и по symlink работает как сейчас.
- Новых подкоманд и новых пользовательских флагов в ходе переноса не добавляем.
- `source`-контракт (`source update_klipper_mcu.sh` в тестах/других скриптах) после этапа 6 отпадает: внутренние `lib/*.sh` удаляются, внешних потребителей у них нет (проверить `grep` перед удалением).

## Требования совместимости (не ломать)
- Все флаги CLI и их смысл, переменные окружения (`PRINTER_DATA`, `BYID_DIR`, `KLIPPER_DIR`, `CONFIGS_DIR`, `DEVICES_FILE`, `VOSTOK_CFG_LOCAL`, `KERNEL_CONFIG`…), коды возврата.
- Форматы `devices.tsv`, `flashed.tsv`, `.board`, лог-файлы, тексты сообщений на русском.
- Кнопка Fluidd работает без терминала и без sudo-пароля: логика `--git-update`, polkit/`sudo -n` переносится 1:1.
- Установка с нуля, когда python3 ещё нет: проверено загрузчиком.
- Реальный `~/printer_data`, реальная прошивка и `install_vostok.sh` без `--dry-run` в тестах не запускаются (правило пользователя).

## Этапы (каждый заканчивается рабочим состоянием, отдельный коммит)

0. **Страховочная сетка.** `tests/`: golden-вывод старых скриптов — `--dry-run`/`--only-detect`/`--list-boards` для каждой платы и режима (с `BYID_DIR`-заглушкой), `update_klipper_mcu.sh --list` на фикстуре, `configure_vostok.sh --dry-run` на копии `printer_data`, регрессия сценариев A–H конфигуратора. Сохранить эталоны в `tests/golden/`.
1. **Основа + листовые утилиты.** `ui`, `system`, `boards`, `state`, `cfgfile` (слить `mcu_merge` + `pin_conflicts` + heredoc правки `printer.cfg` + `module_add_include` + `cfg_state`), `electronics/can_uuid`. Bash пока вызывает их через `python3 -m vostok …` (strangler): убирает все heredoc-вставки и `sed`-парсинг. Юнит-тесты на парсер cfg, `can_uuid` (вектор из C-реализации), tsv.
2. **`update.py`** (замена `update_klipper_mcu.sh`): `Mcu`-dataclass, Moonraker через `urllib`, `flash_can`, порядок прошивки, проверка версий. Это самая простая крупная часть и то, что запускает кнопка; проверка `--list` на живой системе (read-only).
3. **`integrations.py`**: кнопка Fluidd и обе темы (в основном уже JSON/conf-правка на Python внутри bash). Сохранить `--uninstall`, `--dry-run`, маркеры «создано нами».
4. **Конфигуратор**: `configurator.py` + `electronics.py` (рефакторинг `gen_electronics.py` в `Generator`, без глобалов; удалить зашитые `BOARD_NAMES/BOARD_FILE` в пользу реестра). Автономный `configure` и `stage_config` используют один код.
5. **Поток установки**: `host.py` (окружение, пакеты, KIAUH, форк, CAN-интерфейс), `hardware.py`, `firmware.py`, `flashing.py` (стратегии + retry), `install.py` (контекст + конвейер), `--check-can`. Самая рискованная часть: переносить по этапам, после каждого сверять `--dry-run` с golden.
6. **Уборка.** Заменить скрипты обёртками, `tools/gen_configs.sh → .py`, удалить `lib/*.sh`, обновить `AGENTS.md`, `docs/*`, `CONFIGURATOR*.md`, `CHANGELOG*` (ru/en), `VERSION` → 1.4, память проекта (`vostok-install-script.md`).

## Разбивка по агентам

Оркестратор (основная сессия) ставит задачи, принимает ветки, сводит и запускает регрессию; агенты работают в изолированных git worktree от ветки `add-installer` (клон `~/vostok_configuration`), каждый в своей ветке `py/<имя>`. Агенты ничего не пушат и не трогают `~/printer_data`, `~/klipper_mcu`, железо.

### Состав

| # | Агент | Тип | Этап | Владеет файлами (только они) | Зависит от |
|---|---|---|---|---|---|
| A0 | **harness** | general-purpose | 0 | `tests/` (golden, фикстуры `BYID_DIR`, копия `printer_data`, `run_golden.sh`) | — |
| A1 | **core** | general-purpose | 1 | `vostok/{ui,system,boards,state,cfgfile,cli}.py`, `vostok/__main__.py`, `tests/test_{boards,state,cfgfile}.py`; `electronics.py`-часть `can_uuid` | A0 |
| A2 | **update** | general-purpose | 2 | `vostok/{update,firmware,hardware}.py`, обёртка `update_klipper_mcu.sh`, тесты | A1 |
| A3 | **integrations** | general-purpose | 3 | `vostok/integrations.py`, обёртки `install_fluidd_*.sh`, `install_klipperscreen_theme.sh`, тесты | A1 |
| A4 | **configurator** | general-purpose | 4 | `vostok/{configurator,electronics}.py`, обёртка `configure_vostok.sh`, тесты | A1 |
| A5 | **install-flow** | general-purpose | 5 | `vostok/{install,host,flashing}.py`, расширения `hardware.py`/`firmware.py` (после слияния A2), обёртка `install_vostok.sh` (загрузчик) | A1, A2, A3, A4 |
| A6 | **cleanup-docs** | general-purpose | 6 | `tools/gen_configs.py`, удаление `lib/*.sh`, `docs/*`, `CONFIGURATOR*`, `CHANGELOG*`, `VERSION`, `AGENTS.md` | A5 |
| R | **reviewer** (Explore + `/code-review`) | read-only | после каждой волны | ничего не правит, отчёт | предыдущая волна |

Отдельный агент на «перенос bash-тестов» не нужен: A0 делает сетку, остальные добавляют тесты к своему коду. Дробить A5 не нужно до начала работы; если он окажется слишком большим, делить по шву `host.py` (A5a: окружение/пакеты/KIAUH/CAN) и `flashing.py`+`install.py` (A5b).

### Волны и параллелизм

```
Волна 0:  A0                      (последовательно, ~небольшой)
Волна 1:  A1                      (последовательно: фундамент и контракты модулей)
Волна 2:  A2 ‖ A3 ‖ A4            (параллельно, пересечений по файлам нет)
Волна 3:  A5                      (после слияния волны 2)
Волна 4:  A6 → R (итоговое ревью)
Ревью R: после волн 0–1, 2, 3, 4
```
Между волнами оркестратор: сливает ветки (`--no-ff`, порядок A2→A3→A4), гоняет `tests/run_golden.sh` + `unittest`, при расхождении возвращает задачу тому же агенту (SendMessage), а не запускает нового.

### Контракты между агентами (фиксирует A1, остальные не меняют без согласования)
- `ui`: `info/ok/warn/step`, `ask_yn(q, default)`, `ask_choice(q, default, options)`, `pause_hw(msg, allow_skip)`, `set_options(yes, dry_run, log_file)`; исключение `UserAbort`.
- `system.Runner`: `run(cmd, sudo=False, check=True, capture=False, tee=False) -> CompletedProcess`; единственное место с `subprocess`, учитывает dry-run.
- `boards`: `Board` (поля `.board` как атрибуты), `registry().resolve(name)`, `.list(role)`, `.for_chip()`, `.by_cfg()`, `.cfg_path(id, kind)`, `.has_bridge(id)`.
- `state`: `DevicesFile(path).load()/save()/lookup(key)`, `FlashedLog(path).get(key)/set(key, ver)`.
- `cfgfile`: `read_with_includes`, `sections`, `merge_mcus`, `set_canbus_uuid`, `pin_conflicts`, `cfg_state`, `rewrite_printer_cfg`, `atomic_write(path, text, backup=True)`.
- Исключения: `VostokError` (база; сообщение показывается пользователем, `exit 1`), `FlashError(VostokError)`.
- `cli.py`: реестр `COMMANDS = {"update": update.main, …}`; каждый агент добавляет только свою строку.

### Общие правила для всех агентов (вставляются в промпт)
1. Читать `AGENTS.md`, `installer/docs/*`, этот план; сохранить поведение 1:1, golden не править без письменного обоснования оркестратору.
2. Только stdlib, Python 3.8-совместимо; сообщения и комментарии на русском, стиль соседнего кода.
3. Никаких реальных прошивок/`sudo`/записи в `~/printer_data`; тесты на копиях в scratchpad (`PRINTER_DATA=…`, `BYID_DIR=…`), внешние команды через заглушки Runner.
4. Менять только файлы из своей колонки «Владеет»; нужен чужой файл — отчитаться оркестратору.
5. Коммиты маленькими шагами в своей ветке (русские сообщения, автор по настройке репозитория), без push.
6. Итог — отчёт: что перенесено (функция bash → функция Python), что намеренно изменено, результаты `unittest` и golden-diff, открытые вопросы.

### Definition of Done агента
- `python3 -m unittest discover installer/tests` зелёный; `tests/run_golden.sh` без расхождений для затронутых скриптов.
- Старая bash-реализация заменена обёрткой, `--help` и коды возврата идентичны.
- В коде нет TODO без причины, нет дублирования с `core`.

### Промпты (шаблон; оркестратор подставляет строку из таблицы)
> Ты агент «<имя>» проекта переноса установщика VOSTOK на Python. Прочитай `~/.claude/plans/declarative-roaming-coral.md` (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила»). Задача: <этап из плана>. Исходники bash: <файлы>. Работай в worktree, владей только <файлы>. Сверяй результат с `tests/golden`. По завершении верни отчёт по пункту 6 правил.

Специфика:
- **A0 harness**: снять эталоны со старых скриптов (до любых правок): `--help`, `--list-boards`, `--only-detect`/`--dry-run` по матрице плат×режимов, `update --list` (фикстура `BYID_DIR` + мок Moonraker на `http.server`), `configure --dry-run` и реальная запись на копии `printer_data` для сценариев A–H; `run_golden.sh` сравнивает вывод с нормализацией путей/времени.
- **A1 core**: сначала опубликовать сигнатуры (заглушки с докстрингами) отдельным коммитом, чтобы оркестратор мог запустить волну 2 до полного завершения реализации при необходимости; затем реализация и тесты.
- **A2 update**: покрыть режимы `--git-update`, без tty, CAN-мост, порядок прошивки (1→2→3); заменить `json_get(eval)` на разбор JSON.
- **A3 integrations**: сохранить маркеры `VOSTOK-THEME`, `--force/--uninstall/--no-activate/--logo-copy`, поведение `-y` с чужой темой.
- **A4 configurator**: побайтовое совпадение выходных `electronics_*.cfg` и `printer.cfg` со старой версией на всей матрице; убрать глобалы `TABLE_OPTS/SVERIT/TABLE_SRC`; зашитые `h723/f446` — в реестр.
- **A5 install-flow**: `FlashJob` + стратегии вместо `BOARD_PHASE`; все пути меню (`retry/dfu/dfuall/dfuk/skip/abort`) покрыть тестами с поддельным `ui` и `Runner`; загрузчик `install_vostok.sh` проверить в контейнере без python3.
- **A6 cleanup-docs**: `grep` на использование `lib/*.sh` перед удалением; обновить `AGENTS.md`, документацию, CHANGELOG ru/en, `VERSION` → 1.4.
- **R reviewer**: сверка «функция bash → Python» по списку, поиск потерянных ветвей (особенно `--skip-board`, `--reflash`, `-y` без tty, `--check-can`), проверка правил совместимости.

## Выполнение в несколько сессий

Субагенты и контекст между сессиями не сохраняются, поэтому всё состояние живёт в репозитории и памяти, а не в разговоре.

**Сессия 0 (первая после одобрения), подготовка, ничего не переписывается:**
1. Ветка `py-migration` от `add-installer`; каталог `installer/migration/` (временный, удаляется в A6):
   - `PLAN.md`: копия этого плана (источник истины, `~/.claude/plans/` может пропасть);
   - `STATUS.md`: таблица «агент / ветка / статус (todo|in-progress|review|merged) / последний коммит / открытые вопросы / дата»;
   - `CONTRACTS.md`: сигнатуры модулей (из раздела «Контракты»), обновляет только оркестратор;
   - `MAP.md`: таблица соответствия «функция bash → модуль.функция Python» с колонкой статуса; заполняется заранее по текущему коду (это же чек-лист для ревьюера и защита от потерянных ветвей);
   - `prompts/A0…A6.md, R.md`: готовые промпты агентов (шаблон + специфика), чтобы любую сессию можно было продолжить одной командой;
   - `reports/<агент>.md`: итоговый отчёт каждого агента (пишет сам агент).
2. Запись в память проекта (`vostok-install-script.md` и `MEMORY.md`): «идёт перенос на Python, прогресс см. `installer/migration/STATUS.md`, ветка `py-migration`».

**Протокол начала любой сессии:** прочитать `STATUS.md` и `MAP.md` → `git log --oneline py-migration` → найти первую незавершённую волну → запустить агентов по `prompts/*.md` → после каждого агента обновить `STATUS.md`/`MAP.md` и закоммитить.

**Протокол конца сессии:** нет незакоммиченных изменений; агент в `in-progress` либо доведён до коммита-контрольной точки, либо в `STATUS.md` записано, что сделано и с чего продолжить; память обновлена.

**Границы сессий (рекомендуемые, каждая заканчивается зелёными тестами и merge в `py-migration`):**
| Сессия | Содержание |
|---|---|
| S1 | подготовка (Сессия 0) + A0 harness + R |
| S2 | A1 core + R |
| S3 | волна 2: A2 ‖ A3 ‖ A4 + слияние + R |
| S4 | A5 install-flow (при необходимости A5a/A5b в разных сессиях) |
| S5 | A6 cleanup-docs + итоговый R + сводка пользователю |
Допустимо сжимать/растягивать (например, S3 в две сессии: A2+A3, затем A4), если контекст или время закончились; внутри агента контрольные точки — коммиты после каждого перенесённого блока из `MAP.md`.

**Правила для устойчивости:**
- Один агент = одна ветка `py/<имя>` = один отчёт; незавершённого агента продолжать через `SendMessage` в той же сессии, в новой сессии — запуск заново с `prompts/<имя>.md` + «продолжить с контрольной точки из `STATUS.md`».
- Никаких решений только «в голове» сессии: изменение контракта или отклонение от 1:1 записывается в `CONTRACTS.md`/`STATUS.md` (раздел «Решения»).
- Пока перенос идёт, старые bash-скрипты остаются рабочими в `add-installer`; на `py-migration` каждая обёртка заменяется только после зелёного golden-diff, поэтому ветка в любой момент собираемая и запускаемая.
- Слияние `py-migration` → `add-installer` только после S5 и явного одобрения пользователя; push и PR делает сам пользователь (как раньше).

## Проверка
- `python3 -m unittest discover installer/tests` (stdlib).
- Сравнение вывода `--dry-run`/`--only-detect`/`--list-boards`/`--list` до и после на всех 14 платах и на режимах usb/bridge × heads none/v1.3/v2/ebb42.
- `tools/gen_configs --check` и `--build` — без расхождений (конфиги сборки не меняются).
- Конфигуратор на **копии** каталога (`PRINTER_DATA=<scratchpad>/pd`): генерация, merge, модули, pin_conflicts — побайтовое совпадение результатов со старой версией.
- `update --list` на этом хосте (чтение). Обёртка кнопки: `systemd-analyze verify` и запуск без tty с `-y --no-flash`.
- Загрузчик: в контейнере/чистой Debian 11 без python3 — `install_vostok.sh --only-detect`.
- Реальную прошивку плат делает только пользователь, на железе: до этого F446/H36/EBB42 остаются «не проверено», как и сейчас.

## Критичные файлы
`installer/install_vostok.sh`, `installer/update_klipper_mcu.sh`, `installer/lib/vostok_config.sh`, `installer/lib/boards.sh`, `installer/configure_vostok.sh`, `installer/install_fluidd_button.sh`, `installer/install_fluidd_theme.sh`, `installer/install_klipperscreen_theme.sh`, `installer/tools/{gen_electronics,mcu_merge,pin_conflicts,can_uuid}.py`, `installer/tools/gen_configs.sh`, `installer/mcu-update.service.in`, `AGENTS.md`.
