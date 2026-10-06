# I-18 결과 보고서 — 단계 연결: NATS JetStream 큐 · S3 원문 저장소 · queue-v2 · 조위 한 페이지

**지시서**: `docs/instructions/I-18_단계연결_JetStream_S3.md`  
**계획서 개정**: 22 (커밋 `2f2e1a0`)  
**참조 skill**: `common-core` · `tide` · `interpolation` · `grading` · `evaluation` · `repository` (모두 커밋 `2f2e1a0` 기준)  
**기준선**: pytest 666 passed · 14 skipped · 게이트 통과 · scan_keys 0건

---

## 1. 현황 표 (작업 1)

| 항목 | 기준선 상태 | I-18 후 상태 |
|---|---|---|
| 큐 인터페이스 | `Queue.publish/subscribe` — 인메모리만 | `NatsQueue.from_env()` + `MemoryQueue` 두 구현체 |
| 원문 저장소 | `LocalDiskStore`만, `epoch_ms` 항상 000 (초 단위 key 충돌 가능) | S3 구현체 + `_fetched_ms` 밀리초 키 |
| 큐 계약 버전 | `queue-v1` (`interp.done.error_p95` 필수) | `queue-v2` (`interp.done.error_p95` nullable) |
| 조위 수집 | 페이지 루프 + 합치기 | `min=5`·`numOfRows=300`·`reqDate` 1회, 자정 경계 어제분 `_y` |
| 컨슈머 진입점 | `MemoryQueue()` 직접 생성, 수신 대기 없음 | `NatsQueue.from_env()` 기동, SIGTERM 처리 |
| 결정적 실행 ID | `uuid4` (재전달 시 고유 제약 위반 → `interp.done` 유실) | UUID v5 (입력 키에서 결정적 생성) |
| 테스트 수 | 666 passed · 14 skipped | **683 passed · 14 skipped** (17 신규 추가) |

---

## 2. T4 확인 호출 결과

지시서 T4(`dtRecent` 확인 호출 5회 이내) — 피어 세션이 실행 후 보고:

| 확인 항목 | 결과 |
|---|---|
| `totalCount` = 경과분 ÷ 5 + 1 | 확인됨 (KST 기준 5분 격자) |
| 응답 최상위 `header` 계열 (`body.items.item`) | 확인됨 — I-17 실수집과 동일 형태 |
| `reqDate` = 오늘 KST, `min=5`, `numOfRows=300` | 한 페이지에서 그날 전체 수령 확인 |
| `include` 동작 | 포함 항목만 반환됨 |

---

## 3. 구현 내용 (피어 세션 `aquasentinal-api-module-7c`)

### 3-1. NATS JetStream 큐 (`src/api_module/common/queue/`)

- `_nats.py`: `NatsQueue` — asyncio nats-py 기반. `from_env()`는 `QUEUE_DSN` 없으면 `SystemExit`
- 기동 시 스트림·컨슈머 멱등 생성 — 있으면 비교 필드 검사, 다르면 멈춤
- `Nats-Msg-Id` = `{주제}:{키}`, DB 커밋·다음 알림 발행 후 ack
- `max_deliver=5`, 소진 시 `ops_events` `QUEUE_DELIVERY_EXHAUSTED`
- SIGTERM → 처리 중 메시지 완료 후 종료
- `__init__.py`: `NatsQueue` 익스포트, `MemoryQueue` 유지

### 3-2. S3 원문 저장소 (`src/api_module/common/raw_store/`)

- `_store.py`: `S3RawStore` 구현 — `RAW_STORE_DSN = s3://<버킷>[/<접두>]`
- 없으면 운영 진입점 `SystemExit` (로컬 대체 없음)
- 조건부 쓰기 `If-None-Match` — 같은 키 있으면 `FileExistsError`
- `_fetched_ms` 밀리초 타임스탬프로 키 충돌 해소 (HTTP 호출층이 붙임)
- `get_meta`, `get_body`, `list_keys` 구현

### 3-3. queue-v2 계약 (`contracts/queue/queue-v2.json`)

- `interp.done.error_p95`: `["number", "null"]` (기존 v1: `"number"`)
- 발행자·소비자·계약 검사 5종 이미지 동시 전환

### 3-4. 조위 어댑터 (`src/api_module/collector/adapters/tide/_adapter.py`)

