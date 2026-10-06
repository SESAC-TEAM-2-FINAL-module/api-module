# I-17 — 시험 실행기 `flowtest`: 실제 API → 결과 테이블, 한 프로세스 · 이미지 · 사용 안내 (개정 21 구현)

작성 2026-10-06 · 근거 계획서 개정 21(독립 검수 2차 반영, PASS 조건 충족)

---

## 0. 머리말

| 항목 | 내용 |
| --- | --- |
| 번호 | **I-17** |
| 대상 단계 | S14 (10절) |
| 선행 | I-1~I-16 (작업 트리 기준) |
| 적용 수정사항 | 없음 |
| 공공 API 호출 | **허용 — 7.10 FT7에서만.** 실제 수집 모드·**한 번 실행만**(반복 실행으로 실제 호출하지 않는다). 예산(원천별 호출 수 상한, 재시도 포함 전체 합): `dtRecent` **40** · `redtideList` **5** · `sooList` **10** · `femoSeaList` **15**. FT7 실행은 **최대 2회**(첫 실행이 실행기 결함으로 끊긴 경우 1회 더). 예산을 넘겨야 끝나는 상황이면 그 자리에서 멈추고 보고한다. FT1~FT6·다른 모든 작업은 호출 금지 |
| 읽을 skill | `common-core`(③-12 진입점, 원문 저장·큐·설정 로딩·기동 시 검사·`seed-check`) — **먼저 읽는다.** 작업 2의 추출이 필요한 단계만 `grading`·`interpolation`·`evaluation`(대상은 `main()` 본문의 기동 시 검사·구독뿐) |
| 계획서 근거 | **2.1.1(이 지시서의 기준)**, **7.10(FT1~FT7)**, 2.0.2(Dockerfile·이미지 이름), 2.0.3(테이블·시드를 만들지 않음), 2.0.4(`handoff/flowtest/` 예외), 2.0.6(운영 조정·워크로드 설정), 2.1(워크로드), 2.2(구독 관계), 2.3(원문·키 마스킹), 6.1(가져오기 예외·경로→이미지), 7.9(가짜 HTTP 방식), 8(예산), 12 |
| 커밋 | **하지 않는다** — `git add`·`commit`·`push` 금지. 계획서 개정 21은 커밋되지 않았으므로 확인 게이트는 **작업 트리의 계획서 문구**로 한다 |

### 0.1 배경 (짧게)

대시보드 팀이 데이터 흐름 시험용 공유 DB(모듈 스키마로 구성, 운영 아님)에서 **실제 데이터가 적재되는 것을 보고 값을 써 보려** 한다. 그쪽에는 이 모듈의 픽스처가 없고, 단계 이미지 5종은 큐·원문 저장소·컨슈머 수신 대기(점검 C17)가 없어 이어지지 않는다. 그래서 collector(실제 API) → evaluation을 한 프로세스·인메모리 큐로 잇는 시험 전용 실행기와 그 이미지를 만든다. 목표는 **"적재가 관측되고 값을 쓸 수 있는 것"**이고, 오류 처리 보강은 범위 밖이다. 큐(NATS JetStream)·원문 저장소(PostgreSQL)·C2·C4는 다음 지시서(개정 22)다.

### 0.2 지키는 것

