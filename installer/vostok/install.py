"""Первоначальная установка K3D VOSTOK (бывший install_vostok.sh).

Конвейер этапов над одним ``InstallContext`` (опции, окружение, железо, результаты прошивки):
проверки -> пакеты -> KIAUH/Klipper/Moonraker/Fluidd/katapult -> определение железа и план -> CAN -> прошивка плат ->
конфигурация принтера -> запуск Klipper -> кнопка и тема -> итоги. Отдельный режим ``--check-can`` читает
canbus_uuid с шины CAN после установки электроники в принтер.
Флаги, переменные окружения, тексты и коды возврата - как у install_vostok.sh 1.3a.
"""
from __future__ import annotations

import contextlib
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from . import VostokError, cfgfile, hardware, ui, update
from . import configurator as cf
from .boards import Registry, registry as default_registry
from .configurator import TODO_MARK, Configurator, Hardware, HardwareDetector, installer_version
from .flashing import (Flasher, flash_with_retry, main_dfu_mode_text, main_dfu_short, make_alps_job,
                       make_head_dfu_job, make_head_katapult_job, make_head_klipper_job, make_main_job)
from .host import EnvChecks, Env, Options, Results, Software, stage_can, stage_packages, stage_preflight, wait_moonraker
from .state import DevicesFile
from .system import Runner

USAGE = """\
Использование: install_vostok.sh [опции]

  --main ПЛАТА          главная плата: id из реестра boards/ или алиас (h723, f446 - Octopus Pro; список: --list-boards),
                        иначе определит по подключённому железу/спросит
  --list-boards         показать платы реестра (id, чип, наличие моста USB-CAN, проверена ли на железе) и выйти
  --heads none|v1.3|v2|ebb42  платы голов по CAN: нет, Fysetc H36 v1.3/v2, BTT EBB42 (иначе спросит);
                        с платами голов главная плата прошивается мостом USB-CAN. --h36 - то же, прежнее имя
  --alps 0|1|2          сколько датчиков ALPS подключено по USB (иначе определит/спросит)
  --electronics ФАЙЛ    имя electronics_*.cfg из vostok_configuration (иначе предложит по железу)
  --config-source standard|user|generate|skip  откуда брать конфиг: корень main, user_configs, сгенерировать свой
                        (шаблон без плат и драйверов) или пропустить редактирование (только дописать
                        недостающие [mcu] в существующий printer.cfg); иначе спросит
  --drivers СПЕК        драйверы для --config-source generate: all=2130|2208|2209|2240|5160|5160plus или список по моторам
                        x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209 (e0/e1 при платах голов не нужны);
                        без опции спросит в диалоге, с -y возьмёт драйверы стокового конфига
  --only-detect         только определить подключённые MCU и показать план, ничего не менять
  --dry-run             показать все шаги и команды, ничего не менять
  --reference ФАЙЛ|none эталон пинов и параметров для сгенерированного конфига: по умолчанию ваш текущий
                        electronics-файл, при чистой установке стоковый main (H723); none - без эталона
  --modules ИМЕНА       дополнительные модули без вопроса: chamber_heater, all или none
  --skip-software       не ставить пакеты/KIAUH/Klipper/Moonraker/Fluidd (уже стоят)
  --skip-flash          не прошивать MCU
  --skip-config         не трогать конфиг принтера
  --skip-button         не ставить кнопку обновления в Fluidd
  --skip-theme          не ставить тему K3D VOSTOK в Fluidd и KlipperScreen
  --skip-board ПЛАТА    не прошивать плату, уже прошитую раньше: alps, alps0, alps1, main или heads
                        (можно повторять). Без этой опции установщик сам предложит пропустить платы,
                        на которых уже стоит Klipper текущей версии
  --reflash             не предлагать пропуск, прошить все платы заново
  --main-flash dfu|katapult  способ прошивки главной платы: katapult и Klipper сразу по DFU (рекомендуется,
                        по умолчанию с -y) или katapult по DFU, затем Klipper через katapult (иначе спросит)
  --heads-flash dfu|can способ прошивки плат голов: dfu - "на столе", katapult и Klipper сразу по DFU через USB,
                        24 В и CAN не нужны (по умолчанию, в том числе с -y); can - katapult по DFU, Klipper по CAN
                        (для собранного принтера, нужны 24 В и CAN-кабели). Иначе спросит
  --check-can           только прочитать canbus_uuid плат с шины CAN (нужны 24 В и CAN-кабели) и вписать
                        в devices.tsv и printer.cfg вместо вычисленных/ЗАПОЛНИТЕ; ничего не прошивает
  --upgrade             выполнить apt upgrade перед установкой
  -y, --yes             не задавать вопросов, где есть ответ по умолчанию (шаги с железом всё равно ждут Enter)
  -V, --version         показать версию установщика
  -h, --help            эта справка

Переменные окружения: PRINTER_DATA, KLIPPER_DIR, KATAPULT_DIR, KIAUH_DIR, CAN_IFACE (can0).
"""

HEADS_VALUES = ("", "none", "v1.3", "v2", "ebb42")
SKIP_BOARD_VALUES = ("alps", "alps0", "alps1", "main", "heads")

# опции со значением -> (атрибут Options.conf | Options, имя)
_CONF_VALUE_OPTS = {"--main": "main", "--heads": "heads", "--h36": "heads", "--config-source": "config_source",
                    "--drivers": "drivers", "--reference": "reference", "--modules": "modules", "--alps": "alps",
                    "--electronics": "electronics"}
_FLAGS = {"--only-detect": "only_detect", "--dry-run": "dry_run", "--skip-software": "skip_software",
          "--skip-flash": "skip_flash", "--skip-config": "skip_config", "--skip-button": "skip_button",
          "--skip-theme": "skip_theme", "--reflash": "reflash", "--check-can": "check_can", "--upgrade": "upgrade"}


