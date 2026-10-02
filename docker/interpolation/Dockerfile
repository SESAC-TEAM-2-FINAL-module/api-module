# api-module/interpolation — IDW 추정·오차 산출 이미지 (계획서 2.0.2·2.1절)
# 공통 코드(common/) + interpolation/ + config/definitions.yaml 만 포함
FROM python:3.11-slim

WORKDIR /app

# 의존성 — 공통 + interpolation 선택 의존성 (pyproject.toml 6.1절)
RUN pip install --no-cache-dir \
    "python-dotenv" \
    "PyYAML" \
    "httpx" \
    "tenacity" \
    "SQLAlchemy>=2.0" \
    "numpy" \
    "scipy" \
    "psycopg[binary]>=3.1"

# 공통 코드 (PYTHONPATH=/app/src/api_module 기준)
COPY src/api_module/common/ /app/src/api_module/common/

# 단계 전용 코드
COPY src/api_module/interpolation/ /app/src/api_module/interpolation/

# 판정 정의 — 이미지에 포함 (2.0.6절)
COPY config/definitions.yaml /app/config/definitions.yaml

ENV PYTHONPATH=/app/src/api_module
ENV DEFINITIONS_PATH=/app/config/definitions.yaml

ENTRYPOINT ["python", "-m", "interpolation.main"]