- **단계 코드의 동작을 바꾸지 않는다.** 허용은 2.1.1절의 **행위 보존 추출**뿐이다 — 각 단계 `main()` 본문(또는 `if __name__` 블록)에 있는 기동 시 검사·구독 조합을 함수로 꺼내고 `main()`이 그 함수를 부르게 한다. 꺼낸 뒤에도 `main()`의 동작·인자·종료 코드가 같아야 한다. 그 밖에 단계 코드를 고쳐야만 되는 곳은 **멈추고 보고**한다
- 단계 코드가 `flowtest`를 가져다 쓰지 않는다. `flowtest`는 단계를 가져다 쓴다(6.1절 예외)
- **C2(조위 다중 페이지 원문 재구성)는 고치지 않는다** — 기존 코드의 알려진 결함이고, 실행기가 그 코드를 부르는 것은 12절 새 위반이 아니다(2.1.1절). 사용 안내에 알려진 한계로 적는다
- 테이블·시드·`farm_sites`를 만들지 않는다(테스트 컨테이너 안에서 모델로 만드는 것은 기존 테스트 방식 그대로 허용). 운영 DB·공유 시험 DB에 접속하지 않는다 — FT7도 테스트 컨테이너로 한다
- **인증키·요청주소 값·DB 연결 문자열을 출력하지 않는다** — 명령·로그·보고서에 나오면 안 된다. 실행기 로그에도 쓰지 않는다. 원문 키 검사는 `python ci/scan_keys.py`로만, 결과는 건수만
- 이미지에 **운영 조정 값·인증키·DB 연결 문자열을 넣지 않는다.** 반복 주기를 코드·이미지에 박지 않는다(워크로드 설정 — 실행 인자·환경변수로 받고, 반복 모드인데 없으면 기동을 멈춘다)
- 매니페스트(`handoff/k8s/`)·`HANDOFF.md`·대시보드 인계 묶음(`handoff/dashboard-deliver/`)·계약(`contracts/`)·판정 정의(`config/definitions.yaml`)·`ci/gate/expected.yaml`은 고치지 않는다. `.gitlab-ci.yml`에 `flowtest` 이미지 빌드를 넣지 않는다(FT1~FT6을 테스트 단계에서 도는 것은 기존 `tests/` 수집으로 충분하면 손대지 않는다)
- 설명 문장(코드 주석·사용 안내)의 근거는 **계획서 2.1.1절 문장을 옮긴다** — 다르게 풀어 쓰지 않는다. 사용 안내에 **레지스트리 주소를 쓰지 않는다**
- 파일 줄바꿈: 이 저장소는 `core.autocrlf=true`다. 바이트를 비교하는 검사는 LF로 맞춰 비교한다

---

## 1. 작업

경로는 `src/api_module/` 기준.

