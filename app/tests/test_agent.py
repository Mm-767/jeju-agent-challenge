"""장소 추정 단계를 녹음한 가짜 응답으로 시험한다(외부 호출 없음)."""
import datetime as dt
import unittest

import agent

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


if __name__ == "__main__":
    unittest.main()
