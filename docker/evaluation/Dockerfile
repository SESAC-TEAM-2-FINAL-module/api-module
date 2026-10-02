# api-module/evaluation — 침묵 판정·axis_status·운영 조정 게이트 이미지 (계획서 2.0.2·2.1절)
# 공통 코드(common/) + evaluation/ + config/definitions.yaml 포함
# evaluation만 fixtures/synthetic/ 도 포함 — 운영 조정 게이트 판정 재생 픽스처 (2.0.6절)
FROM python:3.11-slim

WORKDIR /app

# 의존성 — 공통 (evaluation 추가 선택 의존성 없음, pyproject.toml 6.1절)
RUN pip install --no-cache-dir \
    "python-dotenv" \
    "PyYAML" \
    "httpx" \
    "tenacity" \
    "SQLAlchemy>=2.0" \
    "jsonschema" \
    "psycopg[binary]>=3.1"

# 공통 코드 (PYTHONPATH=/app/src/api_module 기준)
COPY src/api_module/common/ /app/src/api_module/common/

# 단계 전용 코드
COPY src/api_module/evaluation/ /app/src/api_module/evaluation/

# 판정 정의 — 이미지에 포함 (2.0.6절)
COPY config/definitions.yaml /app/config/definitions.yaml

# 운영 조정 게이트 픽스처 — 판정 재생용 합성 입력 (2.0.6절)
COPY fixtures/synthetic/ /app/fixtures/synthetic/

# 스키마 파일 — evaluation gate가 참조 (evaluation/_gate.py)
COPY contracts/config/operational.schema.json /app/contracts/config/operational.schema.json

ENV PYTHONPATH=/app/src/api_module
ENV DEFINITIONS_PATH=/app/config/definitions.yaml

# 운영 조정 — ConfigMap에서 주입 (OPERATIONAL_CONFIG_PATH)
# gate 명령: docker run ... evaluation python -m evaluation.main gate <cfg_path>
ENTRYPOINT ["python", "-m", "evaluation.main"]
