"""분석 설계(43번) 10-1절 손계산 표와 계획서 5절 규칙을 그대로 시험한다."""
import datetime as dt
import unittest

import calc

# 43번 2-4절 손계산 표(단위 백만 원, 가상). 1~3월 사전 추세용, 4~6월 기준, 7월 제외, 8~9월 행사.
MONTHS = [f"2024{m:02d}" for m in range(1, 10)]
T = dict(zip(MONTHS, [98, 100, 102, 100, 104, 96, 120, 140, 110]))
C = dict(zip(MONTHS, [190, 196, 202, 200, 210, 190, 230, 240, 200]))
C2 = dict(zip(MONTHS, [160, 170, 180, 195, 200, 205, 230, 250, 210]))

SUMMER = calc.months_for(dt.date(2024, 7, 19), dt.date(2024, 9, 15))
GAPADO = calc.months_for(dt.date(2024, 4, 6), dt.date(2024, 4, 28))


def spread(s, n):
    """모집단 표준편차가 정확히 s인 가짜 시점 값 n개(n은 짝수)."""
    return [s, -s] * (n // 2)


class MonthsTest(unittest.TestCase):
    def test_hand_table_months(self):
        self.assertEqual(SUMMER["event"], ["202408", "202409"])
        self.assertEqual(SUMMER["excluded"], ["202407"])
        self.assertEqual(SUMMER["base"], ["202404", "202405", "202406"])
        self.assertEqual(SUMMER["pretrend"], ["202401", "202402", "202403"])
        self.assertTrue(SUMMER["in_coverage"])
        self.assertFalse(SUMMER["diluted"])

    def test_placebo_rules(self):
        # 7·8·9월이 든 창, 처음 걸친 달 앞 6개월과 겹치는 창, 수록 기간 밖 창은 빠진다
        expected = [f"2025{m:02d}" for m in range(1, 7)] + [f"2026{m:02d}" for m in range(1, 7)]
        self.assertEqual(SUMMER["placebo"], expected)

    def test_gapado_counts(self):
        # 52번 계산: 가짜 시점 달 22개, σ 창을 빼면 17개
        self.assertEqual(GAPADO["event"], ["202404"])
        self.assertEqual(len(GAPADO["placebo"]), 17)
        need = calc.required_months(GAPADO)
        self.assertEqual(len(need["required"]), 7)
        self.assertNotIn("202504", need["all"])
        self.assertNotIn("202308", need["all"])

    def test_blocked_month_removes_windows(self):
        m = calc.months_for(dt.date(2024, 7, 19), dt.date(2024, 9, 15), blocked={"202502"})
        # 202502가 든 창은 τ가 202502~202505인 네 개뿐이다
        self.assertEqual(m["placebo"][:2], ["202501", "202506"])
        self.assertEqual(len(m["placebo"]), len(SUMMER["placebo"]) - 4)

    def test_diluted_event(self):
        m = calc.months_for(dt.date(2024, 5, 30), dt.date(2024, 6, 2))
        self.assertTrue(m["diluted"])
        # 5월 2/31보다 6월 2/30이 크다
        self.assertEqual(m["event"], ["202406"])

    def test_too_early_event(self):
        m = calc.months_for(dt.date(2023, 12, 1), dt.date(2023, 12, 3))
        self.assertFalse(m["in_coverage"])


class FeasibilityTest(unittest.TestCase):
    def test_rules_in_order(self):
        d = dt.date
        self.assertEqual(calc.feasibility(None, d(2024, 4, 1)), ("unavailable", "no_date"))
        self.assertEqual(calc.feasibility(d(2024, 4, 2), d(2024, 4, 1)), ("unavailable", "bad_date"))
        self.assertEqual(calc.feasibility(d(2024, 4, 1), d(2024, 7, 2)), ("unavailable", "long_event"))
        self.assertEqual(calc.feasibility(d(2024, 4, 1), d(2024, 4, 3)), ("unavailable", "short_event"))
        self.assertEqual(calc.feasibility(d(2023, 12, 1), d(2023, 12, 20)), ("unavailable", "before_data"))
        self.assertEqual(calc.feasibility(d(2024, 4, 1), d(2024, 4, 10)), ("diluted", "diluted"))
        self.assertEqual(calc.feasibility(d(2024, 4, 6), d(2024, 4, 28)), ("ok", None))


class EffectTest(unittest.TestCase):
    def test_effect_and_delta(self):
        e, delta = calc.effect(T, C, SUMMER["event"], SUMMER["base"])
        self.assertAlmostEqual(e, 0.136364, places=6)
        self.assertAlmostEqual(delta, 0.15, places=9)

    def test_pretrend(self):
        self.assertAlmostEqual(calc.effect(T, C, SUMMER["base"], SUMMER["pretrend"])[0], -0.02, places=9)
        self.assertAlmostEqual(calc.effect(T, C2, SUMMER["base"], SUMMER["pretrend"])[0], -0.15, places=9)

    def test_excluded_month_does_not_matter(self):
        t = dict(T, **{"202407": 999})
        e, _ = calc.effect(t, C, SUMMER["event"], SUMMER["base"])
        self.assertAlmostEqual(e, 0.136364, places=6)

    def test_replace_first_choice(self):
        cands = [
            {"emd": "C2", "L": -0.15, "Q": spread(0.04, 10)},
            {"emd": "C", "L": -0.02, "Q": spread(0.035, 10)},
        ]
        chosen, tried = calc.pick(cands)
        self.assertEqual(chosen["emd"], "C")
        self.assertEqual([x["ok"] for x in tried], [False, True])
        e, _ = calc.effect(T, C, SUMMER["event"], SUMMER["base"])
        self.assertAlmostEqual(e, 0.136364, places=6)


class OutcomeTest(unittest.TestCase):
    E = 0.136

    def test_18_small_placebo_is_strong(self):
        q = spread(0.03, 18)
        p, n = calc.pvalue(self.E, q)
        self.assertAlmostEqual(p, 1 / 19)
        self.assertEqual(n, 0)
        self.assertEqual(calc.choose_outcome(self.E, q), "higher")
        self.assertEqual(calc.choose_outcome(-self.E, q), "lower")

    def test_9_placebo_one_bigger(self):
        q = [x / 100 for x in (-5, -3, -2, -1, 0, 1, 2, 3, 14)]
        p, n = calc.pvalue(self.E, q)
        self.assertAlmostEqual(p, 0.2)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(calc.sigma(q), 0.0516, places=4)
        self.assertEqual(calc.choose_outcome(self.E, q), "no_difference")

    def test_8_placebo_not_computed(self):
        self.assertEqual(calc.choose_outcome(self.E, spread(0.01, 8)), "not_computed")

    def test_reason_forces_not_computed(self):
        self.assertEqual(calc.choose_outcome(self.E, spread(0.01, 18), reason="small_cells"), "not_computed")


class AnalyzeTest(unittest.TestCase):
    def test_same_input_same_result(self):
        months = dict(SUMMER, placebo=[])
        taus = []
        a = calc.analyze(T, [("C", C, taus)], months)
        b = calc.analyze(T, [("C", C, taus)], months)
        self.assertEqual(a, b)
        # 가짜 시점 달이 없으면 σ를 못 구해 비교 읍면을 쓰지 않는다
        self.assertEqual(a["outcome"], "not_computed")
        self.assertEqual(a["tried"][0]["J"], 0)


if __name__ == "__main__":
    unittest.main()
