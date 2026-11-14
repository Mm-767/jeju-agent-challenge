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

    def test_method_allows_two_times_rule(self):
        self.assertEqual(check_numbers("평소 흔들림의 2배 안이면 통과", "method", FACTS), [])


if __name__ == "__main__":
    unittest.main()
