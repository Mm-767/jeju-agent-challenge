"""장소 추정 단계를 녹음한 가짜 응답으로 시험한다(외부 호출 없음)."""
import datetime as dt
import json
import unittest

import agent
import config

EVENTS = [
    {"event_id": str(i), "name": f"행사{i}", "start": dt.date(2024, 4, 1), "end": dt.date(2024, 4, 10), "host": ""}
    for i in (1, 2)
]


def place(i, where="대정읍"):
    return {"event_id": i, "place": where, "spot": "", "kind": "축제", "confidence": "중간", "reason": "이름"}


def tool_use(uid, places, name="submit_place_table"):
    return {"type": "tool_use", "id": uid, "name": name, "input": {"places": places}}


class FakeCall:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, purpose, body, timeout=None):
        self.requests.append(body)
        return {"content": self.replies.pop(0), "usage": {}, "stop_reason": "tool_use"}


class PlacesTest(unittest.TestCase):
    def test_pass_first_time(self):
        call = FakeCall([[tool_use("a", [place("1"), place("2")])]])
        table, attempts = agent.estimate_places(EVENTS, call)
        self.assertEqual(attempts, [1])
        self.assertEqual(table["2"]["place"], "대정읍")

    def test_missing_id_fixed_on_second_try(self):
        call = FakeCall([
            [{"type": "text", "text": "제출합니다."}, tool_use("a", [place("1")])],
            [tool_use("b", [place("1"), place("2")])],
        ])
        table, attempts = agent.estimate_places(EVENTS, call)
        self.assertEqual(attempts, [2])
        second = call.requests[1]["messages"]
        self.assertEqual(second[-2]["role"], "assistant")
        results = second[-1]["content"]
        self.assertEqual([r["tool_use_id"] for r in results], ["a"])
        self.assertTrue(results[0]["is_error"])
        self.assertIn("2", results[0]["content"])

    def test_every_tool_use_gets_a_result(self):
        call = FakeCall([
            [tool_use("x", [], name="other_tool"), tool_use("y", [place("1")])],
            [tool_use("z", [place("1"), place("2")])],
        ])
        agent.estimate_places(EVENTS, call)
        ids = [r["tool_use_id"] for r in call.requests[1]["messages"][-1]["content"]]
        self.assertEqual(ids, ["x", "y"])

    def test_text_only_then_tool(self):
        call = FakeCall([[{"type": "text", "text": "추정 결과는…"}], [tool_use("a", [place("1"), place("2")])]])
        _, attempts = agent.estimate_places(EVENTS, call)
        self.assertEqual(attempts, [2])
        self.assertIn("도구로 제출", call.requests[1]["messages"][-1]["content"])

    def test_three_failures_become_unknown(self):
        call = FakeCall([[tool_use(str(n), [place("1")])] for n in range(3)])
        table, attempts = agent.estimate_places(EVENTS, call)
        self.assertEqual(attempts, [3])
        self.assertEqual({p["place"] for p in table.values()}, {"모름"})
        self.assertEqual(len(call.requests), 3)



import calc  # noqa: E402
import card  # noqa: E402
from pathlib import Path  # noqa: E402

REHEARSAL = sorted((Path(__file__).resolve().parent.parent / "data" / "dummy" / "card_rehearsal").glob("*.csv"))
GAPADO = (dt.date(2024, 4, 6), dt.date(2024, 4, 28))


class RehearsalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = card.new_table()
        for f in REHEARSAL:
            card.ingest(f.read_bytes(), f.name, cls.table)
        cls.codes = sorted(agent.BIZ_NAMES)

    def test_gapado_rehearsal_runs_and_finds_planted_effect(self):
        problems, result, widened = calc.rehearse(self.table, "대정읍", ["한경면", "구좌읍"], *GAPADO,
                                                  ["I56111", "I56220"], self.codes, {})
        self.assertEqual(problems, [])
        self.assertEqual(result["outcome"], "higher")
        self.assertEqual(result["emd"], "한경면")

    def test_no_comparison_is_a_problem(self):
        problems, result, _ = calc.rehearse(self.table, "대정읍", [], *GAPADO, [], self.codes, {})
        self.assertTrue(problems)
        self.assertEqual(result["outcome"], "not_computed")


def plan_ctx():
    return {
        "event": {"event_id": "363", "name": "가파도청보리축제", "start": "2024-04-06", "end": "2024-04-28", "emd": "대정읍"},
        "months": calc.months_for(*GAPADO),
        "ranked": [{"emd": "한경면", "distance": 0.05}, {"emd": "구좌읍", "distance": 0.06}],
        "rule_excluded": [], "other_events": [], "festival_months": {},
    }


def good_plan():
    return {
        "biz_bundle": "먹거리·음료 중심", "biz_reason": "꽃 축제라 음식점 소비를 본다.",
        "result_sentences": {
            "higher": "{{행사_이름}} 기간 {{행사_읍면}}의 관광객 카드 소비는 {{비교_읍면}}보다 {{차이}} 더 늘었습니다.",
            "lower": "{{행사_이름}} 기간 {{행사_읍면}}의 관광객 카드 소비는 {{비교_읍면}}보다 {{차이}} 덜 늘었습니다.",
            "no_difference": "{{비교_읍면}}과 비교한 차이는 평소에도 생기는 크기였습니다.",
            "not_computed": "{{계산_못한_이유}} 때문에 계산하지 못했습니다.",
        },
        "method": "행사 직전 3개월을 기준으로 행사 달의 증가율을 비교 읍면과 견줬습니다.",
        "extra_limits": [],
    }


