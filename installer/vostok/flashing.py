"""Прошивка плат установщика: примитивы (DFU, katapult, flashtool), стратегии, задания и один цикл повтора.

Вместо flash_board + flash_menu + BOARD_PHASE из bash:
  * ``Flasher`` - примитивы (wait_dfu, enter_katapult, flash_klipper_via_katapult, dfu_flash_klipper ...),
    неудача - ``FlashError`` (текст предупреждения, если он ещё не напечатан);
  * стратегии ``DfuAll``, ``KatapultThenKlipper``, ``DfuKlipperOnly``, ``CanKlipper`` - способы прошить одну плату;
  * ``FlashJob`` - плата + выбор стратегии по фазе (full|klipper|dfuall|dfuk) + запись результата;
  * ``flash_with_retry`` - цикл «попытка -> меню (retry|dfu|dfuall|dfuk|skip|abort) -> следующая фаза».
Тексты, порядок вывода и вызовы внешних программ - как в install_vostok.sh 1.3a.
"""
from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from . import FlashError, UserAbort, VostokError, can_uuid, firmware, hardware, ui
from .boards import Registry
from .configurator import Hardware
from .host import Env, Options, Results
from .state import Device, DevicesFile, FlashedLog
from .system import Runner

DEFAULT_DFU_HOW = "джампер BOOT0 или кнопка BOOT, затем RESET"
SKIP_ANSWERS = "sSыЫ"      # ответ на запрос DFU: пропустить (плата уже в katapult)

MENU_RETRY = "Повторить"
MENU_DFU_ALL = "Прошить katapult и Klipper сразу по DFU"
MENU_DFU = "Прошить заново через DFU (katapult), Klipper через katapult"
MENU_DFU_K = "Прошить Klipper напрямую по DFU (без katapult)"
MENU_SKIP = "Пропустить эту плату"
MENU_ABORT = "Прервать установку"
MENU_DFU_K_HEADS = "Прошить только Klipper по DFU (katapult уже записан)"


@dataclass
class Outcome:
    """Результат успешной прошивки: serial USB-устройства и/или вычисленный canbus_uuid."""
    serial: str = ""
    uuid: str = ""


@dataclass
class Target:
    """Что и как прошивается (одна плата)."""
    label: str
    chip: str
    family: str
    klipper_cfg: Path
    katapult_cfg: Optional[Path] = None
    kat_mode: str = "guide"          # make (ALPS: make flash) | guide (команда из гайда, mass-erase)
    bridge: int = 0                  # 0 обычная USB-плата, 1 мост USB-CAN, 2 только CAN (платы голов)
    enter_hint: str = ""             # подсказка по входу в DFU для katapult-шага
    after_hint: str = ""             # что сделать после прошивки katapult по DFU
    dfu_how: str = DEFAULT_DFU_HOW   # вход в DFU в запросе dfu_flash_klipper


# ------------------------------------------------------------------ тексты входа в DFU главной платы

def main_dfu_std(hw: Hardware) -> bool:
    """Octopus (джампер BOOT0, подсказка начинается с «поставьте джампер BOOT0 и нажмите RESET») - прежние формулировки."""
    b = hw.board
    return b.field("DFU_HOW") == "jumper" and b.field("DFU_HINT").startswith("поставьте джампер BOOT0 и нажмите RESET")


def main_dfu_short(hw: Hardware) -> str:
    """Кратко, для плана."""
    if main_dfu_std(hw):
        return "джампер BOOT0"
    if hw.board.field("DFU_HOW") == "jumper":
        return "джампер или перемычка BOOT, затем RESET"
    return "кнопки BOOT и RESET"


def main_dfu_enter_text(hw: Hardware) -> str:
    """Запрос перед прошивкой katapult."""
    if main_dfu_std(hw):
        return "поставьте джампер BOOT0 и нажмите RESET (после прошивки katapult джампер нужно будет снять)"
    return hw.board.field("DFU_HINT")


def main_dfu_after_text(hw: Hardware) -> str:
    """После прошивки katapult по DFU."""
    label = hw.main_label()
    twice = "ДВАЖДЫ быстро нажмите RESET на %s (одиночный RESET после прошивки по DFU может не запустить katapult)." % label
    if main_dfu_std(hw):
        return ("Снимите джампер BOOT0 с %s и ДВАЖДЫ быстро нажмите RESET (одиночный RESET после прошивки по DFU может "
                "не запустить katapult)." % label)
    if hw.board.field("DFU_HOW") == "jumper":
        return "Верните джампер или перемычку входа в DFU в исходное положение и " + twice
    return "Отпустите кнопку входа в DFU и " + twice


def main_dfu_mode_text(hw: Hardware) -> str:
    """Строка «Режим DFU: ...» перед прошивкой."""
    if main_dfu_std(hw):
        return "установите джампер на BOOT0, нажмите RESET (кнопка на плате)"
    return hw.board.field("DFU_HINT")


def main_dfu_klipper_how(hw: Hardware) -> str:
    """Вход в DFU в запросе dfu_flash_klipper."""
    if main_dfu_std(hw):
        return DEFAULT_DFU_HOW
    return hw.board.field("DFU_HINT")