1. **현황 파악(코드 변경 없음)** — 각 단계가 실제 구조에서 무엇을 부르는지 표로 정리한다: collector `main(workload, queue)`, processor `startup()`·`handle_raw_fetched`·`seed-check` 블록, interpolation `main()`의 기동 검사·`handle_obs_loaded`·`run_interpolation_error`, grading `main()`의 기동 검사(빈 시드·지수 판정 정의 전제)·`handle_obs_loaded`·`handle_interp_done`, evaluation `main()`의 저장소·설정 로딩·`handle_grade_done`·`handle_sweep`. 이 표가 FT1 ②의 기대 집합이 된다. 보고서 0절에 싣는다
2. **행위 보존 추출(필요한 단계만)** — 1의 표에서 함수가 아니라 본문에만 있는 기동 시 검사·구독 조합을 함수로 꺼낸다(예: `grading`의 `startup_checks(repo, defs)`, `processor`의 `seed_check(repo)` — 이름은 단계 관례대로). `main()`은 그 함수를 부른다. **바꾼 줄을 보고서에 전후로 싣는다.** 추출 커밋은 해당 단계 이미지의 선택 빌드·이미지 알림을 일으킨다(정상)
3. **실행기 — `flowtest/`** (`flowtest/main.py` 등)
   - **구독**: 인메모리 큐 하나에 2.2절 구독 관계 그대로 — `raw.fetched` → processor, `obs.loaded` → interpolation(조위만 — 거르는 것은 단계 핸들러가 하던 대로)·grading, `interp.done` → grading, `grade.done` → evaluation. 각 핸들러는 **예외 포착 래퍼**로 감싼다(래퍼는 실행기 코드). 실패는 단계·주제·예외 종류로 기록하고 다음 메시지·남은 수집을 계속한다
   - **실행 전 점검**(2.1.1절 표 순서): 읽기 전용 검사 — 단계별 기동 시 검사(테이블·컬럼, 운영 조정 스키마, 계약 버전, 빈 시드, 판정 정의 전제), `seed-check`, `farm_sites` 표·열(입력 계약 `contracts/inputs/`)·활성 1건 이상, 실제 수집 모드면 수집 원천 키·요청주소 변수 **존재만**(이름만 보고). **모두 통과한 뒤에만** 쓰기가 있는 기동 절차(`processor.startup()` 등)를 부른다. 하나라도 실패하면 아무것도 쓰지 않고 0이 아닌 코드로 끝난다 — 무엇이 실패했는지 이름으로 남긴다
   - **모드**: `collect`(기본 — 워크로드 `tide`·`bulletin`·`line`·`fishery-watch`를 collector 진입점으로) / `replay`(원문 저장소의 정기 경로 원문을 키 접두(api·날짜)로 골라 키의 `epoch_ms` 순으로 `raw.fetched` 발행 — HTTP 호출 없음, 새 DB 전제). 백필·분할 합산·`completeness-check`·`reprocess`는 넣지 않는다. 어장환경 감시의 진입점 위치는 `common-core` ③-12대로(`collector.fishery_watch`)
   - **실행 방식**: `once`(기본 — 수집 4종 한 번씩 → `interpolation-error` 한 번 → `evaluation-sweep` 한 번 → 종료 요약 → 종료) / `loop`(수집 4종·`interpolation-error`·`evaluation-sweep` 주기를 인자·환경변수로 받는다. 적조는 시즌(5~10월, KST)·시즌 밖 주기를 따로 받는다. 하나라도 없으면 기동을 멈춘다. 종료 신호를 받으면 진행 중 메시지를 끝내고 요약을 낸다)
   - **원문 저장소**: 기존 로컬 디스크 구현(`RAW_STORE_PATH`). 키 마스킹은 collector 그대로
   - **종료 요약**: 워크로드별 호출 수·응답 상태, 주제별 알림 수, 단계별 처리 실패 수, 결과 테이블(`farm_readings`·`axis_status`·`farm_areas`·`farm_reading_history`·`risk_index_factors`·`risk_index_levels`)과 관측 테이블·`raw_index`·`ingest_runs`의 행 수. 표준 출력에 사람이 읽는 형태 + 기계가 읽는 JSON 한 줄. 비밀 값 없음
   - 설정·비밀은 기존 환경변수 이름 그대로(`.env.example`) — 새 이름이 필요하면 반복 주기·모드 인자뿐이고, 이름을 보고서에 적는다
4. **이미지 — `docker/flowtest/Dockerfile`**: 기존 Dockerfile 형식대로. 단계 코드 5종·`common/`·`flowtest/`·`config/definitions.yaml`·`seeds/`·`contracts/config/operational.schema.json`(processor·evaluation과 같은 것)을 복사. 의존성은 단계 의존성의 합 + DB 드라이버(PostgreSQL). `ENTRYPOINT ["python", "-m", "flowtest.main"]`. 운영 조정 값·키·연결 문자열·`fixtures/`는 넣지 않는다. `pyproject.toml`에 `flowtest` 선택 의존성(단계 의존성의 합)을 추가
5. **사용 안내 — `handoff/flowtest/README.md`** (받는 사람: 대시보드·인프라. 이 저장소 내부 쟁점 번호·문서 경로·절 번호를 쓰지 않고 그 자체로 읽히게)
   - 무엇을 하는가, 무엇을 하지 않는가(운영용 아님, 큐·원문 저장소가 실제 구조와 다름)
   - 실행 전 DB 준비: 모듈 DDL 적용 → 해역 시드 적용 → 시드 점검 통과 → 입력 계약대로 `farm_sites` 만들고 좌표 등록(파일 이름은 이 묶음이나 대시보드 인계 묶음 안의 것으로 안내)
   - 실행 예: `docker run` 한 번 실행 / 반복 실행 / 재생, 필요한 환경변수 **이름**(키·요청주소·`DATABASE_URL`·`OPERATIONAL_CONFIG_PATH`·`RAW_STORE_PATH`·주기), 운영 조정 파일 마운트, 원문 보존용 볼륨. 이미지 주소는 자리표시(`<이미지 주소>`)
   - 반복 실행 권장 주기(조위 10분, 적조 시즌 1시간·시즌 밖 6시간, 정선 1일, 어장환경 감시 주 1회, 침묵 점검 10분, 오늘의 오차 1일)와 하루 호출량(약 1,300건, 대부분 조위), 같은 키로 다른 수집이 돌면 합산된다는 점
   - 종료 요약 읽는 법, 실행 전 점검에서 멈췄을 때 보는 곳
   - 알려진 한계: 조위 다중 페이지(뒤 페이지 실패 시 상태가 정상으로 남을 수 있음), 재전달·동시 실행·확장 미확인, 오류 처리 보강은 다음 단계
