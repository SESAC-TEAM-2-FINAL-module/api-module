# 양식장 좌표 입력 계약 (farm-sites-v1)

계획서 1.6절 · 계약서 버전 `farm-sites-v1`

## 열 목록

| 열 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `farm_id` | 문자열 | NOT NULL, UNIQUE | 양식장 식별자 |
| `lat` | float (십진도) | NOT NULL | WGS84 위도 |
| `lng` | float (십진도) | NOT NULL | WGS84 경도 |
| `active` | boolean | NOT NULL | 활성 여부. `false`가 소프트 삭제 표현 |
| `updated_at_utc` | DATETIME (UTC naive) | NOT NULL | 마지막 수정 시각 |

## 좌표계

WGS84 십진도. 폐구간 검증 `[33.0, 39.0] × [124.0, 132.0]` (계획서 1.5절 `geo`).
검증 실패 → `common/farm_sites/` 가 `valid_coords=False` 표시.
전 축 `provenance = NONE`, `none_reason = INVALID_COORDS` 처리는 `grading` 몫 (4.8절).

## 소유

웹 서비스. 이 모듈은 **읽기만** 한다.