# ------------------------------------------------------------------ примитивы

class Flasher:
    """Операции прошивки над одним набором настроек. Все ошибки - FlashError (после предупреждения пользователю)."""

    def __init__(self, env: Env, opts: Options, hw: Hardware, res: Results, reg: Registry,
                 runner: Optional[Runner] = None) -> None:
        self.env, self.opts, self.hw, self.res, self.reg = env, opts, hw, res, reg
        self.runner = runner or Runner()
        self.built: dict = {}
        self.flashed = FlashedLog(env.cfg.state_file)

    # --- мелочи

    @property
    def dry(self) -> bool:
        return self.runner.dry_run

    def host_version(self) -> str:
        return firmware.host_version_or_empty(self.env.klipper_dir, self.runner)

    def state_set(self, key: str, version: Optional[str] = None) -> None:
        """Записать в журнал прошивок «ключ -> версия хоста» (в dry-run ничего не пишет)."""
        if self.dry:
            return
        self.flashed.set(key, self.host_version() if version is None else version)

    def version_ok(self, key: str) -> bool:
        """На плате с этим ключом стоит Klipper текущей версии хоста (по flashed.tsv)."""
        v = self.flashed.get(key)
        return bool(v) and firmware.norm_version(v) == firmware.norm_version(self.host_version())

    def katapult_devices(self, chip: str) -> List[str]:
        return hardware.byid_find(self.env.byid_dir, "usb-katapult_%s_*" % chip)

    def pick_katapult(self, label: str, devs: List[str]) -> str:
        """Выбор из нескольких найденных katapult-устройств (одно - берём сразу)."""
        if len(devs) <= 1:
            return devs[0] if devs else ""
        names = [os.path.basename(p) for p in devs]
        p = ui.ask_choice("%s: в katapult сразу несколько плат, какая нужна?" % label, names[0], names)
        return "%s/%s" % (self.env.byid_dir, p)

    def wait_new_katapult(self, chip: str, secs: int, before: List[str]) -> Optional[str]:
        """Ждать нового usb-katapult_<чип>_* (которого не было в списке «до»)."""
        for _ in range(secs * 2):
            for f in self.katapult_devices(chip):
                if f not in before:
                    return f
            time.sleep(0.5)
        return None

    def build_katapult_safe(self, cfg) -> str:
        """Сборка katapult; ошибка сборки - сообщение и FlashError (в bash: подоболочка + warn)."""
        try:
            return firmware.build_katapult(cfg, katapult_dir=self.env.katapult_dir, build_dir=self.env.cfg.build_dir,
                                           runner=self.runner)
        except VostokError as e:
            ui.error(str(e))
            ui.warn("сборка katapult (%s) не удалась" % firmware.katapult_key(cfg))
            raise FlashError()

    def build_fw_safe(self, cfg, chip: str) -> str:
        """Сборка прошивки Klipper без выхода из установки при ошибке. В dry-run - пустая строка (сборки нет)."""
        if self.dry:
            return ""
        cfg = str(cfg)
        try:
            dest = firmware.build_firmware(cfg, chip, klipper_dir=self.env.klipper_dir, build_dir=self.env.cfg.build_dir,
                                           firmware_dir=self.env.cfg.firmware_dir, built=self.built, runner=self.runner)
        except VostokError as e:
            ui.error(str(e))
            ui.warn("сборка прошивки Klipper (%s) не удалась" % os.path.basename(cfg))
            raise FlashError()
        if not os.path.isfile(dest):
            ui.warn("нет файла " + dest)
            raise FlashError()
        return dest

    # --- DFU

    def wait_dfu(self, fam: str, label: str) -> None:
        """Ждёт ровно одно DFU-устройство нужного семейства. Отказ пользователя - FlashError."""
        rn = self.runner
        while True:
            n = 0
            for _ in range(20):
                n = hardware.dfu_count(rn)
                if n >= 1:
                    break
                time.sleep(0.5)
            if n == 0:
                ui.warn("устройство DFU (0483:df11) не найдено. Проверьте: USB-кабель данных, питание платы, режим DFU (%s)"
                        % label)
                if not ui.ask_yn("Попробовать ещё раз?", "y"):
                    raise FlashError()
                ui.pause_hw("Переведите %s в DFU и нажмите Enter." % label, True)
                continue
            if n > 1:
                ui.warn("в режиме DFU сразу %d устройства. Оставьте в DFU только %s (остальные перезагрузите/отключите)"
                        % (n, label))
                if not ui.ask_yn("Проверить ещё раз?", "y"):
                    raise FlashError()
                continue
            got = hardware.dfu_family(rn)
            if got != fam:
                ui.warn("в DFU найден чип: %s, ожидался %s (%s)"
                        % (hardware.family_name(self.reg, got), hardware.family_name(self.reg, fam), label))
                if ui.ask_yn("Это всё равно нужная плата, продолжить?", "n"):
                    return
                if not ui.ask_yn("Попробовать ещё раз (перевести в DFU нужную плату)?", "y"):
                    raise FlashError()
                continue
            ui.ok("DFU: " + hardware.family_name(self.reg, got))
            return

    def dfu_flash_katapult(self, mode: str, cfg) -> None:
        """Прошивка katapult по DFU. Режим make - как у пользователя для ALPS (make flash katapult),
        режим guide - команда из гайда (mass-erase, запасной вариант без него)."""
        cfg = str(cfg)
        kbin = self.build_katapult_safe(cfg)
        if self.dry:
            ui.info("[dry-run] dfu-util -> " + kbin)
            return
        if not os.path.isfile(kbin):
            ui.warn("нет " + kbin)
            raise FlashError()
        rn = self.runner
        if mode == "make":
            # make flash из katapult (sudo dfu-util -R -a 0 -s 0x08000000:leave)
            work = firmware.katapult_work_dir(self.env.cfg.build_dir, cfg)
            if firmware.dfu_run(rn, ["make", "-C", self.env.katapult_dir, "KCONFIG_CONFIG=%s" % (work / ".config"),
                                     "OUT=%s/" % (work / "out"), "flash", "FLASH_DEVICE=0483:df11"]):
                return
        else:
            base = ["dfu-util", "-R", "-a", "0", "-s"]
            if firmware.dfu_run(rn, base + ["0x08000000:mass-erase:force:leave", "-D", kbin, "-d", "0483:df11"], sudo=True):
                return
            if hardware.dfu_count(rn) >= 1:
                ui.warn("с mass-erase не вышло, пробую без него (как рекомендует гайд)")
                if firmware.dfu_run(rn, base + ["0x08000000:leave", "-D", kbin, "-d", "0483:df11"], sudo=True):
                    return
        ui.warn("katapult не записан по DFU (в выводе dfu-util нет 'Download done')")
        raise FlashError()

    # --- katapult

    def enter_katapult(self, t: Target) -> str:
        """Получить плату в режиме katapult: через DFU (прошивка katapult) или без DFU, если katapult уже на плате.
        Возвращает путь usb-katapult_*; неудача (причина выведена) - FlashError."""
        label, chip = t.label, t.chip
        ans = ui.pause_hw("%s: %s" % (label, t.enter_hint), True)
        if self.dry:
            self.dfu_flash_katapult(t.kat_mode, t.katapult_cfg)
            if t.after_hint:
                ui.pause_hw(t.after_hint)
            return "%s/usb-katapult_%s_DRYRUN-if00" % (self.env.byid_dir, chip)
        if ans[:1] and ans[:1] in SKIP_ANSWERS:
            # katapult уже на плате (например, прошлая попытка) или он запустится двойным RESET
            found = self.katapult_devices(chip)
            if found:
                dev = self.pick_katapult(label, found)
                ui.ok("%s уже в режиме katapult: %s" % (label, os.path.basename(dev)))
                return dev
            ui.info("Пропускаю DFU: дважды быстро нажмите RESET на %s, чтобы войти в katapult." % label)
            before = hardware.byid_find(self.env.byid_dir, "usb-katapult_*")
            dev = self.wait_new_katapult(chip, 25, before)
            if not dev:
                ui.warn("usb-katapult_%s_* не появился. Двойной RESET нужно нажимать быстро (светодиод katapult мигает "
                        "медленно)." % chip)
                raise FlashError()
        else:
            self.wait_dfu(t.family, label)
            # снимок после входа в DFU: katapult этой платы в by-id сейчас нет, старое имя не помешает
            before = hardware.byid_find(self.env.byid_dir, "usb-katapult_*")
            self.dfu_flash_katapult(t.kat_mode, t.katapult_cfg)
            if t.after_hint:
                ui.pause_hw(t.after_hint)
            dev = self.wait_new_katapult(chip, 20, before)
            if not dev:
                ui.warn("katapult ещё не появился. После прошивки по DFU ОДИНОЧНЫЙ RESET может запустить не katapult, а "
                        "прежнюю прошивку: ДВАЖДЫ быстро нажмите RESET.")
                try:
                    names = sorted(os.listdir(self.env.byid_dir))
                except OSError:
                    names = []
                ui.info("Устройства: " + "".join(n + " " for n in names))
                dev = self.wait_new_katapult(chip, 30, before)
                if not dev:
                    ui.warn("usb-katapult_%s_* так и не появился (ls %s). Если плата в DFU - katapult не записан, "
                            "повторите через DFU." % (chip, self.env.byid_dir))
                    raise FlashError()
        ui.ok("%s в режиме katapult: %s" % (label, os.path.basename(dev)))
        return dev

    def flash_klipper_via_katapult(self, t: Target, dev: str) -> Outcome:
        """Klipper на плату в katapult по USB. Для обычной платы ждёт usb-Klipper_*, для моста - появления gs_usb и can0."""
        env, chip, label = self.env, t.chip, t.label
        m = re.match(r"^usb-katapult_.*_([^_]*)-if[0-9]*$", os.path.basename(dev))
        serial = m.group(1) if m else ""
        ui.step("Klipper -> " + label)
        if self.dry:
            ui.info("[dry-run] сборка %s, flashtool.py -d %s -f <bin>" % (os.path.basename(str(t.klipper_cfg)), dev))
            return Outcome(serial="DRYRUN")
        binpath = self.build_fw_safe(t.klipper_cfg, chip)
        cp = self.runner.run(["python3", env.katapult_dir + "/scripts/flashtool.py", "-d", dev, "-f", binpath],
                             check=False, tee=True)
        if cp.returncode != 0:
            errs = [ln for ln in (cp.stdout or "").split("\n") if "FlashError" in ln]
            err = errs[-1] if errs else ""
            ui.log("flashtool: " + (err or "ошибка"))
            ui.warn("причина: " + (err or "см. вывод выше"))
            sys.stderr.write("""
Прошивка Klipper на %s не удалась. katapult остаётся в плате.
  - ls %s (должен быть usb-katapult_*), при необходимости дважды быстро нажмите RESET;
  - повтор вручную: python3 %s/scripts/flashtool.py -d %s -f %s
  - если запись блока стабильно не проходит, в меню ниже выберите прошивку Klipper напрямую по DFU (katapult не затрагивается)
""" % (label, env.byid_dir, env.katapult_dir, dev, binpath))
            sys.stderr.flush()
            raise FlashError()
        if t.bridge == 1:
            if not hardware.bring_up_can(self.runner, env.can_iface):
                ui.warn("после прошивки моста не появился рабочий интерфейс %s (lsusb: Geschwister Schneider / 1d50:606f; "
                        "ip link show %s)" % (env.can_iface, env.can_iface))
                raise FlashError()
            ui.ok("%s: мост USB-CAN работает, %s поднят" % (label, env.can_iface))
        else:
            if not hardware.wait_for_device("%s/usb-Klipper_%s_%s-if00" % (env.byid_dir, chip, serial), 20):
                ui.warn("после прошивки %s не появился usb-Klipper_%s_%s-if00; проверьте ls %s"
                        % (label, chip, serial, env.byid_dir))
                raise FlashError()
            self.state_set(serial)
            ui.ok("%s прошит (serial %s)" % (label, serial))
        return Outcome(serial=serial)

    def dfu_flash_klipper(self, t: Target, with_katapult: bool) -> Outcome:
        """Klipper напрямую по DFU (запасной путь, если flashtool не может записать блок). Без katapult он в начале
        флеша не затрагивается; с ним katapult и Klipper пишутся за один сеанс DFU (рекомендуемый способ).
        Katapult запускает приложение со смещения CONFIG_FLASH_APPLICATION_ADDRESS."""
        env, label, chip, fam, bridge = self.env, t.label, t.chip, t.family, t.bridge
        cfg = str(t.klipper_cfg)
        addr = ""
        try:
            with open(cfg, encoding="utf-8", errors="replace") as f:
                for line in f.read().split("\n"):
                    m = re.match(r"^CONFIG_FLASH_APPLICATION_ADDRESS=(.*)$", line)
                    if m:
                        addr = m.group(1)
        except OSError:
            pass
        if not addr:
            ui.warn("в %s нет CONFIG_FLASH_APPLICATION_ADDRESS" % os.path.basename(cfg))
            raise FlashError()
        kbin = ""
        kkey = ""
        kcfg = str(t.katapult_cfg) if (with_katapult and t.katapult_cfg) else ""
        if kcfg:
            ui.step("katapult и Klipper по DFU за один сеанс -> " + label)
            kkey = firmware.katapult_key(kcfg)
            self.build_katapult_safe(kcfg)
            kbin = "%s/katapult-%s/out/katapult.bin" % (env.cfg.build_dir, kkey)
        else:
            ui.step("Klipper по DFU (без katapult) -> " + label)
        binpath = self.build_fw_safe(cfg, chip)
        if kcfg:
            ui.pause_hw("%s: переведите плату в DFU (%s) и нажмите Enter. В один сеанс запишутся katapult (0x08000000) и "
                        "Klipper (по адресу %s)." % (label, t.dfu_how, addr))
        else:
            ui.pause_hw("%s: переведите плату в DFU (%s) и нажмите Enter. Katapult в начале флеша не затрагивается; "
                        "Klipper запишется по адресу %s." % (label, t.dfu_how, addr))
        rn = self.runner
        uuid = ""
        if self.dry:
            if kcfg:
                ui.info("[dry-run] dfu-util -a 0 -s 0x08000000%s -D %s/katapult.bin"
                        % (":mass-erase:force" if t.kat_mode == "guide" else "", kkey))
            name = binpath or "%s-%s.bin" % (firmware.katapult_key(cfg), self.host_version())
            ui.info("[dry-run] dfu-util -a 0 -s %s:leave -D %s" % (addr, name))
            if bridge == 2:
                uuid = hardware.dfu_read_uid(rn, fam, env.log_file)
            return Outcome(serial="DRYRUN", uuid=uuid)
        self.wait_dfu(fam, label)
        if bridge == 2:
            # UID читаем, пока плата в DFU: по нему считается canbus_uuid, который без шины CAN узнать нельзя
            uuid = hardware.dfu_read_uid(rn, fam, env.log_file)
            if uuid:
                ui.ok("%s: canbus_uuid по UID чипа: %s (на шине пока не проверен)" % (label, uuid))
            else:
                ui.warn("%s: UID чипа прочитать не удалось, canbus_uuid останется неизвестным (после установки в принтер: "
                        "install_vostok.sh --check-can)" % label)
        dfu = ["dfu-util", "-a", "0", "-s"]
        if kcfg:
            if not os.path.isfile(kbin):
                ui.warn("нет " + kbin)
                raise FlashError()
            if t.kat_mode == "guide":
                if not firmware.dfu_run(rn, dfu + ["0x08000000:mass-erase:force", "-D", kbin, "-d", "0483:df11"], sudo=True):
                    if hardware.dfu_count(rn) < 1:
                        ui.warn("katapult не записан по DFU")
                        raise FlashError()
                    ui.warn("с mass-erase не вышло, пробую без него")
                    if not firmware.dfu_run(rn, dfu + ["0x08000000", "-D", kbin, "-d", "0483:df11"], sudo=True):
                        ui.warn("katapult не записан по DFU (нет 'Download done')")
                        raise FlashError()
            else:
                if not firmware.dfu_run(rn, dfu + ["0x08000000", "-D", kbin, "-d", "0483:df11"], sudo=True):
                    ui.warn("katapult не записан по DFU (нет 'Download done')")
                    raise FlashError()
            time.sleep(1)
            if hardware.dfu_count(rn) < 1:
                ui.warn("после записи katapult плата вышла из DFU; повторите: переведите её в DFU снова")
                raise FlashError()
        before = hardware.byid_find(env.byid_dir, "usb-Klipper_%s_*" % chip)
        if not firmware.dfu_run(rn, dfu + ["%s:leave" % addr, "-D", binpath, "-d", "0483:df11"], sudo=True):
            ui.warn("Klipper не записан по DFU (в выводе dfu-util нет 'Download done')")
            raise FlashError()
        if bridge == 2:
            ui.pause_hw("Выйдите из режима DFU (снимите джампер BOOT0, если ставили; кнопки BOOT/BT0 отпустите) и отключите "
                        "USB от %s. Дальше плата подключается только по CAN (она запустится от питания 24 В в принтере)."
                        % label)
            ui.ok("%s: katapult и Klipper записаны по DFU (дальше доступна только по CAN)" % label)
            return Outcome(uuid=uuid)
        ui.pause_hw("Выйдите из режима DFU (снимите джампер BOOT0, если ставили; кнопки BOOT/BT0 отпустите) и нажмите RESET "
                    "на %s. Если плата не запустилась, нажмите RESET ещё раз." % label)
        if bridge == 1:
            if not hardware.bring_up_can(rn, env.can_iface):
                ui.warn("после прошивки моста не появился рабочий интерфейс " + env.can_iface)
                raise FlashError()
            ui.ok("%s: мост USB-CAN работает, %s поднят" % (label, env.can_iface))
            return Outcome()
        dev = ""
        for _ in range(40):
            new = [f for f in hardware.byid_find(env.byid_dir, "usb-Klipper_%s_*" % chip) if f not in before]
            if new:
                dev = new[0]
                break
            time.sleep(0.5)
        if not dev:
            ui.warn("после прошивки не появился usb-Klipper_%s_* (ls %s)" % (chip, env.byid_dir))
            raise FlashError()
        m = re.match(r"^usb-Klipper_%s_(.*)-if[0-9]*$" % re.escape(chip), os.path.basename(dev))
        serial = m.group(1) if m else ""
        self.state_set(serial)
        ui.ok("%s прошит по DFU (serial %s)" % (label, serial))
        return Outcome(serial=serial)

    # --- мост и devices.tsv

    def set_bridge_uuid(self) -> None:
        """Мост USB-CAN: canbus_uuid считается по USB-serial (это UID чипа), 24 В и шина не нужны."""
        hw, res = self.hw, self.res
        if hw.mode != "bridge":
            return
        if self.dry:
            res.mcu.bridge_uuid = "000000000000"
            return
        ser = hardware.bridge_usb_serial()
        u = ""
        if ser:
            try:
                u = can_uuid.can_uuid(bytes.fromhex(ser))
            except ValueError:
                u = ""
        if u:
            res.mcu.bridge_uuid = u
            self.state_set(u)
            ui.ok("%s: canbus_uuid моста по UID чипа: %s" % (hw.main_label(), u))
        else:
            ui.warn("%s: canbus_uuid моста вычислить не удалось (lsusb -d 1d50:606f -v | grep iSerial); позже: "
                    "install_vostok.sh --check-can" % hw.main_label())

    def cfg_name(self, kind: str) -> str:
        """Имя конфига сборки главной платы (usb|bridge) для devices.tsv."""
        p = self.reg.cfg_path(self.hw.main_board, kind)
        return p.name if p else ""

    def save_devices(self, quiet: bool = False) -> None:
        """devices.tsv: ключ (serial|uuid) -> конфиг сборки и роль (его читает update / кнопка).
        quiet - промежуточное сохранение после каждой платы: к известным платам добавляются строки прошлого запуска."""
        hw, mcu = self.hw, self.res.mcu
        devs: List[Device] = []
        keys = set()

        def add(key: str, cfg: str, role: str) -> None:
            if key:
                devs.append(Device(key, cfg, role))
                keys.add(key)

        if hw.mode == "bridge":
            add(mcu.bridge_uuid, self.cfg_name("bridge"), "bridge")
            for i in (0, 1):
                add(mcu.head_uuid[i], hw.head_cfg_name(), "can")
        else:
            add(mcu.main_serial, self.cfg_name("usb"), "usb")
        for i in range(hw.alps_count):
            add(mcu.alps_serial[i], "stm32f072xb.config", "usb")
        if quiet:
            for d in self.res.prev_devices:
                if d.key and d.key not in keys:
                    devs.append(d)
        text = "".join("%s\t%s\t%s\n" % (d.key, d.cfg, d.role) for d in devs)
        if self.dry:
            if not quiet:
                ui.info("[dry-run] записал бы:")
                sys.stdout.write(text)
                sys.stdout.flush()
            return
        DevicesFile(self.env.devices_file).save(devs)
        if not quiet:
            with open(self.env.devices_file, encoding="utf-8") as f:
                sys.stdout.write(f.read())
            sys.stdout.flush()

    # --- платы голов

    def head_target(self, i: int, with_katapult: bool = True) -> Target:
        hw = self.hw
        name = hw.head_cfg_name()
        return Target(label="%s %s" % (hw.head_label(), hw.head_side(i)), chip=hw.head_chip(), family="g",
                      klipper_cfg=self.env.configs_dir / name,
                      katapult_cfg=self.reg.katapult_dir / name if with_katapult else None, bridge=2)

    def head_dfu_all(self, i: int) -> Outcome:
        """katapult и Klipper платы головы за один сеанс DFU (USB), затем плата работает только по CAN."""
        out = self.dfu_flash_klipper(self.head_target(i), with_katapult=True)
        self.res.head_dfu_done[i] = True
        return out

    def can_uuids(self, app: str) -> List[str]:
        env = self.env
        return hardware.can_uuids(self.runner, app, katapult_dir=env.katapult_dir, klippy_env=env.klippy_env,
                                  klipper_dir=env.klipper_dir, iface=env.can_iface)


