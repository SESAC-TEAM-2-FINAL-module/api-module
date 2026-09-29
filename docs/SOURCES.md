# SOURCES.md — 검증 코드 이식 기록 (계획서 6.3절)

이식·참고·신규·사용 금지 구분은 계획서 6.3절 표를 따른다.
각 지시서 실행 후 실제 이식한 함수·파일 단위를 여기에 추가한다.

| 새 경로 | 검증 코드 위치 | 처리 | 비고 |
|---|---|---|---|
| `common/classifier/_parser.py` | `$SRC_C/probe.py` :: `ParsedResponse`, `_detect_format`, `_parse_xml`, `_parse_json`, `_classify` | TRANSPLANT | `22`→`QUOTA`, `41`→`SUSPENDED` 추가; lxml 복구 파서 제거; 빈 결과 코드→`PARSE_FAILURE` 강화; 스키마 계열 5종 통합 |
| `common/geo/_dms.py` | `$SRC_API/verify_nifs_api.py` :: `DMS_RE`, `dms_to_decimal()` | TRANSPLANT | 그대로 이식 |
| `common/geo/_coords.py` | `$SRC_IDW/src/normalizer.py` :: `validate_coords_closed()` | TRANSPLANT | 범위를 파라미터로 받도록 변경 (판정 정의에서 읽기 위해); 사용 금지 `validate_coords()`는 미사용 |
| `common/http/_client.py` | `$SRC_IDW/src/collector.py` :: (내부 요청 함수) | REFERENCE | `httpx`로 교체; 재시도 `05`에만 1회; 빈 파라미터 전송 금지; `final_url` 마스킹; 대체 금지 |
| | `$SRC_API/verify_nifs_api.py` :: `call()` | REFERENCE | 호출층 구조 참고 |
| `common/raw_store/_store.py` | `$SRC_IDW/src/collector.py` :: `save_raw_response()` (B 수정본) | REFERENCE | 객체 저장소 인터페이스로 추상화; `error` 필드 추가; `fetched_at` UTC 명시 |
| `processor/completeness/_checker.py` | `$SRC_API/verify_nifs_api.py` :: F2 분할 합산 | REFERENCE | 범위 불일치 결함 수정 — 범위 일치 검사를 먼저 수행 (`COMPARISON_RANGE_MISMATCH`) |
| `common/queue/`, `common/config/`, `common/farm_sites/`, `common/contract_check/`, `common/metrics/`, `collector/main.py`, `processor/main.py`, `processor/quality/_rules.py` | — | 신규 | |
| `collector/adapters/tide/_adapter.py` :: `_collect_station()` | `$SRC_IDW/stage2_collect.py` :: `_fetch_all_pages()` | TRANSPLANT | `totalCount`까지 전 페이지 수령; 사전 읽기로만 사용; 다중 페이지 시 합산 결과 JSON 구성(계획서 반영 후보); `_save_raw()` 사용 금지 |
| `processor/adapters/tide/_adapter.py` | `$SRC_IDW/stage2_collect.py` (dtRecent 필드 처리) | TRANSPLANT | `obsrvnDt` KST naive 확인(I-2) → UTC (-9h) 변환 추가; 6개 metric (`wtem`·`slntQty`·`bscTdlvHgt`·`wspd`·`wdir`·`artmp`); `0.000` 결측 위치: processor normalize; `lot` 경도 필드는 stations.csv에서 읽으므로 어댑터 불필요 |
| `processor/adapters/tide/_adapter.py` | `$SRC_IDW/stage1_verify.py` (응답 검증) | REFERENCE | 3종 스키마, 필드명 확인 |
| `collector/adapters/bulletin/_adapter.py` | `$SRC_API/verify_nifs_api.py` (NIFS 호출 구조) | REFERENCE | `id=redtideList&key=…&sdate=…&edate=…` 파라미터 구조 참고 |
| `processor/adapters/bulletin/_adapter.py` | `$SRC_API/verify_nifs_api.py` :: `nested_items` 중첩 처리 | REFERENCE | `probe_followup.py::probe_redtide()` 사용 금지 — item2 없는 속보 버리는 결함 |
| `processor/adapters/bulletin/_adapter.py` | — (신규) | 신규 | 등급 판정 5단계, txt_seas 정규화 5단계, 지점 분리, 별칭·시드 로딩 |
| `seeds/areas.yaml` · `seeds/area_aliases.yaml` · `seeds/axis_coverage.yaml` | — | 신규 | 형식만. 내용 미결(계획서 11절) |

| `collector/adapters/line/_adapter.py` | `$SRC_IDW/src/collector.py` :: `collect_line_survey()` | REFERENCE | 1년 창 1회 호출; pageNo 없음(페이징 없음) |
| `processor/adapters/line/_adapter.py` | `$SRC_IDW/src/normalizer.py` :: `normalize_line_with_depth()` (B v2) | TRANSPLANT | group_type 원문 레코드 단위 계산; 좌표 범위 주입; obs_dtm KST→UTC(-9h) 변환 추가; metric 3종(wtr_tmp·sal·dox)만; 빈 값 레코드 MISSING 저장; is_surface 열 없음 |
| `processor/adapters/line/_adapter.py` | `$SRC_IDW/line_depth_collect_v2.py` :: `_assign_casts()` + `cast_id_x60_map` | TRANSPLANT | 열 이름의 X값을 `cast_rule_version`으로 분리; 전제 감시(10 < gap ≤ 720분 → CAST_RULE_ASSUMPTION_BROKEN) 추가 |

