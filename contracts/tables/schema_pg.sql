-- PostgreSQL DDL — 생성본 (tables.py에서 자동 생성, 직접 수정 금지)
-- DB 소유 측이 적용한다. 마이그레이션 코드 없음 (5.4절)

CREATE TABLE adapter_health (
	adapter VARCHAR(64) NOT NULL, 
	last_success_utc TIMESTAMP WITHOUT TIME ZONE, 
	last_failure_utc TIMESTAMP WITHOUT TIME ZONE, 
	consecutive_failures INTEGER NOT NULL, 
	retry_recovered INTEGER NOT NULL, 
	CONSTRAINT pk_adapter_health PRIMARY KEY (adapter)
);

CREATE TABLE area_aliases (
	alias_key VARCHAR(255) NOT NULL, 
	area_id VARCHAR(64) NOT NULL, 
	source VARCHAR(64), 
	CONSTRAINT pk_area_aliases PRIMARY KEY (alias_key)
);

CREATE TABLE areas (
	area_id VARCHAR(64) NOT NULL, 
	name VARCHAR(255), 
	center_lat DOUBLE PRECISION, 
	center_lng DOUBLE PRECISION, 
	radius_km DOUBLE PRECISION, 
	CONSTRAINT pk_areas PRIMARY KEY (area_id)
);

CREATE TABLE axis_coverage (
	area_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	covered BOOLEAN NOT NULL, 
	season_months JSON, 
	reason VARCHAR(255), 
	CONSTRAINT ck_axis_coverage_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll', 'red_tide_risk'))
);

CREATE TABLE axis_status (
	farm_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	reason VARCHAR(255), 
	basis_utc TIMESTAMP WITHOUT TIME ZONE, 
	last_checked_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT ck_axis_status_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll', 'red_tide_risk')), 
	CONSTRAINT ck_axis_status_state CHECK (state IN ('NORMAL', 'NORMAL_SILENCE', 'PUBLICATION_PENDING', 'NO_MATCH', 'ITEM_SUSPENDED', 'OUT_OF_COVERAGE', 'OUT_OF_SEASON', 'VALUE_FROZEN', 'STALE', 'SERVER_TIMEOUT', 'REQUEST_ERROR', 'PARSE_FAILURE', 'OUTAGE', 'FILTER_IGNORED', 'INTERPOLATION_STALE', 'GRADING_STALE', 'NOT_USABLE'))
);

CREATE TABLE bulletin_detail_areas (
	cod_news VARCHAR(64) NOT NULL, 
	seq INTEGER NOT NULL, 
	part_no INTEGER NOT NULL, 
	area_key VARCHAR(255) NOT NULL, 
	area_id VARCHAR(64)
);

CREATE TABLE bulletin_details (
	cod_news VARCHAR(64) NOT NULL, 
	seq INTEGER NOT NULL, 
	nam_biology VARCHAR(255), 
	species_class VARCHAR(16), 
	txt_seas_raw VARCHAR(255), 
	txt_seas_key VARCHAR(255), 
	min_density DOUBLE PRECISION, 
	max_density DOUBLE PRECISION, 
	grade VARCHAR(16) NOT NULL, 
	CONSTRAINT ck_bulletin_details_species_class CHECK (species_class IN ('TARGET', 'NON_TARGET', 'MISSING')), 
	CONSTRAINT ck_bulletin_details_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
);

CREATE TABLE bulletins (
	cod_news VARCHAR(64) NOT NULL, 
	day_report DATE, 
	detail_count INTEGER, 
	grade VARCHAR(16), 
	raw_id BIGINT, 
	CONSTRAINT pk_bulletins PRIMARY KEY (cod_news), 
	CONSTRAINT ck_bulletins_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
);

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
	checked_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_completeness_checks PRIMARY KEY (run_key, api), 
	CONSTRAINT ck_completeness_checks_status CHECK (status IN ('OK', 'INCOMPLETE', 'COMPARISON_RANGE_MISMATCH', 'INVALID')), 
	CONSTRAINT ck_completeness_checks_reason CHECK (reason IN ('PART_STATUS', 'FILTER_IGNORED', 'WINDOW_MISMATCH', 'RAW_MISSING')), 
	CONSTRAINT ck_completeness_checks_truncated_side CHECK (truncated_side IN ('SINGLE', 'SPLIT'))
);

CREATE TABLE farm_areas (
	farm_id VARCHAR(64) NOT NULL, 
	area_id VARCHAR(64), 
	distance_km DOUBLE PRECISION, 
	rule VARCHAR(64) NOT NULL, 
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_farm_areas PRIMARY KEY (farm_id)
);