# ------------------------------------------------------------------ стратегии и задания

class FlashJob:
    """Плата + способ прошивки: выбор стратегии по фазе и запись результата. Состояние повтора (retry_phase, dev) -
    здесь, а не в глобалах."""

    def __init__(self, label: str, target: Optional[Target], start_phase: str,
                 select: Callable[[str], "Strategy"], commit: Callable[[Outcome], None],
                 menu: str = "std", index: int = 0) -> None:
        self.label, self.target, self.start_phase = label, target, start_phase
        self.select, self.commit, self.menu, self.index = select, commit, menu, index
        self.retry_phase = start_phase     # с какого шага повторять: full (с DFU) | klipper | dfuall | dfuk
        self.phase = start_phase           # фаза текущей попытки
        self.dev = ""                      # usb-katapult_* устройство платы, прошиваемой сейчас


class Strategy:
    """Способ прошивки платы: run(fl, job) -> Outcome или FlashError."""

    def run(self, fl: Flasher, job: FlashJob) -> Outcome:
        raise NotImplementedError


class DfuAll(Strategy):
    """katapult и Klipper за один сеанс DFU."""

    def run(self, fl: Flasher, job: FlashJob) -> Outcome:
        job.retry_phase = "dfuall"
        return fl.dfu_flash_klipper(job.target, with_katapult=True)


