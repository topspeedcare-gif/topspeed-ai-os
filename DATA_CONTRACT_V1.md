# TOPSPEED AI OS — Data Contract v1

- 문서 상태: **FROZEN**
- 범위: 엔진 독립 논리 Schema
- DB Engine: 미정

## 1. 공통 규칙

### 1.1 Type 표기

| Type | 규칙 |
| --- | --- |
| `STRING` | UTF-8 문자열 |
| `INTEGER` | 정수 |
| `DECIMAL` | 부동소수점이 아닌 정확한 10진수 |
| `BOOLEAN` | `true` / `false` |
| `DATE` | `YYYY-MM-DD` |
| `DATETIME` | timezone을 포함한 ISO 8601 |
| `ENUM` | 문서에 정의된 값 중 하나 |
| `JSON` | Schema 검증 대상 구조화 값 |
| `URI` | 위치 또는 외부 참조 URI |

금액은 통화기호와 천 단위 구분자 없이 저장한다. 비율은 `0.108`처럼 0~1 소수로 저장한다. 원본이 퍼센트면 수집 단계에서 변환 규칙을 기록한다.

### 1.2 공통 식별자와 적용 범위

| 식별자 | 규칙 | 적용 |
| --- | --- | --- |
| `sku` | TOPSPEED 내부 불변 상품 식별자 | 상품·채널·광고·재고·콘텐츠·승인·로그 |
| `task_id` | 대표 요청 또는 분할된 하위 요청 식별자 | 처리·승인·로그 |
| `run_id` | 한 번의 실행 시도 식별자 | 수집·계산·감사·승인·로그 |
| `approval_id` | 한 승인 객체 식별자 | 승인·실행·로그 |
| `idempotency_key` | 동일 외부 쓰기 중복 방지 키 | 승인·실행·로그 |
| `source` | 값의 원천 시스템 또는 문서 | 모든 사실·지표·기록 |
| `data_as_of` | Source 데이터가 유효한 기준시각 | 모든 사실·지표·판정 |
| `created_at` | 레코드 생성시각 | 모든 테이블 |

`sku`가 없는 회사 전체 집계 또는 시스템 이벤트는 명시적으로 null을 허용하되 `scope` 또는 `target_id`를 기록한다.

### 1.3 공통 무결성 규칙

- `sku`는 먼저 `PRODUCT_MASTER`에 존재해야 한다.
- 외부 채널 상품 ID는 내부 `sku`를 대체하지 않는다.
- `data_as_of` 없는 외부 사실은 공식 분석 입력으로 사용할 수 없다.
- 동일 Source, 동일 자연키, 동일 기준일의 중복 레코드는 거부하거나 새 버전으로 명시한다.
- 원본 값과 파생 값은 필드 또는 provenance로 구분한다.
- `APPROVAL_QUEUE`와 `AI_RUN_LOG`는 삭제·덮어쓰기 대신 상태 전이 또는 이벤트 추가를 사용한다.

## 2. `PRODUCT_MASTER`

