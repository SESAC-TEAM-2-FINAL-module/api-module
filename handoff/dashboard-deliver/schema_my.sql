-- MySQL 8.0 DDL — 생성본 (tables.py에서 자동 생성, 직접 수정 금지)
-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (5.4절)
-- charset=utf8mb4 collate=utf8mb4_0900_ai_ci (NO PAD, 뒤 공백 구분)

CREATE TABLE adapter_health (
	adapter VARCHAR(64) NOT NULL, 
	last_success_utc DATETIME, 
	last_failure_utc DATETIME, 
	consecutive_failures INTEGER NOT NULL, 
	retry_recovered INTEGER NOT NULL, 
	CONSTRAINT pk_adapter_health PRIMARY KEY (adapter)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE area_aliases (
	alias_key VARCHAR(255) NOT NULL, 
	area_id VARCHAR(64) NOT NULL, 
	source VARCHAR(64), 
	CONSTRAINT pk_area_aliases PRIMARY KEY (alias_key)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE areas (
	area_id VARCHAR(64) NOT NULL, 
	name VARCHAR(255), 
	center_lat DOUBLE, 
	center_lng DOUBLE, 
	radius_km DOUBLE, 
	CONSTRAINT pk_areas PRIMARY KEY (area_id)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE axis_coverage (
	area_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	covered BOOL NOT NULL, 
	season_months JSON, 
	reason VARCHAR(255), 
	CONSTRAINT ck_axis_coverage_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE axis_status (
	farm_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	reason VARCHAR(255), 
	basis_utc DATETIME, 
	last_checked_utc DATETIME NOT NULL, 
	CONSTRAINT ck_axis_status_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll')), 
	CONSTRAINT ck_axis_status_state CHECK (state IN ('NORMAL', 'NORMAL_SILENCE', 'PUBLICATION_PENDING', 'NO_MATCH', 'ITEM_SUSPENDED', 'OUT_OF_COVERAGE', 'OUT_OF_SEASON', 'VALUE_FROZEN', 'STALE', 'SERVER_TIMEOUT', 'REQUEST_ERROR', 'PARSE_FAILURE', 'OUTAGE', 'FILTER_IGNORED', 'INTERPOLATION_STALE', 'GRADING_STALE', 'NOT_USABLE'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE bulletin_detail_areas (
	cod_news VARCHAR(64) NOT NULL, 
	seq INTEGER NOT NULL, 
	part_no INTEGER NOT NULL, 
	area_key VARCHAR(255) NOT NULL, 
	area_id VARCHAR(64)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE bulletin_details (
	cod_news VARCHAR(64) NOT NULL, 
	seq INTEGER NOT NULL, 
	nam_biology VARCHAR(255), 
	species_class VARCHAR(16), 
	txt_seas_raw VARCHAR(255), 
	txt_seas_key VARCHAR(255), 
	min_density DOUBLE, 
	max_density DOUBLE, 
	grade VARCHAR(16) NOT NULL, 
	CONSTRAINT ck_bulletin_details_species_class CHECK (species_class IN ('TARGET', 'NON_TARGET', 'MISSING')), 
	CONSTRAINT ck_bulletin_details_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE bulletins (
	cod_news VARCHAR(64) NOT NULL, 
	day_report DATE, 
	detail_count INTEGER, 
	grade VARCHAR(16), 
	raw_id BIGINT, 
	CONSTRAINT pk_bulletins PRIMARY KEY (cod_news), 
	CONSTRAINT ck_bulletins_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE completeness_checks (
	run_key VARCHAR(64) NOT NULL, 
	api VARCHAR(64) NOT NULL, 
	window_start DATE NOT NULL, 
	window_end DATE NOT NULL, 
	parts INTEGER NOT NULL, 
	single_count INTEGER, 
	split_sum INTEGER, 
	truncated_side VARCHAR(16), 
	status VARCHAR(32) NOT NULL, 
	reason VARCHAR(32), 
	checked_at_utc DATETIME NOT NULL, 
	CONSTRAINT pk_completeness_checks PRIMARY KEY (run_key, api), 
	CONSTRAINT ck_completeness_checks_status CHECK (status IN ('OK', 'INCOMPLETE', 'COMPARISON_RANGE_MISMATCH', 'INVALID')), 
	CONSTRAINT ck_completeness_checks_reason CHECK (reason IN ('PART_STATUS', 'FILTER_IGNORED', 'WINDOW_MISMATCH', 'RAW_MISSING')), 
	CONSTRAINT ck_completeness_checks_truncated_side CHECK (truncated_side IN ('SINGLE', 'SPLIT'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE farm_areas (
	farm_id VARCHAR(64) NOT NULL, 
	area_id VARCHAR(64), 
	distance_km DOUBLE, 
	rule VARCHAR(64) NOT NULL, 
	computed_at_utc DATETIME NOT NULL, 
	CONSTRAINT pk_farm_areas PRIMARY KEY (farm_id)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE farm_reading_history (
	farm_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	ts_utc DATETIME NOT NULL, 
	value DOUBLE, 
	lower DOUBLE, 
	upper DOUBLE, 
	unit VARCHAR(64), 
	derivation VARCHAR(16) NOT NULL, 
	provenance VARCHAR(16) NOT NULL, 
	none_reason VARCHAR(64), 
	validated_scope VARCHAR(64), 
	grade VARCHAR(16), 
	alertable BOOL NOT NULL, 
	source_ref VARCHAR(255), 
	distance_km DOUBLE, 
	observed_at_utc DATETIME, 
	computed_at_utc DATETIME NOT NULL, 
	CONSTRAINT ck_farm_reading_history_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll')), 
	CONSTRAINT ck_farm_reading_history_derivation CHECK (derivation IN ('COMPUTED', 'MEASURED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_reading_history_provenance CHECK (provenance IN ('NONE', 'OBSERVED', 'NEAREST', 'BASELINE', 'INTERPOLATED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_reading_history_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE farm_readings (
	farm_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	value DOUBLE, 
	lower DOUBLE, 
	upper DOUBLE, 
	unit VARCHAR(64), 
	derivation VARCHAR(16) NOT NULL, 
	provenance VARCHAR(16) NOT NULL, 
	none_reason VARCHAR(64), 
	validated_scope VARCHAR(64), 
	grade VARCHAR(16), 
	alertable BOOL NOT NULL, 
	source_ref VARCHAR(255), 
	distance_km DOUBLE, 
	observed_at_utc DATETIME, 
	computed_at_utc DATETIME NOT NULL, 
	CONSTRAINT ck_farm_readings_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll')), 
	CONSTRAINT ck_farm_readings_derivation CHECK (derivation IN ('COMPUTED', 'MEASURED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_readings_provenance CHECK (provenance IN ('NONE', 'OBSERVED', 'NEAREST', 'BASELINE', 'INTERPOLATED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_readings_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE ingest_runs (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	raw_id BIGINT NOT NULL, 
	parser_version VARCHAR(64) NOT NULL, 
	status VARCHAR(64) NOT NULL, 
	result_code VARCHAR(64), 
	total_count INTEGER, 
	item_count INTEGER, 
	format VARCHAR(64), 
	format_mismatch BOOL, 
	processed_at_utc DATETIME NOT NULL, 
	CONSTRAINT pk_ingest_runs PRIMARY KEY (id), 
	CONSTRAINT uq_ingest_runs_raw_id_pver UNIQUE (raw_id, parser_version)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE interpolation_error (
	station_set_key VARCHAR(255) NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	window_days INTEGER NOT NULL, 
	p95 DOUBLE, 
	mae DOUBLE, 
	n_samples INTEGER, 
	computed_on DATE NOT NULL
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE interpolation_runs (
	run_id VARCHAR(64) NOT NULL, 
	load_id VARCHAR(64) NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	method VARCHAR(64), 
	power_p DOUBLE, 
	n_neighbors INTEGER, 
	ref_time_utc DATETIME, 
	station_set_key VARCHAR(255), 
	error_p95 DOUBLE, 
	error_window_days INTEGER, 
	computed_at_utc DATETIME NOT NULL, 
	CONSTRAINT pk_interpolation_runs PRIMARY KEY (run_id), 
	CONSTRAINT uq_interp_runs_load_metric UNIQUE (load_id, metric)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE interpolation_weights (
	run_id VARCHAR(64) NOT NULL, 
	farm_id VARCHAR(64) NOT NULL, 
	station_id VARCHAR(64) NOT NULL, 
	distance_km DOUBLE, 
	weight DOUBLE
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE line_observations (
	station_id VARCHAR(64) NOT NULL, 
	observed_at_utc DATETIME NOT NULL, 
	depth_m DOUBLE NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	value DOUBLE, 
	missing_reason VARCHAR(64), 
	flags JSON, 
	cast_id VARCHAR(64), 
	cast_rule_version VARCHAR(64), 
	group_type VARCHAR(64), 
	raw_id BIGINT
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE observations (
	station_id VARCHAR(64) NOT NULL, 
	observed_at_utc DATETIME NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	value DOUBLE, 
	missing_reason VARCHAR(64), 
	flags JSON, 
	raw_id BIGINT
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE ops_events (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	event_type VARCHAR(64) NOT NULL, 
	api VARCHAR(64), 
	detail JSON, 
	occurred_at_utc DATETIME NOT NULL, 
	CONSTRAINT pk_ops_events PRIMARY KEY (id)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE publication_checks (
	raw_id BIGINT NOT NULL AUTO_INCREMENT, 
	axis VARCHAR(64) NOT NULL, 
	checked_at_utc DATETIME NOT NULL, 
	target_year INTEGER, 
	total_count INTEGER, 
	prev_total_count INTEGER, 
	delta INTEGER, 
	parse_status VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_publication_checks PRIMARY KEY (raw_id)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE raw_index (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	api VARCHAR(64) NOT NULL, 
	tag VARCHAR(64), 
	storage_key VARCHAR(255) NOT NULL, 
	fetched_at_utc DATETIME NOT NULL, 
	http_status INTEGER, 
	body_sha256 VARCHAR(64), 
	body_bytes BIGINT, 
	precheck_code VARCHAR(64), 
	CONSTRAINT pk_raw_index PRIMARY KEY (id), 
	CONSTRAINT uq_raw_index_storage_key UNIQUE (storage_key)
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE stations (
	id VARCHAR(64) NOT NULL, 
	source_api VARCHAR(64) NOT NULL, 
	name VARCHAR(255), 
	lat DOUBLE, 
	lng DOUBLE, 
	sea_area VARCHAR(255), 
	active BOOL NOT NULL, 
	CONSTRAINT pk_stations PRIMARY KEY (id), 
	CONSTRAINT ck_stations_source_api CHECK (source_api IN ('tide', 'bulletin', 'line', 'fishery'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE survey_observations (
	station_id VARCHAR(64) NOT NULL, 
	observed_at_utc DATETIME NOT NULL, 
	surveyed_on DATE NOT NULL, 
	layer VARCHAR(4) NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	value DOUBLE, 
	missing_reason VARCHAR(64), 
	flags JSON, 
	raw_id BIGINT, 
	CONSTRAINT ck_survey_observations_layer CHECK (layer IN ('S', 'B'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE unmapped_locations (
	area_key VARCHAR(255) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	raw_sample VARCHAR(255), 
	occurrence_count INTEGER NOT NULL, 
	first_seen_utc DATETIME NOT NULL, 
	last_seen_utc DATETIME NOT NULL, 
	resolved_at_utc DATETIME, 
	CONSTRAINT pk_unmapped_locations PRIMARY KEY (area_key), 
	CONSTRAINT ck_unmapped_locations_kind CHECK (kind IN ('PARSE_FAILED', 'OUT_OF_SCOPE'))
)
CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