class DfuKlipperOnly(Strategy):
    """Klipper напрямую по DFU, katapult не затрагивается."""

    def run(self, fl: Flasher, job: FlashJob) -> Outcome:
        job.retry_phase = "dfuk"
        return fl.dfu_flash_klipper(job.target, with_katapult=False)


class KatapultThenKlipper(Strategy):
    """katapult по DFU (или уже на плате), затем Klipper через katapult. Фаза klipper пропускает вход в katapult."""

    def run(self, fl: Flasher, job: FlashJob) -> Outcome:
        phase = job.phase
        if phase == "klipper" and not (job.dev and os.path.exists(job.dev)):
            phase = "full"
        if phase == "full":
            job.retry_phase = "full"
            job.dev = fl.enter_katapult(job.target)
        job.retry_phase = "klipper"
        return fl.flash_klipper_via_katapult(job.target, job.dev)


class HeadKatapult(Strategy):
    """Только katapult платы головы (для схемы «Klipper по CAN»); фаза dfuall - katapult и Klipper сразу по DFU."""

    def run(self, fl: Flasher, job: FlashJob) -> Outcome:
        label = job.label[:-len(" (katapult)")]
        hw, i = fl.hw, job.index
        disconnect = "Отключите USB от %s. Дальше она будет подключена только по CAN." % label
        if job.phase == "dfuall":
            job.retry_phase = "dfuall"
            fl.head_dfu_all(i)
            ui.pause_hw(disconnect)
            return Outcome()
        ans = ui.pause_hw("%s: подключите USB, переведите в DFU и нажмите Enter. DFU: %s." % (label, hw.head_dfu_hint()), True)
        if ans[:1] and ans[:1] in SKIP_ANSWERS and not fl.dry:
            ui.info("DFU для этой платы головы пропущен (katapult уже на плате)")
            return Outcome()
        kcfg = fl.reg.katapult_dir / hw.head_cfg_name()
        if fl.dry:
            fl.dfu_flash_katapult("guide", kcfg)
            return Outcome()
        fl.wait_dfu("g", label)
        fl.dfu_flash_katapult("guide", kcfg)
        ui.pause_hw(disconnect)
        return Outcome()


