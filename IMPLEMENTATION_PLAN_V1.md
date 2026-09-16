# TOPSPEED AI OS — Implementation Plan v1

- 목표: Architecture Freeze를 위반하지 않고 신규 `topspeed-ai-os`를 단계적으로 구축
- 범위: 단일 TOPSPEED 사업자
- 원칙: 각 Phase는 산출물, Test, 완료 조건을 충족하기 전 다음 단계의 운영 활성화를 허용하지 않는다.
- 핵심 Data Contract: `PRODUCT_MASTER`, `PRODUCT_FACT`, `CHANNEL_DAILY`, `AD_DAILY`, `INVENTORY`, `CONTENT_ASSET`, `APPROVAL_QUEUE`, `AI_RUN_LOG`

## PHASE 0 — `topspeed-lifeos` 동결 및 보존

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 현재 main commit/tag 기록, 실행 환경과 스케줄러 목록 보존, Legacy 변경 동결 선언 |
| 입력 | GitHub main, 로컬 Task Scheduler 정보, 현재 환경변수 이름 목록 |
| 출력 | 동결 기준 commit/tag, Legacy 운영 목록, rollback 기준 |
| Dependency | 없음 |
| Test | 기존 Slack 알림·스케줄러의 현 상태 smoke 확인; secret이 문서/Git에 포함되지 않는지 검사 |
| 완료 조건 | 기준 commit이 고정되고, 삭제·Migration 없이 현재 기능을 재현할 정보가 있음 |

## PHASE 1 — Architecture Freeze + Data Contract

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 본 4개 문서 확정, 경계·흐름·Schema·Migration 판정 고정 |
| 입력 | Migration Audit, 사용자 확정 결정 |
| 출력 | `ARCHITECTURE_FREEZE_V1.md`, `DATA_CONTRACT_V1.md`, `MIGRATION_MATRIX_V1.md`, `IMPLEMENTATION_PLAN_V1.md` |
| Dependency | PHASE 0의 Legacy 보존 원칙 |
| Test | 용어, 8개 Contract, 6개 Skill, Audit/Approval 흐름 교차 검증 |
| 완료 조건 | 문서 간 충돌이 없고 자체 검증 PASS 또는 명시된 WARN만 존재 |

## PHASE 2 — Core IDs / Engine-independent Schema

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 신규 repo skeleton, ID 발급/검증, Enum, 8개 machine-readable Schema, payload canonicalization/hash |
| 입력 | `DATA_CONTRACT_V1.md` |
| 출력 | `core/ids`, `core/enums`, `contracts/`, Schema tests |
| Dependency | PHASE 1 PASS |
| Test | 필수/선택 필드, 잘못된 enum/type/timezone, SKU 참조, 동일 payload hash, ID 충돌/형식, Approval 상태전이 negative test |
| 완료 조건 | Legacy import 0개, DB 의존 0개, 8개 Schema가 문서와 일치하고 모든 positive/negative test 통과 |

## PHASE 3 — Read-only Tools

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | Coupang Read Tool, Drive Source Read Tool, Excel/CSV Reader; credential adapter와 Tool interface 분리 |
| 입력 | 기존 Capability, 공식 API/파일 sample, Core Schema |
| 출력 | raw response/file + Source metadata + typed Tool result |
| Dependency | PHASE 2 |
| Test | unit/contract test, timeout, 401/403, rate limit, schema 변화, malformed file, secret redaction; 사용 가능한 실제 계정별 최소 1회 read-only live smoke |
| 완료 조건 | allowlist 밖 endpoint 호출 불가, 외부 쓰기 0개, Mock과 Live 결과가 구분되어 기록됨 |

## PHASE 4 — Data Hub Adapter

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | raw → 8개 Contract 변환, SKU mapping, provenance, checksum+자연키 dedup, batch publish gate |
| 입력 | PHASE 3 raw results |
| 출력 | 검증된 Contract records와 rejected records |
| Dependency | PHASE 2, PHASE 3 |
| Test | 중복 날짜/다른 파일, 미등록 SKU, 단위 변환, 기준일 누락, 부분 실패, 재수집 idempotency |
| 완료 조건 | 오류 batch가 current/latest로 승격되지 않고 모든 row의 Source와 기준일 추적 가능 |

## PHASE 5 — Deterministic Calculation Engine

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 공헌이익, CTR/CVR/ROAS, 재고일수/재주문점/권장발주량 계산 |
| 입력 | 검증된 PRODUCT_MASTER, CHANNEL_DAILY, AD_DAILY, INVENTORY |
| 출력 | 파생값, 공식 버전, 사용 input refs, 계산 오류 |
| Dependency | PHASE 4 |
| Test | 고정 fixture 손계산 대조, 0 분모, 음수/누락, 반올림, 시간창, property/edge test |
| 완료 조건 | 동일 입력·버전은 동일 결과, LLM 의존 0개, 모든 공식이 문서와 Test로 재현됨 |

