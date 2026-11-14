"""키 읽기 순서: 환경변수가 있으면 그것, 없으면 app/.env."""
import os
import unittest
from unittest import mock

import config


class EnvTest(unittest.TestCase):
    def test_os_environment_wins_over_dotenv(self):
        with mock.patch.dict(os.environ, {"ZZ_TEST_KEY": "from-os"}):
            self.assertEqual(config.env("ZZ_TEST_KEY"), "from-os")

    def test_blank_environment_falls_back(self):
        with mock.patch.dict(os.environ, {"ZZ_TEST_KEY": "  "}):
            self.assertIsNone(config.env("ZZ_TEST_KEY"))


if __name__ == "__main__":
    unittest.main()
