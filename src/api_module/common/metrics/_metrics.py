"""운영 지표 (9절) — 사용자 화면에는 보내지 않는다"""
from __future__ import annotations
from collections import defaultdict


class Counter:
    def __init__(self, name: str, labelnames: list[str] | None = None) -> None:
        self.name = name
        self._values: dict[tuple, int] = defaultdict(int)

    def labels(self, **kwargs) -> "_CL":
        return _CL(self, tuple(sorted(kwargs.items())))

    def inc(self, n: int = 1) -> None:
        self._values[()] += n


class _CL:
    __slots__ = ("_c", "_k")

    def __init__(self, c: Counter, k: tuple) -> None:
        self._c, self._k = c, k

    def inc(self, n: int = 1) -> None:
        self._c._values[self._k] += n


class Gauge:
    def __init__(self, name: str, labelnames: list[str] | None = None) -> None:
        self.name = name
        self._values: dict[tuple, float] = {}

    def labels(self, **kwargs) -> "_GL":
        return _GL(self, tuple(sorted(kwargs.items())))

    def set(self, v: float) -> None:
        self._values[()] = v


class _GL:
    __slots__ = ("_g", "_k")

    def __init__(self, g: Gauge, k: tuple) -> None:
        self._g, self._k = g, k

    def set(self, v: float) -> None:
        self._g._values[self._k] = v


class Histogram:
    def __init__(self, name: str, labelnames: list[str] | None = None) -> None:
        self.name = name
        self._samples: dict[tuple, list] = defaultdict(list)

    def labels(self, **kwargs) -> "_HL":
        return _HL(self, tuple(sorted(kwargs.items())))

    def observe(self, v: float) -> None:
        self._samples[()].append(v)


class _HL:
    __slots__ = ("_h", "_k")

    def __init__(self, h: Histogram, k: tuple) -> None:
        self._h, self._k = h, k

    def observe(self, v: float) -> None:
        self._h._samples[self._k].append(v)


# 지표 인스턴스 (9절)
collector_calls_total = Counter("collector_calls_total", ["api", "status"])
collector_retry_total = Counter("collector_retry_total", ["api"])
collector_duration_seconds = Histogram("collector_duration_seconds", ["api"])
raw_bytes_total = Counter("raw_bytes_total", ["api"])
processor_parse_failure_total = Counter("processor_parse_failure_total", ["api", "parser_version"])
observation_latest_age_seconds = Gauge("observation_latest_age_seconds", ["station_id", "metric"])
observation_missing_ratio = Gauge("observation_missing_ratio", ["station_id", "metric"])
publication_check_total_count = Gauge("publication_check_total_count", ["axis", "year"])
completeness_mismatch_total = Counter("completeness_mismatch_total", ["api"])
pipeline_event_lag_seconds = Histogram("pipeline_event_lag_seconds", ["topic"])
interpolation_run_duration_seconds = Histogram("interpolation_run_duration_seconds")
interpolation_error_p95 = Gauge("interpolation_error_p95", ["metric", "station_set_key"])
interpolation_stations_used = Gauge("interpolation_stations_used", ["farm_id"])
evaluation_state_total = Gauge("evaluation_state_total", ["axis", "state"])
operational_config_info = Gauge("operational_config_info", ["image", "hash", "schema"])
