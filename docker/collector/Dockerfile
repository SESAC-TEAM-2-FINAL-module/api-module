# api-module/collector — 공공 API 수집 이미지 (계획서 2.0.2·2.1절)
# 공통 코드(common/) + collector/ + config/definitions.yaml 만 포함
# 운영 조정 값은 넣지 않는다 (2.0.6절)
FROM python:3.11-slim

WORKDIR /app

# 의존성 — 공통 + collector 선택 의존성 (pyproject.toml 6.1절)
RUN pip install --no-cache-dir \
    "python-dotenv" \
    "PyYAML" \
    "httpx[http2]" \
    "tenacity" \
    "psycopg[binary]>=3.1"

# 공통 코드 (PYTHONPATH=/app/src/api_module 기준 — common·<stage>가 최상위)
COPY src/api_module/common/ /app/src/api_module/common/

# 단계 전용 코드
COPY src/api_module/collector/ /app/src/api_module/collector/

# 판정 정의 — 이미지에 포함 (CI 게이트 ① 대조 대상, 2.0.6절)
COPY config/definitions.yaml /app/config/definitions.yaml

ENV PYTHONPATH=/app/src/api_module
ENV DEFINITIONS_PATH=/app/config/definitions.yaml

ENTRYPOINT ["python", "-m", "collector.main"]
