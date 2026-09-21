# AiPro 생존 우선 구현 기록 — 2026-09-21

## 검증한 범위

GitHub main `6be27da5e8ba64d3f1ae162855b05c06f063c3bb`, 미병합 PR #75
`1e921fecc4f5f9dbd4d3b0d9c470297e046288ee`를 확인하고 별도 브랜치에서
작업했다. 이전 adaptive 개발 원본은 보존했다. 감사 문서를 먼저 커밋한 뒤
코드를 수정했다. `run.py → telegram.py → main.py → TradingApplication`은 유지한다.

전체 요구사항이 완성된 상태는 아니다. 아래는 실제 구현·시험한 범위이며,
실제 시장의 수익성·운영시간·계좌 체결 증거를 대신하지 않는다.

## 주요 변경과 검증

| 변경 | 필요한 이유 / 실패 시 위험 | 검증 |
|---|---|---|
| crypto 복구 실패 시 정지 | 깨진 계좌를 초기 현금으로 덮으면 손실·보유자산을 숨김 | 손상 원문 보존, 이력 있는 계좌 재지원 금지 |
| 상태와 감사 이벤트 원자적 저장, CAS | 다중 프로세스가 옛 현금으로 주문하거나 저장 실패 뒤 계속 거래 | 오래된 writer 거절, 저장 실패 latch |
| 주문·resume 전 대사 | 내부 현금/포지션 불일치 중 추가 주문 | 불일치 cycle 및 resume 차단 |
| 가격·보유종목·baseline 수치 검증 | NaN/누락 시세로 자산·위험 과소평가 | NaN, 중복, 보유시세 누락, 잘못된 baseline |
| strict bool LIVE gate, PAPER-only runtime | 문자열 false가 승인으로 해석되거나 모의체결이 LIVE로 표시됨 | 잘못된 flag 거절, 실제 어댑터 없는 LIVE 거절 |
| 청산 직후 위험 재평가·최대 주문 cap | 같은 cycle 손실 후 신규 진입으로 위험 증가 | 기존 진입/청산 통합 회귀, 주문 상한 |
| 인증 HTTP redirect 거절·응답 제한 | 인증정보 전달 경계·과대 응답 | redirect 거절, 크기 제한, 기존 조회 어댑터 회귀 |
| 통계 기각과 v3 artifact acceptance 연결 | 연구 보고서에서 기각한 모델이 runtime에 진입 | 낮은 EV 하한/불안정 WF/나쁜 ECE 기각 |
| 보정 여부 강제·모델 horizon 청산 | 신뢰할 수 없는 확률로 sizing, 예측 기간 이후 무한 보유 | uncalibrated NO_TRADE, 실제 cycle time-stop |
| 실험·holdout ledger, 후보 재학습 큐 | 실패 은폐·반복 test 튜닝·자동 배포 | 실패 기록, 시도 예산, holdout 재사용 거절, 후보만 생성 |
| 지속형 adaptive risk/성과·상관 통제 | 손실 회복 베팅·재시작 우회 | 상태 복원, 제한된 가중치/위험 축소, 명시적 resume |
| prospective US frame archive | 나중에 만든 재생을 실시간 관찰로 오인 | 시각 역행·합성·과거 입력 거절, 재시작/내보내기 |
| paired Shadow 승격 | 과거 Champion만 비교해 현재 열등한 후보 승격 | 같은 시각/데이터 Champion 요구, paired bootstrap |

`python -m aipro all`은 Python 3.12.14에서 진단, 컴파일, canonical PAPER smoke,
통합 **158개**, 전체 회귀 **619개**를 통과했다. 테스트 데이터는 소프트웨어
검증용이다. 원격 기준 534개 대비 85개 증가에는 기존 adaptive 작업의 테스트도
포함한다. 타 Python 버전/원격 CI 결과는 별도 확인이 필요하다.

## PAPER 시세 기록과 재생

기존 `config/us_dual_paper.env.example`의 US_DUAL 설정을 사용한다.
`AIPRO_US_FRAME_PATH` 공급 파일은 현재 시각의 실제 데이터여야 하며 공급자가
원자적으로 갱신해야 한다. 새 canonical 파일 경로는 합성 자료를 거절한다.
합성 예제는 `python -m aipro portfolio-demo` 또는 명시적인 replay를 사용한다.
파일 공급기 자체는 이번에 구현하지 않았다.

canonical runtime은 주문 판단 전에 `<US ledger 경로>.frames.sqlite3`에 frame과
별도 수집 시각을 기록한다. 기본 경로의 내보내기 예시는 다음과 같다.

```bash
python -m aipro market-export data/us_dual_paper.sqlite3.frames.sqlite3 --output data/us_frames_export.jsonl
python -m aipro portfolio-replay data/us_frames_export.jsonl --output data/us_replay.json
```

내보내기는 기존 파일을 덮지 않는다. archive hash는 일관성 검사이며 데이터
공급자의 진실성을 보장하지 않는다. 과거 frame replay는 경과 PAPER 시간으로
집계되지 않는다. 실제 운영에서는 신뢰할 공급자·시장 캘린더·기업행사 처리가 필요하다.

