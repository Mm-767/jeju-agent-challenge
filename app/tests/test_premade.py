"""미리 만든 계획은 사람이 확인한 개최 읍면과 같을 때만 쓴다(다르면 다른 읍면으로 계산된다)."""
import unittest

import pipeline


class PremadeTest(unittest.TestCase):
    def test_used_only_for_the_confirmed_emd(self):
        self.assertEqual(pipeline.premade("363", "대정읍")["event"]["emd"], "대정읍")
        self.assertIsNone(pipeline.premade("363", "한림읍"))
        self.assertIsNotNone(pipeline.premade("363"))  # 자가 점검은 읍면 없이 예시 계획을 쓴다

    def test_every_premade_matches_its_file_name(self):
        for path in pipeline.PREMADE.glob("plan_*.json"):
            event_id = path.stem.removeprefix("plan_")
            bundle = pipeline.premade(event_id)
            self.assertEqual(bundle["event"]["event_id"], event_id, path.name)
            self.assertIn(bundle["plan"]["biz_bundle"], ("관광 소비 전체", "먹거리·음료 중심", "숙박·체류 중심", "42개 전체"), path.name)


if __name__ == "__main__":
    unittest.main()
