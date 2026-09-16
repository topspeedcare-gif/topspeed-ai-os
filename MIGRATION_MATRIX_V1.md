# TOPSPEED AI OS — Migration Matrix v1

- 원칙: 파일 복사가 아니라 Capability 추출
- 판정: `KEEP`, `REFACTOR`, `REFERENCE`, `DROP`
- `KEEP`도 신규 저장소에 파일을 그대로 복사한다는 뜻이 아니라, 독립 자산 또는 정책을 최소 수정으로 채택한다는 뜻이다.
- 신규 목적 Data Contract: `PRODUCT_MASTER`, `PRODUCT_FACT`, `CHANNEL_DAILY`, `AD_DAILY`, `INVENTORY`, `CONTENT_ASSET`, `APPROVAL_QUEUE`, `AI_RUN_LOG`

## 1. 판정 기준

| 판정 | 기준 |
| --- | --- |
| `KEEP` | 신규 목적과 계약이 일치하고 최소 수정으로 독립 사용 가능 |
| `REFACTOR` | Capability 가치가 있으나 Legacy 결합·데이터 계약·안전성 수정 필요 |
| `REFERENCE` | 설계/UX/운영 경험만 참고하고 코드는 가져오지 않음 |
| `DROP` | 신규 Core에 기술부채·목적 충돌·보안 위험을 더함 |

## 2. Asset Migration Matrix