class CanKlipper(Strategy):
    """Klipper платы головы по CAN через katapult (нужны 24 В и CAN-кабели); фаза dfuall - сначала по USB/DFU."""

    def run(self, fl: Flasher, job: FlashJob) -> Outcome:
        hw, res, env, i = fl.hw, fl.res, fl.env, job.index
        label = "%s %s" % (hw.head_label(), hw.head_side(i))
        fcfg = env.configs_dir / hw.head_cfg_name()
        if job.phase == "dfuall":
            job.retry_phase = "dfuall"
            ui.pause_hw("Подключите USB-кабелем ТОЛЬКО %s (CAN пока отключите): плату нужно перевести в DFU (%s)."
                        % (label, hw.head_dfu_hint()))
            fl.head_dfu_all(i)
        if res.head_dfu_done[i]:
            ui.pause_hw("Отключите USB, подключите CAN-кабелем ТОЛЬКО %s (вторую плату головы отключите), подайте питание и "
                        "нажмите Enter." % label)
            if fl.dry:
                res.mcu.head_uuid[i] = "00000000000%d" % i
                return Outcome()
            bridge = (res.mcu.bridge_uuid or "x").lower()
            uuids = [u for u in fl.can_uuids("Klipper") if u.lower() != bridge]
            if len(uuids) != 1:
                ui.warn("ожидалась одна новая плата с Klipper на CAN (кроме моста), найдено: %d. Проверьте CAN_H/CAN_L, "
                        "терминаторы, питание; оставьте подключённой только эту плату." % len(uuids))
                raise FlashError()
            res.mcu.head_uuid[i] = uuids[0]
            fl.state_set(uuids[0])
            ui.ok("%s: %s, Application: Klipper" % (label, uuids[0]))
            return Outcome(uuid=uuids[0])
        ui.pause_hw("Подключите CAN-кабелем ТОЛЬКО %s (вторую плату головы отключите) вместе с питанием платы и нажмите Enter."
                    % label)
        uuids = fl.can_uuids("Katapult")
        if not uuids:
            ui.warn("плата katapult по CAN не найдена. Проверьте CAN_H/CAN_L, терминаторы 120 Ом (около 60 Ом на шине), "
                    "питание плат голов.")
            ui.warn("Если на плате уже Klipper, дважды быстро нажмите RESET (красный светодиод мигает) - она станет Katapult.")
            raise FlashError()
        if len(uuids) != 1:
            ui.warn("ожидалась одна плата в katapult на CAN, найдено: %d (оставьте подключённой только %s)"
                    % (len(uuids), label))
            raise FlashError()
        uuid = uuids[0]
        binpath = fl.build_fw_safe(fcfg, hw.head_chip())
        if not fl.dry and not firmware.flash_can_node(env.katapult_dir, env.can_iface, uuid, binpath, fl.runner):
            ui.warn("прошивка %s (%s) не удалась: повтор python3 %s/scripts/flashtool.py -i %s -u %s -f %s"
                    % (label, uuid, env.katapult_dir, env.can_iface, uuid, binpath))
            raise FlashError()
        time.sleep(2)
        if uuid.lower() in [u.lower() for u in fl.can_uuids("Klipper")]:
            ui.ok("%s: %s, Application: Klipper" % (label, uuid))
        else:
            ui.warn("после прошивки %s не отвечает как Klipper (canbus_query.py %s); продолжаю" % (uuid, env.can_iface))
        fl.state_set(uuid)
        res.mcu.head_uuid[i] = uuid
        return Outcome(uuid=uuid)


