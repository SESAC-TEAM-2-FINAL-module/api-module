# flowtest — 데이터 흐름 시험 실행기

공공 API 수집 → 해석·적재 → 수온 추정 → 출처 등급 → 침묵 판정까지 모듈의 전 단계를 **한 컨테이너 안에서 한 번에** 돌려, 시험용 DB의 결과 테이블(`farm_readings`·`axis_status`·`farm_areas` 등)을 실제 데이터로 채웁니다.

- **시험용입니다.** 운영 배포·CI·매니페스트 대상이 아닙니다. 운영 DB에 쓰지 마십시오.
- 단계 사이는 프로세스 안의 메모리 큐로 잇고, 원문은 컨테이너 디스크에 둡니다. 운영 구조(단계별 이미지 + 메시지 큐 + 원문 저장소)와 이 두 가지가 다릅니다. 판정 로직은 운영 이미지와 같은 코드입니다.

---

## 1. 실행 전 DB 준비 (DB 소유 측)

순서를 지켜야 합니다. 하나라도 빠지면 실행기가 **아무것도 쓰지 않고** 멈추고 이유를 출력합니다.

1. **모듈 테이블 생성** — 함께 전달한 DDL(`schema_pg.sql`)을 적용
2. **해역 시드 적용** — 함께 전달한 시드 SQL(`seeds_pg.sql`)을 적용
3. **양식장 좌표 표 `farm_sites`** — 입력 계약대로 만들고 활성(`active = TRUE`) 양식장을 1건 이상 등록
   - 열: `farm_id`, `lat`, `lng`, `active`, `updated_at_utc`
   - 모듈은 이 표를 읽기만 합니다

## 2. 준비물

| 무엇 | 설명 |
|---|---|
| 이미지 | `ryujaehee/aquasentinel-flowtest:2026-10-06` (시험용 — 시험이 끝나면 내립니다) |
| 운영 조정 파일 | 함께 전달한 `operational.yaml`. 컨테이너에 마운트하고 경로를 `OPERATIONAL_CONFIG_PATH`로 지정 |
| 환경변수 | 아래 표. **인증키 값은 별도 경로로 전달합니다** — 파일·저장소에 남기지 마십시오 |
| 볼륨 (선택) | 원문 보관용. 붙이면 컨테이너가 끝나도 원문이 남고, 재생 모드에 쓸 수 있습니다 |

| 환경변수 | 필수 | 설명 |
|---|---|---|
| `DATABASE_URL` | 예 | 시험 DB 연결 문자열 — `postgresql+psycopg://<user>:<password>@<host>:5432/<db>` |
| `OPERATIONAL_CONFIG_PATH` | 예 | 운영 조정 파일의 컨테이너 안 경로 |
| `FT_RAW_STORE_PATH` | 아니오 | 원문 저장 위치(기본 `flowtest_raw_store`). 볼륨을 붙일 경로 |
| `QUEUE_DSN` | **금지** | 설정하면 실행기가 멈춥니다. 운영 NATS에 연결하지 않게 — 단계 간 큐는 프로세스 안의 메모리 큐를 씁니다 |
| `RAW_STORE_DSN` | **금지** | 설정하면 실행기가 멈춥니다. 운영 S3에 쓰지 않게 — 원문은 `FT_RAW_STORE_PATH` 로컬 디스크에만 씁니다 |
| `DTRECENT_URL`·`DTRECENT_KEY` | 수집 모드 | 조위관측소 요청주소·인증키 |
| `NIFS_URL` | 수집 모드 | 수산과학원 요청주소 |
| `NIFS_KEY_BULLETIN`·`NIFS_KEY_LINE`·`NIFS_KEY_FISHERY_SEA` | 수집 모드 | 적조·정선관측·어장환경 인증키 |

## 3. 실행 — 클러스터 (매니페스트)

시험 DB가 클러스터 안에 있으면 이 방법을 씁니다. 파일은 `k8s/` 폴더에 있습니다.

| 파일 | 무엇 |
|---|---|
| `secret-template.yaml` | 전용 Secret `flowtest-secrets` 양식 — 키 이름만. **모듈 운영 Secret을 재사용하지 마십시오**(원문 저장소·큐 연결 값이 들어 있으면 실행기가 멈춥니다) |
| `configmap-operational.yaml` | 운영 조정 ConfigMap `flowtest-operational` — 그대로 씁니다 |
| `job-once.yaml` | **한 번 실행** (Job) |
| `deployment-loop.yaml` | **반복 실행** (Deployment 1대 — 원천별 주기는 컨테이너 안에서 돈다) |

모든 파일의 `<네임스페이스>`를 바꾼 뒤(이미지 주소는 채워져 있습니다):

