# 대시보드 계약 — 결과 테이블 의미 계약 (5.5절)

**배포 주인**: `evaluation`  
**계약 버전**: `tables-v2` (2026-10-01 — 개정 14: DO·클로로필 `source_ref`가 조사·관측 시각 기준, `survey_observations` 키에 조사 시각)  
**계획서 근거**: 5.5절, v1.5 원칙

이 문서는 이 모듈이 결과 테이블에 적재하는 값의 의미와, 대시보드가 지켜야 하는 요구사항을 넘기는 계약이다. 배지·화면 문구·노출·발송 시점은 대시보드가 정한다.

---

## 필드의 의미

| 필드 | 뜻 | 뜻하지 않는 것 |
| --- | --- | --- |
| `derivation` | 값의 유래 — `COMPUTED`(계산) / `MEASURED`(인근 실측) / `OFFICIAL`(기관 발표) / `SURVEY`(조사값) | — |
| `provenance` | 영역 판정 — 오차·방법 기준 등급. `NONE`은 **신뢰 기준 밖** | 배지. `NONE`이 "값 없음"을 뜻하지 않는다 |
| `none_reason` | `grading`이 기록한 `NONE` 사유 | 화면 표시용 사유가 아니다 — 표시는 `axis_status.reason` |
| `lower` · `upper` | 수온: `value` ∓ 오늘의 오차 P95 | 최솟값·최댓값이 아니다 |
| `source_ref` | 근거 원천 행의 키 — 수온 `run_id` / 인근 실측 `station_id` / DO·클로로필 `station_id@observed_at_utc`(조사·관측 시각, UTC ISO — 개정 14) / 적조 `cod_news#seq` | 사람이 읽는 설명이 아니다 |
| `validated_scope` | 계산값의 검증 범위 — `STATION_SITES`는 관측소 위치에서만 교차검증했다는 뜻. 계산값(`COMPUTED`)에만 채운다 | 만 안쪽 양식장의 추정이 검증됐다는 뜻이 아니다 — **만 안쪽은 미검증** |
| `alertable` | **발송 자격** — 계산 시점의 정적 자격 | 지금 보내라는 뜻이 아니다. 신선도를 담지 않는다 — 발송 후보는 `axis_status`와 함께 본다(W5) |
| `bulletins.grade` · `bulletin_details.grade` · `farm_readings.grade` | 적조 공식 4단계 `NONE`(예비특보 미만) / `PRE_ADVISORY` / `ADVISORY` / `WARNING`, 그리고 `NOT_GRADED`(비대상 종) · `UNKNOWN`(원인생물·밀도·세부 행 없음) | 여기의 `NONE`은 `provenance`의 `NONE`(신뢰 기준 밖)과 **다르다**. `farm_readings.grade`는 `grading`이 고른 현재값 행의 등급이다 — 대시보드가 다시 고르지 않는다 |
| `axis_status.state`·`reason` | 침묵 분류(4.9절 상태 값 17종)와 그 사유. 겹치면 4.9절 우선순위 | 화면 문구. `provenance`의 `NONE`과 다르다 — 값을 못 쓰는 경우는 `NOT_USABLE` |
| `farm_areas.area_id` | 모듈이 정한 양식장 해역 — 반경 안 해역 중 중심이 가장 가까운 하나(`rule`). 커버리지 밖·계절 밖 판정에 쓴 해역이다(개정 15) | 행정구역·어업권 구역이 아니다. 적조 속보 대응은 반경 안 해역을 모두 쓴다 — 이 열 하나로 적조 해역을 다시 고르지 않는다 |
| `observed_at_utc` · `computed_at_utc` · `basis_utc` · `last_checked_utc` | 관측 시각 · 산출 시각 · 판정에 쓴 가장 새 입력의 시각 · 판정 시각 | — |

---

## 대시보드 요구사항 W1~W8

| # | 요구사항 | 근거 |
| --- | --- | --- |
| W1 | **배지는 `derivation`과 축으로 정한다.** `derivation = COMPUTED`인 값에 `인근 실측`·`공식 발표` 배지를 붙이지 않는다. `provenance`에서 배지를 끌어내지 않는다 | v1.5 1.4절, 1.3.2절 |
| W2 | **`provenance = NONE` 값은 표시하지 않는다.** 값은 근거 보기·운영 확인용으로 남아 있다 | v1.5 4.6.1절, 6.2절 |
| W3 | **시각으로 신선도를 판단한다.** `axis_status.last_checked_utc`가 한계를 넘으면 값 대신 "확인 불가"류로 보인다. 한계값은 대시보드 설정이다 | v1.5 S3, 4.6.2절 |
| W4 | **두 테이블의 순간 불일치를 감안한다.** `farm_readings`(grading)와 `axis_status`(evaluation)는 쓰는 시점이 다르다. `axis_status.basis_utc`가 `farm_readings.computed_at_utc`보다 이르면 상태가 아직 새 값을 반영하지 않은 것이다 | 4.9절 |
| W5 | **발송 시점은 대시보드가 정한다.** `alertable = true`이고 `axis_status.state`가 정상인 축의 값만 발송 후보다. 두 판정을 조합할 뿐 다시 계산하지 않는다 | v1.5 8.1절 15, 5.3절 |
| W6 | **해역 없는 속보**(`bulletins`에만 있고 대응 양식장 없음)의 표시 정책은 대시보드가 정한다 | 4.8절 |
| W7 | **"발송 안 된 것" 패널**의 변화 감지는 대시보드가 `farm_reading_history`와 `alertable`로 한다 | v1.5 S2' |
| W8 | 침묵 분류(`state`)별 화면 문구는 대시보드가 정한다. v1.5 4.5절 "화면" 열이 기준 | v1.5 4.5절 |

**대시보드가 하지 않는 것**: `provenance`·오차·침묵 분류를 다시 계산하지 않는다.
