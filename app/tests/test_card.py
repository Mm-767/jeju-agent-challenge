"""계획서 3-6절 센터 CSV 처리 규칙의 고정 파일 시험. 가상 CSV 두 달치에서 변형을 만든다."""
import csv
import io
import unittest
from pathlib import Path

import card

DUMMY = sorted((Path(__file__).resolve().parent.parent / "data" / "dummy" / "card_effect").glob("*.csv"))


def rows_of(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def to_bytes(rows, quoting=csv.QUOTE_ALL, encoding="utf-8"):
    buf = io.StringIO()
    csv.writer(buf, quoting=quoting).writerows(rows)
    return buf.getvalue().encode(encoding)


A = rows_of(DUMMY[0])
B = rows_of(DUMMY[1])
HEADER = A[0]


def load(*files):
    table = card.new_table()
    results = [card.ingest(data, name, table) for name, data in files]
    return table, results


class IngestTest(unittest.TestCase):
    def test_spec_file_ok(self):
        table, (r,) = load(("a.csv", to_bytes(A)))
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["months"]), 1)
        self.assertTrue(table["cells"])

    def test_two_months_in_one_file_equals_two_files(self):
        one, (r,) = load(("ab.csv", to_bytes(A + B[1:])))
        two, _ = load(("a.csv", to_bytes(A)), ("b.csv", to_bytes(B)))
        self.assertEqual(len(r["months"]), 2)
        self.assertEqual(one["cells"], two["cells"])

    def test_same_file_twice_rejected_and_table_unchanged(self):
        table, (r1, _) = load(("a.csv", to_bytes(A)), ("a2.csv", to_bytes(A)))
        before = {k: list(v) for k, v in table["cells"].items()}
        r2 = card.ingest(to_bytes(A), "a3.csv", table)
        self.assertTrue(r1["ok"])
        self.assertEqual(r2["problem"], "duplicate_month")
        self.assertIn("a.csv", r2["message"])
        self.assertEqual(table["cells"], before)

    def test_duplicated_row_rejected(self):
        eup = next(r for r in A[1:] if r[4] == "대정읍")
        _, (r,) = load(("dup.csv", to_bytes(A + [eup])))
        self.assertEqual(r["problem"], "duplicate_row")

    def test_missing_emd_rows_reported(self):
        no_daejeong = [r for r in A if r[4] != "대정읍"]
        table, (r,) = load(("nodj.csv", to_bytes(no_daejeong)))
        self.assertTrue(r["ok"])
        ym = r["months"][0]
        cov = card.check_coverage(table, [ym, "209901"], ["대정읍", "표선면"])
        self.assertEqual(cov["missing_rows"], [(ym, "대정읍")])
        self.assertEqual(cov["missing_months"], ["209901"])

    def test_na_counted_as_blank(self):
        idx = HEADER.index("use_amt")
        rows = [list(r) for r in A]
        target = next(r for r in rows[1:] if r[4] == "대정읍" and r[8] in card.TOURIST)
        target[idx] = "NA"
        table, (r,) = load(("na.csv", to_bytes(rows)))
        self.assertTrue(r["ok"])
        self.assertEqual(r["blank_cells"], 1)
        self.assertEqual(table["cells"][(target[4], target[0], target[5])][3], 1)

    def test_bom_accepted(self):
        bom = b"\xef\xbb\xbf" + to_bytes(A)
        plain, _ = load(("a.csv", to_bytes(A)))
        withbom, (r,) = load(("bom.csv", bom))
        self.assertTrue(r["ok"])
        self.assertEqual(withbom["cells"], plain["cells"])

    def test_cp949_rejected(self):
        _, (r,) = load(("excel.csv", to_bytes(A, encoding="cp949")))
        self.assertEqual(r["problem"], "excel")

    def test_reordered_unquoted_and_partition_columns(self):
        order = list(reversed(range(len(HEADER))))
        rows = [[r[i] for i in order] + (["pt_year"] if n == 0 else ["2024"]) for n, r in enumerate(A)]
        plain, _ = load(("a.csv", to_bytes(A)))
        odd, (r,) = load(("odd.csv", to_bytes(rows, quoting=csv.QUOTE_MINIMAL)))
        self.assertTrue(r["ok"], r)
        self.assertEqual(odd["cells"], plain["cells"])

    def test_missing_column_rejected(self):
        rows = [r[:-1] for r in A]
        _, (r,) = load(("cut.csv", to_bytes(rows)))
        self.assertEqual(r["problem"], "format")

    def test_messages_have_no_cell_values(self):
        marker = "987654321"
        idx = HEADER.index("use_amt")
        rows = [list(r) for r in A]
        # 계산에 쓰는 행(읍면 관광객)만 숫자를 읽으므로 그런 행을 고장 낸다
        target = next(r for r in rows[1:] if r[4] in card.EUP_MYEON and r[8] in card.TOURIST)
        target[idx] = marker + "x"
        dup = [list(r) for r in A]
        dup_target = next(r for r in dup[1:] if r[4] in card.EUP_MYEON)
        dup_target[idx] = marker
        broken = [
            ("bad_number.csv", to_bytes(rows)),
            ("excel.csv", to_bytes(rows, encoding="cp949")),
            ("dup.csv", to_bytes(dup + [dup_target])),
        ]
        for name, data in broken:
            r = card.ingest(data, name, card.new_table())
            self.assertFalse(r["ok"])
            self.assertNotIn(marker, r["message"])


if __name__ == "__main__":
    unittest.main()