```bash
NS=<네임스페이스>

# 1) Secret — 값이 파일에 남지 않게 명령으로 만든다 (양식 파일은 키 이름 참고용)
kubectl -n $NS create secret generic flowtest-secrets   --from-literal=DATABASE_URL='postgresql+psycopg://<user>:<password>@<host>:5432/<db>'   --from-literal=DTRECENT_URL='https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService'   --from-literal=DTRECENT_KEY='<조위 인증키>'   --from-literal=NIFS_URL='https://www.nifs.go.kr/OpenAPI_json'   --from-literal=NIFS_KEY_BULLETIN='<적조 인증키>'   --from-literal=NIFS_KEY_LINE='<정선관측 인증키>'   --from-literal=NIFS_KEY_FISHERY_SEA='<어장환경 인증키>'

# 2) 운영 조정
kubectl -n $NS apply -f k8s/configmap-operational.yaml

# 3-a) 한 번 실행
kubectl -n $NS apply -f k8s/job-once.yaml
kubectl -n $NS logs -f job/flowtest-once          # 마지막 줄 JSON이 종료 요약
kubectl -n $NS delete job flowtest-once           # 다시 돌릴 때

# 3-b) 반복 실행
kubectl -n $NS apply -f k8s/deployment-loop.yaml
kubectl -n $NS logs -f deploy/flowtest-loop
kubectl -n $NS scale deploy flowtest-loop --replicas=0   # 멈춤 (진행 중 처리를 끝내고 요약 출력)
```

- **Job과 Deployment를 같은 DB에 동시에 돌리지 마십시오** — 같은 원천을 두 번 적재합니다. Deployment는 1대만 둡니다
- Job은 실패해도 재시도하지 않습니다(`backoffLimit: 0`) — 실행 전 점검에서 멈춘 경우 로그의 이유(7절)를 보고 고친 뒤 다시 실행합니다
- 원문은 기본으로 파드가 끝나면 사라집니다(`emptyDir`). 재생에 쓰려면 매니페스트 주석대로 PVC로 바꿉니다
- 클러스터 밖으로 나가는 통신(egress)이 필요합니다: `apis.data.go.kr`, `www.nifs.go.kr`

## 4. 실행 — docker run (DB에 닿는 곳에서)

시험 DB에 직접 닿는 곳(로컬 등)에서 쓰는 방법입니다.

**한 번 실행** (수집 4종 한 번 → 수온 오차 산출 → 침묵 점검 → 요약 출력 → 종료, 약 1분)

```bash
docker run --rm \
  --env-file flowtest.env \
  -e OPERATIONAL_CONFIG_PATH=/config/operational.yaml \
  -e FT_RAW_STORE_PATH=/app/raw_data \
  -v /path/to/operational.yaml:/config/operational.yaml:ro \
  -v /path/to/raw_data:/app/raw_data \
  ryujaehee/aquasentinel-flowtest:2026-10-06 --mode collect --run once
```

`flowtest.env`에는 위 표의 변수를 `이름=값` 줄로 둡니다(이 파일은 공유 저장소에 올리지 마십시오).

**반복 실행** — 운영과 비슷하게 주기적으로 수집해 결과가 갱신되는 모습을 볼 때. 주기 7개를 **모두** 지정해야 하며, 하나라도 없으면 시작하지 않습니다. 종료는 `docker stop`(진행 중인 처리를 마치고 요약을 출력).

```bash
docker run -d --name flowtest \
  --env-file flowtest.env \
  -e OPERATIONAL_CONFIG_PATH=/config/operational.yaml \
  -e FT_RAW_STORE_PATH=/app/raw_data \
  -e FT_TIDE_INTERVAL_SEC=600 \
  -e FT_BULLETIN_SEASON_INTERVAL_SEC=3600 -e FT_BULLETIN_OFFSEASON_INTERVAL_SEC=21600 \
  -e FT_LINE_INTERVAL_SEC=86400 -e FT_FISHERY_INTERVAL_SEC=604800 \
  -e FT_SWEEP_INTERVAL_SEC=600 -e FT_ERROR_INTERVAL_SEC=86400 \
  -v /path/to/operational.yaml:/config/operational.yaml:ro \
  -v /path/to/raw_data:/app/raw_data \
  ryujaehee/aquasentinel-flowtest:2026-10-06 --mode collect --run loop
```

| 주기 | 권장 | 비고 |
|---|---|---|
| 조위 `FT_TIDE_INTERVAL_SEC` | 600 (10분) | |
| 적조 시즌 `FT_BULLETIN_SEASON_INTERVAL_SEC` | 3600 (1시간) | 5~10월(한국 시각 기준 월) |
| 적조 시즌 밖 `FT_BULLETIN_OFFSEASON_INTERVAL_SEC` | 21600 (6시간) | 11~4월 |
| 정선관측 `FT_LINE_INTERVAL_SEC` | 86400 (1일) | |
| 어장환경 감시 `FT_FISHERY_INTERVAL_SEC` | 604800 (주 1회) | |
| 침묵 점검 `FT_SWEEP_INTERVAL_SEC` | 600 (10분) | API 호출 없음 |
| 수온 오차 산출 `FT_ERROR_INTERVAL_SEC` | 86400 (1일) | API 호출 없음 |