## PHASE 6 — HQ + Router + 6 Skills

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | HQ lifecycle, Structured Router, sourcing/launch/ads_ops/content/inventory/data Skill 계약과 eval |
| 입력 | 검증된 Data/Tool/Calculation 결과 |
| 출력 | 구조화 Skill 결과, 근거, 자료 공백, 권고, 승인 후보 |
| Dependency | PHASE 2~5 |
| Test | trigger/non-trigger, 복합 요청 분할, SKU isolation, 입력 부족, 근거 없는 숫자 거부, Skill당 최소 5 eval |
| 완료 조건 | 6개 Skill 경계 중복 없음, Router Schema 100% 준수, Skill의 직접 외부 쓰기 0개 |

## PHASE 7 — Independent Audit Layer

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 필수값·최신성·SKU·Source·재계산·정책 검사, PASS/WARN/FAIL, post-audit contract |
| 입력 | Skill output, Data refs, 계산 결과, 정책 |
| 출력 | audit_status, machine-readable findings, 사람용 요약 |
| Dependency | PHASE 5, PHASE 6 |
| Test | 숫자 변조, 오래된 Source, 다른 SKU 혼입, 허위 claim, 누락, 규칙 충돌, false PASS 방지 |
| 완료 조건 | 정량 검사는 코드로 재계산되고 FAIL이 승인/실행으로 진입할 수 없음 |

## PHASE 8 — `APPROVAL_QUEUE`

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 승인 state machine, payload canonicalization/hash, expiry, approver identity, idempotency key |
| 입력 | PASS/WARN 승인 후보 |
| 출력 | 불변 승인 객체와 상태 이벤트 |
| Dependency | PHASE 2, PHASE 7 |
| Test | stale approval, tampered payload, 중복 클릭, 만료, 거절 후 실행, 동시 승인, WARN 표시 |
| 완료 조건 | approval_id 없는 실행 요청 생성 불가, payload 변경 시 재승인, 종결 상태 역전 불가 |

## PHASE 9 — Execution Adapters

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | 작업 종류별 최소권한 write adapter, dry-run, before 재조회, 실행, after 재조회 |
| 입력 | APPROVED 승인 객체 |
| 출력 | 외부 실행 결과, before/after, 오류, post-audit 입력 |
| Dependency | PHASE 3 read tools, PHASE 8 |
| Test | 기본 비활성, dry-run, payload hash mismatch, state drift, timeout, 중복 실행, 부분 실패, sandbox/live 분리 |
| 완료 조건 | 대표 승인·멱등성·사전상태 일치 없이는 외부 쓰기 0개; 허용된 action 외 호출 불가 |

## PHASE 10 — Slack Gateway 연결

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | LifeOS → AI OS 요청, 결과/경고/승인 렌더링, 승인/거절 전달 |
| 입력 | AI OS Gateway 계약, 기존 Slack UX 참고 |
| 출력 | 얇은 Gateway와 승인 ID 기반 UI |
| Dependency | PHASE 6~9 |
| Test | 오래된 버튼, 다른 사용자/approval_id, 중복 클릭, API 장애, WARN/FAIL 표시, Core 무상태성 |
| 완료 조건 | LifeOS가 Routing·계산·승인 원장을 소유하지 않고 AI OS 장애가 Legacy 비서 전체를 중단시키지 않음 |

## PHASE 11 — 병행 결과 비교와 단계적 전환

| 항목 | 내용 |
| --- | --- |
| 구현 항목 | Legacy 결과와 AI OS read-only 결과 병행 수집, 차이 분석, 기능별 cutover |
| 입력 | 동일 Source/동일 기간 결과 |
| 출력 | 비교 보고서, 차이 원인, 승인된 전환 목록, rollback plan |
| Dependency | PHASE 10 |
| Test | 결정론적 수치의 원본·공식별 대조, 누락/중복/지연 비교, 실제 알림 전달 smoke |
| 완료 조건 | 중요 수치 차이가 모두 설명·해결되고 기능별 대표 승인 후에만 전환; Legacy 삭제 없음 |

## 1. 첫 구현 작업

코딩을 시작할 때의 첫 작업은 **신규 독립 `topspeed-ai-os` 저장소 skeleton과 PHASE 2 Core Contract package를 만드는 것**이다.

포함:

1. 독립 package 구조와 CI 기본 틀
2. `sku`, `task_id`, `run_id`, `approval_id`, `idempotency_key` 생성/검증
3. Skill, Audit, Approval, Result, Stage, Grade Enum
4. 8개 Data Contract의 machine-readable Schema
5. canonical JSON과 payload SHA-256
6. Contract positive/negative test

