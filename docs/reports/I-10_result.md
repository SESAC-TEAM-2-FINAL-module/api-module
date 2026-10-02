# I-10 결과 보고서 — 빌드·CI

작성일: 2026-09-30  
참조 skill: 없음 (I-10 본문 전용)  
참조 계획서: 2.0.2절·2.0.5절·6.1절·7.6절·7.7절

---

## 1. 산출물 목록

| 파일 | 내용 |
|---|---|
| `docker/collector/Dockerfile` | collector 이미지 — common + collector + definitions.yaml |
| `docker/processor/Dockerfile` | processor 이미지 — common + processor + definitions.yaml |
| `docker/interpolation/Dockerfile` | interpolation 이미지 — common + interpolation + numpy/scipy |
| `docker/grading/Dockerfile` | grading 이미지 — common + grading + definitions.yaml |
| `docker/evaluation/Dockerfile` | evaluation 이미지 — common + evaluation + fixtures/synthetic + operational.schema.json |
| `.gitlab-ci.yml` | 4단계 파이프라인 (test → gate → build → notify) |
| `ci/gate/run_gate.py` | 게이트 ①·①′ 구현 |
| `ci/gate/expected.yaml` | 게이트 기준 문서 (settings·counts) |
| `contracts/release/image_notice.json` | 이미지 알림 형식 명세 (계획서 2.0.5절) |
| `tests/gate/test_counts.py` | ② 건수 보존 테스트 (24 통과, 2 스킵) |
| `tests/gate/__init__.py` | 패키지 초기화 |

**추가 수정 (I-10 진행 중 발견된 버그):**

| 파일 | 수정 내용 |
|---|---|
| `src/api_module/common/classifier/_parser.py` | `OK_EMPTY` 미구현 버그 수정 — CLAUDE.md 6절 "00+0행→OK_EMPTY" 적용 |
| `tests/unit/test_classifier.py` | `test_ok_empty_total_count_zero` 기대값 `OK` → `OK_EMPTY` |
| `tests/unit/test_fishery_processor.py` | `test_parse_status_ok` → `test_parse_status_ok_empty` |

---

## 2. 통과 기준 결과

### ② 건수 보존 (pytest tests/gate/)

```
308 passed, 4 skipped
```

| 테스트 | 결과 |
|---|---|
| femo_2023/2024/2025 raw·stored=1008/1020/1022 | 통과 |
| femo_2026 OK_EMPTY + publication_check=1 | 통과 |
| redtide_r1 51속보/50세부/45코클로/1건unknown | 통과 |
| redtide_r3 15속보/10not_graded/20area_parts | 통과 |
| redtide_all unique_day_report=66 | 통과 |
| soo_v2 raw=10445 | 통과 |
| soo_v2 lat33_kept=523 | 통과 |
| soo_v2 coord_excluded=1029 | 통과 |
| soo_v2 south_count | 스킵 (계획서 반영 후보) |
| soo_v2 empty_value_dropped | 스킵 (계획서 반영 후보) |

### ① 판정 정의 대조 + ①′ 운영 조정 검사

```
python ci/gate/run_gate.py --warn-pending
→ 게이트 통과
```

- ①: 8개 `<미결>` 항목 경고, 나머지 일치
- ①′: `<미결>` 잔존으로 스키마 검사·판정 재생 건너뜀 (계획서 7.7절 — S12 전까지)

---

## 3. CI 파이프라인 설계 요점

**4단계**: `test → gate → build → notify`

- **선택 빌드**: `rules: changes:` 경로 명시 (YAML 앵커 미사용 — `changes:` 시퀀스 인라인 전개 불가)
- **레지스트리**: `REGISTRY` CI 변수 하나로만, 코드에 주소 없음 (계획서 2.0.2절)
- **이미지 알림**: `MANIFEST_TRIGGER_URL` POST — manifest 파일 커밋·PR 없음 (계획서 금지 규칙)
- **`--warn-pending`**: S12 인계 전까지 경고 처리; S12에서 플래그 제거 시 `<미결>` 실패 전환

---

## 4. 계획서 반영 후보 (*(제안)* 항목)

| 항목 | 내용 |
|---|---|
| soo_v2 south_count | 어댑터가 `_region` 메타 미노출 — 추가 시 테스트 활성화 |
| soo_v2 empty_value_dropped (남해 한정) | `_region` 메타 연동 필요 |

---

## 5. 만난 `<미결>` 목록

`config/definitions.yaml`:  
`bulletin.current_window_days`, `line.surface_rule`, `interpolation.exclude_flatline`, `interpolation.error_window_days`, `grading.salinity_mode`, `grading.line_max_distance_km`, `grading.fishery_max_distance_km`, `grading.excluded_zones`

`config/operational.initial.yaml`:  
`tide.flatline_minutes`, `stale_threshold_hours.*` 다수

→ 모두 S12 진입 전 인프라/계획서 결정 필요.