def _echo(text: str) -> None:
    """Вывод в stdout без журнала (``cat <<EOF`` / ``printf`` в bash)."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ------------------------------------------------------------------ аргументы

def print_boards(reg: Registry) -> None:
    """Таблица плат реестра для --list-boards."""
    _echo("%-20s %-12s %-4s %-3s  %s" % ("id", "chip", "can", "ok", "название [роль] (алиасы)"))
    for bid in reg.list():
        b = reg.get(bid)
        al = b.field("ALIASES")
        _echo("%-20s %-12s %-4s %-3s  %s [%s]%s" % (bid, b.field("CHIP"), "bus" if reg.has_bridge(bid) else "-",
                                                    b.field("VERIFIED"), b.field("LABEL"), b.field("ROLE"),
                                                    " (%s)" % al if al else ""))
    _echo("\ncan: bus - у платы есть режим USB-CAN моста (нужен для плат голов по CAN); ok: yes - проверена на железе, "
          "no - только по документации.")
    _echo("Выбор главной платы: install_vostok.sh --main <id|алиас>.")


def parse_args(argv: Sequence[str], env: Env, reg: Registry) -> Optional[Options]:
    """Разбор опций install_vostok.sh. None - уже обработано (--help, --version, --list-boards), код 0.
    Ошибки - VostokError (неизвестная опция: справка в stderr)."""
    o = Options()
    args = list(argv)
    ui.set_options(False, False, env.log_file)
    i = 0
    while i < len(args):
        a = args[i]
        if a in _CONF_VALUE_OPTS or a in ("--skip-board", "--main-flash", "--heads-flash"):
            if i + 1 >= len(args):
                raise VostokError("%s требует аргумент" % a)
            v = args[i + 1]
            if a in _CONF_VALUE_OPTS:
                setattr(o.conf, _CONF_VALUE_OPTS[a], v)
            elif a == "--skip-board":
                o.skip_boards.append(v)
            elif a == "--main-flash":
                o.main_flash = v
            else:
                o.heads_flash = v
            i += 1
        elif a == "--list-boards":
            print_boards(reg)
            return None
        elif a in _FLAGS:
            setattr(o, _FLAGS[a], True)
        elif a in ("-y", "--yes"):
            o.yes = True
        elif a in ("-V", "--version"):
            print("VOSTOK installer %s" % installer_version(env.install_dir))
            return None
        elif a in ("-h", "--help"):
            sys.stdout.write(USAGE)
            return None
        else:
            sys.stderr.write(USAGE)
            raise VostokError("неизвестная опция: %s" % a)
        i += 1
    o.conf.only_detect = o.only_detect
    if o.conf.main:
        HardwareDetector(o.conf, env.conf_env, reg).board_from_opt(o.conf.main)
    if o.conf.heads not in HEADS_VALUES:
        raise VostokError("--heads: none, v1.3, v2 или ebb42")
    if o.conf.config_source not in ("",) + cf.CONFIG_SOURCES:
        raise VostokError("--config-source: standard, user, generate или skip")
    if o.main_flash not in ("", "dfu", "katapult"):
        raise VostokError("--main-flash: dfu или katapult")
    if o.heads_flash not in ("", "dfu", "can"):
        raise VostokError("--heads-flash: dfu или can")
    if o.conf.alps not in ("", "0", "1", "2"):
        raise VostokError("--alps: 0, 1 или 2")
    for b in o.skip_boards:
        if b not in SKIP_BOARD_VALUES:
            raise VostokError("--skip-board: alps, alps0, alps1, main или heads")
    ui.set_options(o.yes, o.dry_run, env.log_file)
    return o


# ------------------------------------------------------------------ контекст

@dataclass
class InstallContext:
    """Всё состояние установки в одном месте (вместо ~45 глобальных переменных bash)."""
    opts: Options
    env: Env
    reg: Registry
    runner: Runner
    res: Results = field(default_factory=Results)
    hw: Hardware = field(init=False)
    updater: update.Updater = field(init=False)
    checks: EnvChecks = field(init=False)
    software: Software = field(init=False)
    flasher: Flasher = field(init=False)
    cfgr: Optional[Configurator] = None
    klipper_stopped: bool = False
    finish_rc: int = 0
    argv: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.hw = Hardware(self.reg)
        self.updater = update.Updater(self.env.cfg, update.Options(assume_yes=self.opts.yes), self.runner)
        self.checks = EnvChecks(self.env, self.opts, self.runner)
        self.software = Software(self.env, self.opts, self.runner)
        self.flasher = Flasher(self.env, self.opts, self.hw, self.res, self.reg, self.runner)

    def set_hardware(self, hw: Hardware) -> None:
        """Подставить определённое железо во все объекты, которые его используют."""
        self.hw = hw
        self.flasher.hw = hw

    @property
    def dry(self) -> bool:
        return self.runner.dry_run


# ------------------------------------------------------------------ железо и план

def choose_heads_flash(ctx: InstallContext) -> None:
    """Способ прошивки плат голов: dfu («на столе») или can (в собранном принтере)."""
    hw, o, res = ctx.hw, ctx.opts, ctx.res
    if hw.heads == "none":
        res.heads_way = "dfu"
        return
    if o.heads_flash in ("dfu", "can"):
        res.heads_way = o.heads_flash
        return
    if ui.opts.yes or o.only_detect or o.dry_run or not ui.have_tty():
        res.heads_way = "dfu"
        return
    w_dfu = "На столе: katapult и Klipper по DFU через USB (24 В и CAN не нужны)"
    w_can = "Собранный принтер: katapult по DFU, Klipper по CAN (нужны 24 В и CAN-кабели)"
    ans = ui.ask_choice("Как прошивать платы голов?", w_dfu, [w_dfu, w_can])
    if ans == w_can:
        res.heads_way = "can"
        ui.warn("Для прошивки по CAN понадобятся источник 24 В (питание %s и плат голов) и подключение плат по CAN "
                "(CAN_H/CAN_L, терминаторы 120 Ом)." % hw.main_short())
    else:
        res.heads_way = "dfu"
        ui.info("Платы голов прошиваются по USB по одной. canbus_uuid будет вычислен по UID чипа; после установки "
                "электроники в принтер его нужно проверить (install_vostok.sh --check-can, нужны 24 В).")


def print_plan(ctx: InstallContext) -> None:
    hw, env, res = ctx.hw, ctx.env, ctx.res
    bridge = hw.mode == "bridge"
    ui.info("")
    ui.info("План установки:")
    ui.info("  Главная плата: %s, режим: %s" % (hw.main_label(), "мост USB-CAN (по гайду)" if bridge else "USB"))
    if hw.board.field("VERIFIED") != "yes":
        ui.warn("%s не проверена на железе: конфиги прошивки составлены по документации производителя (%s). Сверьте "
                "плату и способ входа в DFU, о проблемах сообщите разработчику." % (hw.main_label(), hw.board.field("DOC")))
    if hw.heads == "none":
        ui.info("  Платы голов: нет")
    else:
        ui.info("  Платы голов: %s, 2 шт., CAN %s 1 Мбит" % (hw.head_label(), env.can_iface))
    ui.info("  ALPS: %d" % hw.alps_count)
    ui.info("")
    ui.info("Шаги с железом:")
    n = 1
    for i in range(hw.alps_count):
        ui.info("  %d. ALPS %s: katapult через DFU, затем Klipper" % (n, hw.alps_side(i)))
        n += 1
    if hw.heads != "none":
        if res.heads_way == "dfu":
            ui.info("  %d. %s (обе, по очереди): katapult и Klipper сразу по DFU через USB (на столе, 24 В и CAN не нужны)"
                    % (n, hw.head_label()))
        else:
            ui.info("  %d. %s (обе, по очереди): katapult через DFU по USB" % (n, hw.head_label()))
        n += 1
    ui.info("  %d. %s: katapult и Klipper по DFU (%s; можно выбрать katapult по DFU + Klipper через katapult), режим: %s"
            % (n, hw.main_label(), main_dfu_short(hw), "USB-CAN мост" if bridge else "USB"))
    n += 1
    if hw.heads != "none":
        if res.heads_way == "dfu":
            ui.info("  %d. canbus_uuid плат голов и моста вычисляются по UID чипов; проверка на шине после установки в "
                    "принтер (--check-can, нужны 24 В)" % n)
        else:
            ui.info("  %d. %s (обе, по очереди): Klipper по CAN. ВНИМАНИЕ: нужны источник 24 В и подключение плат голов и "
                    "%s по CAN" % (n, hw.head_label(), hw.main_short()))
        n += 1
    ui.info("  %d. Прошивки собираются из %s и %s" % (n, env.configs_dir, ctx.reg.katapult_dir))


# ------------------------------------------------------------------ прошивка: пропуск уже прошитых плат

def alps_candidates(ctx: InstallContext) -> List[str]:
    """Serial присутствующих ALPS с Klipper: сначала в порядке прошлого devices.tsv, без занятых."""
    env, res = ctx.env, ctx.res
    seen = set(res.mcu.alps_serial)
    names = list(res.prev_keys("stm32f072xb.config"))
    for f in hardware.byid_find(env.byid_dir, "usb-Klipper_stm32f072xb_*"):
        m = re.match(r"^.*stm32f072xb_(.*)-if00$", f)
        if m:
            names.append(m.group(1))
    out: List[str] = []
    for s in names:
        if not os.path.exists("%s/usb-Klipper_stm32f072xb_%s-if00" % (env.byid_dir, s)):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def alps_try_skip(ctx: InstallContext, i: int) -> bool:
    """True - ALPS i пропущен (уже прошит), False - нужно прошивать."""
    o, hw, res, fl = ctx.opts, ctx.hw, ctx.res, ctx.flasher
    forced = o.board_skipped("alps") or o.board_skipped("alps%d" % i)
    if not forced and o.reflash:
        return False
    side = hw.alps_side(i)
    cands = alps_candidates(ctx)
    s = cands[0] if cands else ""
    if not s:
        if not forced:
            return False
        ui.warn("--skip-board: ALPS %s не найден, serial неизвестен (впишите [mcu alps...] вручную)" % side)
        res.skipped.append("ALPS %s: пропущен по --skip-board, serial неизвестен" % side)
        return True
    if not forced:
        if not fl.version_ok(s):
            return False
        if not ui.ask_yn("ALPS %s: найден %s, Klipper %s уже установлен. Пропустить прошивку?"
                         % (side, s, fl.host_version()), "y"):
            return False
    res.mcu.alps_serial[i] = s
    res.skipped.append("ALPS %s: уже прошит (%s)" % (side, s))
    ui.ok("ALPS %s: пропускаю, serial %s" % (side, s))
    fl.save_devices(quiet=True)
    return True


def heads_try_skip(ctx: InstallContext) -> bool:
    """True - платы голов уже прошиты (оба этапа пропускаются), False - прошивать."""
    o, hw, res, fl = ctx.opts, ctx.hw, ctx.res, ctx.flasher
    if hw.heads == "none":
        return False
    forced = o.board_skipped("heads")
    if not forced and o.reflash:
        return False
    keys = res.prev_keys(hw.head_cfg_name()) + ["", ""]
    u0, u1 = keys[0], keys[1]
    if not forced:
        if not (u0 and u1):
            return False
        if res.heads_way == "can":
            if not hardware.can_iface_up(ctx.env.can_iface, ctx.runner):
                return False
            uuids = [u.lower() for u in fl.can_uuids("Klipper")]
            if not (u0.lower() in uuids and u1.lower() in uuids):
                return False
            if not (fl.version_ok(u0) and fl.version_ok(u1)):
                return False
            if not ui.ask_yn("%s: обе платы на шине, Klipper %s уже установлен. Пропустить прошивку плат голов?"
                             % (hw.head_label(), fl.host_version()), "y"):
                return False
        else:
            # на столе шины нет: ориентируемся на devices.tsv и версию, записанную после прошлой прошивки
            if not (fl.version_ok(u0) and fl.version_ok(u1)):
                return False
            if not ui.ask_yn("%s: по записям прошлой установки на обеих платах Klipper %s (UUID %s, %s). Пропустить "
                             "прошивку плат голов?" % (hw.head_label(), fl.host_version(), u0, u1), "y"):
                return False
    elif not (u0 and u1):
        ui.warn("--skip-board heads: UUID плат голов неизвестны (нет devices.tsv), впишите canbus_uuid в printer.cfg вручную")
    res.mcu.head_uuid = [u0, u1]
    res.heads_skip = True
    res.skipped.append("%s: уже прошиты" % hw.head_label())
    ui.ok("платы голов: пропускаю (%s, %s)" % (u0 or "?", u1 or "?"))
    fl.save_devices(quiet=True)
    return True


def main_try_skip(ctx: InstallContext) -> bool:
    """True - главная плата пропущена (уже прошита), False - прошивать."""
    o, hw, res, fl, env = ctx.opts, ctx.hw, ctx.res, ctx.flasher, ctx.env
    forced = o.board_skipped("main")
    if not forced and o.reflash:
        return False
    label = hw.main_label()
    if hw.mode == "usb":
        s = ""
        found = hardware.byid_find(env.byid_dir, "usb-Klipper_%s_*" % hw.main)
        if found:
            m = re.match(r"^.*%s_(.*)-if00$" % re.escape(hw.main), found[0])
            s = m.group(1) if m else ""
        if not s:
            if not forced:
                return False
            ui.warn("--skip-board main: usb-Klipper_%s_* не найден, serial неизвестен (впишите [mcu] вручную)" % hw.main)
        elif not forced:
            # serial записан в devices.tsv за другой платой на этом чипе: пропуск не предлагаем
            known = next((d.cfg for d in res.prev_devices if d.key == s), "")
            if known and known != fl.cfg_name("usb"):
                return False
            if not fl.version_ok(s):
                return False
            if not ui.ask_yn("%s: найден %s, Klipper %s уже установлен. Пропустить прошивку?"
                             % (label, s, fl.host_version()), "y"):
                return False
        res.mcu.main_serial = s
    else:
        keys = res.prev_keys(fl.cfg_name("bridge"))
        u = keys[0] if keys else ""
        if not forced:
            if not u:
                return False
            if not hardware.can_iface_up(env.can_iface, ctx.runner):
                return False
            if u.lower() not in [x.lower() for x in fl.can_uuids("Klipper")]:
                return False
            if not fl.version_ok(u):
                return False
            if not ui.ask_yn("%s: мост на шине (%s), Klipper %s уже установлен. Пропустить прошивку?"
                             % (label, u, fl.host_version()), "y"):
                return False
        elif not u:
            ui.warn("--skip-board main: UUID моста неизвестен (нет devices.tsv), впишите canbus_uuid в [mcu] вручную")
        res.mcu.bridge_uuid = u
    res.skipped.append("%s: уже прошит" % label)
    ui.ok("%s: пропускаю" % label)
    fl.save_devices(quiet=True)
    return True


# ------------------------------------------------------------------ прошивка: этапы по платам

def stage_flash_alps(ctx: InstallContext) -> None:
    hw, fl = ctx.hw, ctx.flasher
    for i in range(hw.alps_count):
        ui.step("ALPS " + hw.alps_side(i))
        if alps_try_skip(ctx, i):
            continue
        _echo("Датчик ALPS подключите USB-кабелем к хосту (другие ALPS можно не отключать).\n"
              "Режим DFU: зажмите BOOT, нажмите и отпустите RESET, отпустите BOOT.")
        flash_with_retry(fl, make_alps_job(fl, i))


def stage_flash_heads_katapult(ctx: InstallContext) -> None:
    hw, fl = ctx.hw, ctx.flasher
    if hw.heads == "none" or heads_try_skip(ctx):
        return
    ui.warn("Вариант «Klipper по CAN»: на следующих этапах понадобятся источник 24 В и подключение плат голов и %s по CAN. "
            "Для прошивки на столе по USB используйте --heads-flash dfu." % hw.main_short())
    for i in range(2):
        ui.step("%s: katapult, плата %s" % (hw.head_label(), hw.head_side(i)))
        _echo("Эти шаги выполняются по одной плате:\n"
              "  - подключите к хосту USB-кабелем ТОЛЬКО %s %s (другую плату головы от USB отключите);\n"
              "  - режим DFU: %s.\n"
              "katapult на этих платах работает только по CAN, поэтому после прошивки отключите USB."
              % (hw.head_label(), hw.head_side(i), hw.head_dfu_hint()))
        if i == 0:
            ui.pinout_hint(ctx.reg, hw.head_board_id())
        if flash_with_retry(fl, make_head_katapult_job(fl, i)):
            ui.ok("katapult записан на %s %s" % (hw.head_label(), hw.head_side(i)))


def stage_flash_heads_dfu(ctx: InstallContext) -> None:
    """Платы голов «на столе»: katapult и Klipper за один сеанс DFU по USB, без 24 В и CAN."""
    hw, fl = ctx.hw, ctx.flasher
    if hw.heads == "none" or heads_try_skip(ctx):
        return
    for i in range(2):
        ui.step("%s: katapult и Klipper по DFU, плата %s" % (hw.head_label(), hw.head_side(i)))
        _echo('Прошивка "на столе": питание 24 В и CAN не нужны, достаточно USB.\n'
              "  - подключите к хосту USB-кабелем ТОЛЬКО %s %s (остальные платы голов от USB отключите);\n"
              "  - режим DFU: %s;\n"
              "  - в один сеанс запишутся katapult и Klipper, после этого USB отключите: в принтере плата работает по CAN."
              % (hw.head_label(), hw.head_side(i), hw.head_dfu_hint()))
        if i == 0:
            ui.pinout_hint(ctx.reg, hw.head_board_id())
        flash_with_retry(fl, make_head_dfu_job(fl, i))


def stage_heads_uuid_check(ctx: InstallContext) -> None:
    """Итог для режима dfu: что вычислено по UID и что нужно проверить на шине."""
    hw, res, env = ctx.hw, ctx.res, ctx.env
    if hw.heads == "none" or res.heads_way != "dfu":
        return
    ui.step("canbus_uuid плат: проверка на шине")
    unknown = not res.mcu.bridge_uuid
    ui.info("  мост (%s): %s" % (hw.main_label(), res.mcu.bridge_uuid or "не определён"))
    for i in range(2):
        u = res.mcu.head_uuid[i]
        ui.info("  %s %s: %s%s" % (hw.head_label(), hw.head_side(i), u or "не определён",
                                  " (вычислен по UID чипа)" if res.head_uuid_src[i] else ""))
        if not u:
            unknown = True
    ui.warn("canbus_uuid получены по UID чипов и на шине CAN не проверены.")
    ui.info("После установки электроники в принтер подайте 24 В и проверьте их командой: %s/install_vostok.sh --check-can"
            % env.install_dir)
    ui.info("(она найдёт платы на шине, сверит UUID и при необходимости исправит devices.tsv и printer.cfg).")
    if unknown:
        ui.warn("Где UUID не определён, в printer.cfg стоит %s: впишите canbus_uuid вручную или выполните --check-can."
                % TODO_MARK)
    if ctx.dry:
        return
    if ui.ask_yn("Сейчас подано 24 В и платы подключены по CAN: проверить UUID на шине прямо сейчас?", "n"):
        check_can_uuids(ctx)


def stage_flash_heads_klipper(ctx: InstallContext) -> None:
    """Klipper плат голов по CAN через katapult (вариант «в собранном принтере»)."""
    hw, res, env, fl = ctx.hw, ctx.res, ctx.env, ctx.flasher
    if hw.heads == "none" or res.heads_skip:
        return
    short = hw.main_short()
    if not ctx.dry and not hardware.can_iface_exists(env.can_iface, ctx.runner):
        ui.warn("интерфейса %s нет (мост USB-CAN не работает): платы голов по CAN не прошиваю" % env.can_iface)
        res.failed.append("%s: не прошиты по CAN (нет %s; прошейте %s и запустите установку снова)"
                          % (hw.head_label(), env.can_iface, short))
        return
    ui.step("UUID моста (%s)" % hw.main_label())
    ui.info("Для этого этапа подайте питание 24 В на %s и платы голов и подключите CAN-кабели по схеме из гайда." % short)
    if ctx.dry:
        ui.info("[dry-run] canbus_query.py %s -> UUID %s" % (env.can_iface, short))
        res.mcu.bridge_uuid = "000000000000"
    elif res.mcu.bridge_uuid:
        ui.info("UUID %s (мост) известен: %s" % (short, res.mcu.bridge_uuid))
    else:
        hardware.check_can_health(ctx.runner, env.can_iface)
        uuids = fl.can_uuids("Klipper")
        if len(uuids) > 1:
            ui.pause_hw("На шине несколько устройств с Klipper. Отключите CAN-кабель от обеих плат голов (должен остаться "
                        "только %s) и нажмите Enter." % short)
            uuids = fl.can_uuids("Klipper")
        if len(uuids) != 1:
            ui.warn("ожидался один UUID на шине, найдено: %d" % len(uuids))
            ui.info("Проверьте: ip -s -d link show %s; %s/bin/python %s/scripts/canbus_query.py %s"
                    % (env.can_iface, env.klippy_env, env.klipper_dir, env.can_iface))
            res.failed.append("%s: UUID моста не определён (впишите canbus_uuid в [mcu] вручную)" % short)
        else:
            res.mcu.bridge_uuid = uuids[0]
            fl.state_set(uuids[0])
            ui.ok("UUID %s (мост): %s" % (short, uuids[0]))
            fl.save_devices(quiet=True)
    for i in range(2):
        ui.step("%s %s: Klipper по CAN" % (hw.head_label(), hw.head_side(i)))
        if ctx.dry:
            ui.info("[dry-run] flashtool.py -i %s -q -> UUID, затем -u UUID -f klipper.bin" % env.can_iface)
            res.mcu.head_uuid[i] = "00000000000%d" % i
            continue
        flash_with_retry(fl, make_head_klipper_job(fl, i))
    if not ctx.dry:
        ui.pause_hw("Подключите CAN-кабелем обе платы голов вместе и нажмите Enter для проверки шины.")
        uuids = fl.can_uuids("Klipper")
        ui.info("На шине устройств с Klipper: %d (ожидается 3: %s и две платы голов)" % (len(uuids), short))
        hardware.check_can_health(ctx.runner, env.can_iface)


def stage_flash_main(ctx: InstallContext) -> None:
    hw, o, fl = ctx.hw, ctx.opts, ctx.flasher
    ui.step(hw.main_label())
    if main_try_skip(ctx):
        return
    m_dfu = "katapult и Klipper сразу по DFU (рекомендуется)"
    m_kat = "katapult по DFU, затем Klipper через katapult"
    if o.main_flash == "dfu":
        way = m_dfu
    elif o.main_flash == "katapult":
        way = m_kat
    else:
        way = ui.ask_choice("Как прошить %s?" % hw.main_label(), m_dfu, [m_dfu, m_kat])
    _echo("Подключите %s USB-кабелем к хосту (питание 24 В не нужно, достаточно USB).\n"
          "Режим DFU: %s.\n"
          "Другие платы в режиме DFU быть не должны." % (hw.main_label(), main_dfu_mode_text(hw)))
    ui.pinout_hint(ctx.reg, hw.main_board)
    if way == m_dfu:
        start = "dfuall"
        ui.info("Способ: katapult и Klipper за один сеанс DFU.")
    else:
        start = "full"
        ui.info("Способ: katapult по DFU, затем Klipper через katapult. Если katapult уже на плате (прошлая попытка), на "
                "запросе DFU ответьте s.")
    flash_with_retry(fl, make_main_job(fl, start))


def stage_flash(ctx: InstallContext) -> None:
    """Остановка Klipper, прошивка ALPS, плат голов и главной платы, карта устройств."""
    env, res, fl = ctx.env, ctx.res, ctx.flasher
    res.prev_devices = DevicesFile(env.devices_file).load() if env.devices_file.is_file() else []
    if not ctx.dry:
        ui.step("Остановка Klipper на время прошивки")
        if ctx.updater.klipper_units():
            ctx.updater.services("stop")
            ctx.klipper_stopped = True
    stage_flash_alps(ctx)
    if res.heads_way == "dfu":
        stage_flash_heads_dfu(ctx)
        stage_flash_main(ctx)
        stage_heads_uuid_check(ctx)
    else:
        stage_flash_heads_katapult(ctx)
        stage_flash_main(ctx)
        stage_flash_heads_klipper(ctx)
    ui.step("Карта устройств (%s)" % env.devices_file)
    fl.save_devices()
    if res.failed:
        ctx.finish_rc = 1


# ------------------------------------------------------------------ конфигурация, запуск, кнопка, тема, итоги

def stage_config(ctx: InstallContext) -> None:
    """Конфигурация принтера - тот же код, что у configure_vostok.sh (Configurator.stage_config)."""
    cfgr = Configurator(ctx.opts.conf, ctx.env.conf_env, ctx.reg, ctx.hw, ctx.runner)
    cfgr.mcu = ctx.res.mcu
    ctx.cfgr = cfgr
    cfgr.show_pinouts = False   # распиновка плат выводится в итоге установки (print_summary)
    cfgr.stage_config()


def stage_start_klipper(ctx: InstallContext) -> None:
    hw, res, up = ctx.hw, ctx.res, ctx.updater
    ui.step("Запуск Klipper")
    if ctx.dry:
        ui.info("[dry-run] systemctl start klipper; проверка ready и версий MCU")
        return
    if ctx.klipper_stopped:
        up.services("start")
        ctx.klipper_stopped = False
    else:
        ctx.runner.systemctl("restart", "klipper")
    if not wait_moonraker(up):
        ui.warn("Moonraker не отвечает: systemctl status moonraker")
        ctx.finish_rc = 1
        return
    if res.heads_way == "dfu" and hw.heads != "none" and not ctx.opts.check_can:
        # прошивка "на столе": CAN и 24 В нет, Klipper не соединится с платами голов, это ожидаемо
        ui.info("Платы голов прошиты на столе: Klipper подключится к ним после установки электроники в принтер и подачи 24 В.")
        if not up.wait_for_klipper():
            ui.info("Klipper не в состоянии ready: пока платы голов недоступны по CAN, это нормально.")
        return
    if not up.wait_for_klipper():
        ctx.finish_rc = 1
    if not up.verify_versions():
        ctx.finish_rc = 1


def stage_button(ctx: InstallContext) -> None:
    d = ctx.env.install_dir
    ui.step("Кнопка обновления в Fluidd")
    if ctx.dry:
        ui.info("[dry-run] %s/install_fluidd_button.sh -y" % d)
        return
    if ctx.runner.run([str(d / "install_fluidd_button.sh"), "-y"], check=False).returncode != 0:
        ui.warn("кнопку установить не удалось; позже: %s/install_fluidd_button.sh" % d)
        ctx.finish_rc = 1


def stage_theme(ctx: InstallContext) -> None:
    d = ctx.env.install_dir
    ks = os.path.isdir(os.path.join(ctx.env.home, "KlipperScreen", "styles"))
    ui.step("Тема K3D VOSTOK в Fluidd")
    if ctx.dry:
        ui.info("[dry-run] %s/install_fluidd_theme.sh -y" % d)
        if ks:
            ui.info("[dry-run] %s/install_klipperscreen_theme.sh -y" % d)
        return
    if ctx.runner.run([str(d / "install_fluidd_theme.sh"), "-y"], check=False).returncode != 0:
        ui.warn("тему установить не удалось; позже: %s/install_fluidd_theme.sh" % d)
        ctx.finish_rc = 1
    if ks:
        ui.step("Тема K3D VOSTOK в KlipperScreen")
        if ctx.runner.run([str(d / "install_klipperscreen_theme.sh"), "-y"], check=False).returncode != 0:
            ui.warn("тему KlipperScreen установить не удалось; позже: %s/install_klipperscreen_theme.sh" % d)
            ctx.finish_rc = 1


def print_summary(ctx: InstallContext) -> None:
    hw, res, env = ctx.hw, ctx.res, ctx.env
    gen_used = ctx.cfgr is not None and ctx.cfgr.gen is not None
    el_name = ctx.cfgr.el_name if ctx.cfgr else ""
    d = env.install_dir
    if gen_used:
        first = ("Вписать пины в сгенерированный %s (поиск: ЗАПОЛНИТЕ), сверить блоки с пометкой СВЕРЬТЕ, проверить "
                 "параметры моторов и драйверов, затем перезапустить Klipper." % el_name)
    else:
        first = ("Адаптировать electronics_*.cfg под вашу электронику (драйверы, термисторы, пины) и проверить printer.cfg: "
                 "все параметры описаны комментариями.")
    _echo("""
