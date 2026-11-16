"""외부 호출의 벽시계 시간 제한: httpx 시간 제한이 못 끊는 멈춤(11/16 측정에서 한 번에 510초)도 끊는다."""
import time
import unittest

import egress


class DeadlineTest(unittest.TestCase):
    def test_hung_call_is_cut(self):
        started = time.time()
        with self.assertRaises(egress.CallTimeout):
            egress.with_deadline(lambda: time.sleep(5), 0.3)
        self.assertLess(time.time() - started, 2)

    def test_result_and_error_pass_through(self):
        self.assertEqual(egress.with_deadline(lambda: 7, 1), 7)
        with self.assertRaises(KeyError):
            egress.with_deadline(lambda: {}["x"], 1)

    def test_timeout_takes_fallback_path(self):
        # pipeline.public_stage는 RuntimeError를 대체 경로로 보낸다
        self.assertTrue(issubclass(egress.CallTimeout, RuntimeError))


if __name__ == "__main__":
    unittest.main()