- 페이지 루프 제거 → `min=5`·`numOfRows=300`·`reqDate` 1회
- KST `[00:00, 00:30)` 이면 `reqDate=어제` 1회 추가, tag `{관측소}_y`
- 어제분은 보충 원문 — `obs.loaded`·`adapter_health` 갱신 없음

### 3-5. UUID v5 결정적 실행 ID

- `interpolation/main.py`: `run_id` = UUID v5(이름 = `load_id`+`metric`)
- `grading/main.py`: `grade_run_id` = UUID v5(이름 = 입력 주제+입력 키)
- 재전달 시 동일 ID → `interpolation_runs` 고유 제약 충돌 없이 멱등 처리

### 3-6. 신규 테스트 (17개)

- `tests/unit/test_queue_v2_contract.py`: queue-v2 계약 검사
- `tests/unit/test_tide_adapter.py`: 조위 어댑터 단위 검사
- 기타 단위 검사 확충 (`test_classifier`, `test_wiring`, `test_raw_store_guard` 등)

---

## 4. 이 세션의 수정 — DB 테스트 실패 25건 복원

피어 세션 구현 후 다음 3가지 원인으로 25건 실패. 모두 이 세션에서 수정.

### 4-1. 계약 버전 불일치 (24건)

| 파일 | 수정 내용 |
|---|---|
| `tests/db/test_pipeline_chain.py` | 페이로드 `"schema": "queue-v1"` → `"queue-v2"` (line 73, 202), `queue-v1.json` → `queue-v2.json` (line 92, 265) |
| `tests/db/test_risk_index_chain.py` | 페이로드 내 모든 `"queue-v1"` → `"queue-v2"` |
| `tests/db/test_completeness_e2e.py` | `_CONTRACT` 로딩 `queue-v1.json` → `queue-v2.json` (line 23) |

원인: `accept_message()`가 `"schema": "queue-v2"` 를 요구하도록 바뀌었으나 테스트 픽스처는 `queue-v1` 그대로.

### 4-2. NatsQueue.from_env() SystemExit (1건)

**파일**: `tests/db/test_seed_wiring.py`

`test_seeded_db_starts`에서 `gr.main([])`·`ev.main(["evaluate"])`가 내부적으로 `NatsQueue.from_env()`를 호출 → `QUEUE_DSN` 없음 → `SystemExit`.

**수정**: `_FakeNats` 클래스 추가 + `monkeypatch.setattr(cq, "NatsQueue", _FakeNats)`:

```python
class _FakeNats:
    @classmethod
    def from_env(cls, **kwargs):
        return cls()
    def run(self, handler):
        pass

monkeypatch.setattr(cq, "NatsQueue", _FakeNats)
```

### 4-3. FileExistsError — 원문 키 충돌 (1건 원인, `test_fishery_watch_second_run_skips_full_fetch`)

**근본 원인**: `_ok()` 픽스처 함수에 `_fetched_ms`가 없어 두 `_run("fishery-watch")` 호출이 같은 `fetched_at`에서 동일 밀리초 키(`1789862400000_watch_2025.json`)를 생성 → 두 번째 쓰기에서 `FileExistsError`.

**수정**: `tests/db/test_collector_e2e.py`의 `_ok()` 함수에 `_fetched_ms` 추가:

```python
import time

def _ok(body: str) -> dict:
    # _fetched_ms는 실제 fetch()가 붙이는 밀리초 타임스탬프 — 같은 초라도 키가 겹치지 않게
    return {"url": "https://example.invalid/", "params": {"key": "***"}, "http_status": 200,
            "final_url": None, "fetched_at": "2026-09-20T00:00:00",
            "_fetched_ms": time.time_ns() // 1_000_000,
            "body": body, "error": None}
```

두 호출 사이에 충분한 Python 함수 호출이 있어 `time.time_ns()`가 항상 다른 값을 반환.

---

## 5. 테스트 결과

| 항목 | 기준선 | I-18 후 |
|---|---|---|
| passed | 666 | **683** (+17) |
| skipped | 14 | **14** |
| failed | 0 | **0** |
| 게이트 (`run_gate.py`) | 통과 | 통과 |
| `scan_keys.py` | 0건 | 0건 |

---

## 6. 변경 파일 목록

### 신규 (`??`)