Что осталось сделать вручную:
  1. %s
  2. Проверить термисторы голов: возьмите термистор пальцами, температура должна расти у нужной головы (иначе поменяйте %s и %s местами).
  3. ALPS: добавьте [static_pwm_clock]/[load_cell_probe] (см. документацию ALPS) и выполните LOAD_CELL_CALIBRATE.
  4. Fluidd: ⏻ (вверху справа) -> mcu-update -> Start обновляет Klipper и прошивки всех MCU.
  5. Конфиг можно перенастроить отдельно, без переустановки (драйверы, другая проводка, модули вроде chamber_heater.cfg): %s/configure_vostok.sh
  6. Если у вашей платы другой кварц или смещение загрузчика, настройте configs/*.config через make menuconfig KCONFIG_CONFIG=...""" % (first, hw.head_mcu[0], hw.head_mcu[1], d))
    cf.print_pinouts(ctx.reg, hw)
    if hw.heads != "none" and res.heads_way == "dfu":
        ui.warn("Платы голов прошиты на столе, canbus_uuid получены по UID чипов и на шине НЕ проверены.")
        ui.info("  После установки электроники в принтер подайте 24 В и выполните: %s/install_vostok.sh --check-can" % d)
        ui.info("  Команда прочитает UUID с шины CAN, исправит devices.tsv и printer.cfg и перезапустит Klipper.")
        ui.info("  Вручную: остановите Klipper и выполните %s/bin/python %s/scripts/canbus_query.py %s, затем впишите "
                "canbus_uuid в [mcu], [mcu %s], [mcu %s]." % (env.klippy_env, env.klipper_dir, env.can_iface,
                                                              hw.head_mcu[0], hw.head_mcu[1]))
    if res.failed:
        ui.warn("Не прошиты платы:")
        sys.stderr.write("".join("  - %s\n" % f for f in res.failed))
        sys.stderr.flush()
        ui.info("В printer.cfg у них стоит %s вместо serial/canbus_uuid. Чтобы повторить, запустите установку снова:" % TODO_MARK)
        ui.info("  уже прошитые платы установщик предложит пропустить (или укажите --skip-board alps|main|heads).")
    if res.skipped:
        ui.info("Пропущено как уже прошитое:")
        _echo("".join("  - %s\n" % s for s in res.skipped).rstrip("\n"))
    if ctx.finish_rc == 0:
        ui.ok("установка завершена")
    else:
        ui.warn("установка завершена с замечаниями (лог: %s)" % env.log_file)


# ------------------------------------------------------------------ проверка canbus_uuid на шине (--check-can)

def write_uuid_to_cfg(ctx: InstallContext, name: str, uuid: str) -> bool:
    """Записать UUID в [mcu ...] printer.cfg (атомарно, с копией .bak-<дата>).
    False - запись не удалась (предупреждение уже выведено); отсутствие файла/секции или отказ пользователя - не ошибка."""
    cfg = ctx.env.printer_cfg_dir / "printer.cfg"
    if not cfg.is_file():
        return True
    try:
        r = cfgfile.set_canbus_uuid(cfg, name, uuid, backup=True)
    except (VostokError, OSError) as e:
        ui.warn("не удалось записать printer.cfg ([%s] canbus_uuid): %s" % (name, e))
        return False
    if r.kind == "SET":
        ui.ok("printer.cfg: [%s] canbus_uuid: %s" % (name, uuid))
    elif r.kind == "SAME":
        ui.info("printer.cfg: [%s] уже содержит %s" % (name, uuid))
    elif r.kind == "NOSECTION":
        ui.warn("в printer.cfg нет секции [%s]: впишите canbus_uuid: %s вручную" % (name, uuid))
    elif r.kind == "DIFF":
        cur = r.args[0] if r.args else ""
        if ui.ask_yn("В printer.cfg у [%s] другое значение (%s). Заменить на найденное на шине (%s)?" % (name, cur, uuid), "y"):
            try:
                cfgfile.set_canbus_uuid(cfg, name, uuid, force=True, backup=True)
            except (VostokError, OSError) as e:
                ui.warn("не удалось записать printer.cfg ([%s] canbus_uuid): %s" % (name, e))
                return False
            ui.ok("printer.cfg: [%s] canbus_uuid: %s" % (name, uuid))
        else:
            ui.warn("[%s] оставлен без изменений, проверьте вручную" % name)
    return True


def check_can_uuids(ctx: InstallContext) -> bool:
    """Читает canbus_uuid с шины, сверяет с ожидаемыми (мост, головы) и исправляет devices.tsv и printer.cfg.
    Нужны 24 В и CAN-кабели. True - все платы найдены, False - есть замечания."""
    hw, res, env, fl = ctx.hw, ctx.res, ctx.env, ctx.flasher
    cfg = env.printer_cfg_dir / "printer.cfg"
    short, iface = hw.main_short(), env.can_iface
    ui.step("canbus_uuid на шине " + iface)
    ui.info("Нужны питание 24 В и подключённые по CAN %s и платы голов." % short)
    if ctx.dry:
        ui.info("[dry-run] canbus_query.py %s, сверка с devices.tsv, запись в printer.cfg" % iface)
        return True
    if not hardware.bring_up_can(ctx.runner, iface):
        ui.warn("интерфейса %s нет: мост USB-CAN не подключён к хосту или не прошит" % iface)
        return False
    hardware.check_can_health(ctx.runner, iface)
    uuids = fl.can_uuids("Klipper")
    ui.info("На шине устройств с Klipper: %d (ожидается 3: %s и две платы голов)" % (len(uuids), short))
    for u in uuids:
        ui.info("  " + u)
    exp = [res.mcu.bridge_uuid, res.mcu.head_uuid[0], res.mcu.head_uuid[1]]
    want = ["mcu", "mcu " + hw.head_mcu[0], "mcu " + hw.head_mcu[1]]
    low = [u.lower() for u in uuids]
    # какие из найденных на шине UUID ещё не закреплены за платой
    free = [u for u in uuids if u and not (u.lower() in exp or u in exp)]
    bad = []
    for slot in range(3):
        if exp[slot] and exp[slot].lower() in low:
            ui.ok("%s: %s найден на шине" % (want[slot], exp[slot]))
        else:
            bad.append(slot)
    if bad and not free:
        for slot in bad:
            ui.warn("%s: %s - на шине не найден. Проверьте питание 24 В, CAN_H/CAN_L, терминаторы (около 60 Ом между CAN_H "
                    "и CAN_L)." % (want[slot], exp[slot] or "UUID неизвестен"))
        return False
    if bad:
        # UUID по UID не подошёл или неизвестен: определяем, какая плата какая
        if len(bad) == 1 and len(free) == 1:
            slot = bad[0]
            ui.info("%s: на шине вместо %s найден %s" % (want[slot], exp[slot] or "неизвестного UUID", free[0]))
            exp[slot] = free[0]
        else:
            if len(bad) == 3:
                ui.pause_hw("Определим мост: отключите CAN-кабель от обеих плат голов (на шине должен остаться только %s) и "
                            "нажмите Enter." % short)
                one = fl.can_uuids("Klipper")
                if len(one) == 1:
                    exp[0] = one[0]
                else:
                    ui.warn("ожидался один UUID (%s), найдено: %d" % (short, len(one)))
                    return False
                free = [u for u in uuids if u and u.lower() != exp[0].lower()]
                bad = [1, 2]
            if len(free) == 2 and len(bad) == 2:
                ui.pause_hw("Подключите к %s по CAN ТОЛЬКО левую голову %s (правую отключите) и нажмите Enter."
                            % (short, hw.head_mcu[0]))
                one = [u for u in fl.can_uuids("Klipper") if u.lower() != exp[0].lower()]
                if len(one) != 1:
                    ui.warn("ожидалась одна плата головы, найдено: %d" % len(one))
                    return False
                exp[1] = one[0]
                for u in free:
                    if u.lower() != one[0].lower():
                        exp[2] = u
                ui.info("правая голова %s: %s" % (hw.head_mcu[1], exp[2]))
                ui.pause_hw("Подключите обе платы голов вместе по CAN и нажмите Enter.")
            else:
                ui.warn("не удалось однозначно сопоставить платы (найдено свободных UUID: %d, не подтверждено: %d). Впишите "
                        "canbus_uuid в printer.cfg вручную." % (len(free), len(bad)))
                return False
    # итог: bus - истина
    res.mcu.bridge_uuid = exp[0]
    res.mcu.head_uuid = [exp[1], exp[2]]
    res.head_uuid_src = ["bus", "bus"]
    res.prev_devices = [d for d in res.prev_devices if d.role not in ("bridge", "can")]
    for u in exp:
        if u:
            fl.state_set(u)
    fl.save_devices(quiet=True)
    written = True
    for slot in range(3):
        if exp[slot] and not write_uuid_to_cfg(ctx, want[slot], exp[slot]):
            written = False
    if not cfg.is_file():
        ui.info("printer.cfg не найден: canbus_uuid записаны только в %s" % env.devices_file)
    if not written:
        ui.warn("canbus_uuid не удалось записать в printer.cfg: проверьте права и место на диске, затем повторите --check-can "
                "или впишите значения вручную")
        return False
    ui.ok("canbus_uuid подтверждены на шине")
    return True


def check_can_main(ctx: InstallContext) -> None:
    """Режим --check-can: отдельный запуск после установки электроники в принтер."""
    hw, res, env, o, reg = ctx.hw, ctx.res, ctx.env, ctx.opts, ctx.reg
    ui.step("Проверка canbus_uuid на шине CAN")
    res.prev_devices = DevicesFile(env.devices_file).load() if env.devices_file.is_file() else []
    heads = 0
    hw.mode = "bridge"
    for d in res.prev_devices:
        r = reg.by_cfg(d.cfg)
        bid = r[0] if r else ""
        if d.role == "bridge":
            res.mcu.bridge_uuid = d.key
            if bid:
                hw.set_main_board(bid)
        elif d.role == "can":
            if heads < 2:
                res.mcu.head_uuid[heads] = d.key
            heads += 1
            if bid:
                hw.heads = bid[len("h36-"):] if bid.startswith("h36-") else bid
    detector = HardwareDetector(o.conf, env.conf_env, reg, ctx.runner)
    if not hw.main_board:
        if o.conf.main:
            bid = detector.board_from_opt(o.conf.main)
        else:
            default = reg.resolve("h723") or ""
            bridge_boards = [b for b in reg.list("main") if reg.has_bridge(b)]
            bid = detector.ask_board("Главная плата:", default, bridge_boards)
        hw.set_main_board(bid)
    if not hw.heads or hw.heads == "none":
        ans = ui.ask_choice("Платы голов:", "v2", ["v1.3", "v2", "ebb42"])
        hw.heads = ans if ans in ("v1.3", "ebb42") else "v2"
    if o.conf.heads:
        hw.heads = o.conf.heads
    hw.set_head_names()
    # имена секций голов берём из printer.cfg (T0*/T1*)
    cfg = env.printer_cfg_dir / "printer.cfg"
    if cfg.is_file():
        try:
            names = [m[0][len("mcu "):] for m in cfgfile.list_mcus(cfg) if m[0].startswith("mcu ")]
        except (VostokError, OSError):
            names = []
        n0 = next((n for n in names if n.startswith("T0")), "")
        n1 = next((n for n in names if n.startswith("T1")), "")
        if n0 and n1:
            hw.head_mcu = [n0, n1]
    if not ctx.dry:
        if ctx.updater.klipper_units():
            ctx.updater.services("stop")
            ctx.klipper_stopped = True
    if not check_can_uuids(ctx):
        ctx.finish_rc = 1
    stage_start_klipper(ctx)
    if ctx.finish_rc == 0:
        ui.ok("проверка завершена")
    else:
        ui.warn("проверка завершена с замечаниями (лог: %s)" % env.log_file)


