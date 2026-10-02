"""
SQLAlchemy Core 구현 — 방언 무관 부분 (5.4절).
방언 분기(upsert, 대량 적재)는 dialect.py에만.
DDL 생성 함수도 여기에 둔다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Connection, Engine, func, inspect, or_, select, text

from common.sources import base_api_of, regular_api_ids

from . import dialect as d
from . import tables as t
from .base import AbstractRepository


def _trunc_sec(dt: datetime) -> datetime:
    """초 단위 절삭 — 반올림 금지 (repository skill ⑤)."""
    return dt.replace(microsecond=0)


class SqlRepository(AbstractRepository):
    def __init__(self, engine: Engine, _conn: Connection | None = None) -> None:
        self._engine = engine
        self._conn = _conn   # transaction() 안에서만 채워진다

    # ── 트랜잭션 ─────────────────────────────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator["SqlRepository"]:
        """
        여러 쓰기를 한 트랜잭션으로 묶는다. 블록 안에서는 돌려받은 저장소만 쓴다.
        예외가 나면 블록 안의 쓰기가 모두 취소된다. 이미 트랜잭션 안이면 그대로 이어 쓴다
        """
        if self._conn is not None:
            yield self
            return
        with self._engine.begin() as conn:
            yield SqlRepository(self._engine, conn)

    @contextmanager
    def _begin(self) -> Iterator[Connection]:
        if self._conn is not None:
            yield self._conn
        else:
            with self._engine.begin() as conn:
                yield conn

    @contextmanager
    def _connect(self) -> Iterator[Connection]:
        if self._conn is not None:
            yield self._conn
        else:
            with self._engine.connect() as conn:
                yield conn

    # ── collector ────────────────────────────────────────────────────────────

    def insert_raw_index(self, row: dict) -> int:
        row = _prep(row)
        with self._begin() as conn:
            # 중복 storage_key면 기존 행을 유지 (DO NOTHING)
            d.upsert(conn, t.raw_index, [row], ["storage_key"], update_cols=[])
            result = conn.execute(
                select(t.raw_index.c.id).where(
                    t.raw_index.c.storage_key == row["storage_key"]
                )
            ).scalar_one()
        return result

    # ── processor ────────────────────────────────────────────────────────────

    def upsert_ingest_run(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.ingest_runs, rows, ["raw_id", "parser_version"])

    def upsert_stations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.stations, rows, ["id"])

    def upsert_observations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            # PK는 고유 인덱스로만 정의 — upsert 충돌 키도 같은 컬럼
            d.upsert(conn, t.observations, rows,
                     ["station_id", "observed_at_utc", "metric"])

    def upsert_line_observations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.line_observations, rows,
                     ["station_id", "observed_at_utc", "depth_m", "metric"])

    def upsert_survey_observations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.survey_observations, rows,
                     ["station_id", "observed_at_utc", "layer", "metric"])

    def upsert_bulletins(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.bulletins, rows, ["cod_news"])

    def upsert_bulletin_details(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.bulletin_details, rows, ["cod_news", "seq"])

    def upsert_bulletin_detail_areas(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.bulletin_detail_areas, rows,
                     ["cod_news", "seq", "part_no"])

    def upsert_unmapped_locations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.unmapped_locations, rows, ["area_key"])

    def upsert_publication_checks(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.publication_checks, rows, ["raw_id"])

    def upsert_adapter_health(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.adapter_health, rows, ["adapter"])

    def insert_ops_events(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.insert_only(conn, t.ops_events, rows)

    # ── 시드 ─────────────────────────────────────────────────────────────────

    def upsert_areas(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.areas, rows, ["area_id"])

    def upsert_area_aliases(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.area_aliases, rows, ["alias_key"])

    def upsert_axis_coverage(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.axis_coverage, rows, ["area_id", "axis"])

    # ── interpolation ────────────────────────────────────────────────────────

    def upsert_interpolation_runs(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.interpolation_runs, rows, ["run_id"])

    def upsert_interpolation_weights(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.interpolation_weights, rows,
                     ["run_id", "farm_id", "station_id"])

    def upsert_interpolation_error(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.interpolation_error, rows,
                     ["station_set_key", "metric", "window_days", "computed_on"])

    # ── grading ──────────────────────────────────────────────────────────────

    def upsert_farm_readings(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.farm_readings, rows, ["farm_id", "axis"])

    def upsert_farm_reading_history(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.farm_reading_history, rows,
                     ["farm_id", "axis", "ts_utc"])

    # ── 적조 위험도 지수 (4.10절, 개정 20) ──────────────────────────────────

    def upsert_risk_index_factors(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.risk_index_factors, rows, ["farm_id", "factor"])

    def upsert_risk_index_levels(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.risk_index_levels, rows, ["farm_id"])

    def delete_risk_index_factors_by_farm(self, farm_ids: list[str]) -> None:
        if not farm_ids:
            return
        with self._begin() as conn:
            conn.execute(
                t.risk_index_factors.delete().where(
                    t.risk_index_factors.c.farm_id.in_(farm_ids)
                )
            )

    def delete_risk_index_levels_by_farm(self, farm_ids: list[str]) -> None:
        if not farm_ids:
            return
        with self._begin() as conn:
            conn.execute(
                t.risk_index_levels.delete().where(
                    t.risk_index_levels.c.farm_id.in_(farm_ids)
                )
            )

    def get_farm_readings_for_risk_index(self, farm_id: str) -> list[dict]:
        axes = ("red_tide", "water_temp", "salinity", "chlorophyll")
        with self._connect() as conn:
            rows = conn.execute(
                select(t.farm_readings)
                .where(t.farm_readings.c.farm_id == farm_id)
                .where(t.farm_readings.c.axis.in_(axes))
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_obs_flags(
        self, station_id: str, observed_at_utc: object, metric: str
    ) -> object | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.observations.c.flags)
                .where(t.observations.c.station_id == station_id)
                .where(t.observations.c.observed_at_utc == observed_at_utc)
                .where(t.observations.c.metric == metric)
            ).first()
        return row[0] if row else None

    def get_survey_obs_flags(
        self, station_id: str, observed_at_utc: object, layer: str, metric: str
    ) -> object | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.survey_observations.c.flags)
                .where(t.survey_observations.c.station_id == station_id)
                .where(t.survey_observations.c.observed_at_utc == observed_at_utc)
                .where(t.survey_observations.c.layer == layer)
                .where(t.survey_observations.c.metric == metric)
            ).first()
        return row[0] if row else None

    # ── evaluation ───────────────────────────────────────────────────────────

    def upsert_axis_status(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.axis_status, rows, ["farm_id", "axis"])

    # ── 읽기 ─────────────────────────────────────────────────────────────────

    def get_stations(self, source_api: str | None = None) -> list[dict]:
        with self._connect() as conn:
            q = select(t.stations)
            if source_api is not None:
                q = q.where(t.stations.c.source_api == source_api)
            rows = conn.execute(q).mappings().all()
        return [dict(r) for r in rows]

    def get_farm_sites(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                text("SELECT farm_id, lat, lng, active, updated_at_utc FROM farm_sites WHERE active = TRUE")
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_survey_count(self, adapter: str, target_year: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.publication_checks.c.total_count)
                .where(t.publication_checks.c.axis == adapter)
                .where(t.publication_checks.c.target_year == target_year)
                .where(t.publication_checks.c.total_count.isnot(None))
                .order_by(t.publication_checks.c.checked_at_utc.desc())
                .limit(1)
            ).first()
        return row[0] if row else None

    def get_recent_observations(self, metric: str, ref_time: datetime, window_min: int) -> list[dict]:
        cutoff = ref_time - timedelta(minutes=window_min)
        with self._connect() as conn:
            rows = conn.execute(
                select(t.observations)
                .where(t.observations.c.metric == metric)
                .where(t.observations.c.observed_at_utc >= cutoff)
                .where(t.observations.c.observed_at_utc <= ref_time)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_observations_for_loocv(self, metric: str, window_days: int) -> list[dict]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now - timedelta(days=window_days)
        with self._connect() as conn:
            rows = conn.execute(
                select(t.observations)
                .where(t.observations.c.metric == metric)
                .where(t.observations.c.observed_at_utc >= cutoff)
                .where(t.observations.c.missing_reason.is_(None))
                .where(t.observations.c.value.isnot(None))
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_interpolation_error(
        self, station_set_key: str, metric: str, window_days: int, computed_on: object
    ) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.interpolation_error)
                .where(t.interpolation_error.c.station_set_key == station_set_key)
                .where(t.interpolation_error.c.metric == metric)
                .where(t.interpolation_error.c.window_days == window_days)
                .where(t.interpolation_error.c.computed_on == computed_on)
            ).mappings().first()
        return dict(row) if row else None

    def get_today_station_sets(self, metric: str, today: object) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                select(t.interpolation_runs.c.station_set_key)
                .where(t.interpolation_runs.c.metric == metric)
                .where(func.date(t.interpolation_runs.c.computed_at_utc) == today)
                .distinct()
            ).all()
        return [r[0] for r in rows]

    # ── grading 읽기 ─────────────────────────────────────────────────────────────

    def get_latest_observations_by_metric(self, metric: str) -> list[dict]:
        sub = (
            select(
                t.observations.c.station_id,
                func.max(t.observations.c.observed_at_utc).label("max_at"),
            )
            .where(t.observations.c.metric == metric)
            .group_by(t.observations.c.station_id)
            .subquery()
        )
        with self._connect() as conn:
            rows = conn.execute(
                select(t.observations).join(
                    sub,
                    (t.observations.c.station_id == sub.c.station_id)
                    & (t.observations.c.observed_at_utc == sub.c.max_at),
                ).where(t.observations.c.metric == metric)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_areas(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(select(t.areas)).mappings().all()
        return [dict(r) for r in rows]

    def get_area_aliases(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(select(t.area_aliases)).mappings().all()
        return [dict(r) for r in rows]

    def get_bulletins_in_window(self, ref_date: object, window_days: int) -> list[dict]:
        from datetime import timedelta
        cutoff = ref_date - timedelta(days=window_days)
        with self._connect() as conn:
            rows = conn.execute(
                select(t.bulletins)
                .where(t.bulletins.c.day_report >= cutoff)
                .where(t.bulletins.c.day_report <= ref_date)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_bulletin_details(self, cod_news_list: list[str]) -> list[dict]:
        if not cod_news_list:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                select(t.bulletin_details)
                .where(t.bulletin_details.c.cod_news.in_(cod_news_list))
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_bulletin_detail_areas(self, cod_news_list: list[str]) -> list[dict]:
        if not cod_news_list:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                select(t.bulletin_detail_areas)
                .where(t.bulletin_detail_areas.c.cod_news.in_(cod_news_list))
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_line_surface_obs(self, metric: str) -> list[dict]:
        sub = (
            select(
                t.line_observations.c.station_id,
                func.max(t.line_observations.c.observed_at_utc).label("max_at"),
            )
            .where(t.line_observations.c.metric == metric)
            .where(t.line_observations.c.depth_m == 0.0)
            .where(t.line_observations.c.missing_reason.is_(None))
            .where(t.line_observations.c.value.isnot(None))
            .group_by(t.line_observations.c.station_id)
            .subquery()
        )
        with self._connect() as conn:
            rows = conn.execute(
                select(t.line_observations).join(
                    sub,
                    (t.line_observations.c.station_id == sub.c.station_id)
                    & (t.line_observations.c.observed_at_utc == sub.c.max_at),
                )
                .where(t.line_observations.c.metric == metric)
                .where(t.line_observations.c.depth_m == 0.0)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_survey_obs(self, metric: str, layer: str) -> list[dict]:
        sub = (
            select(
                t.survey_observations.c.station_id,
                func.max(t.survey_observations.c.observed_at_utc).label("max_at"),
            )
            .where(t.survey_observations.c.metric == metric)
            .where(t.survey_observations.c.layer == layer)
            .where(t.survey_observations.c.missing_reason.is_(None))
            .where(t.survey_observations.c.value.isnot(None))
            .group_by(t.survey_observations.c.station_id)
            .subquery()
        )
        with self._connect() as conn:
            rows = conn.execute(
                select(t.survey_observations).join(
                    sub,
                    (t.survey_observations.c.station_id == sub.c.station_id)
                    & (t.survey_observations.c.observed_at_utc == sub.c.max_at),
                )
                .where(t.survey_observations.c.metric == metric)
                .where(t.survey_observations.c.layer == layer)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_interpolation_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.interpolation_runs).where(t.interpolation_runs.c.run_id == run_id)
            ).mappings().first()
        return dict(row) if row else None

    def get_interpolation_weights_by_run(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                select(t.interpolation_weights).where(
                    t.interpolation_weights.c.run_id == run_id
                )
            ).mappings().all()
        return [dict(r) for r in rows]

    # ── evaluation 읽기 ───────────────────────────────────────────────────────

    def get_farm_readings(self, farm_ids: list[str] | None = None) -> list[dict]:
        stmt = select(t.farm_readings)
        if farm_ids is not None:
            stmt = stmt.where(t.farm_readings.c.farm_id.in_(farm_ids))
        with self._connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_axis_coverage(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(select(t.axis_coverage)).mappings().all()
        return [dict(r) for r in rows]

    def get_adapter_health(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(select(t.adapter_health)).mappings().all()
        return [dict(r) for r in rows]

    def get_publication_checks(self, axis: str | None = None) -> list[dict]:
        stmt = select(t.publication_checks)
        if axis is not None:
            stmt = stmt.where(t.publication_checks.c.axis == axis)
        with self._connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_interpolation_ref_time(self, metric: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.interpolation_runs)
                .where(t.interpolation_runs.c.metric == metric)
                .order_by(t.interpolation_runs.c.ref_time_utc.desc())
                .limit(1)
            ).mappings().first()
        return dict(row) if row else None

    def get_latest_ingest_processed_at(self) -> object:
        # 산출 지연 기준 — 관측을 적재하는 정기 경로 원문만 (분할 합산 제외, 4.9절 개정 17)
        with self._connect() as conn:
            val = conn.execute(
                select(func.max(t.ingest_runs.c.processed_at_utc))
                .join(t.raw_index, t.ingest_runs.c.raw_id == t.raw_index.c.id)
                .where(t.raw_index.c.api.in_(regular_api_ids()))
            ).scalar()
        return val

    def get_axis_status(self, farm_ids: list[str] | None = None) -> list[dict]:
        stmt = select(t.axis_status)
        if farm_ids is not None:
            stmt = stmt.where(t.axis_status.c.farm_id.in_(farm_ids))
        with self._connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_ingest_result_by_adapter(self, adapter: str) -> dict | None:
        # adapter = 수집 원천(tide…), raw_index.api = api_id(dtRecent…, 변형 접미 포함) — 결정 D2
        # 정기 경로 api_id 명시 목록 — 분할 합산 원문은 축 상태로 번지지 않게 뺀다 (3.3절 개정 17)
        apis = regular_api_ids(adapter) if base_api_of(adapter) else [adapter]
        with self._connect() as conn:
            row = conn.execute(
                select(t.ingest_runs)
                .join(t.raw_index, t.ingest_runs.c.raw_id == t.raw_index.c.id)
                .where(t.raw_index.c.api.in_(apis))
                .order_by(t.ingest_runs.c.processed_at_utc.desc())
                .limit(1)
            ).mappings().first()
        return dict(row) if row else None

    # ── 기동 시 검사 ──────────────────────────────────────────────────────────

    def get_ingest_runs_for_raw(self, raw_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                select(t.ingest_runs).where(t.ingest_runs.c.raw_id == raw_id)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_unmapped_locations(self, area_keys: list[str]) -> list[dict]:
        if not area_keys:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                select(t.unmapped_locations).where(t.unmapped_locations.c.area_key.in_(area_keys))
            ).mappings().all()
        return [dict(r) for r in rows]

    def upsert_farm_areas(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.farm_areas, rows, ["farm_id"])

    def get_raw_index_range(self, id_from: int, id_to: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                select(t.raw_index)
                .where(t.raw_index.c.id >= id_from)
                .where(t.raw_index.c.id <= id_to)
                .order_by(t.raw_index.c.id)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_completeness_check(self, run_key: str, api: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                select(t.completeness_checks)
                .where(t.completeness_checks.c.run_key == run_key)
                .where(t.completeness_checks.c.api == api)
            ).mappings().first()
        return dict(row) if row else None

    def upsert_completeness_checks(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._begin() as conn:
            d.upsert(conn, t.completeness_checks, rows, ["run_key", "api"])

    def get_latest_completeness_checked(self) -> dict[str, object]:
        """원천별 최신 checked_at_utc — 지표 completeness_last_checked_timestamp (9절)"""
        with self._connect() as conn:
            rows = conn.execute(
                select(t.completeness_checks.c.api, func.max(t.completeness_checks.c.checked_at_utc))
                .group_by(t.completeness_checks.c.api)
            ).all()
        return {r[0]: r[1] for r in rows}

    def count_table_rows(self, table_name: str) -> int:
        tbl = t.metadata.tables[table_name]
        with self._connect() as conn:
            return conn.execute(select(func.count()).select_from(tbl)).scalar_one()

    def get_bulletin_detail_areas_in_window(self, window_days: int, ref_date: object) -> list[str]:
        from datetime import timedelta
        cutoff = ref_date - timedelta(days=window_days)
        with self._connect() as conn:
            rows = conn.execute(
                select(t.bulletin_detail_areas.c.area_id.distinct())
                .join(t.bulletins, t.bulletin_detail_areas.c.cod_news == t.bulletins.c.cod_news)
                .where(t.bulletin_detail_areas.c.area_id.isnot(None))
                .where(t.bulletins.c.day_report >= cutoff)
                .where(t.bulletins.c.day_report <= ref_date)
            ).scalars().all()
        return list(rows)

    def check_schema(self, include: tuple[str, ...] = ()) -> None:
        """
        tables.py 모델과 실제 DB 스키마를 비교한다.
        테이블·컬럼이 없으면 SystemExit으로 기동을 멈추고 차이를 보고한다 (B4).
        OPTIONAL_TABLES(쓰는 이미지만 요구하는 표)는 include에 있을 때만 검사한다 (5.3절)
        """
        insp = inspect(self._engine)
        existing = set(insp.get_table_names())

        missing_tables: list[str] = []
        missing_cols: list[str] = []

        for table_name, table_obj in t.metadata.tables.items():
            if table_name in t.OPTIONAL_TABLES and table_name not in include:
                continue
            if table_name not in existing:
                missing_tables.append(table_name)
                continue
            db_cols = {col["name"] for col in insp.get_columns(table_name)}
            for col in table_obj.columns:
                if col.name not in db_cols:
                    missing_cols.append(f"{table_name}.{col.name}")

        if missing_tables or missing_cols:
            lines: list[str] = ["DB 스키마 불일치 — 기동 멈춤:"]
            if missing_tables:
                lines.append(f"  없는 테이블: {', '.join(sorted(missing_tables))}")
            if missing_cols:
                lines.append(f"  없는 컬럼: {', '.join(sorted(missing_cols))}")
            raise SystemExit("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _prep(row: dict) -> dict:
    """datetime 값을 초 단위 절삭해 반환한다. 원본 dict는 수정하지 않는다."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = _trunc_sec(v)
        else:
            out[k] = v
    return out
