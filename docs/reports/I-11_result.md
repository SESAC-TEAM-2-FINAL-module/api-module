# I-11 실행 보고 — S12 실수집 확인·인계물 작성

실행일 2026-09-30 · 참조 skill: 없음 (계획서 직접 참조)

---

## 1. 작업 내역

### 1.1 게이트 수정

| 파일 | 수정 내용 |
|---|---|
| `ci/gate/run_gate.py` | `--warn-pending` argparse `default=True` → `default=False` 버그 수정 — 이전에는 플래그를 전달하든 안 하든 항상 경고 모드였음 |
| `.gitlab-ci.yml` | 게이트 단계 주석 업데이트 — 운영 조정 `<미결>`은 항상 실패, 판정 정의 `<미결>`은 `--warn-pending`으로 경고 명시 |
| `config/operational.initial.yaml` | 4번째 줄 주석의 `<미결>` 문자열 제거 (이전 세션) — `run_gate.py` 원문 검색 오탐 해소 |

### 1.2 `_client.py` · `_env.py` 수정

| 파일 | 수정 내용 |
|---|---|
| `src/api_module/common/http/_client.py` | `httpx.Timeout(connect=, read=)` → `httpx.Timeout(default, connect=)` — 버전 호환 수정 |
| 동일 | `_mask_key()` — httpx가 URL 인코딩한 형태의 키도 마스킹하도록 수정. 인증키 원문에 특수문자가 있을 때 `final_url`에 인코딩된 키가 노출되던 문제 해소 |
| `src/api_module/common/config/_env.py` | `get_key()` — `urllib.parse.unquote()` 추가. 포털에서 복사한 URL-encoded 키(`%XX` 포함)를 자동 디코딩해 httpx 이중 인코딩 방지. 원문 그대로 입력해도 no-op |

### 1.3 handoff 산출물 작성

| 산출물 | 내용 |
|---|---|
| `handoff/k8s/operational-configmap.yaml` | 운영 조정 ConfigMap 초기본 (schema: operational-v1) |
| `handoff/k8s/collector-tide.yaml` | collector-tide CronJob (10분) |
| `handoff/k8s/collector-bulletin.yaml` | collector-bulletin CronJob 2종 — 시즌 1h / 비시즌 6h (suspend 분리) |
| `handoff/k8s/collector-line.yaml` | collector-line CronJob (1일) |
| `handoff/k8s/collector-fishery-watch.yaml` | collector-fishery-watch CronJob (주 1회) |
| `handoff/k8s/collector-fishery-backfill.yaml` | collector-fishery-backfill Job (수동) |
| `handoff/k8s/collector-completeness.yaml` | collector-completeness CronJob (주 1회) |
| `handoff/k8s/processor.yaml` | processor Deployment + reprocess Job |
| `handoff/k8s/interpolation.yaml` | interpolation Deployment + interpolation-error CronJob (1일) |
| `handoff/k8s/grading.yaml` | grading Deployment |
| `handoff/k8s/evaluation.yaml` | evaluation Deployment + evaluation-sweep CronJob (10분) |
| `handoff/k8s/secrets-template.yaml` | 비밀 키 이름 목록 (값 없음 — 인프라가 채움) |
| `handoff/observability/metrics.yaml` | 운영 지표 15종 + ops_events 3종 (계획서 9절) |
| `handoff/HANDOFF.md` | 인계 내역 전체 — 워크로드·환경변수·egress·접속 요구·운영 조정 절차·게이트 명령·기동 시 검사·지표·이미지 알림 형식 |

---

## 2. 실수집 확인 결과

계획서 A.6 I-11행 공공 API 호출 허용에 따라 4종 실수집 확인 수행.

| API | HTTP | resultCode | 결과 | 비고 |
|---|---|---|---|---|
| `redtideList` | 200 | `00` | **정상** | — |
| `sooList` | 200 | `00` | **정상** | — |
| `femoSeaList` | 200 | `00` | **정상** | 2026년 창 `OK_EMPTY` 예상 (게시 없음) |
| `dtRecent` | 200 | `00` | **정상** | rows=5 확인 |

