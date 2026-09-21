# AiPro 생존 우선 개발 감사와 실행 계획

작성일: 2026-09-20. 이 문서는 코드 변경 **전** 확인한 기준 상태와 후속 검증을 구분한다.

## 기준과 재현

- GitHub `sosamaru/Ai`의 main: `6be27da5e8ba64d3f1ae162855b05c06f063c3bb`.
- 최신 미병합 PR #75: `feat/us-dual-capital-20260912`, `1e921fecc4f5f9dbd4d3b0d9c470297e046288ee`.
- 원격 기준을 별도 worktree에서 실행: Python 3.12.14, pytest 9.1.1, **534 passed**.
- 기존 `feat/adaptive-validation-20260919` 미커밋 개발도 발견했다. 원본을 보존하고 검토했다.
  이 상태는 **592 passed, 1 failed**. Shadow 테스트가 모델 선택 holdout보다 앞선
  OOS 자료를 제시해 정당한 시간 경계 검사에 거절되었다. 검사 완화로 해결하지 않는다.
- README → PROJECT_ROADMAP → 설계·보안 문서 → 테스트 → 실제 호출 경로 순으로 확인했다.
  기존 확장 포함 패키지 Python 110개, AST 로컬 import 관계 223개를 확인했다.
  전체 파일 구조를 조사하고 실행·자금·검증·승격 경로를 집중 검토했으며,
  모든 외부 API 조합이나 모든 코드 경로를 검증했다는 의미는 아니다.

## 현재 아키텍처

`run.py → telegram.py → main.build_application → TradingApplication`을 유지한다.

| 경로 | 현재 역할 | 실제 연결 한계 |
|---|---|---|
| `aipro/crypto/application.py` → `aipro/app.py` | 건강검사한 DEMO/Upbit 시세, 모멘텀, 로컬 PaperBroker | 기존 모의체결은 수수료·스프레드 없는 모델 |
| `aipro/us_stocks/portfolio_application.py` | US_DUAL 단타 20만 원/장기 80만 원, 비용·환율·결제·원자적 장부 | 파일 입력, 실제 USD 증권계좌 대사 미연결 |
| `model_dataset.py` → `model_training.py` → `model_artifact.py` | 같은 feature 코드, purged walk-forward, 최종 holdout, 숫자 JSON 추론 | 단일 종목 고정시간 markout; 실제 청산전략 수익과 다름 |
| `intelligence/` | 뉴스·공시·거시·regime·EV·선택적 모델 및 거버넌스 | 연구 구성 요소가 모두 canonical runtime에 연결된 것은 아님 |
| 기존 미커밋 `core/adaptive_risk.py`, `runtime_monitor.py` | 손실 시 위험 축소, 수익곡선 감시 | 복구·청산 직후 재평가와 통계 검증을 추가 점검해야 함 |
| 기존 미커밋 `shadow_cohort.py`, `promotion.py` | 분리된 가상 장부, 사후 확정 정답, PAPER 모델 비교 | 실제 경과시간 증거 없음, LIVE 승인 기능 아님 |
| `crypto/account.py`, `upbit_preflight.py` | Upbit 조회 및 test-order만 | 실제 주문 생성 없음 |
| `us_stocks/alpaca_paper.py` | 별도 Alpaca PAPER 어댑터 | US_DUAL 자동 실행·자금 장부와 미연결 |

Crypto/Stock alpha·현금·평가자산·baseline은 분리한다. US 내부 두 sleeve의
손실 통제 합산은 Crypto와 Stock 성과를 섞는 것이 아니다. 계좌별 성과를 별도로 보고한다.

## 구현률 산정

과거 문서의 100%는 특정 개발 묶음의 완료 기록이며 전체 서비스 완료율이 아니다.
아래 20개 기능영역에 동일 가중치를 두고 **0=없음, 1=구성 요소/부분 연결,
2=canonical 경로와 회귀검증 완료**로 소프트웨어 구현을 평가한다.
실데이터 수익 검증이나 운영 승인에는 점수를 주지 않는다. 이 분모는 개발량 추정치이며
성공 확률·수익률·출시 가능성을 뜻하지 않는다.

