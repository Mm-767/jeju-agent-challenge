"""허브 유동인구 결측 규칙(계획서 5-6절)과 비교 읍면 거리 시험."""
import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

import calc
import hub

FIELDS = ["baseDate", "city", "emd", "gender", "ageGroup", "resdPop", "workPop", "visitPop"]
GENDERS = ["남", "여"]
AGES = ["10세미만", "10대", "20대", "30대", "40대", "50대", "60대", "70대이상"]


def day_rows(day, value=10):
    return [
        {"baseDate": day.strftime("%Y%m%d"), "city": "제주시", "emd": "가상읍", "gender": g, "ageGroup": a,
         "resdPop": 1, "workPop": 1, "visitPop": value}
        for g in GENDERS for a in AGES
    ]


def write(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
    f.close()
    return Path(f.name)


class HubTest(unittest.TestCase):
    def setUp(self):
        aug = [dt.date(2023, 8, d) for d in range(1, 32)]
        sep = [dt.date(2023, 9, d) for d in range(1, 27)]  # 30일 중 26일만 있음: 결측 4일(13%)
        rows = [r for day in aug + sep for r in day_rows(day)]
        rows = [r for r in rows if not (r["baseDate"] == "20230805" and r["ageGroup"] == "20대" and r["gender"] == "남")]
        rows.append(day_rows(dt.date(2023, 8, 6))[0])  # 같은 행 한 번 더
        self.path = write(rows)

    def tearDown(self):
        self.path.unlink()

    def test_incomplete_day_is_missing(self):
        v = hub.daily_visits("가상읍", self.path)
        self.assertIn(dt.date(2023, 8, 5), v["missing"])
        self.assertNotIn(dt.date(2023, 8, 5), v["days"])
        self.assertEqual(v["days"][dt.date(2023, 8, 6)], 160)
        self.assertEqual(v["duplicates"], 1)

    def test_month_with_too_many_missing_days_dropped(self):
        means = hub.monthly_means(hub.daily_visits("가상읍", self.path))
        self.assertEqual(means["202308"], 160)  # 결측 1일(3%)은 남은 날로 평균
        self.assertNotIn("202309", means)

    def test_no_file_means_no_public_data(self):
        self.assertIsNone(hub.daily_visits("없는읍", Path("/nonexistent/x.csv")))


class VisitTest(unittest.TestCase):
    START = dt.date(2024, 4, 6)
    END = dt.date(2024, 4, 12)

    def days(self, base_weekend, base_weekday, lift):
        out = {}
        for n in range(-40, 20):
            d = self.START + dt.timedelta(n)
            value = base_weekend if d.weekday() >= 5 else base_weekday
            out[d] = value * (lift if self.START <= d <= self.END else 1)
        return out

    def test_weekday_pattern_does_not_bias(self):
        r, missing = calc.visit_change(self.days(200, 100, 1.2), self.START, self.END)
        self.assertAlmostEqual(r, 0.2)
        self.assertEqual(missing, 0)

    def test_summary_relative_to_candidates(self):
        s = calc.visit_summary(self.days(100, 100, 1.5), {"가": self.days(100, 100, 1.0), "나": None}, self.START, self.END)
        self.assertAlmostEqual(s["R_T"], 0.5)
        self.assertAlmostEqual(s["R_C"], 0.0)
        self.assertAlmostEqual(s["V"], 0.5)
        self.assertEqual(list(s["candidates"]), ["가"])

    def test_too_many_missing_days(self):
        days = self.days(100, 100, 1.0)
        for n in range(1, 6):  # 창 35일 중 5일 결측(14%)
            days.pop(self.START - dt.timedelta(n))
        r, missing = calc.visit_change(days, self.START, self.END)
        self.assertIsNone(r)
        self.assertEqual(missing, 5)


class DistanceTest(unittest.TestCase):
    def test_window_skips_same_month_number(self):
        months = calc.distance_months(dt.date(2024, 4, 6), dt.date(2024, 4, 28))
        self.assertEqual(months[0], "202305")
        self.assertEqual(months[-1], "202403")
        self.assertEqual(len(months), 11)

    def test_parallel_series_distance_zero_and_ranking(self):
        months = [f"2024{m:02d}" for m in range(1, 13)]
        t = {m: 100 + 10 * i for i, m in enumerate(months)}
        same_shape = {m: v * 2 for m, v in t.items()}
        wobbly = {m: v * (1.3 if i % 2 else 0.8) for i, (m, v) in enumerate(t.items())}
        self.assertAlmostEqual(calc.distance(t, same_shape, months), 0.0)
        ranked, skipped = calc.rank(t, {"흔들림": wobbly, "나란함": same_shape, "자료없음": None}, months)
        self.assertEqual([e for e, _ in ranked], ["나란함", "흔들림"])
        self.assertEqual(skipped, ["자료없음"])

    def test_too_few_months(self):
        months = ["202401", "202402", "202403", "202404", "202405"]
        t = {m: 1 for m in months}
        self.assertIsNone(calc.distance(t, t, months))


if __name__ == "__main__":
    unittest.main()