def _by_phase(*pairs):
    """Выбор стратегии по фазе: pairs - (фаза, стратегия) ...; последняя пара - по умолчанию."""
    table = dict(pairs[:-1])
    default = pairs[-1][1]
    return lambda phase: table.get(phase, default)


def make_alps_job(fl: Flasher, i: int) -> FlashJob:
    """ALPS: katapult через DFU (make flash), затем Klipper через katapult."""
    env, hw = fl.env, fl.hw
    t = Target(label="ALPS " + hw.alps_side(i), chip="stm32f072xb", family="f0",
               klipper_cfg=env.configs_dir / "stm32f072xb.config",
               katapult_cfg=fl.reg.katapult_dir / "stm32f072xb.config", kat_mode="make", bridge=0,
               enter_hint="переведите этот ALPS в режим DFU (BOOT + RESET, затем отпустить BOOT)")

    def commit(o: Outcome) -> None:
        fl.res.mcu.alps_serial[i] = o.serial

    return FlashJob(t.label, t, "full", _by_phase(("dfuall", DfuAll()), ("dfuk", DfuKlipperOnly()),
                                                  ("", KatapultThenKlipper())), commit, index=i)


def make_main_job(fl: Flasher, start_phase: str) -> FlashJob:
    """Главная плата: katapult и Klipper за один сеанс DFU либо katapult по DFU + Klipper через katapult."""
    hw = fl.hw
    bridge = 1 if hw.mode == "bridge" else 0
    t = Target(label=hw.main_label(), chip=hw.main, family=hw.board.field("FAMILY"),
               klipper_cfg=hw.klipper_cfg(), katapult_cfg=hw.katapult_cfg(), kat_mode="guide", bridge=bridge,
               enter_hint=main_dfu_enter_text(hw), after_hint=main_dfu_after_text(hw), dfu_how=main_dfu_klipper_how(hw))

    def commit(o: Outcome) -> None:
        if hw.mode == "usb":
            fl.res.mcu.main_serial = o.serial
        else:
            fl.set_bridge_uuid()

    return FlashJob(t.label, t, start_phase, _by_phase(("dfuall", DfuAll()), ("dfuk", DfuKlipperOnly()),
                                                       ("", KatapultThenKlipper())), commit)


