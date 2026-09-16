# TOPSPEED AI OS — Architecture Freeze v1

- 문서 상태: **FROZEN**
- 적용 대상: 신규 독립 저장소 `topspeed-ai-os`
- 기준 저장소: `topspeed-lifeos` Migration Audit 결과
- 변경 규칙: 본 문서의 경계·흐름·승인 원칙을 바꾸려면 사유와 영향 범위를 기록한 ADR 및 차기 버전 문서가 필요하다.

## 1. 시스템 목적

`topspeed-ai-os`는 TOPSPEED 한 사업자의 이커머스 운영을 위해 근거 기반 분석, 정량 계산, 승인, 제한된 실행, 감사 추적을 제공하는 독립 Core다. 다중 판매자용 SaaS나 범용 개인 비서를 목표로 하지 않는다.

최상위 원칙은 다음과 같다.

1. 외부 사실은 Source/Tool로 확인한다.
2. 재현 가능한 숫자는 LLM이 아니라 결정론적 코드로 계산한다.
3. Audit는 Skill과 분리된 독립 Gate로 동작한다.
4. 외부 쓰기와 사업 상태 변경은 대표 승인 전에는 실행하지 않는다.
5. 승인 대상과 실제 실행 payload가 달라지면 승인은 무효다.
6. 모든 시도·차단·승인·실행 결과를 추적 가능한 ID와 함께 기록한다.
7. 현재 SKU의 검증된 사실만 사용하며 다른 SKU 데이터를 혼입하지 않는다.

## 2. 시스템 경계

### 2.1 `topspeed-lifeos`

`topspeed-lifeos`는 **Legacy Assistant / Slack Interface**로 유지한다.

담당 범위:

- Slack 기반 개인 AI 비서
- Gmail, Calendar, Notion 등 개인 업무 보조
- 기존 알림, 스케줄러, 자동화
- 신규 AI OS 결과와 승인 요청을 대표에게 전달하는 사용자 인터페이스

금지 범위:

- 이커머스의 최종 데이터 원장 소유
- HQ Routing 정책 소유
- 공헌이익·광고·재고의 공식 계산 소유
- 승인 상태의 원본 저장소 역할
- 승인되지 않은 AI OS 실행 요청

`src/slack_app.py`, `src/multi_agent.py` 및 기존 Butler 실행 흐름은 신규 Core로 복사하거나 import하지 않는다. 향후 연결은 버전이 명시된 단일 Gateway 계약을 통해서만 수행한다.

### 2.2 `topspeed-ai-os`

`topspeed-ai-os`는 다음 책임을 갖는 신규 독립 저장소다.

- HQ Orchestrator와 Structured Router
- 6개 전문 Skill
- Read-only Tool과 Source Ingestion
- Data Hub Adapter와 Data Contract 검증
- 결정론적 계산 Engine
- 독립 Audit Layer
- `APPROVAL_QUEUE`
- 승인된 Execution Adapter
- `AI_RUN_LOG`와 사후 감사

개인 메일·일정·범용 비서 기능은 포함하지 않는다.

## 3. 고정 실행 흐름

```text
대표 요청
→ HQ Orchestrator
→ Structured Router
→ 전문 Skill / Agent
→ Data / Read Tool 조회
→ Deterministic Code 계산
→ Independent Audit Gate
→ PASS / WARN / FAIL
→ APPROVAL_QUEUE
→ 대표 승인
→ Execution Tool
→ AI_RUN_LOG
→ Post-execution Audit
```

흐름 규칙:

- 읽기·분석 요청도 `AI_RUN_LOG`에 기록한다.
- 외부 쓰기가 없는 요청은 Audit 결과 기록 후 완료할 수 있다.
- 외부 쓰기 요청은 반드시 Audit Gate와 `APPROVAL_QUEUE`를 통과한다.
- `FAIL`은 승인 대기열 및 실행 단계로 진행하지 않는다.
- `WARN`은 경고 내용이 승인 화면에 명시된 경우에만 승인 대기열로 진행할 수 있다.
- `PASS`도 외부 쓰기라면 자동 실행하지 않는다.

## 4. 구성요소 책임

### 4.1 HQ Orchestrator

HQ는 전문 Skill이 아니라 요청의 전체 생명주기를 통제하는 Orchestration 계층이다.

책임:

- 요청 접수 및 `task_id`, `run_id` 발급
- 요청 목적, 대상 SKU, 읽기/쓰기 여부, 위험 수준 식별
- Structured Router 호출
- Skill 입력 계약 충족 여부 확인
- 필요한 Data/Tool/계산/Audit 단계 조립
- 승인 필요 여부 판정
- 결과를 이슈 → 근거 → 권고 → 실행문장으로 요약
- 대표 결정 항목과 다음 행동 3~5개 제시

