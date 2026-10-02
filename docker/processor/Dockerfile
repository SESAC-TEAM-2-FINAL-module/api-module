# api-module/processor — 해석·정규화·품질 판정·적재 이미지 (계획서 2.0.2·2.1절)
# 공통 코드(common/) + processor/ + config/definitions.yaml + 운영 조정 스키마(contracts/config/operational.schema.json) + 적조 해역 시드(seeds/)만 포함
# 운영 조정은 ConfigMap에서 읽는다 (2.0.6절)
FROM python:3.11-slim

WORKDIR /app

# 의존성 — 공통 + processor 선택 의존성 (pyproject.toml 6.1절)
RUN pip install --no-cache-dir \
    "python-dotenv" \
    "PyYAML" \
    "httpx" \
    "tenacity" \
    "SQLAlchemy>=2.0" \
    "lxml" \
    "jsonschema" \
    "psycopg[binary]>=3.1"

# 공통 코드 (PYTHONPATH=/app/src/api_module 기준)
COPY src/api_module/common/ /app/src/api_module/common/

# 단계 전용 코드
COPY src/api_module/processor/ /app/src/api_module/processor/

# 판정 정의 — 이미지에 포함 (2.0.6절)
COPY config/definitions.yaml /app/config/definitions.yaml

# 적조 해역 시드 — 별칭 정규화에 쓴다(4.3절, 확정 2026-10-01). 경로 /app/seeds (processor/adapters/bulletin)
COPY seeds/ /app/seeds/

# 운영 조정 스키마 — 기동 시 검사용 계약 (값이 아니다, 2.0.6절)
COPY contracts/config/operational.schema.json /app/contracts/config/operational.schema.json

ENV PYTHONPATH=/app/src/api_module
ENV DEFINITIONS_PATH=/app/config/definitions.yaml

# 운영 조정 — ConfigMap에서 주입 (OPERATIONAL_CONFIG_PATH)
# 없거나 스키마와 다르면 기동 멈춤 (common/config/_operational.py, 2.0.6절)
ENTRYPOINT ["python", "-m", "processor.main"]