def make_head_katapult_job(fl: Flasher, i: int) -> FlashJob:
    label = "%s %s (katapult)" % (fl.hw.head_label(), fl.hw.head_side(i))
    return FlashJob(label, None, "full", lambda phase: HeadKatapult(), lambda o: None, index=i)


def make_head_dfu_job(fl: Flasher, i: int) -> FlashJob:
    """Платы голов «на столе»: katapult и Klipper за один сеанс DFU (меню - без «katapult через DFU»)."""
    t = fl.head_target(i)

    def commit(o: Outcome) -> None:
        res = fl.res
        res.mcu.head_uuid[i] = o.uuid
        if o.uuid:
            res.head_uuid_src[i] = "uid"
            fl.state_set(o.uuid)
        else:
            res.head_uuid_src[i] = ""

    return FlashJob(t.label, t, "dfuall", _by_phase(("dfuk", DfuKlipperOnly()), ("", DfuAll())), commit,
                    menu="headsdfu", index=i)


def make_head_klipper_job(fl: Flasher, i: int) -> FlashJob:
    label = "%s %s (Klipper)" % (fl.hw.head_label(), fl.hw.head_side(i))
    return FlashJob(label, None, "full", lambda phase: CanKlipper(), lambda o: None, index=i)


# ------------------------------------------------------------------ меню и повтор