| 기능영역 | 변경 전 점수 / 2 | 근거 또는 부족한 점 |
|---|---:|---|
| 기존 진입점·도메인 분리 | 2 | canonical 진입점 회귀검증 |
| 데이터 품질·공급자 연결 | 1 | US 공급기 없음, crypto 입력 검증 보완 필요 |
| 동일 Feature pipeline·메타데이터 | 1 | US 모델 공통 8개 지표; 전 도메인 feature store 부족 |
| Crypto Alpha | 1 | 단순 모멘텀; 검증된 다중 horizon 모델 없음 |
| Stock Alpha·랭킹 | 1 | 단타/장기 규칙, 제한된 후보 정렬 |
| Regime | 1 | hard heuristic, 검증된 확률 regime 없음 |
| ML benchmark·ensemble | 1 | 로지스틱 연결; 선택적 backend 실실행 미검증 |
| Meta label·Triple barrier | 1 | 기존 신호 필터/markout만, barrier 포트폴리오 비교 없음 |
| 확률 calibration | 1 | 미커밋 sigmoid/isotonic, 운영 검증 없음 |
| EV·실현 payoff | 1 | markout EV, 실체결 payoff로 검증되지 않음 |
| Risk Guardian·HALTED | 1 | 기초 latch 존재; 아래 P0 결함 |
| 포트폴리오·자금 분리 | 2 | US 별도 장부·최초 지원금·재투자 제한 |
| 주문 수명·재시작 | 1 | crypto 복구 결함; 실제 adapter 통합 없음 |
| 대사·실계좌 동기화 | 1 | 조회/비교 함수 존재, 주문 차단 연결 불완전 |
| 현실적 Backtest | 1 | 비용 엔진과 US replay 존재, 전시장 기업행사·체결 지연 부족 |
| 시간순 검증·purging | 2 | outcome availability·embargo·분리 holdout 회귀검증 |
| 실험 장부·다중검정 | 1 | 미커밋 ledger/bootstrap/DSR; PBO/CSCV 없음 |
| Monitoring·drift·audit | 1 | 부분 연결; 호스트 감시·변조 방어·복구 훈련 부족 |
| PAPER·Shadow 승격 | 1 | 로컬 가상 장부; 실제 계정 관찰 없음 |
| Small/limited LIVE 운영 | 0 | 실제 주문 어댑터·운영 승인 없음 |

변경 전: **22/40 = 55.0% (위에 한정한 소프트웨어 구현 척도)**.
독립 실데이터로 양의 기대값이 검증된 운영 모델: **0개 확인**.
이번 작업에 제공된 실제 장기 PAPER 증거: **0/30일 확인**.
LIVE readiness: **BLOCKED**. 소프트웨어 점수와 별도로 관리한다.

## 가장 위험한 버그와 보안·검증 문제

| 우선순위 | 문제 | 확인 방법 / 영향 |
|---|---|---|
| P0 | 손상된 crypto 계좌를 초기 현금으로 덮어씀 | 깨진 JSON 복구 시 100만 원 생성과 원본 삭제 재현. 손실·보유 포지션 은폐 |
| P0 | crypto 주문 전 대사 강제 없음 | 현금 1원 불일치 상태에서 대사 False인데 주문 2건 재현 |
| P0 | LIVE gate가 truthy 문자열을 승인 | `explicit_live_guard='false'`도 allowed=True 재현. 현재 실제 주문 경로는 없음 |
| P0 | 시장 snapshot 수치/중복/보유종목 시세 누락 | health wrapper가 시각만 검사; broker equity는 누락가격을 원가로 대체 |
| P0 | 실험 통계 기각과 모델 qualified 불일치 | 미커밋 학습기의 robust_blockers가 보고서에만 있고 artifact acceptance에 없음 |
| P0 | 청산 후 건강 상태 재평가 지연 | 실현 손실·비용이 생긴 동일 cycle의 다음 진입 전에 새 상태 반영 필요 |
| P0 | 손상·NaN 위험 상태, 실패한 저장·재시작 | 잘못된 baseline 복구/쓰기 실패로 메모리와 디스크 불일치 가능 |
| P0 | 인증 HTTP redirect/응답 크기 검토 | Alpaca PAPER 클라이언트에 무제한 read와 기본 redirect 사용; 자격증명 전달 경계 보완 필요 |
| P1 | markout과 실제 포트폴리오 손익 불일치 | 고정시간 정답은 TP/SL/시간청산·자본제약을 검증하지 않음 |
| P1 | 기업행사·PIT universe·실제 USD 결제 없음 | 생존편향, 미래 재무정보, split/gap 오인 가능 |
| P1 | adaptive ensemble 결과 재보정 부족 | 개별 확률 보정만으로 결합 확률 calibration은 보장되지 않음 |
| P2 | 두 model registry와 세 별도 backtest 경로 | lineage·승격 판단 중복; 통합과 migration 필요 |

보안상 숫자 JSON·hash pinning·비밀정보 redaction은 재사용한다. hash는 서명이나
실데이터 진실성 증명이 아니다. SECRET 값·개인 계정 기록을 테스트/문서에 넣지 않는다.
사용자 계정의 인프라/키 권한/백업 상태는 이번 소스 감사로 확인되지 않았다.

## Leakage와 과적합 판단

- purged walk-forward는 정답 확정시각을 확인하고 이전 embargo를 실제 제외한다.
  최종 holdout 모델 재학습은 하지 않는다. 기존 회귀 테스트를 유지한다.
