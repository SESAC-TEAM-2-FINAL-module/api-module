"""
SQLAlchemy 2.0 테이블 모델 — DDL 생성과 기동 시 검사의 기준 (5.3·5.4절)
방언 분기 없음 — dialect.py에만.

금지 목록 (3절·repository skill ③-2):
- ENUM → VARCHAR + CHECK
- 배열 → 자식 테이블
- JSONB 연산자 → JSON은 저장·통째 조회만
- RETURNING 의존 → 재조회
- 시각: DATETIME (초 단위 절삭은 앱 책임, _utc 접미)
- 식별자 64자 이하
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime,
    Double, Index, Integer, JSON, MetaData, String, Table,
    UniqueConstraint, Identity,
)

# MetaData 이름 규칙 — 64자 이하 보장 (MySQL 한계)
_CONV = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=_CONV)

# --- 허용값 상수 (CHECK 제약과 앱 코드가 같은 목록 공유) ---

SOURCE_API_VALS = ("tide", "bulletin", "line", "fishery")

AXIS_VALS = (
    "water_temp", "salinity", "tide_level", "wind_speed",
    "air_temp", "red_tide", "dissolved_oxygen", "chlorophyll",
)

DERIVATION_VALS = ("COMPUTED", "MEASURED", "OFFICIAL", "SURVEY")

PROVENANCE_VALS = ("NONE", "OBSERVED", "NEAREST", "INTERPOLATED", "OFFICIAL", "SURVEY")

GRADE_VALS = ("NONE", "PRE_ADVISORY", "ADVISORY", "WARNING", "NOT_GRADED", "UNKNOWN")

STATE_VALS = (
    "NORMAL", "NORMAL_SILENCE", "PUBLICATION_PENDING", "NO_MATCH",
    "ITEM_SUSPENDED", "OUT_OF_COVERAGE", "OUT_OF_SEASON", "VALUE_FROZEN",
    "STALE", "SERVER_TIMEOUT", "REQUEST_ERROR", "PARSE_FAILURE",
    "OUTAGE", "FILTER_IGNORED", "INTERPOLATION_STALE", "GRADING_STALE",
    "NOT_USABLE",
)

SPECIES_CLASS_VALS = ("TARGET", "NON_TARGET", "MISSING")
UNMAPPED_KIND_VALS = ("PARSE_FAILED", "OUT_OF_SCOPE")
LAYER_VALS = ("S", "B")


def _in(col: str, vals: tuple) -> str:
    """CHECK 제약 IN 절 SQL 문자열 생성."""
    quoted = ", ".join(f"'{v}'" for v in vals)
    return f"{col} IN ({quoted})"


# ─────────────────────────────────────────────────────────────────────────────
# 원문·수집 계층
# ─────────────────────────────────────────────────────────────────────────────

raw_index = Table(
    "raw_index", metadata,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("api", String(64), nullable=False),
    Column("tag", String(64), nullable=True),
    Column("storage_key", String(255), nullable=False),
    Column("fetched_at_utc", DateTime(), nullable=False),
    Column("http_status", Integer, nullable=True),
    Column("body_sha256", String(64), nullable=True),
    Column("body_bytes", BigInteger, nullable=True),
    Column("precheck_code", String(64), nullable=True),
    UniqueConstraint("storage_key", name="uq_raw_index_storage_key"),
)

ingest_runs = Table(
    "ingest_runs", metadata,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("raw_id", BigInteger, nullable=False),
    Column("parser_version", String(64), nullable=False),
    Column("status", String(64), nullable=False),
    Column("result_code", String(64), nullable=True),
    Column("total_count", Integer, nullable=True),
    Column("item_count", Integer, nullable=True),
    Column("format", String(64), nullable=True),
    Column("format_mismatch", Boolean, nullable=True),
    Column("processed_at_utc", DateTime(), nullable=False),
    # 재처리 시 파서 버전이 바뀜 — 같은 파서·원문의 중복은 행을 늘리지 않는다
    UniqueConstraint("raw_id", "parser_version", name="uq_ingest_runs_raw_id_pver"),
)

# ─────────────────────────────────────────────────────────────────────────────
# 관측소
# ─────────────────────────────────────────────────────────────────────────────

stations = Table(
    "stations", metadata,
    Column("id", String(64), primary_key=True),   # "source:code" 형식
    Column("source_api", String(64), nullable=False),
    Column("name", String(255), nullable=True),
    Column("lat", Double, nullable=True),
    Column("lng", Double, nullable=True),
    Column("sea_area", String(255), nullable=True),
    Column("active", Boolean, nullable=False, default=True),
    CheckConstraint(_in("source_api", SOURCE_API_VALS), name="source_api"),
)

# ─────────────────────────────────────────────────────────────────────────────
# 관측값
# ─────────────────────────────────────────────────────────────────────────────

observations = Table(
    "observations", metadata,
    Column("station_id", String(64), nullable=False),
    Column("observed_at_utc", DateTime(), nullable=False),
    Column("metric", String(64), nullable=False),
    Column("value", Double, nullable=True),
    Column("missing_reason", String(64), nullable=True),
    Column("flags", JSON, nullable=True),
    Column("raw_id", BigInteger, nullable=True),
)
# PK는 (station_id, observed_at_utc, metric) — 복합 PK
Index("pk_observations", observations.c.station_id,
      observations.c.observed_at_utc, observations.c.metric, unique=True)

line_observations = Table(
    "line_observations", metadata,
    Column("station_id", String(64), nullable=False),
    Column("observed_at_utc", DateTime(), nullable=False),
    Column("depth_m", Double, nullable=False),
    Column("metric", String(64), nullable=False),
    Column("value", Double, nullable=True),
    Column("missing_reason", String(64), nullable=True),
    Column("flags", JSON, nullable=True),
    Column("cast_id", String(64), nullable=True),
    Column("cast_rule_version", String(64), nullable=True),
    Column("group_type", String(64), nullable=True),
    Column("raw_id", BigInteger, nullable=True),
)
Index("pk_line_obs", line_observations.c.station_id,
      line_observations.c.observed_at_utc, line_observations.c.depth_m,
      line_observations.c.metric, unique=True)

survey_observations = Table(
    "survey_observations", metadata,
    Column("station_id", String(64), nullable=False),
    Column("surveyed_on", Date, nullable=False),
    Column("layer", String(4), nullable=False),
    Column("metric", String(64), nullable=False),
    Column("value", Double, nullable=True),
    Column("missing_reason", String(64), nullable=True),
    Column("raw_id", BigInteger, nullable=True),
    CheckConstraint(_in("layer", LAYER_VALS), name="layer"),
)
Index("pk_survey_obs", survey_observations.c.station_id,
      survey_observations.c.surveyed_on, survey_observations.c.layer,
      survey_observations.c.metric, unique=True)

# ─────────────────────────────────────────────────────────────────────────────
# 적조 속보
# ─────────────────────────────────────────────────────────────────────────────

bulletins = Table(
    "bulletins", metadata,
    Column("cod_news", String(64), primary_key=True),
    Column("day_report", Date, nullable=True),
    Column("detail_count", Integer, nullable=True),
    # item2 없는 속보에만 채움 — 나머지는 bulletin_details.grade
    Column("grade", String(16), nullable=True),
    Column("raw_id", BigInteger, nullable=True),
    CheckConstraint(_in("grade", GRADE_VALS), name="grade"),
)

bulletin_details = Table(
    "bulletin_details", metadata,
    Column("cod_news", String(64), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("nam_biology", String(255), nullable=True),
    Column("species_class", String(16), nullable=True),
    Column("txt_seas_raw", String(255), nullable=True),
    Column("txt_seas_key", String(255), nullable=True),
    Column("min_density", Double, nullable=True),
    Column("max_density", Double, nullable=True),
    Column("grade", String(16), nullable=False),
    CheckConstraint(_in("species_class", SPECIES_CLASS_VALS), name="species_class"),
    CheckConstraint(_in("grade", GRADE_VALS), name="grade"),
)
Index("pk_bulletin_details", bulletin_details.c.cod_news,
      bulletin_details.c.seq, unique=True)

bulletin_detail_areas = Table(
    "bulletin_detail_areas", metadata,
    Column("cod_news", String(64), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("part_no", Integer, nullable=False),
    Column("area_key", String(255), nullable=False),
    Column("area_id", String(64), nullable=True),
)
Index("pk_bda", bulletin_detail_areas.c.cod_news,
      bulletin_detail_areas.c.seq, bulletin_detail_areas.c.part_no, unique=True)

unmapped_locations = Table(
    "unmapped_locations", metadata,
    Column("area_key", String(255), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("raw_sample", String(255), nullable=True),
    Column("occurrence_count", Integer, nullable=False, default=0),
    Column("first_seen_utc", DateTime(), nullable=False),
    Column("last_seen_utc", DateTime(), nullable=False),
    Column("resolved_at_utc", DateTime(), nullable=True),
    CheckConstraint(_in("kind", UNMAPPED_KIND_VALS), name="kind"),
)

# ─────────────────────────────────────────────────────────────────────────────
# 게시 감시·지역·커버리지·별칭
# ─────────────────────────────────────────────────────────────────────────────

publication_checks = Table(
    "publication_checks", metadata,
    Column("raw_id", BigInteger, primary_key=True),
    Column("axis", String(64), nullable=False),
    Column("checked_at_utc", DateTime(), nullable=False),
    Column("target_year", Integer, nullable=True),
    Column("total_count", Integer, nullable=True),
    Column("prev_total_count", Integer, nullable=True),
    Column("delta", Integer, nullable=True),
    Column("parse_status", String(64), nullable=False),
)

areas = Table(
    "areas", metadata,
    Column("area_id", String(64), primary_key=True),
    Column("name", String(255), nullable=True),
    Column("center_lat", Double, nullable=True),
    Column("center_lng", Double, nullable=True),
    Column("radius_km", Double, nullable=True),
)

area_aliases = Table(
    "area_aliases", metadata,
    Column("alias_key", String(255), primary_key=True),
    Column("area_id", String(64), nullable=False),
    Column("source", String(64), nullable=True),
)

axis_coverage = Table(
    "axis_coverage", metadata,
    Column("area_id", String(64), nullable=False),
    Column("axis", String(64), nullable=False),
    Column("covered", Boolean, nullable=False),
    Column("season_months", JSON, nullable=True),
    Column("reason", String(255), nullable=True),
    CheckConstraint(_in("axis", AXIS_VALS), name="axis"),
)
Index("pk_axis_coverage", axis_coverage.c.area_id,
      axis_coverage.c.axis, unique=True)

# ─────────────────────────────────────────────────────────────────────────────
# 상태·이벤트
# ─────────────────────────────────────────────────────────────────────────────

adapter_health = Table(
    "adapter_health", metadata,
    Column("adapter", String(64), primary_key=True),
    Column("last_success_utc", DateTime(), nullable=True),
    Column("last_failure_utc", DateTime(), nullable=True),
    Column("consecutive_failures", Integer, nullable=False, default=0),
    Column("retry_recovered", Boolean, nullable=False, default=False),
)

ops_events = Table(
    "ops_events", metadata,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("event_type", String(64), nullable=False),
    Column("api", String(64), nullable=True),
    Column("detail", JSON, nullable=True),
    Column("occurred_at_utc", DateTime(), nullable=False),
    # 고유 키 없음 — 운영 이벤트 로그, 쌓이는 것이 정상
)

# ─────────────────────────────────────────────────────────────────────────────
# IDW 추정
# ─────────────────────────────────────────────────────────────────────────────

interpolation_runs = Table(
    "interpolation_runs", metadata,
    Column("run_id", String(64), primary_key=True),
    Column("load_id", String(64), nullable=False),
    Column("metric", String(64), nullable=False),
    Column("method", String(64), nullable=True),
    Column("power_p", Double, nullable=True),
    Column("n_neighbors", Integer, nullable=True),
    Column("ref_time_utc", DateTime(), nullable=True),
    Column("station_set_key", String(255), nullable=True),
    Column("error_p95", Double, nullable=True),
    Column("error_window_days", Integer, nullable=True),
    Column("computed_at_utc", DateTime(), nullable=False),
    # 적재 한 번·항목 하나에 IDW 한 번
    UniqueConstraint("load_id", "metric", name="uq_interp_runs_load_metric"),
)

interpolation_weights = Table(
    "interpolation_weights", metadata,
    Column("run_id", String(64), nullable=False),
    Column("farm_id", String(64), nullable=False),
    Column("station_id", String(64), nullable=False),
    Column("distance_km", Double, nullable=True),
    Column("weight", Double, nullable=True),
)
Index("pk_interp_weights", interpolation_weights.c.run_id,
      interpolation_weights.c.farm_id, interpolation_weights.c.station_id,
      unique=True)

interpolation_error = Table(
    "interpolation_error", metadata,
    Column("station_set_key", String(255), nullable=False),
    Column("metric", String(64), nullable=False),
    Column("window_days", Integer, nullable=False),
    Column("p95", Double, nullable=True),
    Column("mae", Double, nullable=True),
    Column("n_samples", Integer, nullable=True),
    Column("computed_on", Date, nullable=False),
)
Index("pk_interp_error", interpolation_error.c.station_set_key,
      interpolation_error.c.metric, interpolation_error.c.window_days,
      interpolation_error.c.computed_on, unique=True)

# ─────────────────────────────────────────────────────────────────────────────
# 결과 테이블 — 웹 서비스가 읽는 것 (5.5절)
# ─────────────────────────────────────────────────────────────────────────────

farm_readings = Table(
    "farm_readings", metadata,
    Column("farm_id", String(64), nullable=False),
    Column("axis", String(64), nullable=False),
    Column("value", Double, nullable=True),
    Column("lower", Double, nullable=True),
    Column("upper", Double, nullable=True),
    Column("unit", String(64), nullable=True),
    Column("derivation", String(16), nullable=False),
    Column("provenance", String(16), nullable=False),
    Column("none_reason", String(64), nullable=True),
    Column("validated_scope", String(64), nullable=True),
    Column("grade", String(16), nullable=True),         # 적조만
    Column("alertable", Boolean, nullable=False),
    Column("source_ref", String(255), nullable=True),
    Column("distance_km", Double, nullable=True),
    Column("observed_at_utc", DateTime(), nullable=True),
    Column("computed_at_utc", DateTime(), nullable=False),
    CheckConstraint(_in("axis", AXIS_VALS), name="axis"),
    CheckConstraint(_in("derivation", DERIVATION_VALS), name="derivation"),
    CheckConstraint(_in("provenance", PROVENANCE_VALS), name="provenance"),
    CheckConstraint(_in("grade", GRADE_VALS), name="grade"),
)
Index("pk_farm_readings", farm_readings.c.farm_id, farm_readings.c.axis, unique=True)

farm_reading_history = Table(
    "farm_reading_history", metadata,
    Column("farm_id", String(64), nullable=False),
    Column("axis", String(64), nullable=False),
    Column("ts_utc", DateTime(), nullable=False),
    Column("value", Double, nullable=True),
    Column("lower", Double, nullable=True),
    Column("upper", Double, nullable=True),
    Column("unit", String(64), nullable=True),
    Column("derivation", String(16), nullable=False),
    Column("provenance", String(16), nullable=False),
    Column("none_reason", String(64), nullable=True),
    Column("validated_scope", String(64), nullable=True),
    Column("grade", String(16), nullable=True),
    Column("alertable", Boolean, nullable=False),
    Column("source_ref", String(255), nullable=True),
    Column("distance_km", Double, nullable=True),
    Column("observed_at_utc", DateTime(), nullable=True),
    Column("computed_at_utc", DateTime(), nullable=False),
    CheckConstraint(_in("axis", AXIS_VALS), name="axis"),
    CheckConstraint(_in("derivation", DERIVATION_VALS), name="derivation"),
    CheckConstraint(_in("provenance", PROVENANCE_VALS), name="provenance"),
    CheckConstraint(_in("grade", GRADE_VALS), name="grade"),
)
Index("pk_farm_reading_history", farm_reading_history.c.farm_id,
      farm_reading_history.c.axis, farm_reading_history.c.ts_utc, unique=True)

axis_status = Table(
    "axis_status", metadata,
    Column("farm_id", String(64), nullable=False),
    Column("axis", String(64), nullable=False),
    Column("state", String(32), nullable=False),
    Column("reason", String(255), nullable=True),
    Column("basis_utc", DateTime(), nullable=True),
    Column("last_checked_utc", DateTime(), nullable=False),
    CheckConstraint(_in("axis", AXIS_VALS), name="axis"),
    CheckConstraint(_in("state", STATE_VALS), name="state"),
)
Index("pk_axis_status", axis_status.c.farm_id, axis_status.c.axis, unique=True)
