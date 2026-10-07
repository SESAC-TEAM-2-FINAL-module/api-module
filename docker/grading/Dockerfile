# api-module/grading — 출처 등급·발송 자격·farm_readings 적재 이미지 (계획서 2.0.2·2.1절)
# 공통 코드(common/) + grading/ + config/definitions.yaml 만 포함
FROM python:3.11-slim

WORKDIR /app

# 의존성 — 공통 (grading 추가 선택 의존성 없음, pyproject.toml 6.1절)
RUN pip install --no-cache-dir \
    "python-dotenv" \
    "PyYAML" \
    "httpx" \
    "tenacity" \
    "SQLAlchemy>=2.0" \
    "nats-py>=2.6" \
    "psycopg[binary]>=3.1"

# 공통 코드 (PYTHONPATH=/app/src/api_module 기준)
COPY src/api_module/common/ /app/src/api_module/common/

# 단계 전용 코드
COPY src/api_module/grading/ /app/src/api_module/grading/

# 판정 정의 — 이미지에 포함 (2.0.6절)
COPY config/definitions.yaml /app/config/definitions.yaml

# 큐 정의 — 스트림·컨슈머·Nats-Msg-Id 키 (2.2절, 개정 22). 기동 시 스트림·컨슈머를 이 정의로 멱등 생성
COPY contracts/queue/jetstream.json /app/contracts/queue/jetstream.json

ENV PYTHONPATH=/app/src/api_module
ENV DEFINITIONS_PATH=/app/config/definitions.yaml

ENTRYPOINT ["python", "-m", "grading.main"]
