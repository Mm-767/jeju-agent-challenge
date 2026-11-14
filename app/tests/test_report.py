"""가상 데이터로 가파도 결과물(문장, 그림 2장, PDF)을 끝까지 만든다."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

import agent
import calc
import card
import report
from test_agent import GAPADO, REHEARSAL, good_plan


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = card.new_table()
        for f in REHEARSAL:
            card.ingest(f.read_bytes(), f.name, cls.table)
        cls.codes = sorted(agent.BIZ_NAMES)
        cls.event = {"name": "가파도청보리축제", "start": GAPADO[0], "end": GAPADO[1]}
        cls.months = calc.months_for(*GAPADO)
        _, cls.result, cls.widened = calc.rehearse(cls.table, "대정읍", ["한경면", "구좌읍"], *GAPADO,
                                                   ["I56111"], cls.codes, {})

    def test_sentence_filled_without_leftover_blank(self):
        vals = report.values(self.event, "대정읍", self.result, self.months)
        text = report.fill(good_plan()["result_sentences"][self.result["outcome"]], vals)
        self.assertNotIn("{", text)
        self.assertIn("한경면", text)
        self.assertIn(report.pct(self.result["E"]), text)
        self.assertIn("번이었다.", report.strength(self.result))
        with self.assertRaises(KeyError):
            report.fill("{{없는_빈칸}}", vals)

    def test_usage_reason_complete(self):
        need = calc.required_months(self.months)["all"]
        text = report.usage_reason(self.event, need, "결과보고서")
        self.assertNotIn("{", text)
        self.assertIn("가파도청보리축제(2024년 4월 6일~4월 28일)", text)

    def test_charts_and_pdf(self):
        biz = self.widened[self.result["emd"]]
        t = calc.series(self.table, "대정읍", biz)
        c = calc.series(self.table, self.result["emd"], biz)
        days = {GAPADO[0] - dt.timedelta(40) + dt.timedelta(n): 1000 + (n % 7) * 50 for n in range(80)}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report.index_chart(t, c, self.months, "대정읍", self.result["emd"], out / "index.png", example=True)
            report.visit_chart(days, days, *GAPADO, "대정읍", self.result["emd"], out / "visit.png")
            rows = report.evidence_rows(self.result, len(biz))
            report.pdf(out / "result.pdf", "가파도청보리축제 관광객 카드 소비 비교", "예시 문장입니다.",
                       [out / "index.png", out / "visit.png"], rows, [("업종 범위 이유", "꽃 축제")], report.LIMITS)
            self.assertTrue((out / "result.pdf").read_bytes().startswith(b"%PDF"))
            self.assertEqual(report.export_check(out), [])
            (out / "notes.txt").write_text("x")
            self.assertEqual(report.export_check(out), ["notes.txt"])
        self.assertTrue(all("원" not in v for _, v in rows))



class JosaTest(unittest.TestCase):
    def test_particles_follow_filled_value(self):
        vals = {"행사_이름": "가파도청보리축제", "행사_읍면": "대정읍", "차이": "+24.9%", "비교_읍면": "성산읍"}
        self.assertEqual(report.fill("{{행사_이름}}이 열린 {{행사_읍면}}은", vals), "가파도청보리축제가 열린 대정읍은")
        self.assertEqual(report.fill("{{비교_읍면}}과 비교해 {{차이}}를", vals), "성산읍과 비교해 +24.9%를")
        self.assertEqual(report.fill("{{행사_이름}}으로", vals), "가파도청보리축제로")
        self.assertEqual(report.fill("{{행사_읍면}}로", vals), "대정읍으로")


if __name__ == "__main__":
    unittest.main()
