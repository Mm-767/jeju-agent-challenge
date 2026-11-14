"""표시값 자가 점검과 센터 단계를 가파도 계획 묶음으로 끝까지 돌린다(외부 호출 없음)."""
import unittest

import egress
import selfcheck
from test_agent import good_plan


def gapado_bundle():
    p = good_plan()
    return {
        "event": {"event_id": "363", "name": "가파도청보리축제", "start": "2024-04-06", "end": "2024-04-28", "emd": "대정읍"},
        "festival_months": {}, "kept": ["한경면", "구좌읍"],
        "judgement": {"visit": {"judgement": "증가 뚜렷"}, "extra_excluded": []},
        "plan": {"biz_codes": p["biz_codes"], "biz_reason": p["biz_reason"]},
        "texts": {"result_sentences": p["result_sentences"], "method": p["method"], "extra_limits": []},
    }


class SelfCheckTest(unittest.TestCase):
    def test_all_items_pass_and_lock_released(self):
        rows = selfcheck.run(gapado_bundle())
        failed = [(item, detail) for item, ok, detail in rows if not ok]
        self.assertEqual(failed, [])
        self.assertFalse(egress.is_locked())
        self.assertEqual(len(rows), 7)


if __name__ == "__main__":
    unittest.main()