- 보정 학습 구간은 모델 fitting 이후, 최종 test 이전이어야 한다.
- 실험 ledger는 삭제/복제하면 우회할 수 있는 협력적 통제다. 서버 보관·ACL·서명은 후속 과제다.
- 실패·예외·holdout 사용을 모두 기록해야 한다. 폴더나 실험 이름 변경으로 같은 기간을 재사용하지 않는다.
- 최종 검증 지표에 accuracy 최소값이 남아 있지만 수익 대용으로 쓰지 않는다.
  양의 순 EV, 비용 stress, 신뢰구간, 포트폴리오 성능을 함께 요구한다.
- 실제 dataset이 없으므로 alpha/우연/누수 중 무엇인지 결론낼 수 없다.
  합성 테스트 성과나 통과 개수를 경제적 증거로 사용하지 않는다.

## 재사용과 새 작업

재사용: canonical 진입점, SQLite 저장·order ID, 독립 baseline, 기존 Telegram 승인,
Upbit health/조회, US_DUAL 원자적 장부, market feature, purged 학습기, JSON artifact,
비용 simulator, 선택적 연구 backend, readiness evidence/export.

필요: 입력·수치·대사 강제, 실현 비용에 일치하는 공통 execution adapter,
시장별 TradeIntent→RiskValidation→OrderPlan 계약, prospective data capture,
단계별 운영 evidence와 자금 상한, broker 상태 대사, point-in-time corporate actions,
종목 universe·cross-sectional 학습, triple-barrier/시간청산 비교,
portfolio stress·PBO/CSCV, 모델 lineage 단일화, 감시/백업/rollback 훈련.

## P0–P3 개발 계획

| 단계 | 작업 | 완료 조건 |
|---|---|---|
| P0 | 원본 복구 보존, 대사 후 주문, 잘못된 입력/승인 차단, 청산 후 위험 재평가, 통계 기각 강제, 기존 확장 안정화 | 실패 재현 회귀 테스트, 전체 suite·canonical smoke, 문서 동기화 |
| P1 | 동일 replay/PAPER/Shadow pipeline, 실시간 입력 기록, 비용 3단계·market/system stress, 고정된 승격 기준, 소액/제한 LIVE 경계 | 분리된 시장 자료·계좌 계약·주문대사 및 운영 gate 검증; 실제 실행은 증거 충족 후 |
| P2 | 실제 momentum/ranking/linear/tree 비교, meta/calibration, feature store, trial/PBO/DSR, 불확실성·상관 위험 | 독립 다기간 OOS와 비용 포함 포트폴리오에서 개선 입증 |
| P3 | 검증된 후보 운영, 제한적 재학습, champion rollback, 소액→제한 실거래 | 최소 실제 PAPER 관찰·regime별 표본·Shadow·계좌/인증/독립 검토 동시 통과 |

P1에서 broker-dependent 구현과 실제 장기 관찰은 테스트 fixture로 대체하지 않는다.
BACKTEST에서 개발을 종료하는 계획이 아니다. PAPER/Shadow 실행과 다음 운영 단계의
정책·연결 코드를 개발하되, 관찰 기간이나 계좌 조건을 허위로 채워 승격하지 않는다.

## 참고한 원칙

- [Alpaca PAPER 공식 설명](https://docs.alpaca.markets/us/docs/paper-trading):
  PAPER는 market impact·지연 slippage·배당 등을 모두 재현하지 않는다.
- [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html):
  fitting과 calibration 데이터 분리 및 reliability 평가 원칙.
- [Bailey / López de Prado DSR 논문](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf):
  다중 시도와 비정규성 때문에 최고 Sharpe만 보고 승격하면 안 된다.
  DSR 유효 시도 수·분산 입력은 전체 실험에서 얻어야 하며 추정 가정을 기록한다.

## 변경 후 결과

2026-09-21: 확인한 P0 결함 8개 그룹을 수정하고 기존 adaptive 작업을 통합했다.
`python -m aipro all`: 진단·컴파일·canonical PAPER 실행, 통합 158개,
전체 회귀 619개 통과(경고를 오류로 처리). 검증 환경은 Python 3.12.14다.

위 평가표에서 calibration과 Risk Guardian을 각각 1→2로 갱신한다.
현재 소프트웨어 구현 척도는 **24/40 = 60.0%**다. 다른 영역은 미연결 요소가
남아 기존 점수를 유지한다. 실데이터 검증 모델 0개, 제공된 실제 PAPER 증거
0/30일, LIVE BLOCKED는 변하지 않았다.

모델 통계 기각을 실제 acceptance에 연결했으며, 보정되지 않은 ensemble은
NO_TRADE가 된다. Shadow는 같은 시점의 Champion 비교를 요구한다. 기존의
사후 비용 차감은 실제 스트레스 포트폴리오 재생이 아니므로 승격 증거에서 제외했다.
이로 인해 canonical cohort 자동 승격은 해당 증거 연결 전까지 차단된다.

구체적인 변경 이유·검증·호환성·남은 우선순위는
[운영 개발 기록](SURVIVAL_RUNTIME_20260921.md)에 정리했다.
