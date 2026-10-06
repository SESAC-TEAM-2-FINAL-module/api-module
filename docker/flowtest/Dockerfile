# api-module/flowtest — 전 파이프라인 시험 실행기 이미지 (계획서 2.1.1절, 개정 21)
# 단계: collector · processor · interpolation · grading · evaluation + 공통 코드
# 이 이미지는 CI / 매니페스트 / 이미지 알림 대상이 아니다 (2.1.1절 FT6·FT7 전용)
FROM python:3.11-slim

WORKDIR /app

# 의존성 — 전 단계 합집합 (pyproject.toml flowtest 그룹, 2.1.1절)
RUN pip install --no-cache-dir \
    "python-dotenv" \
    "PyYAML" \
    "httpx[http2]" \
    "tenacity" \
    "SQLAlchemy>=2.0" \
    "lxml" \
    "jsonschema" \
    "numpy" \
    "scipy" \
    "psycopg[binary]>=3.1"

# 공통 코드 (PYTHONPATH=/app/src/api_module 기준)
COPY src/api_module/common/ /app/src/api_module/common/

# 단계 전용 코드 (단계 간 import 금지 — flowtest만 예외, 2.1절)
COPY src/api_module/collector/  /app/src/api_module/collector/
COPY src/api_module/processor/  /app/src/api_module/processor/
COPY src/api_module/interpolation/ /app/src/api_module/interpolation/
COPY src/api_module/grading/    /app/src/api_module/grading/
COPY src/api_module/evaluation/ /app/src/api_module/evaluation/
COPY src/api_module/flowtest/   /app/src/api_module/flowtest/

# 판정 정의 — 이미지에 포함 (2.0.6절)
COPY config/definitions.yaml /app/config/definitions.yaml

# 적조 해역 시드 — processor/adapters/bulletin 별칭 정규화 (4.3절)
COPY seeds/ /app/seeds/

# 운영 조정 스키마 — 기동 시 검사용 계약 (값이 아니다, 2.0.6절)
# evaluation gate 합성 픽스처 대신 운영 조정 스키마만 복사 (flowtest는 gate 미실행)
COPY contracts/config/operational.schema.json /app/contracts/config/operational.schema.json

ENV PYTHONPATH=/app/src/api_module
ENV DEFINITIONS_PATH=/app/config/definitions.yaml

# 운영 조정 — ConfigMap에서 주입 (OPERATIONAL_CONFIG_PATH)
# DB 연결 — .env 또는 환경 변수 DATABASE_URL
# 원문 저장소 — RAW_STORE_PATH (collect 모드에서 원문 저장, replay 모드에서 원문 읽기)
ENTRYPOINT ["python", "-m", "flowtest.main"]