SKU별 기준 정보와 운영 상태의 단일 논리 원장이다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `sku` | STRING | Y | 내부 불변 SKU | 내부 발급 | `TS-KITCHEN-001` |
| `product_name` | STRING | Y | 대표 상품명 | 대표 승인/상품 원장 | `스테인리스 배수구 거름망` |
| `category` | STRING | Y | 내부 표준 카테고리 | 내부 원장 | `주방용품` |
| `channel_ids` | JSON | N | 채널별 product/vendor item ID | 채널 API | `{"coupang_vendor_item_id":"12345"}` |
| `stage` | ENUM | Y | `SOURCE/TEST/SCALE/CORE/EXIT` | launch 승인 | `TEST` |
| `grade` | ENUM | N | `S/A/B/T/X` | launch 계산/승인 | `B` |
| `status` | ENUM | Y | `DRAFT/ACTIVE/PAUSED/ENDED` | 내부 원장 | `ACTIVE` |
| `supplier` | STRING | N | 공급처 식별명 | 계약/수기 검증 | `SUP-001` |
| `currency` | STRING | Y | ISO 4217 통화 | 내부 정책 | `KRW` |
| `purchase_cost` | DECIMAL | N | 단위 매입원가 | 발주/원가 자료 | `5200` |
| `sale_price` | DECIMAL | N | 기준 판매가 | 채널/내부 승인 | `12900` |
| `fee_rate` | DECIMAL | N | 판매 수수료율 | 채널 계약 | `0.108` |
| `fulfillment_cost` | DECIMAL | N | 단위 물류비 | 물류 계약 | `2500` |
| `expected_return_cost` | DECIMAL | N | 단위 기대 반품비 | 확정 계산식 | `350` |
| `other_variable_cost` | DECIMAL | N | 기타 단위 변동비 | 내부 원가 | `100` |
| `contribution_margin` | DECIMAL | N | 광고비 제외 단위 공헌이익 파생값 | Calculation Engine | `3356.8` |
| `contribution_margin_rate` | DECIMAL | N | 공헌이익/판매가 | Calculation Engine | `0.2602` |
| `source` | STRING | Y | 기준정보 원천 | 내부/채널 | `manual_verified` |
| `data_as_of` | DATETIME | Y | 원가·가격 기준시각 | Source | `2026-09-16T09:00:00+09:00` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T09:10:00+09:00` |
| `updated_at` | DATETIME | Y | 최종 변경시각 | 시스템 | `2026-09-16T09:10:00+09:00` |

공헌이익 공식:

`sale_price - purchase_cost - (sale_price × fee_rate) - fulfillment_cost - expected_return_cost - other_variable_cost`

`SOURCE` 또는 `DRAFT` 단계에서는 원가 필드가 비어 있을 수 있다. `launch` 판정과 공헌이익 계산을 시작하려면 위 6개 입력값이 모두 필요하며, 하나라도 없으면 결론을 생성하지 않는다.

## 3. `PRODUCT_FACT`

상품 주장, 인증, 규격, 소재, 사용 조건 등 검증 가능한 사실을 SKU별로 격리한다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `fact_id` | STRING | Y | 사실 레코드 ID | 시스템 | `fact_01J...` |
| `sku` | STRING | Y | 대상 SKU | PRODUCT_MASTER | `TS-KITCHEN-001` |
| `fact_type` | STRING | Y | 사실 분류 | 내부 분류 | `material` |
| `fact_value` | JSON | Y | 구조화 사실 값 | 원본 자료 | `{"value":"STS304"}` |
| `unit` | STRING | N | 측정 단위 | 원본 자료 | `mm` |
| `verification_status` | ENUM | Y | `UNVERIFIED/VERIFIED/REJECTED/EXPIRED` | data/audit | `VERIFIED` |
| `source` | STRING | Y | 원천 유형/시스템 | Tool | `supplier_certificate` |
| `source_uri` | URI | N | 원본 위치 | Source | `drive://file/abc` |
| `source_checksum` | STRING | N | 원본 SHA-256 | Ingestion | `sha256:ab12...` |
| `verified_at` | DATETIME | N | 검증시각 | Audit/사람 | `2026-09-15T16:00:00+09:00` |
| `valid_from` | DATE | N | 효력 시작일 | 원본 | `2026-01-01` |
| `valid_to` | DATE | N | 효력 종료일 | 원본 | `2027-01-01` |
| `run_id` | STRING | N | 수집/검증 run | 시스템 | `run_01J...` |
| `task_id` | STRING | N | 요청 ID | 시스템 | `task_01J...` |
| `data_as_of` | DATETIME | Y | 사실 기준시각 | Source | `2026-09-15T15:00:00+09:00` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T09:10:00+09:00` |

콘텐츠에 사용할 수 있는 사실은 기본적으로 `VERIFIED`이며 유효기간이 지나지 않아야 한다.

## 4. `CHANNEL_DAILY`

채널별 SKU 일간 판매·환불·수수료 지표다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `channel` | STRING | Y | 판매 채널 | Connector | `coupang` |
| `stat_date` | DATE | Y | 집계일 | 채널 API | `2026-09-15` |
| `sku` | STRING | Y | 내부 SKU | Mapping | `TS-KITCHEN-001` |
| `channel_product_id` | STRING | N | 채널 상품 ID | 채널 API | `987654` |
| `gross_sales` | DECIMAL | Y | 총 결제 매출 | 채널 API | `1290000` |
| `net_sales` | DECIMAL | Y | 환불 반영 순매출 | Adapter | `1225500` |
| `orders` | INTEGER | Y | 주문 건수 | 채널 API | `102` |
| `units_sold` | INTEGER | Y | 판매 수량 | 채널 API | `108` |
| `refunds` | INTEGER | Y | 환불 건수 | 채널 API | `5` |
| `refund_amount` | DECIMAL | Y | 환불 금액 | 채널 API | `64500` |
| `channel_fees` | DECIMAL | N | 채널 수수료 | 정산/API | `132354` |
| `settlement_amount` | DECIMAL | N | 정산 예정/확정액 | 정산/API | `1093146` |
| `page_views` | INTEGER | N | 상품 조회수 | 채널 API | `3410` |
| `conversion_rate` | DECIMAL | N | 주문 또는 구매 전환율 | Calculation Engine | `0.0299` |
| `run_id` | STRING | Y | 수집 run | 시스템 | `run_01J...` |
| `source` | STRING | Y | 원천 endpoint/file | Connector | `coupang_api/orders` |
| `data_as_of` | DATETIME | Y | 원천 기준시각 | 채널 API | `2026-09-16T06:00:00+09:00` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T06:05:00+09:00` |

