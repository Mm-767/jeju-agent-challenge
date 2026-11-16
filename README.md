# 행사 효과 나란히

제주 읍면 축제가 열린 달에 개최 읍면의 관광객 카드 소비가 비교 읍면보다 더 늘었는지 계산해, 제주빅데이터센터 반출 신청용 보고서로 만드는 AI Agent입니다. 「제주 AI·빅데이터 활용 AI Agent 개발 챌린지」 출품작입니다.

## 어떻게 동작하나

1. 행사를 고르고 개최 읍면을 확인합니다.
2. AI(Claude Haiku 5.5)가 공개 유동인구와 행사 목록만 보고 계산 계획을 세웁니다. 코드가 AI의 답을 검사하고, 가상 데이터로 미리 돌려 본 뒤에 받습니다.
3. 센터 카드 CSV를 넣는 순간 외부 연결이 잠기고, 계산은 그 PC 안에서 코드가 합니다. AI는 센터 카드 값을 보지 않습니다.
4. 결론부터 쓰는 보고서 PDF, 그림 2장, 반출 신청용 활용 사유가 나옵니다.

## 실행

- **센터 PC(윈도우).** 제출용 묶음에 Python과 패키지가 모두 들어 있습니다. 압축을 풀고 `install.bat`, `run.bat` 순서로 실행합니다. 자세한 순서는 [사용자 매뉴얼](docs/manual_ko.pdf)에 있습니다.
- **소스에서(개발용).** Python 3.11에서 아래처럼 실행합니다. AI 계획을 쓰려면 환경변수 `ANTHROPIC_API_KEY`가 필요하고, 없으면 미리 만든 계획으로 동작합니다.

```
cd app
python -m venv .venv && .venv/bin/pip install -r requirements.in
.venv/bin/python tools/make_dummy_card.py      # 예시용 가상 카드 데이터
.venv/bin/python -X utf8 server.py             # http://127.0.0.1:18501
.venv/bin/python -m unittest discover -s tests # 자동 시험
```

## 문서

- [기획서](docs/proposal/proposal.pdf)
- [사용자 매뉴얼](docs/manual_ko.pdf)
- [데이터 활용 명세](docs/data_spec_ko.pdf)
- [결과 설명자료](docs/result_ko.pdf)

## 폴더

| 폴더 | 내용 |
|---|---|
| `app/` | 프로그램(서버, 계산, AI 단계, 화면), 지시문, 자동 시험, 묶음 만드는 도구 |
| `app/data/` | 동봉한 공개 자료(제주데이터허브 유동인구·주요행사정보)와 미리 만든 계획 |
| `.github/` | 윈도우에서 묶음을 풀어 설치부터 자가 점검까지 돌리는 자동 시험 |
| `docs/` | 기획서, 매뉴얼, 데이터 명세, 결과 설명자료, 시연 영상 스크립트 |
| `qa/` | AI 단계 측정 기록과 장소 추정표 정답표 |
| `team-reports/` | 주제와 설계를 정할 때 쓴 기획 문서 |

센터 카드 데이터는 이 저장소에 없습니다. 개발과 시험에는 센터 명세서 구조를 따른 가상 데이터만 썼습니다.