def flash_menu(label: str, kind: str = "std") -> str:
    """Меню после неудачи: retry|dfu|dfuall|dfuk|skip|abort. Без терминала или с -y - skip."""
    if ui.opts.yes or not ui.have_tty():
        return "skip"
    q = "%s: прошивка не удалась. Что делать?" % label
    if kind == "headsdfu":
        ans = ui.ask_choice(q, MENU_RETRY, [MENU_RETRY, MENU_DFU_K_HEADS, MENU_SKIP, MENU_ABORT])
        return {MENU_DFU_K_HEADS: "dfuk", MENU_SKIP: "skip", MENU_ABORT: "abort"}.get(ans, "retry")
    ans = ui.ask_choice(q, MENU_RETRY, [MENU_RETRY, MENU_DFU_ALL, MENU_DFU, MENU_DFU_K, MENU_SKIP, MENU_ABORT])
    return {MENU_DFU_ALL: "dfuall", MENU_DFU: "dfu", MENU_DFU_K: "dfuk", MENU_SKIP: "skip",
            MENU_ABORT: "abort"}.get(ans, "retry")


def flash_with_retry(fl: Flasher, job: FlashJob) -> bool:
    """Прошивка одной платы с повтором. True - прошита (devices.tsv сохранён), False - пропущена пользователем
    (установка продолжается), прерывание - UserAbort."""
    phase = job.start_phase
    job.retry_phase, job.dev = phase, ""
    while True:
        job.phase = phase
        try:
            outcome = job.select(phase).run(fl, job)
        except FlashError as e:
            if str(e):
                ui.warn(str(e))
        else:
            job.commit(outcome)
            fl.save_devices(quiet=True)
            return True
        ui.warn("%s: прошивка не удалась" % job.label)
        choice = flash_menu(job.label, job.menu)
        if choice == "retry":
            phase = job.retry_phase
        elif choice == "dfu":
            phase = "full"
        elif choice in ("dfuall", "dfuk"):
            phase = choice
        elif choice == "skip":
            fl.res.failed.append("%s: не прошита" % job.label)
            ui.warn("%s пропущена, продолжаю с остальными платами" % job.label)
            return False
        else:
            raise UserAbort("установка прервана пользователем (%s)" % job.label)