자연키는 `(channel, stat_date, sku)`다. 집계 정의가 달라지는 경우 별도 `metric_version`을 추가하고 같은 정의처럼 합치지 않는다.

## 5. `AD_DAILY`

SKU·캠페인 단위 일간 광고 성과다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `channel` | STRING | Y | 광고 채널 | Connector/파일 | `coupang_ads` |
| `stat_date` | DATE | Y | 집계일 | 광고 보고서 | `2026-09-15` |
| `sku` | STRING | Y | 내부 SKU | Mapping | `TS-KITCHEN-001` |
| `campaign_id` | STRING | Y | 캠페인 ID | 광고 Source | `cmp_123` |
| `campaign_name` | STRING | N | 캠페인 명칭 | 광고 Source | `키친_테스트` |
| `ad_group_id` | STRING | N | 광고그룹 ID | 광고 Source | `grp_10` |
| `impressions` | INTEGER | Y | 노출수 | 광고 Source | `82500` |
| `clicks` | INTEGER | Y | 클릭수 | 광고 Source | `1030` |
| `ad_spend` | DECIMAL | Y | 광고비 | 광고 Source | `206000` |
| `ad_orders` | INTEGER | Y | 광고 기여 주문수 | 광고 Source | `52` |
| `ad_units` | INTEGER | N | 광고 기여 판매수량 | 광고 Source | `55` |
| `ad_revenue` | DECIMAL | Y | 광고 기여 매출 | 광고 Source | `709500` |
| `ctr` | DECIMAL | N | clicks/impressions | Calculation Engine | `0.0125` |
| `cvr` | DECIMAL | N | ad_orders/clicks | Calculation Engine | `0.0505` |
| `roas` | DECIMAL | N | ad_revenue/ad_spend | Calculation Engine | `3.4442` |
| `source_file_hash` | STRING | N | 파일 수집 시 SHA-256 | Ingestion | `sha256:cd34...` |
| `run_id` | STRING | Y | 수집 run | 시스템 | `run_01J...` |
| `source` | STRING | Y | 원천 파일/API | Connector | `coupang_ad_xlsx` |
| `data_as_of` | DATETIME | Y | 원천 기준시각 | Source | `2026-09-16T05:30:00+09:00` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T06:10:00+09:00` |

자연키는 `(channel, stat_date, sku, campaign_id, ad_group_id)`다. 파일 hash가 달라도 자연키가 같으면 중복 검사를 수행한다.

## 6. `INVENTORY`

시점별 SKU 재고 Snapshot과 재발주 계산 입력·결과다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `snapshot_at` | DATETIME | Y | 재고 관측시각 | 채널/창고 | `2026-09-16T08:00:00+09:00` |
| `sku` | STRING | Y | 내부 SKU | Mapping | `TS-KITCHEN-001` |
| `location` | STRING | Y | 채널/창고 위치 | Source | `coupang_fulfillment` |
| `on_hand_qty` | INTEGER | Y | 물리 재고 | 채널/창고 | `320` |
| `available_qty` | INTEGER | Y | 판매 가능 재고 | 채널/창고 | `285` |
| `reserved_qty` | INTEGER | Y | 예약/할당 재고 | 채널/창고 | `20` |
| `inbound_qty` | INTEGER | Y | 입고 예정 수량 | 발주/창고 | `100` |
| `avg_daily_units` | DECIMAL | N | 확정 기간 일평균 판매 | Calculation Engine | `24.5` |
| `stock_days` | DECIMAL | N | available/avg daily units | Calculation Engine | `11.63` |
| `lead_time_days` | INTEGER | N | 조달 리드타임 | 공급처 계약 | `14` |
| `safety_stock_qty` | INTEGER | N | 안전재고 | Calculation Engine/정책 | `98` |
| `reorder_point_qty` | INTEGER | N | 재주문점 | Calculation Engine | `441` |
| `recommended_order_qty` | INTEGER | N | 권장 발주량 | Calculation Engine | `356` |
| `run_id` | STRING | Y | 수집/계산 run | 시스템 | `run_01J...` |
| `source` | STRING | Y | 재고 원천 | Connector | `coupang_api/inventory` |
| `data_as_of` | DATETIME | Y | 원천 기준시각 | Source | `2026-09-16T08:00:00+09:00` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T08:03:00+09:00` |

