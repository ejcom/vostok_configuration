"""Тесты vostok.can_uuid: векторы из C-реализации (lib/fast-hash из Klipper); tools/can_uuid.py - обёртка над ним."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, INSTALL)

from vostok import can_uuid as cu  # noqa: E402

# (UID, ожидаемый canbus_uuid): посчитано C-кодом fasthash64(uid, 12, 0xA16231A7), первые 6 байт
C_VECTORS = [
    ("f837828554d61ba6121517b1", "04f27af19b13"),
    ("6510d50c57ef245dfaf4131b", "95a3453a9d2c"),
    ("569111587dfd60f911309acf", "432e7da33c41"),
    ("4213b6c6b3137a403d68e05d", "0a1209a2168f"),
    ("115eaaf294d66f0f6e0cd478", "4c99dc5a8a9f"),
    ("e30ba795d8863003c8d47964", "5f82cb43e924"),
    ("d43eb357c91430f0ead8015f", "a5d16dae2598"),
    ("6e02214c0c9c4676e17451d6", "9193b903d6c9"),
    # из golden-эталонов старого скрипта
    ("0123456789ABCDEF01234567", "38c9bdae9652"),
    ("001122334455667788990011", "8a0921a2cf9a"),
    ("0102030405060708090a0b0c", "fe1c3739242f"),
]


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cu.main(argv)
    return rc, out.getvalue(), err.getvalue()


class CanUuidTest(unittest.TestCase):
    def test_c_vectors(self):
        for uid, want in C_VECTORS:
            self.assertEqual(cu.can_uuid(bytes.fromhex(uid)), want, uid)

    def test_bad_uid(self):
        for uid in (b"", b"\x01\x02", b"\x00" * 12, b"\xff" * 12, bytes(range(13))):
            with self.assertRaises(ValueError):
                cu.can_uuid(uid)

    def test_main_hex(self):
        rc, out, err = _run(["can_uuid", "--uid-hex", "  001122334455667788990011  "])
        self.assertEqual((rc, out, err), (0, "8a0921a2cf9a\n", ""))

    def test_main_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "uid.bin")
            with open(p, "wb") as f:
                f.write(bytes(range(1, 13)))
            self.assertEqual(_run(["can_uuid", "--uid-file", p]), (0, "fe1c3739242f\n", ""))
            rc, out, err = _run(["can_uuid", "--uid-file", os.path.join(d, "nosuch")])
            self.assertEqual((rc, out), (1, ""))
            self.assertIn("can_uuid: [Errno 2] No such file or directory", err)

    def test_main_errors_like_old(self):
        self.assertEqual(_run(["can_uuid", "--uid-hex", "0123"])[0::2], (1, "can_uuid: UID должен быть 12 байт, получено 2\n"))
        self.assertEqual(_run(["can_uuid", "--uid-hex", "00" * 12])[0::2],
                         (1, "can_uuid: UID состоит из одинаковых байт (чтение не удалось)\n"))
        rc, out, err = _run(["can_uuid", "--uid-hex", "zz"])
        self.assertEqual(rc, 1)
        self.assertTrue(err.startswith("can_uuid: non-hexadecimal"))
        rc, out, err = _run(["can_uuid"])
        self.assertEqual(rc, 2)
        self.assertIn("Вычисляет canbus_uuid", err)


if __name__ == "__main__":
    unittest.main()
