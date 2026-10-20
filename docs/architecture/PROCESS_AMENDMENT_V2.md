**SELF-CHECK = PASS | INDEPENDENT AUDIT = NOT YET PASSED | STATUS = PROPOSAL / NOT EFFECTIVE**

# TOPSPEED AI OS - PROCESS AMENDMENT V2 / R2

## 1. 첫 페이지 실행 체크리스트

**현재 권한은 단일 문서 교정·감사뿐이다.** 코드·테스트 변경, commit/push, visibility 변경, 실제 데이터 처리·등록, Phase 변경은 미승인이다. 현재 PRODUCT_MASTER producer는 기존 절차로 끝까지 완료한다. 재시작·기존 감사 무효화·commit 재작성·publication 생략·V2 시범 포함 금지. V2는 발효 후 신규 승인 WO부터 적용한다.

| Tier | 분류 / 발효 후 실제 수동 경로 |
| --- | --- |
| 0 | 비규범 문구 교정: 대표 WO 승인 → Codex → Audit1 exact-SHA PASS → publication |
| 1 | ADR 직접 근거의 내부 구현: Audit1 WO 승인 → Codex → Audit1 exact-SHA PASS → publication → 의무/표본 Audit2 |
| 2 | 새 계약·ADR·공식·Source·저장/표시 설계·안전 경계·테스트 정리: Audit1 draft → Audit2 WO 승인 → Codex → 양측 동일 SHA PASS → publication |
| 3 | 외부 쓰기·승인 변경·실행 허가/연결·운영 영속화·credential/main 변경: Tier 2 + 행위별 Human 승인 |

모든 경로의 공통 체크리스트: ① Tier/WO 권한 확인. ② **staged 전체 name-status·범위·diff/blob·실제 사업 데이터/비공개 mapping·Gitleaks PASS**. 실패·미확인은 COMMIT BLOCKED. ③ WO가 허용한 parent/paths로 local 단일-parent commit. ④ 봉인 후 exact scope/committed blob 대조. ⑤ **exact parent..authorized SHA 전체 commit/경로/blob·사업 데이터·Gitleaks PASS**, clean/staged 0·remote race·main 불변 확인. 미실시·실패·불명확은 publication BLOCKER. ⑥ **Human이 exact SHA·branch·normal non-force push 1회 승인**. ⑦ Builder와 별도 세션/권한의 **지정 Publication Executor**가 audit branch에 1회 push. ⑧ remote SHA/parent/scope/blob·exact-SHA CI. ⑨ 아래 Tier별 Audit2. 추가 commit/push·force/main 변경·운영 실행 금지.

Tier 1 **pending Audit2** = 첫 5건 의무 대상 또는 이후 5건 batch의 지정 sample 중 exact-SHA Audit2 PASS 전 audit-branch publication. WAITING·IN_REVIEW·FAIL·BLOCKED·미해결 교정을 모두 세며, PASS 또는 Human의 명시적 폐기+main merge 잠금 때만 뺀다. 동시 **최대 2건**: 2건이면 신규 Tier 1 publication을 중단하되 다음 WO·local 구현은 계속하고 새 commit은 기존 승인 범위·보안 Gate를 지킨다. 1건 이하에서 재개하며 표본 제외 재분류·batch 번호 변경으로 우회하지 않는다. 첫 **5건은 각각 의무 Audit2**이고 자기 exact-SHA Audit2 PASS 전 main merge 금지; Audit1 PASS와 publication은 상한 안에서 선행 가능하다. 이후는 publication 순서의 고정 5건 batch로, 시작 전에 첫 publication을 교체 불가 sample로 기록한다. sample 검토 중 나머지 4건과 다음 batch 시작·publication도 같은 상한을 적용한다. 이 4건은 개별 Audit2 없이 **자기 Audit1 exact-SHA PASS·commit 전/push 전 보안 Gate PASS·exact-SHA CI PASS·같은 batch 지정 sample Audit2 PASS·미해결 BLOCKER/MAJOR 없음·Human 별도 exact-SHA main merge 승인**을 모두 갖춰야 merge할 수 있다. queue에는 WO/SHA·batch/sample·검토자·상태(WAITING/IN_REVIEW/FAIL/BLOCKED/교정/PASS/폐기)·기한을 기록한다. Audit1/대표는 영향이 크면 사전 감사를 요구하고 미해결 안전 우려는 push 전에 해소한다.

## 2. V1 대체 조항과 적용 시작

