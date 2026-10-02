"""
DB 접근 계층 추상 인터페이스 (5.4절).
각 단계는 이 인터페이스만 보고 구체 구현(SqlRepository)을 몰라도 된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


class AbstractRepository(ABC):
    # ── 트랜잭션 ─────────────────────────────────────────────────────────────

    @abstractmethod
    def transaction(self) -> AbstractContextManager["AbstractRepository"]:
        """여러 쓰기를 한 트랜잭션으로 묶는 컨텍스트 — 블록 안에서는 돌려받은 저장소만 쓴다."""

    # ── collector ────────────────────────────────────────────────────────────

    @abstractmethod
    def insert_raw_index(self, row: dict) -> int:
        """raw_index에 삽입 후 생성된 id를 반환한다 (재조회, RETURNING 미사용)."""

    # ── processor ────────────────────────────────────────────────────────────

    @abstractmethod
    def upsert_ingest_run(self, rows: list[dict]) -> None:
        """고유 (raw_id, parser_version) 기준 upsert."""

    @abstractmethod
    def upsert_stations(self, rows: list[dict]) -> None:
        """고유 id(source:code) 기준 upsert."""

    @abstractmethod
    def upsert_observations(self, rows: list[dict]) -> None:
        """고유 (station_id, observed_at_utc, metric) 기준 upsert."""

    @abstractmethod
    def upsert_line_observations(self, rows: list[dict]) -> None:
        """고유 (station_id, observed_at_utc, depth_m, metric) 기준 upsert."""

    @abstractmethod
    def upsert_survey_observations(self, rows: list[dict]) -> None:
        """고유 (station_id, observed_at_utc, layer, metric) 기준 upsert — 조사 시각이 키 (개정 14)."""

    @abstractmethod
    def upsert_bulletins(self, rows: list[dict]) -> None:
        """고유 cod_news 기준 upsert."""

    @abstractmethod
    def upsert_bulletin_details(self, rows: list[dict]) -> None:
        """고유 (cod_news, seq) 기준 upsert."""

    @abstractmethod
    def upsert_bulletin_detail_areas(self, rows: list[dict]) -> None:
        """고유 (cod_news, seq, part_no) 기준 upsert."""

    @abstractmethod
    def upsert_unmapped_locations(self, rows: list[dict]) -> None:
        """고유 area_key 기준 upsert — occurrence_count 누적."""

    @abstractmethod
    def upsert_publication_checks(self, rows: list[dict]) -> None:
        """고유 raw_id 기준 upsert."""

    @abstractmethod
    def upsert_adapter_health(self, rows: list[dict]) -> None:
        """고유 adapter 기준 upsert."""

    @abstractmethod
    def insert_ops_events(self, rows: list[dict]) -> None:
        """고유 키 없는 단순 INSERT — 운영 이벤트 로그."""

    # ── 시드 (areas·aliases·coverage) ────────────────────────────────────────

    @abstractmethod
    def upsert_areas(self, rows: list[dict]) -> None:
        """고유 area_id 기준 upsert."""

    @abstractmethod
    def upsert_area_aliases(self, rows: list[dict]) -> None:
        """고유 alias_key 기준 upsert."""

    @abstractmethod
    def upsert_axis_coverage(self, rows: list[dict]) -> None:
        """고유 (area_id, axis) 기준 upsert."""

    # ── interpolation ────────────────────────────────────────────────────────

    @abstractmethod
    def upsert_interpolation_runs(self, rows: list[dict]) -> None:
        """고유 run_id 기준 upsert (같은 load_id·metric은 고유 제약으로 막힘)."""

    @abstractmethod
    def upsert_interpolation_weights(self, rows: list[dict]) -> None:
        """고유 (run_id, farm_id, station_id) 기준 upsert."""

    @abstractmethod
    def upsert_interpolation_error(self, rows: list[dict]) -> None:
        """고유 (station_set_key, metric, window_days, computed_on) 기준 upsert."""

    # ── grading ──────────────────────────────────────────────────────────────

    @abstractmethod
    def upsert_farm_readings(self, rows: list[dict]) -> None:
        """고유 (farm_id, axis) 기준 upsert."""

    @abstractmethod
    def upsert_farm_reading_history(self, rows: list[dict]) -> None:
        """고유 (farm_id, axis, ts_utc) 기준 upsert."""

    # ── evaluation ───────────────────────────────────────────────────────────

    @abstractmethod
    def upsert_axis_status(self, rows: list[dict]) -> None:
        """고유 (farm_id, axis) 기준 upsert."""

    # ── 읽기 ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def get_stations(self, source_api: str | None = None) -> list[dict]:
        """stations 행 목록. source_api 지정 시 해당 원천만."""

    @abstractmethod
    def get_farm_sites(self) -> list[dict]:
        """farm_sites 행 목록 (웹 서비스 소유 테이블, 읽기만)."""

    @abstractmethod
    def get_latest_survey_count(self, adapter: str, target_year: int) -> int | None:
        """어장환경 이전 감시 건수 조회 — None이면 이력 없음."""

    @abstractmethod
    def get_recent_observations(self, metric: str, ref_time: object, window_min: int) -> list[dict]:
        """IDW 입력용 — [ref_time-window_min, ref_time] 안의 조위 관측 조회."""

    @abstractmethod
    def get_observations_for_loocv(self, metric: str, window_days: int) -> list[dict]:
        """LOOCV용 — 최근 window_days일 관측 (missing_reason 없음, value 있음)."""

    @abstractmethod
    def get_interpolation_error(
        self, station_set_key: str, metric: str, window_days: int, computed_on: object
    ) -> dict | None:
        """interpolation_error 캐시 조회 — 없으면 None."""

    @abstractmethod
    def get_today_station_sets(self, metric: str, today: object) -> list[str]:
        """오늘 interpolation_runs에 사용된 station_set_key 목록."""

    # ── grading 읽기 ─────────────────────────────────────────────────────────────

    @abstractmethod
    def get_latest_observations_by_metric(self, metric: str) -> list[dict]:
        """관측소별 최신 관측 — 발송 자격 판단·최근접 대응용 (missing_reason 포함)."""

    @abstractmethod
    def get_areas(self) -> list[dict]:
        """areas 시드 전체 — 적조 해역 중심·반경."""

    @abstractmethod
    def get_area_aliases(self) -> list[dict]:
        """area_aliases 전체 — 정규화 키 → area_id 매핑."""

    @abstractmethod
    def get_bulletins_in_window(self, ref_date: object, window_days: int) -> list[dict]:
        """day_report >= ref_date - window_days 속보 목록."""

    @abstractmethod
    def get_bulletin_details(self, cod_news_list: list[str]) -> list[dict]:
        """해당 속보의 세부 행 전체."""

    @abstractmethod
    def get_bulletin_detail_areas(self, cod_news_list: list[str]) -> list[dict]:
        """해당 속보의 지점별 해역 대응 전체."""

    @abstractmethod
    def get_latest_line_surface_obs(self, metric: str) -> list[dict]:
        """정선 표층(depth_m=0) 최신 유효값 — DO 대응용. missing_reason 없음, value 있음."""

    @abstractmethod
    def get_latest_survey_obs(self, metric: str, layer: str) -> list[dict]:
        """어장환경 조사 최신값 — 클로로필 대응용. missing_reason 없음, value 있음."""

    @abstractmethod
    def get_interpolation_run(self, run_id: str) -> dict | None:
        """grading이 수온 재계산에 쓰는 interpolation_runs 행 — 없으면 None."""

    @abstractmethod
    def get_interpolation_weights_by_run(self, run_id: str) -> list[dict]:
        """run_id에 속한 가중치 행 전체 — (farm_id, station_id, weight, distance_km)."""

    # ── evaluation 읽기 ───────────────────────────────────────────────────────

    @abstractmethod
    def get_farm_readings(self, farm_ids: list[str] | None = None) -> list[dict]:
        """farm_readings 현재값. farm_ids가 있으면 해당 양식장만, 없으면 전체."""

    @abstractmethod
    def get_axis_coverage(self) -> list[dict]:
        """axis_coverage 전체 — 커버리지·계절 선언."""

    @abstractmethod
    def get_adapter_health(self) -> list[dict]:
        """adapter_health 전체 — 어댑터별 마지막 성공·실패 시각."""

    @abstractmethod
    def get_publication_checks(self, axis: str | None = None) -> list[dict]:
        """publication_checks. axis가 있으면 해당 축만, 없으면 전체."""

    @abstractmethod
    def get_latest_interpolation_ref_time(self, metric: str) -> dict | None:
        """metric의 가장 최근 interpolation_runs 행 — ref_time_utc, computed_at_utc. 없으면 None."""

    @abstractmethod
    def get_latest_ingest_processed_at(self) -> object:
        """MAX(ingest_runs.processed_at_utc) — GRADING_STALE 기준. 행 없으면 None."""

    @abstractmethod
    def get_axis_status(self, farm_ids: list[str] | None = None) -> list[dict]:
        """axis_status 현재값. farm_ids가 있으면 해당 양식장만, 없으면 전체. basis_utc 비교용."""

    @abstractmethod
    def get_latest_ingest_result_by_adapter(self, adapter: str) -> dict | None:
        """수집 원천(adapter, 예: tide)의 가장 최근 ingest_runs 행 — raw_index.api가 그 원천의 api_id(변형 접미 포함)인 것. 없으면 None."""

    @abstractmethod
    def get_ingest_runs_for_raw(self, raw_id: int) -> list[dict]:
        """원문 하나(raw_index.id)의 ingest_runs 행 전부 — 중복 알림·재처리 판별용 (I-12)."""

    @abstractmethod
    def get_unmapped_locations(self, area_keys: list[str]) -> list[dict]:
        """검토 큐 행 — 횟수·처음 시각을 이어 쓰기 위해 읽는다 (4.3절, I-12)."""

    @abstractmethod
    def upsert_farm_areas(self, rows: list[dict]) -> None:
        """고유 farm_id 기준 upsert — 모듈이 정한 양식장 해역 (개정 15)."""

    @abstractmethod
    def get_raw_index_range(self, id_from: int, id_to: int) -> list[dict]:
        """raw_index.id가 [id_from, id_to]인 색인 행, id 순 — reprocess 범위 (2.1절, 개정 15)."""

    @abstractmethod
    def get_completeness_check(self, run_key: str, api: str) -> dict | None:
        """분할 합산 결과 한 행 (3.3절, 개정 17)."""

    @abstractmethod
    def upsert_completeness_checks(self, rows: list[dict]) -> None:
        """고유 (run_key, api) 기준 upsert."""

    @abstractmethod
    def get_latest_completeness_checked(self) -> dict[str, object]:
        """원천(api)별 최신 checked_at_utc."""

    # ── 기동 시 검사 ──────────────────────────────────────────────────────────

    @abstractmethod
    def check_schema(self, include: tuple[str, ...] = ()) -> None:
        """
        tables.py 모델과 실제 DB 스키마를 비교한다.
        테이블·컬럼이 다르면 SystemExit으로 기동을 멈추고 차이를 보고한다 (B4).
        """
