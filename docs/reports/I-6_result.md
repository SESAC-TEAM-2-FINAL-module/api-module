# I-6 (S7) 결과 보고서 — repository

**작성일**: 2026-09-29  
**지시서**: I-6 / S7 `repository`  
**참조 skill**: `repository` (commit: 9d67a2f 이후 신규)

---

## 1. 산출물

| 경로 | 내용 |
| --- | --- |
| `src/api_module/common/repository/tables.py` | SQLAlchemy 2.0 — 22개 테이블 모델 + CHECK 제약 상수 |
| `src/api_module/common/repository/base.py` | `AbstractRepository` — 각 단계 인터페이스 |
| `src/api_module/common/repository/sql.py` | `SqlRepository` 구현 + DDL 생성 함수 |
| `src/api_module/common/repository/dialect.py` | 방언 분기 유일 파일 — PG `ON CONFLICT` / MySQL `ON DUPLICATE KEY` |
| `src/api_module/common/repository/__init__.py` | 공개 API |
| `contracts/tables/schema_pg.sql` | PostgreSQL DDL 생성본 |
| `contracts/tables/schema_my.sql` | MySQL DDL 생성본 |
| `tests/db/conftest.py` | testcontainer 픽스처 (psycopg3 URL 자동 변환) |
| `tests/db/test_schema.py` | DDL 적용·스키마 일치·기동 검사 |
| `tests/db/test_upsert.py` | upsert 멱등성·콜레이션·ops_events 중복 허용 |
| `tests/db/test_counts.py` | S4·S6 픽스처 DB 적재 기대값 검증 |

---

## 2. 테스트 결과

| 스위트 | 결과 |
| --- | --- |
| `tests/db/` — 22개 (DB 연동) | **22 passed** |
| `tests/` (기존 단위) — 226개 | 224 passed, 2 skipped (회귀 없음) |

**testcontainer 환경**: PostgreSQL 16-alpine, psycopg3, Docker Desktop (Windows)

---

## 3. 구현 결정 사항

### 3-1. 중복 배치 dedup (`dialect.py`)
`ON CONFLICT DO UPDATE command cannot affect row a second time` — PostgreSQL은 같은 배치에 중복 충돌 키를 허용하지 않음. `upsert()` 진입 시 conflict_keys 기준으로 마지막 값을 남기는 dedup을 적용함.

### 3-2. 메타 필드 자동 제거 (`dialect.py`)
어댑터가 `_type` 같은 라우팅 메타 키를 rows에 포함시킬 수 있음. `upsert()` 진입 시 테이블 컬럼에 없는 키를 자동 제거하여 `Unconsumed column names` 오류 방지.

### 3-3. `insert_raw_index` — DO NOTHING 멱등성 (`sql.py`)
중복 `storage_key`로 `insert_raw_index` 재호출 시 기존 행을 유지하고 ID를 반환. `upsert(update_cols=[])` → `ON CONFLICT DO NOTHING`으로 구현.

### 3-4. testcontainer psycopg3 URL (`conftest.py`)
`PostgresContainer.get_connection_url()`이 `psycopg2://` URL을 반환하므로 `psycopg://`로 교체.

### 3-5. `TestStartupCheck` 스키마 격리 (`test_schema.py`)
URL 문자열 concatenation(`?options=...`) 방식이 psycopg3에서 인증 실패를 일으킴. `create_engine(url, connect_args={"options": "-csearch_path=..."})` 방식으로 변경.

---

## 4. 계획서 반영 후보 (*(제안)*)

- `12`(`NO_SERVICE`) 상태 처리 — 현재 결과 코드 표에 *(제안)* 표시 (3.2절)
- `KEY_ERROR`/`QUOTA`/`INCOMPLETE` 응답 상태 → 축 상태 대응 — *(제안)* (3.2·3.3절)

---

## 5. `<미결>` 확인

- `farm_reading_history` 보존 기간 — `<미결>` 유지 (11절)

---

## 6. 남은 한계

- **MySQL 방언 분기·DDL 생성본 실행 검증 안 됨** — DB가 확정(PostgreSQL)되어 MySQL 측은 DDL 파일 생성까지만 확인. DB 전환 시 MySQL testcontainer로 선택 검사 필요.
- `TEST_DATABASE_URL_ALT` 두-DB 비교 검사 — 미실행 (선택 항목, 7.4절)

---

## 7. 제작자 제안 추가사항

### 실제 DB 연결 테스트 방법 (testcontainer 미사용 시)

운영 DB나 로컬 PostgreSQL에 직접 연결해서 DB 테스트를 실행하려면:

1. `.env`에서 `TEST_DATABASE_URL` 주석을 풀고 실제 연결 문자열 입력:
   ```
   TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/dbname_test
   ```

2. 해당 DB에 테스트 전용 데이터베이스(`dbname_test`)를 미리 생성:
   ```sql
   CREATE DATABASE dbname_test;
   ```
   스키마는 테스트 시작 시 `metadata.create_all()`이 자동 적용하고, 종료 시 `drop_all()`로 정리함.

3. 테스트 실행:
   ```bash
   python -m pytest tests/db/ -v
   ```

> **주의**: testcontainer와 달리 `drop_all()` 후 테이블이 남지 않으므로, 공유 DB에서 실행하면 기존 테이블이 삭제됨. 반드시 테스트 전용 DB를 사용할 것.

두 DB 비교 검사(`TEST_DATABASE_URL_ALT`)를 사용하려면 `.env.example` 주석 참조.