**재생** — 볼륨에 남은 원문을 API 호출 없이 다시 흘립니다. **비운 DB(새 DB)** 에 쓰십시오. 원천마다 한 번씩 돌립니다(조위를 먼저).

```bash
docker run --rm --env-file flowtest.env -e OPERATIONAL_CONFIG_PATH=/config/operational.yaml \
  -v /path/to/operational.yaml:/config/operational.yaml:ro -v /path/to/raw_data:/app/raw_data \
  ryujaehee/aquasentinel-flowtest:2026-10-06 --mode replay --run once --replay-api dtRecent --replay-date 2026/10/06
```

`--replay-api`: `dtRecent`(조위) · `redtideList`(적조) · `sooList`(정선관측) · `femoSeaList-watch`(어장환경 감시). `--replay-date`: 원문 폴더의 날짜(`YYYY/MM/DD`, UTC).

## 5. 호출량

| 원천 | 한 번 실행 | 반복 실행(권장 주기) |
|---|---|---|
| 조위 | 9회 (9개소 × 1페이지, 자정 경계 시 +9회) | 하루 약 1,320회 (자정 3회 구간 +9회) |
| 적조 | 1회 | 하루 24회(시즌) / 4회(시즌 밖) |
| 정선관측 | 1회 | 하루 1회 |
| 어장환경 감시 | 1회 (게시가 바뀌었으면 그 해 전량 추가) | 주 1회 |

같은 인증키로 다른 수집이 함께 돌면 호출량이 합산됩니다. 일일 한도를 확인하고 반복 실행하십시오.

## 6. 종료 요약 읽기

끝나면 사람이 읽는 요약과 JSON 한 줄이 출력됩니다. 2026-10-06 실제 수집 한 번 실행의 예(양식장 1곳):

```json
{"runs": 1,
 "published_by_topic": {"raw.fetched": 12, "obs.loaded": 12, "interp.done": 8, "grade.done": 112, "result.updated": 111},
 "stage_failures": {},
 "result_table_rows": {"farm_readings": 9, "axis_status": 9, "farm_areas": 1, "farm_reading_history": 105,
                       "interpolation_runs": 8, "observations": 36882, "raw_index": 12, "ingest_runs": 12, "...": "..."}}
```

- `stage_failures`가 비어 있지 않으면 그 단계의 메시지 처리가 실패한 것입니다(로그에 단계·종류가 남습니다). 다른 원천의 처리는 계속됩니다
- 이때 양식장의 축별 결과: 수온 `NORMAL`(계산값 — 발송 자격 없음), 기온·조위·풍속 `NORMAL`(인근 실측), 염분 `NOT_USABLE`(하구 영향 관측소라 신뢰 기준 밖 — 값은 저장됨), DO `STALE`(최신 조사가 2025-11), 클로로필 `NOT_USABLE`(올해 게시 없음), 적조 `NORMAL_SILENCE`(유효 속보 없음), 적조 위험도 지수 `NOT_USABLE`(규칙 값 미정). 값을 쓸 때의 의미는 대시보드 계약을 따릅니다

## 7. 멈췄을 때

실행 전 점검이 실패하면 `실행 전 점검 실패: …` 또는 `… 기동 멈춤` 메시지와 함께 0이 아닌 코드로 끝나고, DB에는 아무것도 쓰지 않습니다.

| 메시지 | 확인할 것 |
|---|---|
| DB 스키마 불일치 | 1절 1번 DDL 적용 여부·버전. "없는 고유 키"가 나오면 그 표의 고유 인덱스(`CREATE UNIQUE INDEX`)가 빠진 것 — 현재 판 DDL로 다시 적용 |
| 해역 시드 표가 비었다 / seed-check 차이 | 1절 2번 시드 SQL 적용 여부·버전 |
| farm_sites 표 없음 / 활성 행 없음 | 1절 3번 |
| 운영 조정 파일 없음 / 스키마 위반 | 마운트 경로와 `OPERATIONAL_CONFIG_PATH` |
| 수집 환경 변수 없음 | 2절 표의 변수 이름(값은 출력하지 않습니다) |

## 8. 알려진 한계

- **큐·원문 저장소가 운영 구조와 다름** — 단계 사이를 메모리 큐로 잇고 원문을 로컬 디스크에 둡니다. 재전달·동시 실행·확장은 이 실행기로 확인되지 않습니다
- **보충 원문(자정 경계)** — KST `[00:00, 00:30)` 실행 시 조위 어제분을 추가로 받아 저장하지만, `obs.loaded`를 내지 않으므로 처리 연쇄는 시작되지 않습니다
- 오류 처리 보강은 다음 단계 범위입니다