## 학습과 모델 호환성

```bash
python -m aipro model-train data/us_frames_export.jsonl --symbol AAPL --experiment-id aapl-v3-001 --ledger data/research_experiments.sqlite3 --calibration sigmoid --output-dir data/models/aapl-v3-001
python -m aipro model-inspect data/models/aapl-v3-001/model.json
```

실제 해당 종목 데이터와 충분한 독립 표본이 있어야 한다. 이 예시는 결과물을
보장하지 않는다. 후보 조건 실패가 정상 결과다. 같은 최종 holdout을 반복해서
관찰하려고 ledger를 삭제하거나 다른 경로로 바꾸면 안 된다.

새 serving schema는 `aipro-us-logistic-paper-v3`다. v1/v2는 조회할 수 있지만
추론에 사용할 수 없으므로 재학습해야 한다. 파일 안 schema나 qualified 값을
수동으로 바꾸는 migration은 허용되는 검증 절차가 아니다. 모델 선택은 기존
`AIPRO_US_MODEL_PATH`와 `AIPRO_US_MODEL_SHA256`의 일치가 필요하다.
통계 검증·보정·유효기간·feature·policy·domain 검사를 모두 통과해야 진입한다.
90일 유효기간 상한은 검증된 안정성 보장이 아니며 위험 감시를 대체하지 않는다.

개별 확률을 보정했다고 ensemble 확률도 보정된 것은 아니다. 현재 ensemble
출력은 결합 확률 보정 증거가 없어서 신규 진입이 차단된다. 원래 규칙 baseline은
연구용 PAPER에서 유지되며 검증된 alpha라는 의미는 아니다.

## Shadow와 retraining

`AIPRO_US_COHORT_PATH`와 `AIPRO_US_COHORT_SHA256`으로 고정한 2–6개 모델을
서로 분리된 가상 장부에서 관찰한다. 모델 선택 holdout 이후의 독립 portfolio
OOS 증거가 필요하다. 단일 모델·ensemble·cohort는 동시에 선택하지 않는다.
각 후보의 가상 장부는 실제 추가 자금이 아니며 운영 장부의 자금을 늘리지 않는다.

관찰 시각, 확정된 horizon 정답, 체결 episode, 비용, 일별 자산을 기록한다.
승격은 같은 기간 Champion/Challenger, 순기대값, drawdown, calibration,
거래 표본, 레짐, 경과기간, paired 통계를 요구한다. **현재 cohort에 실제
비용 스트레스 재생 증거가 연결되지 않아 자동 승격은 차단된다.** 사후 수수료
차감만으로 스트레스 통과를 선언하지 않는다. 테스트의 수작업 증거는 실증이 아니다.

`AIPRO_US_TRAINING_ARCHIVE`가 설정되면 제한된 후보 재학습 작업을 등록할 수 있다.
별도 worker는 다음과 같이 한 작업을 처리하며 운영 모델을 배포하지 않는다.

```bash
python -m aipro model-retrain-worker --queue data/us_dual_paper.sqlite3.shadow/retraining.sqlite3
```

HALTED를 풀기 위해 DB를 삭제하지 않는다. 기존 인증된 Telegram 복구 경로와
건강상태 검사를 사용하며 불일치/손상 상태는 원인 수정과 대사가 먼저다.

## 남은 개발과 운영 기준

- **P0:** 이번 감사에서 재현한 8개 결함 그룹 수정 완료. 새 실브로커 연결 시 같은
  불변조건을 다시 시험해야 한다. 테스트 통과가 모든 장애 부재를 보장하지 않는다.
- **P1:** 신뢰할 PIT 자료·universe·기업행사, USD 계좌/결제/브로커 PAPER 통합,
  normal/stress/extreme 비용·부분체결·실패·지연의 같은 pipeline 포트폴리오 재생.
  crypto 기존 PaperBroker의 무비용 체결을 현실화하고 실계좌 대사 경로를 연결한다.
  OOS markout→실제 exit→portfolio 손익 차이를 검증하고 Shadow 스트레스 증거를 연결한다.
- **P2:** cross-sectional ranking, 사전 제한 모델 benchmark, 확률 regime,
  결합 확률 calibration, full feature store, registry 통합, PBO/CSCV와 trial 전체 비교.
- **P3:** 실제 PAPER/Shadow 표본·레짐·안정성 기준 충족, 장애 복구 훈련,
  소액/제한 LIVE 예산과 단계 승격 기준 고정, 명시적 승인 후 실제 주문 어댑터 연결.

현재 검증 모델 **0개 확인**, 제공된 실제 PAPER 증거 **0/30일**, LIVE **BLOCKED**.
30일만 지났다고 승격하지 않는다. 실브로커/외부 시세 계정에 접속하거나 실제 주문을
전송하지 않았다. 현재 소프트웨어 평가 24/40(60%)와 경제적·운영 준비 상태를 분리한다.
