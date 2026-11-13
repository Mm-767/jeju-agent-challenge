"""센터 「카드 이용 현황(읍면동)_v02」 형식 그대로의 가상 CSV를 만든다.

효과를 심은 판(effect)과 심지 않은 판(none)을 같은 난수로 만들어, 두 판은 EFFECTS 칸만 다르다.
값은 전부 가상이며 실제 통계가 아니다.
"""
import csv
import json
import random
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
SEED = 20261113
# 리허설용 판은 다른 난수로 만들어, 예시용 판의 값이 리허설 결과로 외부에 나갈 수 없게 한다
REHEARSAL_SEED = 20261114

# (읍면, 연월) -> 관광객(개별·단체) 이용 증가율. 행사 파일에 그 읍면 축제가 있는 달에만 심는다(ADR-152).
EFFECTS = {
    ("대정읍", "202404"): 0.30,  # 가파도청보리축제
    ("표선면", "202503"): 0.15, ("표선면", "202504"): 0.20,  # 보롬왓 튤립축제
    ("안덕면", "202403"): 0.20,  # 마노르블랑 봄에 꽃향기축제
    ("성산읍", "202406"): 0.20,  # 혼인지 수국 축제
    ("조천읍", "202410"): 0.20,  # 자청비 와흘메밀문화제
    ("애월읍", "202410"): 0.25, ("애월읍", "202411"): 0.25,  # 억새바당, 같은 달 제외 장면용
}

CITY = {
    "한림읍": ("제주시", "제주시 서부"), "애월읍": ("제주시", "제주시 서부"),
    "한경면": ("제주시", "제주시 서부"), "구좌읍": ("제주시", "제주시 동부"),
    "조천읍": ("제주시", "제주시 동부"), "우도면": ("제주시", "제주시 동부"),
    "추자면": ("제주시", "제주시 중부(서)"),
    "대정읍": ("서귀포시", "서귀포시 서부"), "안덕면": ("서귀포시", "서귀포시 서부"),
    "남원읍": ("서귀포시", "서귀포시 동부"), "성산읍": ("서귀포시", "서귀포시 동부"),
    "표선면": ("서귀포시", "서귀포시 동부"),
    "노형동": ("제주시", "제주시 중부(서)"), "건입동": ("제주시", "제주시 중부(동)"),
}
# 지역 규모(가상). 작은 섬 지역은 10 미만 칸이 자주 생긴다.
SIZE = {
    "한림읍": 1.0, "애월읍": 1.3, "한경면": 0.4, "구좌읍": 0.8, "조천읍": 0.9,
    "우도면": 0.15, "추자면": 0.06, "대정읍": 0.7, "안덕면": 0.8, "남원읍": 0.8,
    "성산읍": 1.1, "표선면": 0.6, "노형동": 2.5, "건입동": 1.2,
}
BIZ = [
    "I56111", "I56220", "I55111", "I55113", "G47122", "G47121",
    "L69110", "G47842", "I56114", "R91239", "G47711", "I56219",
]
TICKET = {"I55111": 180000, "I55113": 150000, "L69110": 90000, "R91239": 40000, "G47711": 60000}
GROUPS = [  # (user_type, tour_type, 상대 규모)
    ("제주도민", "도민", 1.0), ("내국인", "개별", 0.9), ("내국인", "단체", 0.2),
    ("중국", "개별", 0.12), ("일본", "개별", 0.05),
]
AGES = ["20", "30", "40", "50", "60", "70"]
SEASON = {1: 0.8, 2: 0.85, 3: 0.95, 4: 1.0, 5: 1.05, 6: 1.0, 7: 1.25, 8: 1.35, 9: 1.0, 10: 1.1, 11: 0.9, 12: 0.85}


def months():
    y, m = 2023, 8
    while (y, m) <= (2026, 8):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def build_rows(spec, variant, seed=SEED):
    biz_names = spec["codes"]["biz"]
    rng = random.Random(seed)
    # 칸 존재 여부를 한 번만 정해 모든 달에 같은 칸이 나오게 한다(패널 구조)
    cells = []
    for bjd in CITY:
        for biz in BIZ:
            for user_type, tour_type, share in GROUPS:
                for age in AGES:
                    for sex in ("남성", "여성"):
                        if rng.random() < 0.35:
                            cells.append((bjd, biz, user_type, tour_type, share, age, sex))
            if rng.random() < 0.5:
                cells.append((bjd, biz, "법인", "NA", 0.3, "NA", "알수없음"))

    out = {}
    for y, m in months():
        ym = f"{y}{m:02d}"
        trend = 1.0 - 0.04 * (y - 2024)  # 내국인 관광이 해마다 조금씩 준다(가상)
        common = rng.uniform(0.97, 1.03)  # 모든 지역이 함께 겪는 달별 흔들림
        rows = []
        for bjd, biz, user_type, tour_type, share, age, sex in cells:
            city, dstrct = CITY[bjd]
            tourist = tour_type in ("개별", "단체")
            base = 60 * SIZE[bjd] * share * common * rng.uniform(0.9, 1.1)
            if tourist:
                base *= SEASON[m] * trend
            if variant in ("effect", "rehearsal") and tourist:
                base *= 1 + EFFECTS.get((bjd, ym), 0)
            user_cnt = max(1, round(base))
            use_cnt = max(user_cnt, round(user_cnt * rng.uniform(1.1, 1.5)))
            use_amt = round(use_cnt * TICKET.get(biz, 15000) * rng.uniform(0.8, 1.2))
            rows.append([
                ym, dstrct, city, "도심" if bjd.endswith("동") else "읍면", bjd,
                biz, biz_names[biz], user_type, tour_type, age, sex,
                user_cnt, use_cnt, use_amt,
            ])
        out[ym] = rows
    return out


def write(out_dir, spec, rows_by_month):
    out_dir.mkdir(parents=True, exist_ok=True)
    header = [c["name"] for c in spec["csv_columns"]]
    for i, (ym, rows) in enumerate(sorted(rows_by_month.items())):
        # 실제 파일명은 다운로드 시각이다. 연월은 base_year_month로만 알 수 있다.
        name = f"Results_20261113_{9 + i // 60:02d}{i % 60:02d}{(i * 7) % 60:02d}.csv"
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(header)
            w.writerows(rows)


def check(spec, effect, none):
    assert effect.keys() == none.keys()
    diff = set()
    for ym in effect:
        for a, b in zip(effect[ym], none[ym]):
            if a != b:
                assert a[8] in ("개별", "단체"), a
                diff.add((a[4], ym))
    assert diff and diff <= set(EFFECTS), diff - set(EFFECTS)
    small = sum(1 for rows in none.values() for r in rows if r[11] < 10)
    assert small > 0
    return small


if __name__ == "__main__":
    spec = json.loads((APP / "spec" / "card_v02.json").read_text(encoding="utf-8"))
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else APP / "data" / "dummy"
    effect = build_rows(spec, "effect")
    none = build_rows(spec, "none")
    rehearsal = build_rows(spec, "rehearsal", REHEARSAL_SEED)
    small = check(spec, effect, none)
    assert rehearsal["202404"] != effect["202404"]
    write(root / "card_effect", spec, effect)
    write(root / "card_none", spec, none)
    write(root / "card_rehearsal", spec, rehearsal)
    n = sum(len(r) for r in none.values())
    print(f"ok months={len(none)} rows_per_variant={n} cells_under_10={small}")
