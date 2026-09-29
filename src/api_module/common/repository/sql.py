"""
SQLAlchemy Core 구현 — 방언 무관 부분 (5.4절).
방언 분기(upsert, 대량 적재)는 dialect.py에만.
DDL 생성 함수도 여기에 둔다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Engine, func, inspect, select, text

from . import dialect as d
from . import tables as t
from .base import AbstractRepository


def _trunc_sec(dt: datetime) -> datetime:
    """초 단위 절삭 — 반올림 금지 (repository skill ⑤)."""
    return dt.replace(microsecond=0)


class SqlRepository(AbstractRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ── collector ────────────────────────────────────────────────────────────

    def insert_raw_index(self, row: dict) -> int:
        row = _prep(row)
        with self._engine.begin() as conn:
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
        with self._engine.begin() as conn:
            d.upsert(conn, t.ingest_runs, rows, ["raw_id", "parser_version"])

    def upsert_stations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.stations, rows, ["id"])

    def upsert_observations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            # PK는 고유 인덱스로만 정의 — upsert 충돌 키도 같은 컬럼
            d.upsert(conn, t.observations, rows,
                     ["station_id", "observed_at_utc", "metric"])

    def upsert_line_observations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.line_observations, rows,
                     ["station_id", "observed_at_utc", "depth_m", "metric"])

    def upsert_survey_observations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.survey_observations, rows,
                     ["station_id", "surveyed_on", "layer", "metric"])

    def upsert_bulletins(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.bulletins, rows, ["cod_news"])

    def upsert_bulletin_details(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.bulletin_details, rows, ["cod_news", "seq"])

    def upsert_bulletin_detail_areas(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.bulletin_detail_areas, rows,
                     ["cod_news", "seq", "part_no"])

    def upsert_unmapped_locations(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.unmapped_locations, rows, ["area_key"])

    def upsert_publication_checks(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.publication_checks, rows, ["raw_id"])

    def upsert_adapter_health(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.adapter_health, rows, ["adapter"])

    def insert_ops_events(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.insert_only(conn, t.ops_events, rows)

    # ── 시드 ─────────────────────────────────────────────────────────────────

    def upsert_areas(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.areas, rows, ["area_id"])

    def upsert_area_aliases(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.area_aliases, rows, ["alias_key"])

    def upsert_axis_coverage(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.axis_coverage, rows, ["area_id", "axis"])

    # ── interpolation ────────────────────────────────────────────────────────

    def upsert_interpolation_runs(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.interpolation_runs, rows, ["run_id"])

    def upsert_interpolation_weights(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.interpolation_weights, rows,
                     ["run_id", "farm_id", "station_id"])

    def upsert_interpolation_error(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.interpolation_error, rows,
                     ["station_set_key", "metric", "window_days", "computed_on"])

    # ── grading ──────────────────────────────────────────────────────────────

    def upsert_farm_readings(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.farm_readings, rows, ["farm_id", "axis"])

    def upsert_farm_reading_history(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.farm_reading_history, rows,
                     ["farm_id", "axis", "ts_utc"])

    # ── evaluation ───────────────────────────────────────────────────────────

    def upsert_axis_status(self, rows: list[dict]) -> None:
        rows = [_prep(r) for r in rows]
        with self._engine.begin() as conn:
            d.upsert(conn, t.axis_status, rows, ["farm_id", "axis"])

    # ── 읽기 ─────────────────────────────────────────────────────────────────

    def get_stations(self, source_api: str | None = None) -> list[dict]:
        with self._engine.connect() as conn:
            q = select(t.stations)
            if source_api is not None:
                q = q.where(t.stations.c.source_api == source_api)
            rows = conn.execute(q).mappings().all()
        return [dict(r) for r in rows]

    def get_farm_sites(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT farm_id, lat, lng, active, updated_at_utc FROM farm_sites WHERE active = TRUE")
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_survey_count(self, adapter: str, target_year: int) -> int | None:
        with self._engine.connect() as conn:
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
        with self._engine.connect() as conn:
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
        with self._engine.connect() as conn:
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
        with self._engine.connect() as conn:
            row = conn.execute(
                select(t.interpolation_error)
                .where(t.interpolation_error.c.station_set_key == station_set_key)
                .where(t.interpolation_error.c.metric == metric)
                .where(t.interpolation_error.c.window_days == window_days)
                .where(t.interpolation_error.c.computed_on == computed_on)
            ).mappings().first()
        return dict(row) if row else None

    def get_today_station_sets(self, metric: str, today: object) -> list[str]:
        with self._engine.connect() as conn:
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
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(t.observations).join(
                    sub,
                    (t.observations.c.station_id == sub.c.station_id)
                    & (t.observations.c.observed_at_utc == sub.c.max_at),
                ).where(t.observations.c.metric == metric)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_areas(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(t.areas)).mappings().all()
        return [dict(r) for r in rows]

    def get_area_aliases(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(t.area_aliases)).mappings().all()
        return [dict(r) for r in rows]

    def get_bulletins_in_window(self, ref_date: object, window_days: int) -> list[dict]:
        from datetime import timedelta
        cutoff = ref_date - timedelta(days=window_days)
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(t.bulletins)
                .where(t.bulletins.c.day_report >= cutoff)
                .where(t.bulletins.c.day_report <= ref_date)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_bulletin_details(self, cod_news_list: list[str]) -> list[dict]:
        if not cod_news_list:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(t.bulletin_details)
                .where(t.bulletin_details.c.cod_news.in_(cod_news_list))
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_bulletin_detail_areas(self, cod_news_list: list[str]) -> list[dict]:
        if not cod_news_list:
            return []
        with self._engine.connect() as conn:
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
        with self._engine.connect() as conn:
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
                func.max(t.survey_observations.c.surveyed_on).label("max_on"),
            )
            .where(t.survey_observations.c.metric == metric)
            .where(t.survey_observations.c.layer == layer)
            .where(t.survey_observations.c.missing_reason.is_(None))
            .where(t.survey_observations.c.value.isnot(None))
            .group_by(t.survey_observations.c.station_id)
            .subquery()
        )
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(t.survey_observations).join(
                    sub,
                    (t.survey_observations.c.station_id == sub.c.station_id)
                    & (t.survey_observations.c.surveyed_on == sub.c.max_on),
                )
                .where(t.survey_observations.c.metric == metric)
                .where(t.survey_observations.c.layer == layer)
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_interpolation_run(self, run_id: str) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(t.interpolation_runs).where(t.interpolation_runs.c.run_id == run_id)
            ).mappings().first()
        return dict(row) if row else None

    def get_interpolation_weights_by_run(self, run_id: str) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(t.interpolation_weights).where(
                    t.interpolation_weights.c.run_id == run_id
                )
            ).mappings().all()
        return [dict(r) for r in rows]

    # ── 기동 시 검사 ──────────────────────────────────────────────────────────

    def check_schema(self) -> None:
        """
        tables.py 모델과 실제 DB 스키마를 비교한다.
        테이블·컬럼이 없으면 SystemExit으로 기동을 멈추고 차이를 보고한다 (B4).
        """
        insp = inspect(self._engine)
        existing = set(insp.get_table_names())

        missing_tables: list[str] = []
        missing_cols: list[str] = []

        for table_name, table_obj in t.metadata.tables.items():
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
# DDL 생성 (contracts/tables/ 저장)
# ─────────────────────────────────────────────────────────────────────────────

_CONTRACTS_DIR = Path(__file__).parents[4] / "contracts" / "tables"


def generate_ddl_pg(out_path: Path | None = None) -> str:
    """PostgreSQL DDL 생성본을 반환하고 out_path에 저장한다."""
    from sqlalchemy.dialects.postgresql import dialect as PGDialect
    from sqlalchemy.schema import CreateTable, CreateIndex

    dialect = PGDialect()
    parts: list[str] = [
        "-- PostgreSQL DDL — 생성본 (tables.py에서 자동 생성, 직접 수정 금지)",
        "-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (5.4절)",
        "",
    ]
    for tbl in t.metadata.sorted_tables:
        ddl = str(CreateTable(tbl).compile(dialect=dialect)).strip()
        parts.append(ddl + ";")
        for idx in tbl.indexes:
            if not idx.unique:  # unique 인덱스는 CREATE TABLE에 포함됨
                idx_ddl = str(CreateIndex(idx).compile(dialect=dialect)).strip()
                parts.append(idx_ddl + ";")
        parts.append("")

    sql = "\n".join(parts)
    path = out_path or (_CONTRACTS_DIR / "schema_pg.sql")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")
    return sql


def generate_ddl_my(out_path: Path | None = None) -> str:
    """MySQL DDL 생성본을 반환하고 out_path에 저장한다."""
    from sqlalchemy.dialects.mysql import dialect as MyDialect
    from sqlalchemy.schema import CreateTable, CreateIndex

    dialect = MyDialect()
    parts: list[str] = [
        "-- MySQL 8.0 DDL — 생성본 (tables.py에서 자동 생성, 직접 수정 금지)",
        "-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (5.4절)",
        "-- charset=utf8mb4 collate=utf8mb4_0900_ai_ci (NO PAD, 뒤 공백 구분)",
        "",
    ]
    for tbl in t.metadata.sorted_tables:
        ddl = str(CreateTable(tbl).compile(dialect=dialect)).strip()
        # MySQL에 charset·collate 추가
        ddl = ddl.rstrip(";") + "\nCHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
        parts.append(ddl)
        for idx in tbl.indexes:
            if not idx.unique:
                idx_ddl = str(CreateIndex(idx).compile(dialect=dialect)).strip()
                parts.append(idx_ddl + ";")
        parts.append("")

    sql = "\n".join(parts)
    path = out_path or (_CONTRACTS_DIR / "schema_my.sql")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")
    return sql


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