W = docs/architecture/ADR_DEVELOPMENT_WORKFLOW_AUTOMATION_V1.md. S = docs/architecture/DEVELOPMENT_WORKFLOW_STATE_CONTRACT_V1.md. **발효시각 T**는 Audit2 델타 PASS, Human의 본 R2 exact 문서 버전·아래 예외 승인, 기존 절차에 따른 별도 docs-only publication/CI를 모두 충족한 뒤 Human이 명시한다. 이번 요청은 발효/게시 승인이 아니다.

**T 이후 Tier 0/1의 audit-branch publication에 한해** W Fixed Workflow(기준본 L50~64), Publication Preconditions(L127~138), S Publication Contract(L287~299)의 **Audit2 사전 PASS·양측 동일 result_sha 조건**을 1절 수동 경량 경로로 대체한다. **Audit1 exact-SHA PASS·Human exact-SHA 승인·remote race check·normal non-force push·보안 Gate는 유지**한다. **Tier 2/3·main merge·기존 진행 작업은 V1 Gate 그대로**다. 행 번호 기준본은 마지막 절의 remote SHA다.

State Contract V2 승인 전 경량 경로는 **수동 workflow만** 사용한다. V1 Coordinator/Schema에 강제 입력하거나 stage를 조작·우회하지 않는다. V1 모델을 쓰는 작업·자동화 구현 Steps는 V1 규칙을 전부 따른다. Business Freeze/DATA_CONTRACT 의미와 운영 권한은 불변이다.

<!-- PAGE BREAK -->

## 3. 고정 보안 명령과 오염 이력 처리

저장소 루트에서 현재 승인 기준 **Gitleaks 8.30.1**을 사용한다. 버전 변경은 별도 기록 후 승인한다. Human의 본 버전 발효 승인이 V2 도구/명령 기준의 승인이고, Audit1이 실제 version·배포 checksum·범위·결과를 확인한다. local config file 없음, default config 사용. 실행 시 .gitleaks.toml/.gitleaksignore 부재와 GITLEAKS_CONFIG/GITLEAKS_CONFIG_TOML 미설정을 확인한다(값 출력 금지). 임의 config·baseline·제외로 통과시키지 않는다.

**Commit 전:** git diff --cached --name-status 와 git diff --cached 및 staged blob을 전체 확인하여 WO 범위·사업 데이터 Gate를 통과시킨 뒤 아래 명령을 실행한다.

    gitleaks git --pre-commit --staged --redact --no-banner .

PASS는 정상 종료 exit 0이고 검사 대상이 실제 staged 후보와 일치할 때뿐이다. 검사 뒤 index가 변하면 재검사한다. 승인된 parent의 후손으로 exact staged tree를 봉인하며 committed blob과 비교한다.

**Push 전:** PARENT는 WO가 승인한 기존 remote tip, AUTHORIZED_SHA는 push 승인 대상의 실제 40자리 SHA다. 실행자는 자리표시자를 실제 값으로 치환하고 범위를 보고한다. git rev-list --parents PARENT..AUTHORIZED_SHA 로 모든 commit/parent를 확인한다. 기본은 sole parent=PARENT인 1개 commit이며 추가 commit은 별도 승인 없으면 차단한다. git log --format= --name-status PARENT..AUTHORIZED_SHA 및 각 commit의 diff/blob 전체를 검토한다. 최종 net diff만 보고 중간 오염을 놓치지 않는다.

    gitleaks git --log-opts="<parent>..<authorized_sha>" --redact --no-banner .

명령의 <parent>/<authorized_sha>는 위 PARENT/AUTHORIZED_SHA의 실제 값으로 치환한다. 범위는 **parent 제외·authorized SHA 포함의 모든 새 commit**이다. staged 옵션을 섞지 않는다. 빈 범위·ancestry/object/검사 완결성 미확인은 publication BLOCKER다. exact-range PASS 뒤 Human 승인, 지정 Executor의 audit branch 1회 push. CI는 .github/workflows/ci.yml의 **gitleaks/gitleaks-action@v2**이며 사전 로컬 검사를 대체하지 않는다. action @v2와 CLI 버전은 별개다.

두 명령의 version/flag/범위 의미는 upstream v8.30.1 cmd/git.go·cmd/root.go·sources/git.go와 대조했다. 실제 검사 성공은 실행 시 증명한다. 보고에는 **명령·version/설정 식별·범위·exit code·PASS/FAIL·검토자**만 남기고 비밀 후보 실제 값/raw는 남기지 않는다. 내용/설정/범위 변경, 실행 실패·결과 불명확은 재검증 전 진행 금지다.