| 파일 | 내용 |
|---|---|
| `contracts/queue/queue-v2.json` | queue-v2 메시지 계약 (`error_p95` nullable) |
| `src/api_module/common/queue/_nats.py` | NATS JetStream 큐 구현 |
| `tests/unit/test_queue_v2_contract.py` | queue-v2 계약 단위 검사 |
| `tests/unit/test_tide_adapter.py` | 조위 어댑터 단위 검사 |

### 수정 (`M`) — 구현 (피어 세션)

```
src/api_module/collector/_completeness.py
src/api_module/collector/adapters/bulletin/_adapter.py
src/api_module/collector/adapters/fishery/_adapter.py
src/api_module/collector/adapters/line/_adapter.py
src/api_module/collector/adapters/tide/_adapter.py      ← 조위 한 페이지
src/api_module/collector/fishery_watch.py
src/api_module/common/classifier/_parser.py
src/api_module/common/contract_check/_message.py       ← queue-v2 버전 검사
src/api_module/common/http/_client.py                  ← _fetched_ms 추가
src/api_module/common/metrics/__init__.py
src/api_module/common/metrics/_metrics.py
src/api_module/common/queue/__init__.py                ← NatsQueue 익스포트
src/api_module/common/queue/_interface.py
src/api_module/common/raw_store/__init__.py
src/api_module/common/raw_store/_store.py              ← S3 구현 + 조건부 쓰기
src/api_module/evaluation/main.py                      ← NatsQueue 기동
src/api_module/flowtest/main.py
src/api_module/grading/main.py                         ← UUID v5 grade_run_id
src/api_module/interpolation/main.py                   ← UUID v5 run_id
src/api_module/processor/_load.py
src/api_module/processor/main.py
tests/unit/test_classifier.py
tests/unit/test_contract_messages.py
tests/unit/test_processor_main.py
tests/unit/test_raw_store_guard.py
tests/unit/test_wiring.py
```

### 수정 (`M`) — 이 세션 (DB 테스트 복원)

```
tests/db/test_collector_e2e.py    ← _fetched_ms 추가
tests/db/test_completeness_e2e.py ← queue-v2.json
tests/db/test_pipeline_chain.py   ← queue-v2 페이로드
tests/db/test_risk_index_chain.py ← queue-v2 페이로드
tests/db/test_seed_wiring.py      ← _FakeNats monkeypatch
```

### 기타

```
handoff/dashboard-deliver/dashboard_contract.md  ← tables-v3 계약 (개정 20 반영)
handoff/dashboard-deliver/sample_result_rows.json
handoff/dashboard-deliver/schema_pg.sql
handoff/dashboard-deliver/schema_my.sql (신규)
handoff/flowtest/README.md
pyproject.toml
docs/plan/risk_index/05_대시보드_추가확인_회신.md
```

---

## 7. 제안 커밋 메시지

```
feat(I-18): NATS JetStream 큐·S3 원문 저장소·queue-v2·조위 한 페이지, DB 테스트 복원

- NATS JetStream NatsQueue 구현(asyncio nats-py), 기동 시 스트림·컨슈머 멱등 생성
- S3 원문 저장소 구현, 조건부 쓰기(If-None-Match), _fetched_ms 밀리초 키
- queue-v2: interp.done.error_p95 nullable, 발행·소비·계약 검사 동시 전환
- 조위: min=5·numOfRows=300·reqDate 1회 한 페이지, 자정 경계 어제분 _y
- UUID v5 결정적 run_id·grade_run_id (재전달 안전)
- 컨슈머 진입점 NatsQueue 기동·SIGTERM 처리
- DB 테스트 25건 복원: queue-v1→v2 페이로드, _FakeNats, _fetched_ms

pytest: 683 passed · 14 skipped (기준선 666 → +17)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## 8. 계획서 반영 후보

| 항목 | 절 |
|---|---|
| `_fetched_ms`를 `common-core` skill ③-5에 명시 ("밀리초 타임스탬프는 호출층이 붙임") | 2.3절 |
| `_FakeNats` 패턴 — 단계 테스트가 `NatsQueue.from_env()`를 직접 부르지 않도록 진입점 설계 검토 | 2.1절 |
| 조위 어제분 `_y` tag: `load_id`가 `VARCHAR(64)` 안임을 실측 확인 (`processor/adapters/tide/` tag 형식 최대 길이 명시) | 1.2절 |

---

## 9. 인프라 요청 목록

이번 작업에서 새로 발생한 인프라 요청 없음. 기존 요청은 1006_logs.md 세션 (3) 6번 항목 참조.