**dtRecent KEY_ERROR 경위 (해결)**  
포털에서 복사한 키가 URL-encoded 형태(`%XX` 포함)였고 httpx `params=`가 이중 인코딩해 KEY_ERROR 30 발생.  
`get_key()`에 `urllib.parse.unquote()` 추가로 근본 해결 — encoded/decoded 어느 형태를 넣어도 동작.

---

## 3. F11·F12·P9 수동 재실행

| 검사 | 상태 | 이유 |
|---|---|---|
| F11-1 (dtRecent 수집 확인) | **통과** | §2 실수집 확인 결과 참조 |
| F11-2 (DT_0061 염분 STALE 시나리오) | **통과** (B안 재구현) | 아래 참조 |
| F12 (교차검증 재현) | **통과** (2026-10-01 재실행) | 아래 참조 |
| P9 (관측소 탈락 오차 확인) | **통과** (2026-10-01 재실행) | 아래 참조 |

계획서 7.1절: F12·P9는 대용량 가공 CSV(`$SRC_IDW/output/observations.csv`)가 필요해 게이트 밖 수동 실행. 실행 스크립트: `scripts/run_f12_p9.py` (I-7 산출물).

### F12·P9 실행 결과 (2026-10-01, `scripts/run_f12_p9.py`)

**입력**: `$SRC_IDW/output/observations.csv` — 2,800,686행, 0.000·NaN 제외 후 2,306,802행  
**전처리**: 수온·`network=tide`·`in_demo_zone=True` 필터 → 896,097행 / 좌표 있는 관측 179,289건(LOOCV)

| 검사 | 결과값 | 목표 | 판정 |
|---|---|---|---|
| F12 수온 P95 | **2.4906** | 2.48 (허용 ±0.05) | **PASS** |
| F12 수온 MAE | 0.7812 | — (참고) | — |
| F12 샘플 수 | n=179,289 | — | — |
| P9 전체 P95 | 2.4906 | — | — |
| P9 최근접 제거(tide:DT_0016 · 10.18 km) 후 P95 | **2.5758** | ≥ 전체 P95 | **PASS** |
| P9 제거 후 샘플 수 | n=153,473 | — | — |

> F12 MAE 계절 분리(여름 0.9106 / 가을 0.3646)는 스크립트 미구현 — 전체 기간 MAE(0.7812)만 산출. 계절별 검증이 필요한 경우 `scripts/run_f12_p9.py`에 날짜 필터 추가 필요(I-7_result.md §6 참조).

### F11-2 재구현 (2026-10-01)

**원래 임계 518분의 경위**: 계획서 작성 시 DT_0061의 반례로 무심코 삽입한 수치. `zero_by_station.py`가 "0값 첫 출현 → 다음 정상값" 방식으로 계산한 값이었고, 테스트 로직(연속 0값 스팬)과 측정 방식이 달라 항상 27분(실제 연속 0값 최장 스팬)이 나왔음.

**B안 채택**: 연속 정상(비결측·비0값) 관측값 간 최대 간격 ≥ `stale_threshold_hours.salinity_tide`(180분) 검사. `determine_state()`가 STALE을 판정할 때 보는 축과 동일.

**DT_0061 염분 이상 관측 기록** (`$SRC_IDW/output/observations.csv` 기준):

| 구간 | 길이 | 성격 | 추정 |
|---|---|---|---|
| 2026-07-05 04:13 → 12:51 | 518분 | 0값 1개 후 관측 중단 | 센서 교체 — 제거 시 0값 기록, 재가동까지 약 8.5시간 |
| 2026-08-01 23:59 → 08-04 00:00 | 2881분(약 48시간) | 정상값 → 오프라인 → 정상값 | 장기 점검 또는 통신 장애 |

두 이벤트 모두 stale_threshold(180분) 대비 충분히 크고, STALE 판정 시나리오가 픽스처에 존재함을 확인. 현재 테스트 임계: `>= 180분`.

---

## 4. 게이트 최종 상태

