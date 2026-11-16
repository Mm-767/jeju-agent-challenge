"""계획서 4-4 완료 기준: 가파도청보리축제 단계 입력을 맥락으로 한 정상 문장 통과와 위반 문장 차단."""
import datetime as dt
import unittest

from grounding import check_numbers

GAPADO = dt.date(2024, 4, 6)
FACTS = {
    "dates": {GAPADO + dt.timedelta(n) for n in range(23)} | {dt.date(2024, 3, 2), dt.date(2024, 6, 29)},
    "months": {"202404", "202401", "202402", "202403", "202310", "202311", "202312"},
    "counts": {2, 9, 11, 12, 42},
    "names": ["가파도청보리축제", "9.81파크 <구팔일 억새바당>", "9.81파크 구팔일 억새바당", "9.81파크", "가파도"],
    "codes": {"I56111", "I56220", "G47122"},
    "blanks": {"visit.R_T", "visit.V"},
}

PASS = [
    "2024년 4월 6일부터 4월 28일까지",
    "4월 6일부터 28일까지",
    "직전 1~3월",
    "직전 4주 같은 요일 평균보다",
    "1순위 후보인 안덕면은",
    "두 곳을 비교했습니다",
    "9.81파크에서 열린 억새 행사",
    "음식점(I56) 계열",
    "섬 지역 2곳",
    "카드 자료는 2023년 8월부터",
    "이곳은 행사 전 흐름이 비슷합니다",
    "행사 읍면 방문은 {{visit.R_T}} 변했습니다",
    "2024-04-06부터 열렸습니다",
]
BLOCK = ["삼 배", "십오 프로", "곱절로 늘었습니다", "반으로 줄었습니다", "백 명이 더 왔습니다",
         "Ⅲ배", "두어 배", "이십여 곳", "크게 급증했습니다"]


class NumbersTest(unittest.TestCase):
    def test_normal_sentences_pass(self):
        for text in PASS:
            with self.subTest(text=text):
                self.assertEqual(check_numbers(text, "reason", FACTS), [])

    def test_violations_blocked_in_result(self):
        for text in BLOCK:
            with self.subTest(text=text):
                self.assertTrue(check_numbers(text, "result", FACTS))

    def test_unknown_blank_and_ungrounded_number(self):
        self.assertTrue(check_numbers("{{visit.avg}} 늘었습니다", "reason", FACTS))
        self.assertTrue(check_numbers("방문객이 37명 늘었습니다", "reason", FACTS))
        self.assertTrue(check_numbers("2024년 5월 3일에", "reason", FACTS))

    def test_slash_dates_and_event_ids_from_input(self):
        facts = dict(FACTS, ids={"244"})
        # 실제 판단 단계 제출에서 오탐이 났던 형식(11/14 와흘 실행)
        self.assertEqual(check_numbers("증가가 4/6~4/12 주말에 몰렸다", "reason", facts), [])
        self.assertEqual(check_numbers("선샤인(event_id 244)이 있다", "reason", facts), [])
        self.assertEqual(check_numbers("다른 행사(3/2~6/29)가 겹친다", "reason", facts), [])
        self.assertTrue(check_numbers("5/3에 몰렸다", "reason", facts))
        self.assertTrue(check_numbers("event_id 999", "reason", facts))
        self.assertEqual(check_numbers("생태관광 프로그램이 겹친다", "reason", facts), [])

    def test_shortened_dates_and_bare_ids_from_input(self):
        facts = dict(FACTS, ids={"244"})
        # 11/15 혼인지 실행에서 판단 단계가 제출 3번을 모두 돌려받은 형식
        self.assertEqual(check_numbers("다른 행사(2024-04-06~04-28)가 겹친다", "reason", facts), [])
        self.assertEqual(check_numbers("4월 6~9일 상승", "reason", facts), [])
        self.assertEqual(check_numbers("신석기 행사(244)가 있다", "reason", facts), [])
        self.assertTrue(check_numbers("2024-04-06~05-03에 몰렸다", "reason", facts))
        self.assertTrue(check_numbers("4월 6~30일 상승", "reason", facts))
        self.assertTrue(check_numbers("244명이 왔다", "reason", facts))
        self.assertIn("'두어'는", check_numbers("두어 곳", "reason", facts)[0])

    def test_ranks_month_codes_and_years_from_input(self):
        facts = dict(FACTS, ranks={1, 2, 3, 4})
        # 11/16 가파도 실행: 후보 4곳, 계획 단계 method에 연월 코드와 연도
        self.assertEqual(check_numbers("구좌읍은 4순위 후보다", "reason", facts), [])
        self.assertEqual(check_numbers("기준 기간 202401~202403과 2023년 말을 본다", "method", facts), [])
        self.assertTrue(check_numbers("5순위 후보", "reason", facts))
        self.assertTrue(check_numbers("202405에 늘었다", "method", facts))
        self.assertTrue(check_numbers("2019년에 늘었다", "method", facts))

    def test_dates_survive_names_that_start_with_a_year(self):
        # 11/16 가파도 실행: 같은 시기 행사 「2024 JEJU MUSIC WEEKEND」의 조각 '2024'가 날짜를 깨뜨렸다
        from agent import name_variants
        facts = dict(FACTS, names=FACTS["names"] + name_variants("2024 JEJU MUSIC WEEKEND") + name_variants("9.81파크 축제"))
        self.assertEqual(check_numbers("축제가 2024-04-28 하루 열렸다", "reason", facts), [])
        self.assertEqual(check_numbers("행사 기간(2024-04-06~2024-04-28)", "reason", facts), [])
        self.assertEqual(check_numbers("2024 JEJU MUSIC WEEKEND는 장기 행사다", "reason", facts), [])
        self.assertEqual(check_numbers("9.81파크에서 열렸다", "reason", facts), [])

    def test_date_ranges_with_shortened_end_day(self):
        # 11/16 가파도 실행: 같은 시기 행사를 「2024-04-13~14」로 써서 '14'가 걸렸다
        self.assertEqual(check_numbers("고사리축제(2024-04-13~14)가 열렸다", "reason", FACTS), [])
        self.assertEqual(check_numbers("4/13~14에 열렸다", "reason", FACTS), [])
        self.assertEqual(check_numbers("04-13~14에 열렸다", "reason", FACTS), [])
        self.assertTrue(check_numbers("2024-04-13~30에 열렸다", "reason", FACTS))
        self.assertTrue(check_numbers("4/13~30에 열렸다", "reason", FACTS))

    def test_method_allows_two_times_rule(self):
        self.assertEqual(check_numbers("평소 흔들림의 2배 안이면 통과", "method", FACTS), [])


if __name__ == "__main__":
    unittest.main()