평균 판매기간, 안전재고 공식과 정책 버전은 계산 결과 provenance에 기록한다. 평균 판매량이 0이면 `stock_days`를 임의의 큰 숫자로 만들지 않고 null 및 사유를 기록한다.

## 7. `CONTENT_ASSET`

현재 SKU에 귀속되는 콘텐츠 초안·승인본·게시본의 버전 기록이다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `asset_id` | STRING | Y | 콘텐츠 자산 ID | 시스템 | `asset_01J...` |
| `sku` | STRING | Y | 대상 SKU | PRODUCT_MASTER | `TS-KITCHEN-001` |
| `asset_type` | ENUM | Y | `COPY/IMAGE_BRIEF/IMAGE/DETAIL_PAGE/AD_CREATIVE` | content | `DETAIL_PAGE` |
| `title` | STRING | Y | 자산명 | content/사용자 | `상세페이지 초안 v1` |
| `storage_uri` | URI | Y | 실제 파일/문서 위치 | 저장 Tool | `drive://file/xyz` |
| `checksum_sha256` | STRING | Y | 콘텐츠 checksum | 시스템 | `sha256:ef56...` |
| `mime_type` | STRING | Y | MIME type | 파일 | `text/markdown` |
| `version` | INTEGER | Y | SKU·유형별 버전 | 시스템 | `1` |
| `status` | ENUM | Y | `DRAFT/APPROVED/PUBLISHED/ARCHIVED` | 승인/실행 | `DRAFT` |
| `claim_fact_ids` | JSON | Y | 주장에 연결된 PRODUCT_FACT IDs | content/audit | `["fact_01J..."]` |
| `generated_by` | STRING | Y | 생성 주체/모델/사람 | 시스템 | `content_skill` |
| `task_id` | STRING | Y | 생성 요청 | 시스템 | `task_01J...` |
| `run_id` | STRING | Y | 생성 run | 시스템 | `run_01J...` |
| `approved_by` | STRING | N | 승인자 | APPROVAL_QUEUE | `owner` |
| `source` | STRING | Y | 사용한 Source 집합 참조 | Data Layer | `product_fact` |
| `data_as_of` | DATETIME | Y | 사용 사실 기준시각 | Data Layer | `2026-09-15T16:00:00+09:00` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T10:00:00+09:00` |
| `updated_at` | DATETIME | Y | 최종 변경시각 | 시스템 | `2026-09-16T10:00:00+09:00` |

게시 완료는 Execution Adapter의 사후 확인 전에는 `PUBLISHED`로 전환하지 않는다.

## 8. `APPROVAL_QUEUE`

외부 쓰기와 사업 상태 변경을 위한 승인 상태 원장이다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `approval_id` | STRING | Y | 승인 객체 ID | 시스템 | `apr_01J...` |
| `task_id` | STRING | Y | 원 요청 ID | HQ | `task_01J...` |
| `run_id` | STRING | Y | 승인안 생성 run | HQ | `run_01J...` |
| `sku` | STRING | N | 대상 SKU | Router | `TS-KITCHEN-001` |
| `action_type` | STRING | Y | 실행 종류 | Skill/HQ | `AD_BUDGET_UPDATE` |
| `target_type` | STRING | Y | 대상 객체 종류 | Execution Contract | `campaign` |
| `target_id` | STRING | Y | 외부/내부 대상 ID | Source | `cmp_123` |
| `proposed_payload` | JSON | Y | 승인할 정확한 실행값 | HQ | `{"daily_budget":300000}` |
| `payload_hash` | STRING | Y | 정규화 payload SHA-256 | 시스템 | `sha256:9012...` |
| `before_value` | JSON | Y | 승인 시점 현재 값 | Read Tool | `{"daily_budget":200000}` |
| `after_value` | JSON | Y | 제안 값 | Skill/Calculation | `{"daily_budget":300000}` |
| `risk_level` | ENUM | Y | `LOW/MEDIUM/HIGH` | 정책 | `HIGH` |
| `audit_status` | ENUM | Y | `PASS/WARN/FAIL` | Audit | `WARN` |
| `audit_summary` | STRING | Y | 경고/검증 요약 | Audit | `최근 1일 데이터 지연` |
| `approval_status` | ENUM | Y | `PENDING/APPROVED/REJECTED/EXPIRED/CANCELLED/EXECUTED/FAILED` | State machine | `PENDING` |
| `requested_by` | STRING | Y | 요청 주체 | HQ/사용자 | `owner` |
| `approved_by` | STRING | N | 결정자 | Gateway | `owner` |
| `requested_at` | DATETIME | Y | 승인 요청시각 | 시스템 | `2026-09-16T10:10:00+09:00` |
| `decided_at` | DATETIME | N | 승인/거절시각 | 시스템 | `2026-09-16T10:15:00+09:00` |
| `expires_at` | DATETIME | Y | 승인 만료시각 | 정책 | `2026-09-16T12:10:00+09:00` |
| `execution_tool` | STRING | Y | 허용된 실행 Tool | 정책 | `coupang_ads_write_v1` |
| `idempotency_key` | STRING | Y | 중복 실행 방지 키 | 시스템 | `idem_01J...` |
| `source` | STRING | Y | 제안 근거 Source 참조 | Data Layer | `ad_daily` |
| `data_as_of` | DATETIME | Y | 승인 근거 기준시각 | Data Layer | `2026-09-16T06:00:00+09:00` |
| `error` | STRING | N | 실패 요약 | 시스템 | `STATE_CHANGED` |
| `created_at` | DATETIME | Y | 생성시각 | 시스템 | `2026-09-16T10:10:00+09:00` |
| `updated_at` | DATETIME | Y | 최종 상태 변경시각 | 시스템 | `2026-09-16T10:15:00+09:00` |

`FAIL` Audit는 `PENDING`을 생성할 수 없다. 승인 만료, payload hash 불일치, `before_value` 변화 중 하나라도 있으면 실행을 차단한다.

## 9. `AI_RUN_LOG`

전체 처리 생명주기의 append-only 이벤트 기록이다.

| 이름 | Type | Required | 의미 | Source | Example |
| --- | --- | --- | --- | --- | --- |
| `log_id` | STRING | Y | 로그 이벤트 ID | 시스템 | `log_01J...` |
| `event_seq` | INTEGER | Y | run 내 순서 | 시스템 | `7` |
| `event_type` | STRING | Y | 처리 단계/이벤트 | 시스템 | `AUDIT_COMPLETED` |
| `run_id` | STRING | Y | 실행 시도 ID | HQ | `run_01J...` |
| `task_id` | STRING | Y | 요청 ID | HQ | `task_01J...` |
| `parent_run_id` | STRING | N | 재시도/하위 run 부모 | HQ | `run_01H...` |
| `agent` | STRING | Y | 수행 계층/Agent | 시스템 | `hq_orchestrator` |
| `skill` | ENUM | N | 6개 Skill 중 하나 | Router | `ads_ops` |
| `sku` | STRING | N | 대상 SKU | Router | `TS-KITCHEN-001` |
| `source` | JSON | Y | 사용 Source와 참조 ID | Tool/Data | `["ad_daily:2026-09-15"]` |
| `data_as_of` | DATETIME | N | 분석 기준시각 | Data Layer | `2026-09-16T06:00:00+09:00` |
| `input_summary` | STRING | Y | 비밀 제외 입력 요약 | 실행 계층 | `예산 20만→30만원 제안` |
| `output_summary` | STRING | Y | 결과 요약 | 실행 계층 | `WARN, 승인 요청 생성` |
| `tool_name` | STRING | N | 호출 Tool | Tool Layer | `ad_metrics_calculator_v1` |
| `approval_id` | STRING | N | 관련 승인 ID | Approval | `apr_01J...` |
| `approval_status` | ENUM | N | 해당 시점 승인 상태 | Approval | `PENDING` |
| `audit_status` | ENUM | N | `PASS/WARN/FAIL` | Audit | `WARN` |
| `before_value` | JSON | N | 실행 전 값 | Read/Execution | `{"daily_budget":200000}` |
| `after_value` | JSON | N | 실행 후 확인값 | Execution/Post-audit | `{"daily_budget":300000}` |
| `result` | ENUM | Y | `STARTED/SUCCEEDED/BLOCKED/FAILED/CANCELLED` | 시스템 | `BLOCKED` |
| `error_code` | STRING | N | 기계 판독 오류 코드 | 시스템 | `APPROVAL_EXPIRED` |
| `error` | STRING | N | 사람용 오류 요약 | 시스템 | `승인 유효시간 경과` |
| `human_edit_ratio` | DECIMAL | N | 승인 전 사람이 수정한 비율 | 비교기 | `0.12` |
| `idempotency_key` | STRING | N | 실행 중복 방지 키 | Approval | `idem_01J...` |
| `started_at` | DATETIME | Y | 단계 시작시각 | 시스템 | `2026-09-16T10:10:00+09:00` |
| `finished_at` | DATETIME | N | 단계 종료시각 | 시스템 | `2026-09-16T10:10:02+09:00` |
| `created_at` | DATETIME | Y | 이벤트 기록시각 | 시스템 | `2026-09-16T10:10:02+09:00` |

## 10. 상태 전이와 참조 규칙

### Approval 상태 전이

허용:

- `PENDING → APPROVED | REJECTED | EXPIRED | CANCELLED`
- `APPROVED → EXECUTED | FAILED | EXPIRED | CANCELLED`

그 외 직접 전이는 거부한다. `REJECTED`, `EXPIRED`, `CANCELLED`, `EXECUTED`는 종결 상태다.

### 교차 참조

- `CONTENT_ASSET.claim_fact_ids`는 동일 SKU의 `PRODUCT_FACT.fact_id`만 참조한다.
- `APPROVAL_QUEUE.run_id/task_id`는 `AI_RUN_LOG`에서 추적 가능해야 한다.
- 실행 이벤트의 `approval_id`, payload hash, `idempotency_key`는 승인 레코드와 일치해야 한다.
- `CHANNEL_DAILY`, `AD_DAILY`, `INVENTORY`의 파생 지표는 계산 버전과 원본 필드를 로그에서 재현할 수 있어야 한다.