**오염 SHA는 publication 금지.** local commit 후 발견해도 후속 삭제 commit으로 해결했다고 보지 않는다. batch 동결 후 Audit1의 clean-history corrective WO 및 **별도 Human 승인**으로만 history를 교정하고 깨끗한 부모/후보를 재확인한다. 이전 SHA 승인/PASS는 승계하지 않는다. 무승인 reset/amend/rebase/force 금지. 이미 원격 노출됐다면 별도 사고 대응한다.

## 4. 사업 데이터 Gate와 evidence

실제 판매·재고·주문·반품 CSV/XLSX, raw payload와 비공개 mapping은 **repo 밖 승인 로컬 입력 폴더**에서만 읽는다. repo 안 복사 금지, .gitignore만으로 보호했다고 보지 않는다. commit 전 staged 전체와 push 전 **범위 내 각 commit**에서 .csv/.tsv/.xls/.xlsx/.parquet/.jsonl, 다른 확장자·코드/문서에 삽입된 raw까지 확인한다. 실제/출처 불명이면 BLOCKER. Gitleaks PASS는 사업 데이터 공개 승인이 아니다.

합성 fixture는 tests/fixtures/synthetic/ 아래 **WO의 exact path**만 허용 후보로 삼는다. 합성 또는 적절히 비식별화되고 실제 주문·고객·매출·재고 raw가 아니며 Audit1 공개 가능 확인이 필요하다. 디렉터리 자체는 쓰기 권한이 아니다. 실제 데이터는 repo 내부 **모든 경로에서 금지**다.

실데이터 시작 전 대표가 visibility를 확인한다. PRIVATE 권고/변경 별도 승인. PUBLIC 유지 시 실제 데이터·raw·고객/주문·비공개 mapping은 어떤 형태로도 commit 금지. PRIVATE 전환도 과거 이력·복제본을 회수하지 않는다.

증거는 repo/branch/base/result SHA·parent, tracked/staged/untracked·diff/blob, 관련 QA 명령/환경/exit code, 양 보안 Gate, 승인·Executor, remote/CI로 연결한다. 동일 bytes/설정/환경의 유효 QA는 재사용한다. 필수 QA와 실패·불일치·안전 우려 재검증은 유지한다. 원문의 반복 복사·근거 없는 재실행은 요구하지 않는다. 미실시를 PASS로 쓰지 않는다.

<!-- PAGE BREAK -->

## 5. 분류·테스트·역할 규칙

Audit1은 최고 위험 Tier로 분류, Codex 하향·분할 은폐 금지. Tier 1 WO에 **ADR exact 파일명·구현 권한 절·인수 조건별 대응·공개 계약/schema/자연키/authority 불변**을 적는다. '취지상' 해석 불가. 새 의미·공식·Source·저장/승인/실행 권한·공개 계약은 Tier 2 이상. 의미 불변 변수명·내부 함수·테스트 배치는 자유다. Approval Queue: 기승인 read-only 조회/표시는 Tier 1 가능, 새 제안/기록·표시 계약 Tier 2, 승인/실행/운영 저장 Tier 3.

테스트는 공개 계약·사업 규칙/계산·입력 실패·provenance/checksum/중복·충돌·무승인 실행 차단·결함 회귀 중 보호 속성을 설명한다. private identity/type·내부 필드/호출 순서·오류 우선순위는 기본 조건이 아니다. 요구 시 **실패 사례·계약/사업 불변조건·실제 영향** 필수, 없으면 MINOR/NOTE BACKLOG. 안전 타입·직렬화·fail-closed·기존 normative 계약은 유지. 기존 테스트 삭제/약화는 이번 개정·첫 슬라이스에서 금지. 보호 속성/대체 테스트를 먼저 정한 **별도 한정 Tier 2**이며 선행조건이 아니다. 개수/줄 수·구현 복제는 품질 지표가 아니다.

WO 밖 실제 계약 위반·손상·유출·무승인 부작용·중대 재현 결함도 위치/조건/영향/근거가 있으면 **BLOCKER/MAJOR 가능**. 선호·스타일·추가 기능은 MINOR/NOTE이며 Finding·영향 델타와 독립 동일 SHA 검토를 허용한다. 첫 5건 의무 Audit2나 이후 sample의 BLOCKER/MAJOR는 batch 전체 main merge·신규 Tier 1 publication 중단 → batch 동결·원인 분석·임시 전체 Tier 2 복귀(Tier 3 유지) → Human 재개를 적용한다.