6. **테스트 — 아래 2절**
7. **이미지 빌드 확인** — `docker build -f docker/flowtest/Dockerfile -t api-module/flowtest:local .` 성공, 컨테이너에서 `python -c "import flowtest.main, collector.main, processor.main, interpolation.main, grading.main, evaluation.main"` 성공, 인자 없이(또는 도움말로) 실행해 실행 전 점검이 DB 연결 없음으로 멈추는지 확인. 이미지 안에 `operational*.yaml`·`.env`가 없는지 확인. **푸시하지 않는다**

## 2. 통과 기준

FT1~FT6은 HTTP 호출층만 픽스처 원문을 돌려주는 가짜로 바꾸고(7.9절·기존 `tests/db/` 방식), 고른 DB(PostgreSQL)의 테스트 컨테이너에 모델로 만든 스키마·시드, **입력 계약 형식의 합성 `farm_sites`**(`tests/db/test_pipeline_chain.py` 방식)를 쓴다.

| # | 기대 |
| --- | --- |
| FT1 | ① 실행기가 구독·호출하는 함수(래퍼 **안쪽**)가 각 단계 `main`이 부르는 것과 같은 객체 ② 각 단계 `main`을 기동 시 검사·구독 함수에 스파이를 달아 돌렸을 때의 **기동 시 검사 호출 집합 = 실행기의 것** ③ 단계 코드(`collector/`·`processor/`·`interpolation/`·`grading/`·`evaluation/`)에 `flowtest` 가져오기 0건 |
| FT2 | `collect`·`once`로 `farm_readings`·`axis_status`·`farm_areas`에 합성 양식장 행, 관측 테이블·`raw_index`·`ingest_runs` 채워짐. 수온 `COMPUTED`·`alertable = false`(N11). 종료 요약 행 수 = DB 행 수 |
| FT3 | 테이블 하나 없음 / 시드 빔 / 운영 조정 파일 없음 / `farm_sites` 없음 / `farm_sites` 활성 0건 / (`collect`) 키 변수 하나 없음 — 경우마다 **어느 테이블에도 행 없음(`ops_events` 포함)**, HTTP 호출 0건, 0이 아닌 종료 코드 |
| FT4 | FT2가 남긴 원문으로 `replay`를 새 DB에 → HTTP 0건. 단계 시각 함수를 FT2와 같은 값으로 고정했을 때 관측 테이블·`raw_index` 행과 결과 테이블 값(`value`·`provenance`·`state`)이 FT2와 같다(산출 시각 필드 제외) |
| FT5 | 한 단계 핸들러가 예외를 내게 하면 그 단계 실패 수가 요약에 남고 다른 원천 적재는 끝까지 간다 |
| FT6 | 더미 키·더미 연결 문자열(비밀번호 자리에 표식 문자열)로 돌린 로그·종료 요약·원문에 표식 0건 — 실제 키를 읽지 않는다 |
| FT7 | **(머리말 허용 — 실제 호출)** 테스트 컨테이너에 `collect`·`once` 1회 → 결과 테이블에 행이 생긴다. 원천별 호출 수가 예산 안(요약 값으로 보고). 원문을 보관하고, 새 컨테이너 DB에 `replay` → HTTP 0건이고 관측 테이블·`raw_index` 행이 같다. 보관 원문의 `url`·`params`·`final_url` 키 자리가 `***`로 마스킹됐는지 확인(키 값을 출력하지 않는다 — 마스킹 여부와 건수만). 보관 원문은 `fixtures/`로 옮기지 않는다 |
| 추출 | 2번에서 바꾼 단계마다 `main()`의 인자·종료 코드·기동 시 검사 순서가 같고, 기존 7.4·7.9(E1~E7)·K9·SD1~SD4 검사가 그대로 통과 |
| 이미지 | 1절 7번 전부 |
| 판별력 | FT2·FT4에서 연결 하나(예: grading 구독)를 끊은 상태, FT3에서 점검 하나를 끈 상태로 각각 한 번 실패를 확인하고 보고서에 적는다 |
| 회귀 | 전체 `pytest`(DB 포함) 회귀 없음, `PYTHONIOENCODING=utf-8 python ci/gate/run_gate.py --warn-pending` 통과, `python ci/scan_keys.py` 0건 |

