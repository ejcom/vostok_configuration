"""Оборудование хоста: устройства в by-id, состояние CAN-интерфейса, ожидание устройств.

Перенос из update_klipper_mcu.sh (by_id_chip/by_id_serial, can_iface_up, wait_for_device и поиск
usb-katapult_* в flash_can). Расширяется A5 (lsusb/dfu-util, canbus_query).
"""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import List, Optional, Tuple

from .system import Runner

# usb-Klipper_<чип>_<серийный номер>-if00 (как sed в bash: чип жадный, серийный без "_")
_BYID_RE = re.compile(r"^usb-Klipper_(.*)_([^_]*)-if[0-9]*$")


def run_quiet(argv: List[str], runner: Optional[Runner] = None) -> Tuple[int, str]:
    """Запрос состояния без вывода ошибок на экран (``2>/dev/null``): (код, stdout). Нет программы - код 127.
    Выполняется и в dry-run (readonly), потому что ничего не меняет."""
    runner = runner or Runner()
    cp = runner.run(argv, quiet=True, capture=True, check=False, readonly=True)
    return cp.returncode, cp.stdout or ""


def by_id_chip(path: str) -> str:
    """Чип из имени usb-Klipper_<чип>_<серийный>-if00 (пустая строка, если имя не подходит)."""
    m = _BYID_RE.match(os.path.basename(path))
    return m.group(1) if m else ""


def by_id_serial(path: str) -> str:
    """Серийный номер из имени usb-Klipper_<чип>_<серийный>-if00 (пустая строка, если имя не подходит)."""
    m = _BYID_RE.match(os.path.basename(path))
    return m.group(2) if m else ""


def list_byid(byid_dir: str, prefix: str) -> List[str]:
    """Полные пути BYID_DIR/<prefix>* (существующие, с учётом ссылок), отсортированные как glob в bash."""
    try:
        names = sorted(n for n in os.listdir(byid_dir) if n.startswith(prefix))
    except OSError:
        return []
    return [os.path.join(byid_dir, n) for n in names if os.path.exists(os.path.join(byid_dir, n))]


def find_katapult(byid_dir: str, chip: str) -> Optional[str]:
    """Первое устройство BYID_DIR/usb-katapult_<чип>_* или None."""
    devs = list_byid(byid_dir, "usb-katapult_%s_" % chip)
    return devs[0] if devs else None


def can_iface_up(iface: str) -> bool:
    """Интерфейс CAN поднят: в выводе ``ip link show`` встречается ``UP`` (как ``grep -q UP`` в bash)."""
    rc, out = run_quiet(["ip", "link", "show", iface])
    return rc == 0 and "UP" in out


def can_iface_exists(iface: str) -> bool:
    """Интерфейс существует (``ip link show`` успешен)."""
    return run_quiet(["ip", "link", "show", iface])[0] == 0


def ifup(iface: str, runner: Optional[Runner] = None) -> None:
    """``sudo -n ifup <iface>`` без вывода; результат игнорируется (как в bash). В dry-run только печатается."""
    (runner or Runner()).run(["sudo", "-n", "ifup", iface], quiet=True, check=False)


def have_ip() -> bool:
    """Есть ли команда ip (пакет iproute2)."""
    return shutil.which("ip") is not None


def wait_for_device(path: str, seconds: int) -> bool:
    """Ждать появления пути до ``seconds`` секунд (опрос каждые 0.5 с). True - появился."""
    for _ in range(seconds * 2):
        if os.path.exists(path):
            return True
        time.sleep(0.5)
    return False


def wait_for_katapult(byid_dir: str, chip: str, tries: int = 40) -> Optional[str]:
    """Ждать устройство usb-katapult_<чип>_* до ``tries`` * 0.5 с (20 с). Путь или None."""
    for _ in range(tries):
        dev = find_katapult(byid_dir, chip)
        if dev:
            return dev
        time.sleep(0.5)
    return None


def wait_for_can_iface(iface: str, tries: int = 40) -> bool:
    """Ждать появления интерфейса CAN до ``tries`` * 0.5 с (20 с); True - интерфейс есть."""
    for _ in range(tries):
        if can_iface_exists(iface):
            return True
        time.sleep(0.5)
    return can_iface_exists(iface)