Audit1: 분류·최초/교정 WO·1차 감사. Audit2: 별도 컨텍스트 검토. Codex: 승인 구현. Human: 발효·고위험·push 승인. **Publication Executor: Builder와 분리된 제한 실행**. 대표의 직접 Git 수행은 필수가 아니다. main 변경은 Tier 3 별도 승인. 생성기·Coordinator·Runner 개발 제외. 보고: 요약·SHA·증거·Finding·필요 결정·NEXT OWNER/ROLE/ACTION.

## 6. 첫 실제 CSV 준비·측정

TS-WAIST-BRACE-L 허리보호대: **실제 CSV → 승인 내부 SKU mapping → 기존 계산 → 근거 있는 read-only 판단안 → 승인 기록/출력**. fixture는 단위/회귀용. 실제 완료 대체·운영 폐루프 완성 표기 금지.

mapping 준비 항목: channel, channel_product_id, channel_option_id, internal_sku, option_description, mapping_status, source_reference, verified_at, verified_by 또는 Human 승인 근거. 이는 검토 항목이며 새 schema 승인이 아니다. 상품명 조인·추정 매핑·외부 ID 대체 금지. 미매핑/중복·충돌 옵션을 격리하고 해당 행 계산/판단안을 만들지 않는다. 실매핑표는 repo 밖, 공개 테스트는 합성 fixture만 쓴다.

**완료 증거 0 / mapping NOT READY**. 전체 옵션표·실제 CSV 미제공: 미매핑/충돌 총수·기간/시각·단위·취소/반품 의미·단일 SKU/채널 30일 완전성 미검증. 누락일 0/미확인 값 보충 금지. Audit1은 WO 전 옵션별 완료/미매핑/충돌, CSV 기간/시점, **A** 기존 parser·mapping/duplicate/conflict·계산, **B** 연결/대사, **C** 실제 Source·mapping 활성화·기록/출력 승인 공백을 반환한다. synthetic 성공은 실제 Source 승인이 아니다.

첫 Tier 미확정. C 부재가 증명된 B만 Tier 1, 새 계약 한정 Tier 2, 운영 저장/승인/실행 Tier 3. 큐·DB·화면·lead-time·Reorder Point/ROQ 추가 금지. 개발 보고서는 AI_RUN_LOG 대체 불가. 단계별 입력/수용/격리/중복/충돌 건수·사유, 주문/수량 합계, source/checksum/data_as_of·mapping·공식/출력 refs를 대사한다. 일별 집계 전후 행 수는 구분한다.

시범 전 최대 3건 승인→audit branch publication 대조. Policy Producer 3c4236e / Safety Stock bb738e5 / Projection 833140e는 제공 기록에 시작 승인시각 연결이 없어 **각 NOT MEASURABLE**. commit으로 승인/실작업시간 추정 금지. 첫 V2부터 WO 승인·구현/Audit1 완료·push 승인·publication/CI 완료시각, 릴레이/교정 횟수 기록. **50% 단축은 목표, 5영업일은 자료/매핑 확보 후 초기 목표**. CI·사업 KPI 분리.

## 7. 단일 문서·감사 한도·상태

기존 4개는 발효 시 아래처럼 대체하며 현재 원본은 보존한다.

| 원본 PROPOSAL | 대체 규칙 |
| --- | --- |
| 00_운영가이드.md / 01_TIERED_REVIEW_AMENDMENT_PROPOSAL.md | 본 문서 1~7절 |
| 02_TEMPLATES.md / 03_ROLE_PROMPTS.md | 4~6절 evidence·결과 항목/역할 |

Audit2 최초 검토 완료 → **이번 Audit1 교정 1회 → Audit2 델타 1회**. 핵심 충돌이 남으면 확장 없이 STOP/대표 선택지. MINOR/NOTE는 BACKLOG. SELF-CHECK는 독립 PASS가 아니며 Finding 최종 closure는 Audit2 소유다. 다음 구현 WO의 한정 교정도 2회 미해결이면 Human에 escalate하며 안전 결함을 면제하지 않는다.

근거: remote audit 7c75b955140ca54ad3ff055493b43c57080a0a49, main f51dde902e1d460f9e55ff41841aa80970ea723f; **2026-10-19 20:07 KST PRIVATE** 재확인. Windows worktree/로컬 scanner 미검증. 과거 PUBLIC은 이전 관측이다. PHASE 4 COMPLETE / 5 NOT COMPLETE / 6 NOT STARTED. **NEXT OWNER=Audit2 / ACTION=M-02 closure.**
