# 모듈 → 대시보드 답변 (2026-10-02)

원문: `모듈_확인요청_farm_areas_2026-10-02.md`

## 1. `farm_areas` 관련

**네, 맞습니다. 되돌려 주세요.**

- `farm_areas`는 **모듈이 양식장 좌표로 계산해서 쓰는 결과 테이블**입니다(계획서 개정 15). 규칙은 "양식장 좌표가 반경 안에 드는 해역 중 **중심이 가장 가까운 하나**, 없으면 `area_id = NULL`"이고, `evaluation`이 판정할 때마다 갱신합니다
- **대시보드도 이 표를 읽으시면 됩니다.** 열: `farm_id`(PK) · `area_id`(nullable) · `distance_km` · `rule`(`NEAREST_CENTER_WITHIN_RADIUS`) · `computed_at_utc`. 결과 테이블 계약 `tables-v2`에 포함돼 있습니다
- `farm_sites.area_id`는 **모듈이 읽지 않습니다**(모듈의 `farm_sites` 읽기는 좌표·활성 여부만 씁니다). 원래 입력 계약 `farm-sites-v1` — `farm_id, lat, lng, active, updated_at_utc` — 으로 되돌리셔도 모듈 쪽 변경은 없습니다. 모듈에서 `area_id`를 받을 필요도 없습니다 — 해역은 모듈이 정해 알리는 쪽으로 정했습니다(웹이 계산하면 같은 판정이 두 곳에 생깁니다)

주의할 점:

- `farm_areas.area_id`는 **커버리지 밖·계절 밖 판정에 쓴 해역**입니다. 행정구역·어업권 구역이 아닙니다
- **적조 속보 대응은 반경 안 해역을 모두 씁니다** — 적조 해역을 `farm_areas.area_id` 하나로 다시 고르지 마시고, 적조 현재값은 `farm_readings`(axis `red_tide`)를 그대로 읽어 주세요

혼선 원인은 저희 쪽입니다 — 드린 `handoff/dashboard-deliver/farm_sites_format.csv`가 개정 15 이전 양식이었습니다. **입력 계약 열로 고쳤습니다**(`area_id` 삭제, `updated_at_utc` 추가). 같은 묶음의 나머지(`schema_pg.sql`·`sample_result_rows.json` 등)도 개정 14·15 이전이라 다시 만들 예정입니다 — 그 전까지는 **`contracts/tables/`**(DDL·`dashboard_contract.md`)와 **`contracts/inputs/farm_sites.md`**를 기준으로 봐 주세요. `handoff/dashboard-deliver.zip`은 옛 묶음이라 저장소에 올리지 않았습니다.

## 2. 작업물 git 업로드

올렸습니다 — `origin`(`SESAC-TEAM-2-FINAL-module/api-module`) `main`. 최신 계약은 위 `contracts/` 경로, 위험도 지수 설계는 `docs/plan/risk_index/`(03 결정 목록, 05 추가 확인 회신)에 있습니다.
