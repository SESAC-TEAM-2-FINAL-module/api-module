# I-14 결과 — 적조 정기 창 30일 · 분할 합산 제외 · 직전 원문 대조 (개정 18 구현)

실행 2026-10-02 · 지시서 `docs/instructions/I-14_적조창30일_직전원문대조.md` · 참조 skill `common-core`(③-4 적조 직전 원문 대조, ③-5)·`bulletin`(③-2) — 작업 트리의 개정 18 반영본(미커밋, 기준 커밋 `6e1e698`)

## 0. 실행 전 확인

- 계획서 개정 18: 독립 검수 1차 FAIL(8건) → 사용자 승인으로 반영 → 2차 PASS, 권고 5건 문장 보강
- 공공 API 호출: 없음(지시서 머리말 금지). Docker(PostgreSQL 16 테스트 컨테이너) 사용

## 1. 판정표

| 검사 | 결과 |
| --- | --- |
| N15 ① 창 안 속보 하나 빠짐 → 1건, 다음 원문 0건, `ingest_runs.status` `OK` | 통과 |
| N15 ② 이번 `OK_EMPTY`, 직전 창 안 3건 → 1건(3개) | 통과 |
| N15 ③ `day_report` = `sdate` 경계 포함 | 통과 |
| N15 ④ 같은 `day_report` 번호 교체 → `same_day_replaced = true` | 통과 |
| N16 ① 창 밖으로 밀림 | 통과 |
| N16 ② 순서 뒤바뀜 — 처리 순서 두 가지 모두 N−1에서 1건만 | 통과 |
| N16 ③ 늦게 온 옛 원문 | 통과 |
| N16 ④ 중복 알림·파서 버전 재처리 | 통과 |
| N16 ⑤ 바로 앞 원문 `NET_ERROR`·`PARSE_FAILURE` → 그 앞 정상 원문을 직전으로 | 통과 |
| N16 ⑥ 처음 실행 → `NO_PREV` 지표 | 통과 |
| N16 ⑦ 이번 원문 `PARSE_FAILURE`·`FILTER_IGNORED` → 대조 안 함 | 통과 |
| 직전 원문 후보 — 정기 원문 아님(tag)·창 길이 다름(14일 원문) 제외, 손상 원문 `PREV_UNREADABLE`(적재는 성공), 창 변수 없음 `NO_WINDOW` | 통과 |
| E7 — `completeness` 워크로드에서 적조 호출·알림·결과 행 0, 정선·어장환경 기존 그대로 | 통과 (기존 검사 갱신) |
| 전체 `pytest`(단위 + DB) | **479 passed** · 13 skipped(환경 의존 기존 skip) |
| 게이트(`--warn-pending`) | 통과 |
| `scan_keys` | 0건 |

## 2. 예상과 달랐던 결과

| API 특성 | 우리 코드·명세 결함 |
| --- | --- |
| — | `processor/completeness/_split_check.py`가 `processor._load`를 import해, `_load`가 모듈 맨 위에서 `processor.completeness`를 가져오면 순환 import가 된다 → `_load._check_bulletin_window()` 안에서 늦게 가져온다 |

## 3. 새로 발견한 함정

- 정기 적조 원문 픽스처(`redtideList_r1`·`r3`)는 메타에 `params`가 없다 — 기존 DB 검사에서는 `NO_WINDOW`로 대조를 건너뛴다(이벤트 없음, 기존 기대값 불변)

## 4. 산출물

| 경로 | 내용 |
| --- | --- |
| `collector/adapters/bulletin/_adapter.py`·`__init__.py` | 창 30일, 분할 수집 어댑터 제거 |
| `collector/main.py` | `completeness` 워크로드 = 정선·어장환경 |
| `common/raw_store/_store.py`·`__init__.py` | `list_keys(prefix)`·`list_raw_keys` |
| `processor/completeness/_bulletin_window.py` (신규) | 요청 창·속보 코드·빠진 속보(순수 함수), 직전 원문 고르기, `check_window` |
| `processor/completeness/__init__.py` | 내보내기 |
| `processor/_load.py` | 첫 처리·정상 응답일 때 트랜잭션 안에서 대조, `BULLETIN_WINDOW_MISSING`, `LoadResult.window_missing`·`window_skip` |
| `processor/main.py` | 지표 두 종 — 커밋 뒤 |
| `common/metrics/` | `bulletin_window_missing_total`, `bulletin_window_check_skipped_total{reason}` |
| `tests/db/test_bulletin_window.py` (신규, 18) | N15·N16·후보 선택 |
| `tests/db/test_completeness_e2e.py` | E7 적조 제외 반영 |

## 5. 계획서 반영 후보

- 4-B′(짧은 창 교차 호출) 채택 여부 — 직전 원문 대조가 동작하는 것은 확인. 실제 절단 빈도는 운영 데이터가 있어야 보인다(사용자 결정)
- 인계 요청(11절): `HANDOFF.md`·매니페스트 주석 "14일", 적조 수집 동시 실행 금지 권장
- 결과 코드 `04` → `BAD_REQUEST` *(제안)*
