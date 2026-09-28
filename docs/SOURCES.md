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

## 원천 시각 시간대 확인 기록 (계획서 SKILL.md ③-3 의무)

| 항목 | 확인 결과 |
|---|---|
| API | `dtRecent` — 조위관측소 최신관측 (국립해양조사원) |
| 필드 | `obsrvnDt` |
| 형식 | `YYYY-MM-DD HH:MM:SS` naive datetime |
| 시간대 | **KST(UTC+9) naive** — `$SRC_IDW/stage2_collect.py`의 `parse_dt()`에서 timezone 변환 없이 저장 확인 (`observations.csv` 시각이 KST 형식과 일치) |
| 처리 | `processor/adapters/tide/_adapter.py` `_kst_to_utc()` — `-9h` 적용 후 UTC ISO 저장 |
| 확인일 | I-2 (2026-09-28) |