금지:

- 근거 없는 사실 생성
- 공식 수치 직접 산출
- Skill을 우회한 Tool 호출
- Audit 우회
- 대표 승인 없는 외부 쓰기

### 4.2 Structured Router

Router는 자유형 역할극이 아니라 구조화된 Routing 결과를 반환한다.

최소 출력 계약:

| 필드 | 의미 |
| --- | --- |
| `task_id` | 사용자 요청 단위 ID |
| `run_id` | 이번 처리 시도 ID |
| `intent` | 정규화된 요청 목적 |
| `skill` | `sourcing`, `launch`, `ads_ops`, `content`, `inventory`, `data` 중 하나 |
| `sku` | 단일 SKU 또는 명시된 SKU 목록 |
| `requested_action` | 조회, 분석, 초안, 변경 제안, 실행 요청 |
| `risk_level` | LOW, MEDIUM, HIGH |
| `required_data` | 필요한 Data Contract와 기준일 |
| `requires_approval` | 승인 필요 여부 |
| `route_reason` | 선택 이유와 제외한 경로 |

Router는 기본적으로 하나의 주 Skill을 선택한다. 복합 요청은 HQ가 하위 `task_id`로 분할하고 각 결과를 다시 조합한다.

### 4.3 전문 Skill

| Skill | 책임 | 명시적 비책임 |
| --- | --- | --- |
| `sourcing` | 상품 소싱, 시장 조사, 경쟁상품 사실과 출처 정리, 자료 공백 식별 | 확인되지 않은 검색량·매출·리뷰 수 생성, 상품 등록 |
| `launch` | 원가·수수료·물류·예상 반품비·판매가 기반 공헌이익, 단계/등급, GO/HOLD/DROP/RETEST 제안 | 입력 부족 상태에서 결론 강제, 가격 변경 실행 |
| `ads_ops` | 광고 지표 조회, 이상 탐지, 예산/소재/캠페인 조정안 작성 | 광고비·입찰·캠페인 직접 변경 |
| `content` | 현재 SKU에 한정한 상품명, 후킹, 이미지 브리프, 상세페이지 초안 | 타 SKU 사실 혼입, 미증빙 효능·인증 주장, 게시 실행 |
| `inventory` | 재고일수, 품절 위험, 재주문점, 권장 발주량 계산과 승인안 | 발주 생성·전송, 재고 수량 임의 수정 |
| `data` | 수집, 정규화, 품질·최신성 검증, 조회 결과 제공 | 사업 의사결정 대행, 외부 Source 값 임의 보정 |

각 Skill은 정확한 trigger/non-trigger, 입력 계약, 처리 절차, 출력 계약, 승인 조건, 실패 규칙과 최소 5개 eval 사례를 가져야 한다.

### 4.4 Tool

Tool은 LLM의 판단과 외부 시스템의 세부 구현을 분리한다.

- **Read Tool:** 외부 조회 및 원본 캡처. 외부 상태를 변경하지 않는다.
- **Ingestion Tool:** 원본을 Data Contract로 변환하며 Source, `data_as_of`, checksum을 보존한다.
- **Calculation Tool:** 공헌이익, 광고 지표, 재고/발주 수치를 순수 결정론적 코드로 계산한다.
- **Execution Tool:** 승인된 불변 payload만 외부에 쓴다.

모든 Tool은 timeout, 오류 분류, 재시도 정책, 요청 추적 ID를 명시해야 한다. 재시도는 읽기 또는 멱등성이 검증된 쓰기에만 허용한다.

### 4.5 Data Layer

Data Layer는 다음 8개 핵심 계약을 제공한다.

`PRODUCT_MASTER`, `PRODUCT_FACT`, `CHANNEL_DAILY`, `AD_DAILY`, `INVENTORY`, `CONTENT_ASSET`, `APPROVAL_QUEUE`, `AI_RUN_LOG`.

역할:

- SKU 기반 사실 격리
- 원본 Source와 기준일 추적
- 정량 데이터와 비정형 사실 분리
- 중복 수집 방지
- 승인 및 실행의 불변 기록

DB Engine은 v1 Architecture Freeze에서 결정하지 않는다. Schema와 Adapter는 특정 DB의 자동 증가 ID, trigger, JSON 함수에 의존하지 않아야 한다.

### 4.6 Independent Audit Layer

Audit는 6개 Skill 중 하나가 아니며 중요한 처리에 공통 적용되는 독립 Gate다.

검증 항목:

- 필수 입력 및 Source 누락
- `data_as_of` 최신성
- SKU 혼입과 Scope 위반
- 공식·계산 결과의 코드 재계산 일치 여부
- 출처와 주장 간 연결
- 규칙·승인 정책 위반
- 중복 실행과 `idempotency_key`
- 실행 전후 값과 실제 결과

