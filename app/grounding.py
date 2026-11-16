"""LLM이 쓴 글의 숫자 근거 대조(계획서 4-4). 숫자는 그 단계 입력에 같은 종류의 값이 있을 때만 통과한다.

facts: {"dates": {date}, "months": {"YYYYMM"}, "counts": {int}, "names": [str], "codes": {str}, "blanks": {str}, "ids": {str}}
field: "reason"(판단 이유), "result"(결과 문장 틀), "method"(방법 문단). 앞의 둘은 크기·비율 표현을 항상 막는다.
"""
import re
import unicodedata

CONSTANT_SPANS = {("주", 4), ("개월", 3), ("개월", 6), ("개월", 12)}
CONSTANT_NUMBERS = {10}
RANKS = {1, 2, 3}
BOUNDARY_MONTHS = {"202308", "202608"}

NATIVE = {"두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
SINO_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
SINO_UNITS = {"십": 10, "백": 100, "천": 1000, "만": 10000}
COUNT_UNITS = "곳|개|건|명|군데|가지|번"

APPROX = re.compile(r"두어|서너|수십|수백|수천|수만|\d+\s*여\s*(?:곳|개|건|명|일|배)|[일이삼사오육칠팔구십백천만]+여\s*(?:곳|개|건|명|일|배)")
MAGNITUDE = re.compile(
    r"곱절|갑절|반으로|반토막|절반|%|급증|급감|대폭|크게|뚜렷하게"
    r"|(?:\d|[일이삼사오육칠팔구십백])\s*(?:퍼센트|프로)(?!그램|젝트|모션)"
    r"|(?:\d|[일이삼사오육칠팔구십백]|I{1,3}|IV|V|두|세|네)\s*(?:배|할)(?![가-힣])"
)
BLANK = re.compile(r"\{\{([^}]*)\}\}")


def _q(x):
    """'x'은/는. 따옴표 안 마지막 글자의 받침에 맞춘다(숫자는 읽는 소리, 영문은 받침 없음으로 본다)."""
    last = x[-1]
    final = (ord(last) - 0xAC00) % 28 != 0 if "가" <= last <= "힣" else last in "013678"
    return f"'{x}'" + ("은" if final else "는")


def _sino(text):
    total, current = 0, 0
    for ch in text:
        if ch in SINO_DIGITS:
            current = SINO_DIGITS[ch]
        else:
            total += (current or 1) * SINO_UNITS[ch]
            current = 0
    return total + current


def check_numbers(text, field, facts):
    """위반 문장 목록(LLM에게 돌려주는 말). 비어 있으면 통과."""
    problems = []
    text = unicodedata.normalize("NFKC", text)
    for key in BLANK.findall(text):
        if key not in facts.get("blanks", set()):
            problems.append(f"{{{{{key}}}}}는 쓸 수 없는 빈칸입니다.")
    text = BLANK.sub(" ", text)
    for m in APPROX.finditer(text):
        problems.append(f"어림 표현 {_q(m.group(0))} 쓰지 않습니다.")
    if field in ("reason", "result"):
        for m in MAGNITUDE.finditer(text):
            problems.append(f"크기·비율 표현 {_q(m.group(0))} 쓰지 않습니다. 크기는 코드가 채웁니다.")
    for name in sorted(facts.get("names", []), key=len, reverse=True):
        if name:
            text = text.replace(name, " ")
    for code in re.findall(r"[A-Z]\d{2,5}", text):
        if any(c.startswith(code) for c in facts.get("codes", set())):
            text = text.replace(code, " ")

    dates = facts.get("dates", set())
    months = set(facts.get("months", set())) | BOUNDARY_MONTHS
    month_numbers = {int(m[4:]) for m in months} | {d.month for d in dates}
    days = {d.day for d in dates}
    counts = set(facts.get("counts", set()))
    ranks = RANKS | set(facts.get("ranks", set()))
    years = {int(m[:4]) for m in months} | {d.year for d in dates}

    def take(pattern, judge):
        nonlocal text
        for m in list(re.finditer(pattern, text)):
            bad = judge(m)
            if bad:
                problems.append(bad)
        text = re.sub(pattern, " ", text)

    def full_date(m):
        y, mo, d = int(m.group(1)), int(m.group(2)), m.group(3)
        if d:
            ok = any(x.year == y and x.month == mo and x.day == int(d) for x in dates)
        else:
            ok = f"{y}{mo:02d}" in months
        return None if ok else f"{_q(m.group(0))} 입력에 없는 날짜입니다."

    take(r"event_id\s*:?\s*(\d+)", lambda m: None if m.group(1) in facts.get("ids", set())
         else f"{_q(m.group(0))} 입력 목록에 없는 행사 번호입니다.")

    def short_range(m):
        """2024-04-13~14, 4/13~14, 04-13~14: 끝 날만 줄여 쓴 기간. 시작 날짜와 같은 달의 끝 날 둘 다 입력에 있어야 한다."""
        y, mo, d1, d2 = (int(m.group(1)) if m.group(1) else None), int(m.group(2)), int(m.group(3)), int(m.group(4))
        ok = all(any(x.month == mo and x.day == d and (y is None or x.year == y) for x in dates) for d in (d1, d2))
        return None if ok else f"{_q(m.group(0))} 입력에 없는 날짜입니다."

    take(r"(?:(\d{4})-)?(\d{1,2})[-/](\d{1,2})\s*[~∼]\s*(\d{1,2})(?![\d/\-.])", short_range)
    take(r"(?<![\d.])(\d{1,2})/(\d{1,2})(?![\d/])", lambda m: None if any(
        x.month == int(m.group(1)) and x.day == int(m.group(2)) for x in dates) else f"{_q(m.group(0))} 입력에 없는 날짜입니다.")
    take(r"(\d{4})\s*년\s*(\d{1,2})\s*월(?:\s*(\d{1,2})\s*일)?", full_date)
    take(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", lambda m: None if any(
        x.month == int(m.group(1)) and x.day == int(m.group(2)) for x in dates) else f"{_q(m.group(0))} 입력에 없는 날짜입니다.")
    take(r"(\d{1,2})\s*[~∼-]\s*(\d{1,2})\s*월", lambda m: None if {int(m.group(1)), int(m.group(2))} <= month_numbers
         else f"{_q(m.group(0))} 입력에 없는 달입니다.")
    take(r"(\d{1,2})\s*월", lambda m: None if int(m.group(1)) in month_numbers else f"{_q(m.group(0))} 입력에 없는 달입니다.")
    take(r"(\d{1,2})\s*[~∼-]\s*(\d{1,2})\s*일", lambda m: None if {int(m.group(1)), int(m.group(2))} <= days
         else f"{_q(m.group(0))} 입력에 없는 날입니다.")
    take(r"(\d{1,2})\s*일", lambda m: None if int(m.group(1)) in days else f"{_q(m.group(0))} 입력에 없는 날입니다.")
    take(r"(\d+)\s*(주|개월)", lambda m: None if (m.group(2), int(m.group(1))) in CONSTANT_SPANS
         else f"{_q(m.group(0))} 정해진 기간이 아닙니다.")
    take(r"(\d{1,2})\s*순위", lambda m: None if int(m.group(1)) in ranks else f"{_q(m.group(0))} 없는 순위입니다.")
    take(rf"(\d+)\s*({COUNT_UNITS})", lambda m: None if int(m.group(1)) in counts else f"{_q(m.group(0))} 입력에 없는 개수입니다.")
    take(r"(\d{4})-(\d{2})-(\d{2})", lambda m: None if any(
        x.isoformat() == m.group(0) for x in dates) else f"{_q(m.group(0))} 입력에 없는 날짜입니다.")
    take(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)", lambda m: None if m.group(0) in months else f"{_q(m.group(0))} 입력에 없는 달입니다.")
    take(r"(20\d{2})\s*년", lambda m: None if int(m.group(1)) in years else f"{_q(m.group(0))} 입력에 없는 해입니다.")
    take(r"(\d{4})-(\d{2})", lambda m: None if m.group(1) + m.group(2) in months else f"{_q(m.group(0))} 입력에 없는 달입니다.")
    take(r"(?<![\d-])(\d{1,2})-(\d{1,2})(?![\d-])", lambda m: None if any(
        x.month == int(m.group(1)) and x.day == int(m.group(2)) for x in dates) else f"{_q(m.group(0))} 입력에 없는 날짜입니다.")
    take(rf"(?<![가-힣])({'|'.join(NATIVE)})\s*({COUNT_UNITS})", lambda m: None if NATIVE[m.group(1)] in counts
         else f"{_q(m.group(0))} 입력에 없는 개수입니다.")
    # "이곳"처럼 한 글자 수사가 붙어 쓰인 말은 수가 아니므로, 한 글자 수사는 띄어 쓴 경우만 본다
    sino = lambda m: None if _sino(m.group(1)) in counts else f"{_q(m.group(0))} 입력에 없는 개수입니다."  # noqa: E731
    take(rf"(?<![가-힣])([일이삼사오육칠팔구십백천만]{{2,}}|[십백천만])\s*({COUNT_UNITS})", sino)
    take(rf"(?<![가-힣])([일이삼사오육칠팔구])\s+({COUNT_UNITS})", sino)
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        if m.group(0) in facts.get("ids", set()):
            continue
        if not (m.group(0).isdigit() and int(m.group(0)) in counts | CONSTANT_NUMBERS | ranks):
            problems.append(f"숫자 '{m.group(0)}'의 근거가 입력에 없습니다. 빈칸을 쓰세요.")
    return problems