| `collector/adapters/fishery/_adapter.py` | `$SRC_IDW/src/collector.py` :: `collect_fishery_sea()` | REFERENCE | 달력 연도 단위 1회 호출; sdate=YYYY0101, edate=YYYY1231(올해는 오늘까지); 페이징 없음 |
| `collector/fishery_watch.py` | — | 신규 | 게시 감시(주 1회 사전 읽기 → 건수 변화 시 전량 수집 같은 실행); 호출 실패 게시 대기 금지 |
| `processor/adapters/fishery/_adapter.py` | `$SRC_API/verify_nifs_api.py` :: `extract_dates()` | REFERENCE | DATE_Y/M/D int 변환 결함(한 자리 값 "5") → int() 후 format 으로 수정 |
| `processor/adapters/fishery/_adapter.py` | `$SRC_API/verify_nifs_api.py` :: DMS 좌표 파싱 | REFERENCE | LATITUDE/LONGITUDE DMS → dms_to_decimal() (already in common/geo) |

| `common/geo/_haversine.py` :: `haversine()` | `$SRC_IDW/src/idw.py` :: `haversine()`, `EARTH_RADIUS_KM` | TRANSPLANT | SHA-256: `6184B0C5622370627922B0F215281B80498FDCAE03C4D77BE4A59956C3BAF689`. 함수 본문 동일 — F12 P95 2.48 재현을 위해 상수·공식 변경 금지. 주석·타입힌트·docstring만 한국어로 변경 |
| `interpolation/` :: IDW 계산, LOOCV | `$SRC_IDW/src/idw.py` :: `idw_estimate()`, `sorted_by_dist()` | TRANSPLANT | IDW 본체. 입력을 CSV가 아니라 DB·양식장 좌표로 |
| `interpolation/` :: LOOCV 교차검증 | `$SRC_IDW/stage3_idw.py` :: `run_e1()` (2차 재검증) | TRANSPLANT | 그룹 내 동일 관측소 중복 제거(`drop_duplicates`) 포함판. `$SRC_IDW/src/experiments.py run_e1()` 사용 금지 |

## 원천 필드 확인 기록 — femoSeaList (I-5)

| 필드 | 원천 필드명 | 확인 방법 | 확인일 |
|---|---|---|---|
| 수온 (표층) | `TEMP_S` | 픽스처 `femoSeaList_f3_2023_*.json` 직접 확인 | I-5 (2026-09-29) |
| 수온 (저층) | `TEMP_B` | 동일 | I-5 (2026-09-29) |
| 염분 (표층) | `SAL_S` | 동일 | I-5 (2026-09-29) |
| 염분 (저층) | `SAL_B` | 동일 | I-5 (2026-09-29) |
| 클로로필 (표층) | `CHL_S` | 동일 | I-5 (2026-09-29) |
| 클로로필 (저층) | `CHL_B` | 동일 | I-5 (2026-09-29) |
| 정점 | `FISHERY`, `LOCATION_POINT` | 동일 | I-5 (2026-09-29) |
| 날짜 | `DATE_Y`, `DATE_M`, `DATE_D` | 동일 — 한 자리 정수값("5") 가능 확인 | I-5 (2026-09-29) |
| 좌표 | `LATITUDE`, `LONGITUDE` | DMS 형식 `34°47′19″` 확인 | I-5 (2026-09-29) |

## 원천 시각 시간대 확인 기록 (계획서 SKILL.md ③-3 의무)

| 항목 | 확인 결과 |
|---|---|
| API | `dtRecent` — 조위관측소 최신관측 (국립해양조사원) |
| 필드 | `obsrvnDt` |
| 형식 | `YYYY-MM-DD HH:MM:SS` naive datetime |
| 시간대 | **KST(UTC+9) naive** — `$SRC_IDW/stage2_collect.py`의 `parse_dt()`에서 timezone 변환 없이 저장 확인 (`observations.csv` 시각이 KST 형식과 일치) |
| 처리 | `processor/adapters/tide/_adapter.py` `_kst_to_utc()` — `-9h` 적용 후 UTC ISO 저장 |
| 확인일 | I-2 (2026-09-28) |

| 항목 | 확인 결과 |
|---|---|
| API | `sooList` — 정선해양관측 (국립수산과학원) |
| 필드 | `obs_dtm` |
| 형식 | `YYYY-MM-DD HH:MM` naive datetime (초 없음) |
| 시간대 | **KST(UTC+9) naive** — 간접 증거 3종: ① IDW(`$SRC_IDW/src/normalizer.py`) 저장 시 timezone 변환 없음(KST로 취급) ② 픽스처 관측 시각이 한국 관측선 운항 시간대(오전·오후)와 일치 ③ 동일 기관(NIFS) dtRecent도 KST 확인(I-2). 직접 API 문서 확인 불가(계획서 반영 후보) |
| 처리 | `processor/adapters/line/_adapter.py` `_kst_to_utc()` — `-9h` 적용 후 UTC ISO 저장 |
| 확인일 | I-4 (2026-09-29) |