판정:

| 판정 | 의미 | 다음 단계 |
| --- | --- | --- |
| `PASS` | 필수 근거와 재계산이 충족되고 중대한 충돌 없음 | 읽기는 완료, 쓰기는 승인 대기 |
| `WARN` | 비핵심 자료 공백 또는 설명 가능한 차이가 있음 | 경고를 노출한 승인 대기 또는 보완 요청 |
| `FAIL` | 핵심 입력·출처 누락, 계산 불일치, 정책 위반, SKU 혼입 | 중단, 로그 기록, 보완 후 새 `run_id` |

LLM 기반 논리 검토는 사용할 수 있지만, 숫자 재계산과 데이터 무결성 검증을 대체할 수 없다.

### 4.7 Approval

다음은 항상 대표 승인 대상이다.

- 상품·가격·재고·발주·광고 상태 변경
- 콘텐츠 게시 또는 외부 파일 쓰기
- 외부 시스템의 생성·수정·삭제
- 금액 또는 고객 노출 결과가 바뀌는 작업

승인 객체는 `approval_id`, 대상, 제안 payload, payload hash, 전/후 값, Audit 결과, 승인자, 만료, `idempotency_key`를 가진다. 승인 후 payload가 한 글자라도 실질적으로 바뀌면 새로운 승인을 받아야 한다. 범용 “최신 요청 승인” 방식은 금지한다.

### 4.8 Logging

`AI_RUN_LOG`는 append-only 이벤트 기록이다.

- 성공뿐 아니라 오류, 차단, 거절, 만료를 기록한다.
- `run_id`, `task_id`, agent, skill, SKU, source, 기준일, 입출력 요약, 승인, Audit, 실행 전후 값, 오류를 연결한다.
- 민감한 인증정보와 원문 secret은 저장하지 않는다.
- 사후 감사가 동일한 입력과 계산 버전을 재현할 수 있어야 한다.

### 4.9 Execution 정책

- 초기에는 모든 Execution Adapter를 비활성 상태로 둔다.
- 실행 요청은 승인된 `approval_id`와 정확히 일치하는 payload hash를 요구한다.
- 동일 `idempotency_key`의 성공 실행은 반복하지 않는다.
- 실행 전 현재 상태를 다시 읽어 승인 당시 `before_value`와 비교한다.
- 상태가 달라졌으면 실행하지 않고 재승인을 요청한다.
- 실행 후 실제 값을 재조회해 `after_value`와 비교하고 Post-execution Audit를 기록한다.

## 5. LifeOS 연결 계약

LifeOS는 다음만 수행한다.

1. 사용자 요청을 AI OS Gateway에 전달한다.
2. AI OS가 반환한 결과·경고·승인 ID를 표시한다.
3. 대표의 명시적 승인/거절을 해당 `approval_id`와 함께 전달한다.
4. 실행 결과를 표시한다.

LifeOS가 Routing, 계산, Audit 판정, 승인 원본 상태 또는 실행 payload를 자체 재구성해서는 안 된다.

## 6. 금지된 결합 구조

다음 구조는 v1에서 금지한다.

- 신규 Core가 `topspeed-lifeos` Python 모듈을 직접 import
- `slack_app.py` 내부에 이커머스 계산·승인·실행 로직 추가
- `multi_agent.py`의 역할 프롬프트를 HQ/독립 Agent로 간주
- Skill이 Execution Tool을 직접 호출
- Audit를 각 Skill 내부 선택 절차로 구현
- LLM 출력 숫자를 공식 저장값으로 사용
- 최신 JSON 파일 하나를 원장처럼 사용
- 부분 실패 수집 결과를 `latest`로 승격
- 파일 hash만으로 날짜 중복 데이터를 허용
- 승인 버튼을 사용자별 최신 pending 작업에 연결
- 다른 SKU의 사실·이미지·후기를 현재 상품에 사용
- DB Engine 전용 기능을 Data Contract에 포함
- Mock test만으로 외부 연동을 운영 가능 판정

## 7. Architecture 불변조건

1. LifeOS와 AI OS는 배포·실행·장애 범위가 분리된다.
2. 모든 공식 수치는 원본과 계산 버전을 추적할 수 있다.
3. 모든 외부 쓰기는 Audit와 명시적 승인에 묶인다.
4. Approval과 Execution은 `approval_id`와 payload hash로 1:1 연결된다.
5. 감사 불가한 실행은 실행 불가다.
6. Core는 Slack, 특정 DB, 단일 로컬 PC에 종속되지 않는다.
7. Legacy 기능은 신규 OS 검증이 끝날 때까지 삭제하거나 대체하지 않는다.