포함하지 않음:

- Coupang/Drive/Slack 연결
- DB Engine 선택
- LLM Prompt 또는 Agent 구현
- 광고·가격·발주·게시 쓰기
- Legacy 파일 복사

### 첫 구현 작업 완료 조건

- 신규 저장소가 LifeOS와 독립적으로 설치·테스트된다.
- `topspeed-lifeos` import가 0개다.
- 8개 Schema가 `DATA_CONTRACT_V1.md`와 필드·필수성·Enum 면에서 일치한다.
- 잘못된 타입, timezone 없는 시각, 미등록 enum, 잘못된 상태 전이, payload 변조가 모두 실패한다.
- 동일 payload는 동일 hash, 실질적으로 다른 payload는 다른 hash가 된다.
- DB·Slack·API·LLM 없이 전체 Contract test가 통과한다.
- CI가 test, lint, secret scan 실패를 차단한다.

## 2. 아직 불확실한 항목

다음은 구현 전에 사실 확인 또는 후속 ADR이 필요하나 Architecture Freeze를 막지는 않는다.

| 항목 | 현재 상태 | 확정 시점 |
| --- | --- | --- |
| 실제 Coupang endpoint별 성공 여부 | 코드 존재, 실제 계정 live 검증 미확인 | PHASE 3 |
| 광고 보고서 실제 컬럼 버전 | 샘플/기간 중복 규칙 추가 확인 필요 | PHASE 3~4 |
| 내부 SKU와 채널 ID mapping 원본 | 공식 Master 확인 필요 | PHASE 4 |
| 원가·수수료·물류·반품비 공식 Source | 기존 runtime 값 provenance 불명 | PHASE 4~5 |
| 재고 평균 기간·안전재고 정책 | 사업 정책 선택 필요 | PHASE 5 |
| Launch S/A/B/T/X 경계값 | 대표 정책/실적 근거 필요 | PHASE 5~6 |
| Source 최신성의 허용 시간 | 데이터 유형별 SLA 미정 | PHASE 7 |
| Approval 만료시간·위험등급별 규칙 | 운영 정책 미정 | PHASE 8 |
| 첫 Write Adapter 대상 | 광고/발주/가격/게시 중 미정 | PHASE 9 전 |
| DB Engine과 배포 위치 | 의도적으로 미정 | PHASE 2 이후 ADR |

## 3. 아직 건드리면 안 되는 LifeOS 자산

현재 단계에서 아래를 삭제·이동·개조하지 않는다.

- `src/slack_app.py`
- `src/multi_agent.py`
- `app.py`
- Gmail, Calendar, Notion, Kakao 관련 모듈
- `automation/`의 기존 스케줄러와 알림
- `start_bot*`, `start_dashboard*`, `INSTALL_*`, `RESET_*`, `REGISTER_*`
- `slack-manifest.yaml`
- 기존 `.env`, `secrets/`, 로컬 OAuth/token 파일
- `runtime_workspace/`의 운영 상태·원본·로그
- Windows Task Scheduler의 기존 TOPSPEED 작업

신규 OS가 병행 검증을 통과하기 전에는 기존 기능을 교체하거나 비활성화하지 않는다.

## 4. 문서 간 자체 검증

| 검사 | 결과 | 근거 |
| --- | --- | --- |
| LifeOS/AI OS 경계 일치 | PASS | 4개 문서 모두 Legacy Interface와 신규 Core를 분리 |
| 6개 Skill 및 Audit 분리 | PASS | Audit를 독립 Gate로 정의하고 Skill 목록에서 제외 |
| 8개 Data Contract 일치 | PASS | Architecture와 Plan이 동일한 8개 이름 사용 |
| Approval 이전 외부 쓰기 차단 | PASS | Architecture, Contract 상태전이, Phase 8~9가 일치 |
| DB Engine 미확정 유지 | PASS | 논리 Type만 정의하고 구현 선택을 유보 |
| Capability 단위 Migration | PASS | Matrix가 원천 파일과 신규 Capability를 분리 |
| Mock-only 완료 금지 | PASS | PHASE 3·9·11에 Live/병행 검증 조건 존재 |
| Legacy 삭제/복사 금지 | PASS | Do Not Migrate와 보호 목록이 일치 |
| 미확정 운영 임계값 | WARN | 최신성 SLA, 등급 경계, 승인 만료시간은 근거 확보 후 확정 필요 |

**종합 판정: PASS**

WARN 항목은 정책 수치를 임의로 만들지 않기 위해 의도적으로 미확정한 것이며, Core Schema와 첫 구현 작업을 시작하는 데에는 장애가 아니다.
