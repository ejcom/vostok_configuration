"""unittest-обёртка над run_golden.sh: тест зелёный, если все golden-эталоны совпали.

Код 2 от run_golden.sh (хост не подходит: нет systemd, pyserial и т. п.) - пропуск, а не падение.
"""
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class GoldenTest(unittest.TestCase):
    def test_golden(self):
        pr = subprocess.run([os.path.join(HERE, "run_golden.sh")], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, universal_newlines=True)
        if pr.returncode == 2:
            self.skipTest(pr.stdout.strip())
        self.assertEqual(pr.returncode, 0, "расхождения с эталонами:\n" + pr.stdout)


if __name__ == "__main__":
    unittest.main()