| 기존 경로 / 자산 | 현재 역할 | 판정 | 신규 목적지 / Capability | 필수 수정 | 위험도 | 근거 |
| --- | --- | --- | --- | --- | --- | --- |
| `.gitignore` 보안 제외 규칙 | secret/runtime/venv 제외 | REFACTOR | 신규 저장소 보안 baseline | 안전한 제외 원칙만 가져와 새 경로와 예외 규칙을 재작성 | LOW | 원칙은 유효하지만 Legacy 경로와 깨진 주석을 복사할 이유 없음 |
| `.env.example` | 환경변수 예시 | REFACTOR | `config/env.example` | Legacy 비서 키 제거, AI OS connector별 최소권한만 기재 | MEDIUM | 설정 명칭 참고 가능하나 범위 과다 |
| `src/coupang_client.py` | Coupang HMAC API 조회 | REFACTOR | `tools/read/coupang` | 인증부 분리, typed response, timeout/retry/rate-limit, read-only allowlist | HIGH | 가치 높은 실제 Capability지만 운영 계약 부족 |
| `src/coupang_sync.py` | 쿠팡 데이터 수집·집계·latest 생성 | REFACTOR | `adapters/commerce/coupang` | Data Contract 변환, 부분 실패 시 publish 금지, provenance/기준일 | HIGH | 오류 상태에서도 latest 덮어쓰기 가능 |
| 기존 쿠팡 HMAC 생성 로직 | API 서명 | REFACTOR | Coupang auth helper | 공식 fixture 검증, secret 비노출, clock skew 처리 | MEDIUM | 파일 전체보다 서명 Capability만 필요 |
| 쿠팡 raw/snapshot 집계 로직 | 매출·주문·상품·재고 집계 | REFACTOR | `CHANNEL_DAILY`, `INVENTORY` adapter | 내부 SKU mapping, 자연키 중복 방지, 단위/정의 명시 | HIGH | 현재 runtime JSON 구조는 공식 계약 아님 |
| `src/ad_report_importer.py` | 광고 Excel parser/hash dedupe | REFACTOR | `tools/ingest/ad_daily_excel` | 날짜·SKU·캠페인 자연키, 중복 기간 검출, 헤더 버전 검사 | HIGH | 파일 hash만으로는 교차 파일 중복 방지 불가 |
| `src/spreadsheet_hub.py` | 활성 Spreadsheet 선택/처리 | REFACTOR | `tools/ingest/tabular` | 전역 활성 파일 제거, 명시적 input URI, schema validation | MEDIUM | 파서 아이디어는 유효, 상태 결합 제거 필요 |
| Drive read-only ingestion 모듈 | Drive 파일 검색/수집 | REFACTOR | `tools/read/drive_source` | readonly scope 고정, Source metadata, checksum, 기준일 | MEDIUM | Source Ingestion에 직접 가치 있음 |
| SHA-256 지식 중복 방지 로직 | 파일 중복 수집 방지 | KEEP | `ingestion/dedup` | 표준 checksum 표기와 자연키 중복 검사를 함께 사용 | LOW | 결정론적이고 독립적 Capability |
| knowledge index JSONL | 수집된 지식 인덱스 | REFERENCE | Source metadata 설계 참고 | 원장으로 이전 금지, Data Contract로 재수집 | MEDIUM | runtime 상태이며 GitHub에 없음 |
| `src/inventory_monitor.py` | 재고 위험 판단 | REFERENCE | `calculators/inventory` 요구사항 | 하드코딩 제거, 공식 공식·정책을 새로 구현 | HIGH | 샘플 SKU/placeholder로 운영 근거 부족 |
| `src/inventory_slack.py` | Slack 재고 알림/상태 갱신 | DROP | Slack Gateway 표시 전용 | 직접 상태 변경 대신 AI OS 결과 렌더링 | HIGH | alias 하드코딩 및 UI와 상태 로직 결합 |
| `src/cost_tracker.py` | 이름 기반 비용 연결 | DROP | SKU 기반 Cost Adapter | 내부 SKU/근거 Source 기반으로 신규 구현 | HIGH | 문자열 부분일치는 오배부 위험 |
| `src/settlement_report.py` | 정산 파일 분류·ledger 기록 | REFERENCE | 정산 수집 요구사항 참고 | 포맷 명시·검증 실패 시 중단·쓰기 분리 | HIGH | 미지 포맷을 Coupang으로 간주하고 자동 쓰기 가능 |
| `src/audit.py` | JSONL 이벤트 기록 | REFACTOR | `audit/` + `AI_RUN_LOG` writer | 전체 필드 계약, append-only, ID 연결, redaction | HIGH | 안정 필드가 timestamp/event_type에 그침 |
| 기존 JSONL 감사 포맷 | 이벤트 로그 | REFERENCE | Event taxonomy 참고 | 공식 AI_RUN_LOG에 직접 import 금지 | MEDIUM | 출처·승인·SKU·전후값 추적 부족 |
| `src/slack_app.py` | 3,487줄 Slack/명령/승인/업무 허브 | REFERENCE | `gateways/slack` UX 참고 | Core logic 복사 금지, API client로 얇게 재작성 | HIGH | 58 exact handler와 background loop가 강결합 |
| 기존 Slack 승인 카드/버튼 UX | 사람 승인 인터페이스 | REFERENCE | Approval UI | approval_id/payload hash/만료/상태 표시 추가 | HIGH | 사용자별 최신 pending을 실행할 위험 |
| 기존 pending approval JSON | 사용자별 단일 대기 작업 | DROP | `APPROVAL_QUEUE` | 승인 상태 machine 신규 구현 | HIGH | 승인 ID, payload 고정, 만료, 멱등성 없음 |
| `src/multi_agent.py` | 5개 부서 Prompt를 한 Codex 호출로 합성 | DROP | HQ + Structured Router + 독립 Skill | 코드 복사 금지, 역할 설명만 재검토 | HIGH | 실제 Multi-Agent/Tool 격리가 아님 |
| Butler command dispatcher | Slack 명령 routing | REFERENCE | Structured Router 테스트 아이디어 | exact command registry를 사업 Router로 사용 금지 | MEDIUM | UI 명령 분배와 Domain routing은 목적이 다름 |
| 부서 역할 Prompt | 개인비서 역할 분담 | REFERENCE | Skill non-trigger 작성 참고 | 사실/계약/Tool 권한을 새로 정의 | MEDIUM | 역할극 Prompt이며 실행 경계가 없음 |
| `prompts/` 일일 브리핑 계열 | 요약 문구 생성 | REFERENCE | HQ presentation template | Data Contract 참조와 불확실성 표기 추가 | LOW | 표현 형식만 참고 가치 |
| `prompts/` task/Butler 계열 | 비서 작업 지침 | DROP | 없음 | 신규 OS에 복사하지 않음 | MEDIUM | 이커머스 Core 목적과 불일치 |
| Gmail integration | 메일 조회/전송 | DROP | LifeOS에 잔류 | AI OS Core에 넣지 않음 | MEDIUM | 개인비서 책임 |
| Calendar integration | 일정 CRUD | DROP | LifeOS에 잔류 | AI OS Core에 넣지 않음 | MEDIUM | 개인비서 책임 |
| Notion integration | Notion CRUD | DROP | LifeOS에 잔류 | 필요 시 향후 Gateway로만 연결 | MEDIUM | Core 업무 원장과 충돌 가능 |
| Kakao send integration | 메시지 발송 | DROP | LifeOS에 잔류 | 신규 Core 직접 발송 금지 | MEDIUM | 인터페이스 책임 |
| Wing session cookie 자동화 | 세션 기반 비공식 접근 | DROP | 공식 API/수기 검증 Source | credential/약관/세션 의존 제거 | HIGH | 취약한 인증과 로컬 종속 |
| Naver config flags | 구현 없는 설정 | DROP | 향후 별도 ADR | 실제 Connector 전까지 추가 금지 | LOW | 계획과 구현 구분 필요 |
| Google Sheets 관련 placeholder | Sheet 연동 예정 코드 | DROP | 향후 Data Adapter | 요구 시 계약부터 신규 작성 | MEDIUM | 실제 API client 부재 |
| `runtime_workspace/05_DATA_HUB/...` | 로컬 raw/snapshot/state | REFERENCE | Data Contract/fixture 참고 | Source 확인 후 재수집, 원장으로 복사 금지 | HIGH | Git 미추적·품질/최신성 불명 |
| `runtime_workspace/06_INVENTORY/...` | 임계값·원가·실험 상태 | REFERENCE | 정책 seed 후보 | 각 값 출처/승인/기준일 확인 | HIGH | 운영 값의 provenance 불명 |
| `runtime_workspace/07_FINANCE/ledger.*` | 로컬 재무 ledger | REFERENCE | 정산 Contract 후보 | 공식 회계 원장으로 사용 금지 | HIGH | 자동 기록 경로와 검증 부족 |
| `runtime_workspace/09_AI_DEPARTMENTS/...` | 회사/부서 정책 문서 | REFACTOR | `policies/legacy_reviewed` | 조항별 소유자·버전·충돌 검토 후 채택 | MEDIUM | 정책 지식은 가치 있으나 현재 내용 미감사 |
| `runtime_workspace/AGENTS.md` | Legacy workspace 운영 지침 | DROP | 신규 `AGENTS.md` | Architecture Freeze 기준으로 새로 작성 | HIGH | Legacy 실행 방식 전파 위험 |
| `app.py` | LifeOS 애플리케이션 진입점 | DROP | 없음; LifeOS 잔류 | 신규 Core에서 import/복사 금지 | HIGH | 실행 생명주기 강결합 |
| `start_bot*.bat/ps1` | Windows 자동 시작 | DROP | LifeOS에 잔류 | 신규 배포는 별도 설계 | MEDIUM | 로컬 PC와 Legacy 경로 종속 |
| `start_dashboard*.bat/ps1` | Dashboard 자동 시작 | DROP | LifeOS에 잔류 | 신규 OS 배포와 분리 | MEDIUM | 로컬 UI 책임 |
| `INSTALL_*`, `RESET_*`, `REGISTER_*` | Legacy 설치/스케줄러 | DROP | LifeOS에 잔류 | 신규 저장소로 이동 금지 | MEDIUM | Windows/Legacy bootstrap 종속 |
| `automation/` 스케줄러 | 기존 알림·주기 작업 | REFERENCE | 향후 trigger/gateway 참고 | AI OS 승인/로그 계약을 거쳐 재설계 | HIGH | 자동 실행과 Legacy 상태의 결합 가능 |
| `dashboard/` | LifeOS Dashboard | REFERENCE | 결과 표현 요구사항 | AI OS 원장/계산 로직 포함 금지 | MEDIUM | 화면만 참고, Core로 사용 불가 |
| `scripts/` 데이터 유틸 | 설치/점검/보조 스크립트 | REFERENCE | 개별 Capability 검토 | script별 입력·부작용·secret 사용 재감사 | MEDIUM | 일괄 Migration 불가 |
| `tests/` 순수 파서/계산 테스트 | 기존 unit test | REFACTOR | Connector/Calculator fixtures | 신규 Contract 기준 expected value 재작성 | MEDIUM | 일부 fixture 아이디어는 재사용 가능 |
| `tests/` Slack/Butler 테스트 | Legacy UI/명령 테스트 | DROP | LifeOS에 잔류 | 신규 Core 테스트로 복사 금지 | LOW | 신규 목적과 불일치 |
| 기존 Mock API 테스트 | 외부 연동 모의 검사 | REFERENCE | contract test 참고 | live smoke test 별도 필수 | HIGH | 실제 계정/API 성공을 증명하지 않음 |
| `VERSION.txt` 및 버전 테스트 | Legacy 버전 표기 | DROP | 신규 SemVer/Schema version | 새 저장소에서 독립 발급 | LOW | 현재 4.0.0과 test 3.0.0 불일치 |
| `README.md`, `START_HERE.md`, `DESKTOP_SETUP.md` | LifeOS 사용/설치 문서 | DROP | LifeOS에 잔류 | 신규 OS 문서는 처음부터 작성 | LOW | 로컬 Butler 운영 문서 |
| `requirements.txt` | Legacy 전체 의존성 | DROP | 신규 최소 의존성 manifest | Layer별 실제 필요 패키지만 pin | HIGH | 비서 기능 의존성/버전 잠금 부족 |
| `slack-manifest.yaml` | LifeOS Slack App 권한 | REFERENCE | Slack Gateway 권한 참고 | 최소 scope의 별도 App/manifest 검토 | HIGH | 기존 광범위 권한을 신규 Core와 공유하면 안 됨 |
| `.github/workflows` | CI | DROP | 신규 CI | 현재 파일 부재; 신규 구축 | MEDIUM | 자동 검증 체계 없음 |