# ------------------------------------------------------------------ main

def run(ctx: InstallContext) -> int:
    """Конвейер установки; возвращает код выхода."""
    o, env = ctx.opts, ctx.env
    ui.log("=== install_vostok.sh %s: %s ===" % (installer_version(env.install_dir), " ".join(ctx.argv)))
    with contextlib.ExitStack() as stack:
        if o.check_can:
            if os.geteuid() == 0:
                ui.die("не запускайте от root; sudo спросит пароль сам")
            stack.enter_context(ctx.runner.sudo_keepalive(enabled=not o.only_detect))
            check_can_main(ctx)
            return ctx.finish_rc
        stage_preflight(env, o, ctx.runner, ctx.checks)
        stack.enter_context(ctx.runner.sudo_keepalive(enabled=not o.only_detect))

        need_flash = not o.skip_flash
        if not o.skip_software and not o.only_detect:
            stage_packages(env, o, ctx.runner)
            ctx.software.stage_software()
            ctx.checks.check_tools(need_flash, True)
        else:
            ctx.checks.check_tools(need_flash, False)

        ctx.set_hardware(HardwareDetector(o.conf, env.conf_env, ctx.reg, ctx.runner).detect())
        choose_heads_flash(ctx)
        print_plan(ctx)
        if need_flash:
            ctx.checks.check_hw_requirements(ctx.hw)
        if o.only_detect:
            return 0
        if not ctx.dry:
            if not ui.ask_yn("Продолжить с этим планом?", "y"):
                ui.info("отменено")
                return 0

        if need_flash:
            stage_can(env, o, ctx.hw, ctx.runner)
            stage_flash(ctx)
            if not o.skip_config:
                stage_config(ctx)
        else:
            ui.info("Прошивка пропущена (--skip-flash): serial/UUID для printer.cfg неизвестны, впишите [mcu ...] вручную")
        stage_start_klipper(ctx)
        if not o.skip_button:
            stage_button(ctx)
        if not o.skip_theme:
            stage_theme(ctx)
        print_summary(ctx)
        return ctx.finish_rc


def main(argv: Sequence[str]) -> int:
    """Точка входа ``python3 -m vostok install``: код возврата как у install_vostok.sh."""
    env = Env.from_environ()
    reg = default_registry()
    opts = parse_args(argv, env, reg)
    if opts is None:
        return 0
    ctx = InstallContext(opts, env, reg, Runner(), argv=list(argv))
    rc = 1
    try:
        rc = run(ctx)
    except VostokError as e:
        ui.error(str(e))
        rc = 1
    except BaseException:
        _klipper_hint(ctx)
        raise
    if rc != 0:
        _klipper_hint(ctx)
    return rc


def _klipper_hint(ctx: InstallContext) -> None:
    """Выход с ошибкой при остановленном Klipper: напомнить, как его запустить (trap cleanup в bash)."""
    if ctx.klipper_stopped:
        sys.stderr.write("Klipper остановлен. После устранения проблемы запустите установку снова или: "
                         "sudo systemctl start klipper\n")
        sys.stderr.flush()