기준선(2026-10-06, 작업 시작 전): 전체 `pytest` **624 passed · 14 skipped**(`IDW_OUTPUT_DIR` 미설정 시). Docker Desktop이 꺼져 있으면 DB 테스트가 `DockerException`으로 실패한다 — `C:\Users\USER\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` 실행 후 `docker info`.

## 3. 순서 · 중단 조건

- 순서: 1 → 2 → 3 → 6(FT1~FT6) → 4 → 7 → 5 → **FT7은 맨 마지막**(FT1~FT6·회귀·이미지 확인이 끝난 뒤)
- **확인 게이트**: 시작 전에 계획서 작업 트리에 2.1.1절과 7.10절(FT1~FT7)이 있는지 확인한다. 없으면 멈춘다
- 단계 코드를 행위 보존 추출 밖으로 바꿔야만 되는 곳, 2.1.1절이 정하지 않은 동작이 필요한 곳, 계획서·skill·코드가 다르게 읽히는 곳 → **멈추고 보고**(고르지 않는다)
- 기존 테스트가 깨지는데 그 테스트를 약하게 해야만 통과한다면 멈추고 보고한다
- FT7에서 예산을 넘길 상황, `KEY_ERROR`·`QUOTA`가 나오는 상황 → 그 자리에서 멈추고 보고(다른 키·창으로 바꿔 다시 부르지 않는다). 실제 호출에서 드러난 **단계 코드 결함은 고치지 않는다** — 보고서 2절 "우리 코드·명세 결함"에 적는다. 실행기 자체 결함만 고치고 FT7을 한 번 더(최대 2회) 돈다

## 4. 산출물

- `flowtest/`(실행기), 단계 `main.py`의 행위 보존 추출분(있으면)
- `docker/flowtest/Dockerfile`, `pyproject.toml`(`flowtest` 선택 의존성)
- `handoff/flowtest/README.md`
- `tests/`(FT1~FT6·추출·판별력 — FT7은 수동 실행 기록)
- FT7 보관 원문: `RAW_STORE_PATH`로 정한 저장소 밖 임시 경로(저장소 안에 두지 않는다), 보고서에 경로 별칭과 원천별 파일 수만
- `docs/reports/I-17_result.md` — 계획서 A.5 양식: 실행 시각 / **호출 수(원천별, 예산 대비)** / 참조한 skill과 상태("작업 트리, 개정 21 반영본") · 0 실행 전 확인(1번 현황 표 포함) · 1 판정표(위 2절 각 행: 통과/실패/검사 무효/실행 안 함) · 2 예상과 달랐던 결과(API 특성 / 우리 코드·명세 결함) · 3 새로 발견한 함정 · 4 계획서 반영 후보(새 환경변수·인자 이름, 만난 `<미결>`). 변경 파일 목록, 제안 커밋 메시지