## 3. Capability Migration 묶음

| 우선 Capability | 원천 | 신규 계약 | 판정 |
| --- | --- | --- | --- |
| Coupang read/auth | `coupang_client.py` | Read Tool Interface | REFACTOR |
| Commerce aggregation | `coupang_sync.py` | `CHANNEL_DAILY`, `INVENTORY` | REFACTOR |
| Ad Excel ingestion | `ad_report_importer.py` | `AD_DAILY` | REFACTOR |
| Drive source ingestion | Drive 모듈 | `PRODUCT_FACT`, `CONTENT_ASSET` Source | REFACTOR |
| SHA-256 dedup | knowledge ingestion | Ingestion Dedup | KEEP |
| Approval presentation | Slack approval UX | Gateway rendering | REFERENCE |

## 4. Do Not Migrate List

| 자산 | 그대로 가져오면 안 되는 이유 | 대체 방식 |
| --- | --- | --- |
| `src/slack_app.py` | UI, routing, 승인, 상태, background loop가 한 파일에 결합 | 얇은 Slack Gateway + AI OS API 계약 |
| `src/multi_agent.py` | 한 번의 LLM 역할극 호출이며 Tool/상태/검증 격리가 없음 | HQ + Structured Router + 6 Skill |
| 사용자별 pending JSON | 오래된 메시지가 최신 작업을 승인할 수 있음 | 불변 `approval_id` + payload hash + 만료 |
| runtime `latest.json` 원장 | 부분 실패와 최신성 오류를 숨길 수 있음 | 검증 완료 batch만 Data Hub에 publish |
| hardcoded SKU/alias | 다른 상품 데이터 혼입과 잘못된 비용 연결 | 내부 SKU와 명시적 mapping table |
| Wing session cookie | 세션 만료·보안·운영 안정성 위험 | 공식 read API 또는 승인된 수기 Source |
| Windows startup scripts | 한 PC와 사용자 경로에 종속 | 신규 배포/스케줄링 ADR에서 설계 |
| Legacy 전체 requirements | 개인비서 의존성까지 Core에 유입 | 신규 최소 pin/lock 구성 |

## 5. 이번 Freeze에서 변경된 감사 판단

1. 최종 Architecture 선택은 기존의 선택지 C를 유지하되, **LifeOS를 폐기 후보가 아닌 영구적인 Legacy Assistant/Gateway로 명확히 보존**한다.
2. Slack 승인 기능은 재사용 코드가 아니라 **UI 참고 자산**으로 한 단계 낮춘다. 승인 원장은 전부 AI OS가 소유한다.
3. `audit.py`는 단순 Logging 재사용이 아니라 **독립 Audit Layer와 AI_RUN_LOG writer로 분해하여 재구축**한다.
4. `multi_agent.py`는 HQ 후보가 아니라 **DROP**으로 확정한다.
5. 단일 사업자 전용이므로 tenant/account 추상화는 v1 범위에서 제외한다.
6. DB Engine 선택은 Migration 선행 조건에서 제거하고 Data Contract 이후로 연기한다.