class PlanStageTest(unittest.TestCase):
    def judgement(self, kept):
        return {"ok": True, "input": {"kept": [{"emd": k, "reason": ""} for k in kept]}, "pending": []}

    def test_too_few_candidates_stops_without_calling(self):
        call = FakeCall([])
        result, _ = agent.plan(plan_ctx(), self.judgement(["한경면"]), [], call, lambda *a: None, lambda i: [])
        self.assertEqual(result["why"], "too_few_candidates")
        self.assertEqual(call.requests, [])

    def test_missing_blank_then_fixed(self):
        bad = good_plan()
        bad["result_sentences"]["higher"] = "{{행사_읍면}}의 소비가 더 늘었습니다."
        call = FakeCall([[{"type": "tool_use", "id": "p1", "name": "submit_plan", "input": bad}],
                         [{"type": "tool_use", "id": "p2", "name": "submit_plan", "input": good_plan()}]])
        result, kept = agent.plan(plan_ctx(), self.judgement(["한경면", "구좌읍"]), [], call, lambda *a: None, lambda i: [])
        self.assertTrue(result["ok"])
        self.assertEqual(result["submits"], 2)
        self.assertEqual(kept, ["한경면", "구좌읍"])
        # 마지막은 통과한 응답이고, 그 앞이 첫 제출을 돌려보낸 tool_result다
        error = call.requests[1]["messages"][-2]["content"][0]["content"]
        self.assertIn("{{차이}}", error)

    def test_causal_word_blocked(self):
        bad = good_plan()
        bad["result_sentences"]["higher"] = "{{비교_읍면}}보다 {{차이}} 늘어 축제 덕분임이 입증되었습니다."
        problems = agent.validate_plan(bad, plan_ctx(), set(), lambda i: [])
        self.assertTrue(any("인과" in p for p in problems))

    def test_blanks_known_after_calculation_only_in_result_sentences(self):
        ok = dict(good_plan(), biz_reason="{{행사_이름}}은 꽃 축제라 음식점 소비를 본다.",
                  extra_limits=["{{행사_기간}}에 연휴가 겹쳤다."])
        self.assertEqual(agent.validate_plan(ok, plan_ctx(), set(), lambda i: []), [])
        bad = dict(good_plan(), method="{{비교_읍면}}과 증가율을 견줬다.")
        problems = agent.validate_plan(bad, plan_ctx(), set(), lambda i: [])
        self.assertTrue(problems and problems[0].startswith("method"), problems)

    def test_bundle_fills_blanks_outside_result_sentences(self):
        # 11/15 보롬왓 측정 실행: biz_reason에 쓴 {{행사_이름}}이 화면과 보고서에 그대로 보였다
        import pipeline

        ctx = dict(plan_ctx(), visit={"R_T": 0.207, "R_C": 0.136, "V": None, "missing_days": 0})
        judgement = {"visit": {"judgement": "증가 약함", "evidence": ["R_T"], "reason": "변화는 {{visit.R_T}}다.", "caution": "{{visit.V}}"},
                     "kept": [{"emd": "한경면", "reason": "{{행사_읍면}}과 흐름이 비슷하다."}],
                     "extra_excluded": [{"emd": "구좌읍", "event_id": "", "reason": "방문이 {{visit.R_C}} 움직였다."}],
                     "treated_month_other_events": []}
        plan = dict(good_plan(), biz_reason="{{행사_이름}}은 꽃 축제다.", extra_limits=["{{행사_기간}}에 연휴가 있다."])
        j, p = pipeline.fill_known(ctx, judgement, plan)
        self.assertEqual(j["visit"]["reason"], "변화는 +20.7%다.")
        self.assertEqual(j["visit"]["caution"], "값 없음")
        self.assertEqual(j["kept"][0]["reason"], "대정읍과 흐름이 비슷하다.")
        self.assertEqual(j["extra_excluded"][0]["reason"], "방문이 +13.6% 움직였다.")
        self.assertEqual(p["biz_reason"], "가파도청보리축제는 꽃 축제다.")
        self.assertEqual(p["extra_limits"], ["2024년 4월 6일~4월 28일에 연휴가 있다."])
        self.assertEqual(p["result_sentences"], good_plan()["result_sentences"])
        self.assertIn("{{", judgement["visit"]["reason"])

    def test_rehearsal_problem_returned(self):
        problems = agent.validate_plan(good_plan(), plan_ctx(), set(), lambda i: ["리허설 실패"])
        self.assertEqual(problems, ["리허설 실패"])


class BizBundleTest(unittest.TestCase):
    def test_bundles_use_known_codes_and_match_tool_enum(self):
        tools = json.loads((config.PROMPTS / "tools.json").read_text(encoding="utf-8"))
        enum = tools["submit_plan"]["input_schema"]["properties"]["biz_bundle"]["enum"]
        self.assertEqual(enum, list(agent.BIZ_BUNDLES))
        for name, codes in agent.BIZ_BUNDLES.items():
            self.assertEqual(len(codes), len(set(codes)), name)
            self.assertTrue(set(codes) <= set(agent.BIZ_NAMES), name)


if __name__ == "__main__":
    unittest.main()
