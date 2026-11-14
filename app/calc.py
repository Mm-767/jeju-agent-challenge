"""PC 안에서만 도는 계산. 센터 값에서 나온 숫자는 이 모듈 밖 외부 전송으로 가지 않는다.

시계열은 {"YYYYMM": 값} 사전이다. 표준 라이브러리만 쓴다.
"""
import calendar
import datetime as dt
import math
import statistics

# 카드 수록 기간(명세서 1-08)
FIRST = "202308"
LAST = "202608"

EVENT_SHARE = 0.5
MIN_PLACEBO = 9
P_STRONG = 0.1
MIN_DISTANCE_MONTHS = 6


def shift(ym, k):
    y, m = divmod(int(ym[:4]) * 12 + int(ym[4:]) - 1 + k, 12)
    return f"{y}{m + 1:02d}"


def coverage():
    out = []
    cur = FIRST
    while cur <= LAST:
        out.append(cur)
        cur = shift(cur, 1)
    return out


def overlap(start, end):
    """달마다 걸침 비중 = 그 달에 든 행사 일수 / 그 달 일수."""
    counts = {}
    day = start
    while day <= end:
        ym = f"{day.year}{day.month:02d}"
        counts[ym] = counts.get(ym, 0) + 1
        day += dt.timedelta(days=1)
    # 하루치(1/일수)를 더하면 15/30이 0.4999…가 되어 0.5 기준에서 빠진다
    return {ym: n / calendar.monthrange(int(ym[:4]), int(ym[4:]))[1] for ym, n in counts.items()}


def window(tau):
    return [shift(tau, -3), shift(tau, -2), shift(tau, -1), tau]


def months_for(start, end, blocked=frozenset()):
    """행사 날짜로 계산에 쓸 달을 정한다.

    blocked: 두 읍면 가운데 한 곳이라도 다른 축제가 걸친 달(걸침 0.25 이상). 가짜 시점 달에서 뺀다.
    """
    shares = overlap(start, end)
    event = sorted(m for m, s in shares.items() if s >= EVENT_SHARE)
    diluted = not event
    if diluted:
        event = [max(shares, key=shares.get)]
    first = min(shares)
    base = [shift(first, k) for k in (-3, -2, -1)]
    pretrend = [shift(first, k) for k in (-6, -5, -4)]
    event_month_numbers = {m[4:] for m in shares}
    sigma_window = set(pretrend + base)
    placebo = []
    for tau in coverage():
        four = window(tau)
        if four[0] < FIRST:
            continue
        if any(m[4:] in event_month_numbers for m in four):
            continue
        if any(m in blocked or m in sigma_window for m in four):
            continue
        placebo.append(tau)
    return {
        "event": event,
        "excluded": sorted(m for m in shares if m not in event),
        "base": base,
        "pretrend": pretrend,
        "placebo": placebo,
        "diluted": diluted,
        "in_coverage": pretrend[0] >= FIRST and max(shares) <= LAST,
    }


def distance_months(start, end):
    """비교 읍면 거리를 재는 창: 처음 걸친 달 앞 12개월에서 행사가 걸친 달과 달 숫자가 같은 달을 뺀다."""
    shares = overlap(start, end)
    first = min(shares)
    numbers = {m[4:] for m in shares}
    return [m for m in (shift(first, -k) for k in range(12, 0, -1)) if m[4:] not in numbers]


def distance(v_t, v_c, months):
    """공개 유동인구 월평균의 로그 차이 표준편차. 쓸 수 있는 달이 6개월 미만이면 None."""
    logs = [math.log(v_t[m] / v_c[m]) for m in months if m in v_t and m in v_c]
    if len(logs) < MIN_DISTANCE_MONTHS:
        return None
    return statistics.pstdev(logs)


def rank(v_t, candidates, months, top=3):
    """candidates: {읍면: 월평균}. 거리가 작은 순으로 최대 top곳, 거리를 못 잰 곳은 이유와 함께 따로."""
    scored = []
    skipped = []
    for emd, v_c in candidates.items():
        d = distance(v_t, v_c, months) if v_c is not None else None
        if d is None:
            skipped.append(emd)
        else:
            scored.append((d, emd))
    scored.sort()
    return [(emd, d) for d, emd in scored[:top]], skipped


BASELINE_DAYS = 28
VISIT_MISSING_LIMIT = 0.10


def visit_change(days, start, end):
    """행사 기간 일평균 / 직전 4주 같은 요일 평균 - 1. days는 {날짜: 그날 방문 인구}.

    행사 기간과 직전 4주를 합친 창에서 결측일이 10%를 넘으면 None(판단 불가).
    """
    event = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    base = [start - dt.timedelta(n) for n in range(1, BASELINE_DAYS + 1)]
    window = event + base
    missing = sum(1 for d in window if d not in days)
    if missing > VISIT_MISSING_LIMIT * len(window):
        return None, missing
    by_weekday = {}
    for d in base:
        if d in days:
            by_weekday.setdefault(d.weekday(), []).append(days[d])
    present = [d for d in event if d in days and d.weekday() in by_weekday]
    if not present:
        return None, missing
    actual = statistics.fmean(days[d] for d in present)
    expected = statistics.fmean(statistics.fmean(by_weekday[d.weekday()]) for d in present)
    return actual / expected - 1, missing


def visit_summary(t_days, candidate_days, start, end):
    """행사 읍면 변화 R_T, 후보 읍면 변화의 가운데 값 R_C, 상대 비율 V. 판단은 LLM이 하고 카드 계산을 막지 않는다."""
    r_t, missing = visit_change(t_days, start, end) if t_days else (None, None)
    changes = {}
    for emd, days in candidate_days.items():
        if days:
            r, _ = visit_change(days, start, end)
            if r is not None:
                changes[emd] = r
    r_c = statistics.median(changes.values()) if changes else None
    v = (1 + r_t) / (1 + r_c) - 1 if r_t is not None and r_c is not None else None
    return {"R_T": r_t, "R_C": r_c, "V": v, "candidates": changes, "missing_days": missing}