CREATE TABLE farm_reading_history (
	farm_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	ts_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	value DOUBLE PRECISION, 
	lower DOUBLE PRECISION, 
	upper DOUBLE PRECISION, 
	unit VARCHAR(64), 
	derivation VARCHAR(16) NOT NULL, 
	provenance VARCHAR(16) NOT NULL, 
	none_reason VARCHAR(64), 
	validated_scope VARCHAR(64), 
	grade VARCHAR(16), 
	alertable BOOLEAN NOT NULL, 
	source_ref VARCHAR(255), 
	distance_km DOUBLE PRECISION, 
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE, 
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT ck_farm_reading_history_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll', 'red_tide_risk')), 
	CONSTRAINT ck_farm_reading_history_derivation CHECK (derivation IN ('COMPUTED', 'MEASURED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_reading_history_provenance CHECK (provenance IN ('NONE', 'OBSERVED', 'NEAREST', 'BASELINE', 'INTERPOLATED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_reading_history_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
);

CREATE TABLE farm_readings (
	farm_id VARCHAR(64) NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	value DOUBLE PRECISION, 
	lower DOUBLE PRECISION, 
	upper DOUBLE PRECISION, 
	unit VARCHAR(64), 
	derivation VARCHAR(16) NOT NULL, 
	provenance VARCHAR(16) NOT NULL, 
	none_reason VARCHAR(64), 
	validated_scope VARCHAR(64), 
	grade VARCHAR(16), 
	alertable BOOLEAN NOT NULL, 
	source_ref VARCHAR(255), 
	distance_km DOUBLE PRECISION, 
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE, 
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT ck_farm_readings_axis CHECK (axis IN ('water_temp', 'salinity', 'tide_level', 'wind_speed', 'air_temp', 'red_tide', 'dissolved_oxygen', 'chlorophyll', 'red_tide_risk')), 
	CONSTRAINT ck_farm_readings_derivation CHECK (derivation IN ('COMPUTED', 'MEASURED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_readings_provenance CHECK (provenance IN ('NONE', 'OBSERVED', 'NEAREST', 'BASELINE', 'INTERPOLATED', 'OFFICIAL', 'SURVEY')), 
	CONSTRAINT ck_farm_readings_grade CHECK (grade IN ('NONE', 'PRE_ADVISORY', 'ADVISORY', 'WARNING', 'NOT_GRADED', 'UNKNOWN'))
);

CREATE TABLE ingest_runs (
	id BIGINT GENERATED BY DEFAULT AS IDENTITY, 
	raw_id BIGINT NOT NULL, 
	parser_version VARCHAR(64) NOT NULL, 
	status VARCHAR(64) NOT NULL, 
	result_code VARCHAR(64), 
	total_count INTEGER, 
	item_count INTEGER, 
	format VARCHAR(64), 
	format_mismatch BOOLEAN, 
	processed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_ingest_runs PRIMARY KEY (id), 
	CONSTRAINT uq_ingest_runs_raw_id_pver UNIQUE (raw_id, parser_version)
);

CREATE TABLE interpolation_error (
	station_set_key VARCHAR(255) NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	window_days INTEGER NOT NULL, 
	p95 DOUBLE PRECISION, 
	mae DOUBLE PRECISION, 
	n_samples INTEGER, 
	computed_on DATE NOT NULL
);

CREATE TABLE interpolation_runs (
	run_id VARCHAR(64) NOT NULL, 
	load_id VARCHAR(64) NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	method VARCHAR(64), 
	power_p DOUBLE PRECISION, 
	n_neighbors INTEGER, 
	ref_time_utc TIMESTAMP WITHOUT TIME ZONE, 
	station_set_key VARCHAR(255), 
	error_p95 DOUBLE PRECISION, 
	error_window_days INTEGER, 
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_interpolation_runs PRIMARY KEY (run_id), 
	CONSTRAINT uq_interp_runs_load_metric UNIQUE (load_id, metric)
);

CREATE TABLE interpolation_weights (
	run_id VARCHAR(64) NOT NULL, 
	farm_id VARCHAR(64) NOT NULL, 
	station_id VARCHAR(64) NOT NULL, 
	distance_km DOUBLE PRECISION, 
	weight DOUBLE PRECISION
);

CREATE TABLE line_observations (
	station_id VARCHAR(64) NOT NULL, 
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	depth_m DOUBLE PRECISION NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	value DOUBLE PRECISION, 
	missing_reason VARCHAR(64), 
	flags JSON, 
	cast_id VARCHAR(64), 
	cast_rule_version VARCHAR(64), 
	group_type VARCHAR(64), 
	raw_id BIGINT
);

CREATE TABLE observations (
	station_id VARCHAR(64) NOT NULL, 
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	value DOUBLE PRECISION, 
	missing_reason VARCHAR(64), 
	flags JSON, 
	raw_id BIGINT
);

CREATE TABLE ops_events (
	id BIGINT GENERATED BY DEFAULT AS IDENTITY, 
	event_type VARCHAR(64) NOT NULL, 
	api VARCHAR(64), 
	detail JSON, 
	occurred_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_ops_events PRIMARY KEY (id)
);

CREATE TABLE publication_checks (
	raw_id BIGSERIAL NOT NULL, 
	axis VARCHAR(64) NOT NULL, 
	checked_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	target_year INTEGER, 
	total_count INTEGER, 
	prev_total_count INTEGER, 
	delta INTEGER, 
	parse_status VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_publication_checks PRIMARY KEY (raw_id)
);

CREATE TABLE raw_index (
	id BIGINT GENERATED BY DEFAULT AS IDENTITY, 
	api VARCHAR(64) NOT NULL, 
	tag VARCHAR(64), 
	storage_key VARCHAR(255) NOT NULL, 
	fetched_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	http_status INTEGER, 
	body_sha256 VARCHAR(64), 
	body_bytes BIGINT, 
	precheck_code VARCHAR(64), 
	CONSTRAINT pk_raw_index PRIMARY KEY (id), 
	CONSTRAINT uq_raw_index_storage_key UNIQUE (storage_key)
);

CREATE TABLE risk_index_factors (
	farm_id VARCHAR(64) NOT NULL, 
	factor VARCHAR(64) NOT NULL, 
	input_axis VARCHAR(64) NOT NULL, 
	input_value DOUBLE PRECISION, 
	input_lower DOUBLE PRECISION, 
	input_upper DOUBLE PRECISION, 
	input_unit VARCHAR(64), 
	input_grade VARCHAR(16), 
	input_baseline DOUBLE PRECISION, 
	score DOUBLE PRECISION, 
	score_lower DOUBLE PRECISION, 
	score_upper DOUBLE PRECISION, 
	weight DOUBLE PRECISION NOT NULL, 
	contribution DOUBLE PRECISION NOT NULL, 
	ok BOOLEAN NOT NULL, 
	excluded_reason VARCHAR(64), 
	input_none_reason VARCHAR(64), 
	source_ref VARCHAR(255), 
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE, 
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT ck_risk_index_factors_factor CHECK (factor IN ('nearby_bulletin', 'water_temp_band', 'salinity_band', 'chlorophyll_level')), 
	CONSTRAINT ck_risk_index_factors_excluded_reason CHECK (excluded_reason IN ('NO_INPUT', 'INPUT_NONE', 'SENSOR_QUALITY', 'RULE_UNDECIDED'))
);

CREATE TABLE risk_index_levels (
	farm_id VARCHAR(64) NOT NULL, 
	level VARCHAR(64) NOT NULL, 
	level_at_lower VARCHAR(64) NOT NULL, 
	level_at_upper VARCHAR(64) NOT NULL, 
	level_straddle BOOLEAN NOT NULL, 
	computed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_risk_index_levels PRIMARY KEY (farm_id)
);

CREATE TABLE stations (
	id VARCHAR(64) NOT NULL, 
	source_api VARCHAR(64) NOT NULL, 
	name VARCHAR(255), 
	lat DOUBLE PRECISION, 
	lng DOUBLE PRECISION, 
	sea_area VARCHAR(255), 
	active BOOLEAN NOT NULL, 
	CONSTRAINT pk_stations PRIMARY KEY (id), 
	CONSTRAINT ck_stations_source_api CHECK (source_api IN ('tide', 'bulletin', 'line', 'fishery'))
);

CREATE TABLE survey_observations (
	station_id VARCHAR(64) NOT NULL, 
	observed_at_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	surveyed_on DATE NOT NULL, 
	layer VARCHAR(4) NOT NULL, 
	metric VARCHAR(64) NOT NULL, 
	value DOUBLE PRECISION, 
	missing_reason VARCHAR(64), 
	flags JSON, 
	raw_id BIGINT, 
	CONSTRAINT ck_survey_observations_layer CHECK (layer IN ('S', 'B'))
);

CREATE TABLE unmapped_locations (
	area_key VARCHAR(255) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	raw_sample VARCHAR(255), 
	occurrence_count INTEGER NOT NULL, 
	first_seen_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_seen_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	resolved_at_utc TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_unmapped_locations PRIMARY KEY (area_key), 
	CONSTRAINT ck_unmapped_locations_kind CHECK (kind IN ('PARSE_FAILED', 'OUT_OF_SCOPE'))
);