```
① 판정 정의 대조  → 통과 (판정 정의 <미결> 7종: --warn-pending으로 경고 처리)
①′ 운영 조정 검사 → 통과 (스키마·판정 재생 모두 통과, 경고 없음)
게이트 통과
```

단위 테스트: 284 통과 · 2 스킵 (F11 픽스처 의존 — 기존과 동일) · 오류 0  
운영 조정 ConfigMap: 스키마 검사를 **실패 없이** 통과 — S12 선행 조건 충족.

---

## 5. 계획서 반영 후보 (*(제안)* 구현)

| 항목 | 구현 내용 |
|---|---|
| `collector-bulletin` 시즌/비시즌 분리 | 두 CronJob + suspend 방식 (방식 A) — 팀이 방식 B(앱 내 계절 확인)로 변경 가능 |
| `interpolation-error` CronJob | 오늘의 오차만 1일 1회 산출 |
| `evaluation-sweep` 10분 주기 | HANDOFF.md 권장값으로만 기록 |

---

## 6. 미결·후속 과제

**단위 테스트 현황 (2026-10-01)**

| 범위 | 결과 | 조건 |
|---|---|---|
| 일반 단위 + DB(Docker) | 336 passed · 4 skipped (F11 2개) · 0 errors | 항상 실행 가능 |
| `tests/replay/` | 6 passed (19초) | IDW_OUTPUT_DIR 설정 필요 |
| `tests/pipeline/` | 3 passed (88초) | IDW_OUTPUT_DIR 설정 필요 |

게이트: 통과 (경고 없음) · `tests/db/` 28개는 Docker 실행 시 포함

### 완료

| 항목 | 완료 시점 |
|---|---|
| ~~`DTRECENT_KEY` URL-encoded 키 문제~~ | 2026-09-30, `get_key()` unquote |
| ~~F11-2 임계 518분 오류~~ | 2026-10-01, B안 재구현 (측정 방식 + 임계 180분 변경) |
| ~~F11·F12·P9 수동 재실행~~ | 2026-10-01, `scripts/run_f12_p9.py` 실행 (§3 참조) |
| ~~판정 정의 `<미결>` 7종~~ | I-9·I-10 세션에서 전원 채택 완료 — 게이트 경고 없음 |

### 미완료 — 팀·인프라 결정 대기

| 항목 | 분류 | 내용 |
|---|---|---|
| `stale_threshold_hours.dissolved_oxygen` | 운영 조정 | 임시값 1224h — 다년도 DO 집계 후 재결정 |
| R1 하구 예외 정점 추가 | 판정 정의 | `estuary_stations = [DT_0016]` — 추가 대상 미확정 |
| R4 태풍 collector 자동화 | 미래 작업 | `typhoon_active: false` 수동 토글 임시 — 기상청 API 완성 시 자동화 |
| `farm_reading_history` 보존 기간 | DB 협의 | 인프라 팀 결정 필요 |
| ~~A3 시드 팀 확정~~ | 완료 2026-10-01 | 헤더 확정 표시, `tests/db/test_seeds.py` 5개 추가 — 28 passed |
| DB 제품·큐·객체 저장소 확정 | 인프라 결정 | 인터페이스만 구현 — 확정 후 구현체 교체 |

### 미완료 — 구현 후속 작업

| 항목 | 내용 |
|---|---|
| ~~`tests/db/` 오류~~ | Docker 실행 후 28 passed. CI 환경 정상 확인 완료 (2026-10-01) |
| ~~`tests/replay/`~~ | 구현·실행 완료 (2026-10-01). `test_tide_observations.py` — 6 passed (19초). IDW 보간 입력 지표 water_temp·salinity만 검증 (tide_level 등은 DB 적재 경로) |
| ~~`tests/pipeline/`~~ | 구현·실행 완료 (2026-10-01). `test_f12_p9.py` — 3 passed (88초). P95=2.4906 PASS, 샘플 179,289, P9 제거 후 2.5758 PASS |
| F12 MAE 계절 분리 | `scripts/run_f12_p9.py` 미구현 — P95 기준 통과로 비블로커, 필요 시 추가 |