SMALL = 10


def _cell_small(table, emd, ym, biz):
    cells = [table["cells"].get((emd, ym, b)) for b in biz]
    cells = [c for c in cells if c]
    if not cells:
        return True
    # 인원은 업종을 더하면 같은 사람이 겹치므로 업종별 인원 중 가장 큰 값(하한)을 쓴다
    count = sum(c[1] for c in cells)
    users = max(c[2] for c in cells)
    return count < SMALL or users < SMALL or any(c[3] for c in cells)


def widen(biz, all_codes):
    """계획 범위, 중분류(앞 3자리), 대분류(첫 글자), 전체 순으로 넓힌 업종 범위들."""
    steps = [sorted(biz) if biz else sorted(all_codes)]
    for key in (lambda c: c[:3], lambda c: c[:1]):
        keys = {key(c) for c in steps[-1]}
        wider = sorted(c for c in all_codes if key(c) in keys)
        if wider != steps[-1]:
            steps.append(wider)
    if steps[-1] != sorted(all_codes):
        steps.append(sorted(all_codes))
    return steps


def small_cells(table, emds, months, biz, all_codes):
    """두 읍면의 모든 계산 달에서 10 미만 칸이 없는 가장 좁은 업종 범위. 없으면 (None, 10 미만이 남은 (읍면, 달))."""
    for step in widen(biz, all_codes):
        bad = [(e, m) for e in emds for m in months if _cell_small(table, e, m, step)]
        if not bad:
            return step, []
    return None, bad


LONG_EVENT_DAYS = 92
SHORT_SHARE = 0.25


def feasibility(start, end):
    """장소와 무관한 분석 가능 판정. ("ok"|"diluted"|"unavailable", 이유 코드)."""
    if start is None or end is None:
        return "unavailable", "no_date"
    if end < start:
        return "unavailable", "bad_date"
    if (end - start).days + 1 > LONG_EVENT_DAYS:
        return "unavailable", "long_event"
    top = max(overlap(start, end).values())
    if top < SHORT_SHARE:
        return "unavailable", "short_event"
    if not months_for(start, end)["in_coverage"]:
        return "unavailable", "before_data"
    if top < EVENT_SHARE:
        return "diluted", "diluted"
    return "ok", None


def required_months(months):
    required = set(months["event"] + months["base"] + months["pretrend"])
    for_sigma = {m for tau in months["placebo"] for m in window(tau)} - required
    return {
        "required": sorted(required),
        "for_sigma": sorted(for_sigma),
        "all": sorted(required | for_sigma),
    }


def growth(series, event, base):
    return statistics.fmean(series[m] for m in event) / statistics.fmean(series[m] for m in base) - 1


def effect(t, c, event, base):
    """상대 효과 E와 퍼센트포인트 차이 Δ."""
    g_t = growth(t, event, base)
    g_c = growth(c, event, base)
    return (1 + g_t) / (1 + g_c) - 1, g_t - g_c


def pair_stats(t, c, months, taus):
    """한 비교 읍면에 대한 사전 추세 값 L과 가짜 시점 값 Q 목록."""
    pretrend = effect(t, c, months["base"], months["pretrend"])[0]
    placebo = [effect(t, c, [tau], window(tau)[:3])[0] for tau in taus]
    return {"L": pretrend, "Q": placebo}


def sigma(placebo):
    return statistics.pstdev(placebo)


def pvalue(e, placebo):
    bigger = sum(1 for q in placebo if abs(q) >= abs(e))
    return (1 + bigger) / (1 + len(placebo)), bigger


def choose_outcome(e, placebo, reason=None):
    if reason or len(placebo) < MIN_PLACEBO:
        return "not_computed"
    p, _ = pvalue(e, placebo)
    if p > P_STRONG:
        return "no_difference"
    return "higher" if e > 0 else "lower"


def pick(candidates):
    """거리 순 후보(최대 3곳) 가운데 사전 추세 |L| ≤ 2σ를 처음 통과한 곳을 고른다.

    candidates: [{"emd", "L", "Q"}]. 결과를 보고 후보를 바꾸지 않도록 E는 여기서 보지 않는다.
    """
    tried = []
    for cand in candidates[:3]:
        q = cand["Q"]
        s = sigma(q) if len(q) >= MIN_PLACEBO else None
        ok = s is not None and abs(cand["L"]) <= 2 * s
        tried.append({"emd": cand["emd"], "L": cand["L"], "sigma": s, "J": len(q), "ok": ok})
        if ok:
            return cand, tried
    return None, tried


def analyze(t, comparisons, months):
    """comparisons: [(읍면, 시계열, τ 목록)] 거리 순. 결과 문장 종류까지 정한다."""
    candidates = [
        {"emd": emd, "series": c, **pair_stats(t, c, months, taus)}
        for emd, c, taus in comparisons
    ]
    chosen, tried = pick(candidates)
    if chosen is None:
        return {"outcome": "not_computed", "reason": "no_comparison", "tried": tried}
    e, delta = effect(t, chosen["series"], months["event"], months["base"])
    p, bigger = pvalue(e, chosen["Q"])
    return {
        "outcome": choose_outcome(e, chosen["Q"]),
        "emd": chosen["emd"],
        "E": e,
        "delta": delta,
        "L": chosen["L"],
        "sigma": sigma(chosen["Q"]),
        "J": len(chosen["Q"]),
        "p": p,
        "n": bigger,
        "tried": tried,
    }
