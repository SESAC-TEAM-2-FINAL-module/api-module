# api-module

AquaSentinel API 모듈 — 공공 API 수집부터 판정 결과 DB 적재까지.

**범위**: 원문 보관 → 해석 → 정규화 → 품질 판정 → 적재 → IDW 추정 → 출처 등급 → 침묵 판정 → 결과 테이블  
**표시·발송**: 웹 서비스(대시보드) 소유. 이 모듈은 판정과 값을 적재한다.

## 시작하기

```bash
cp .env.example .env        # 키·URL·DB 연결 채우기
cp .env.sources.example .env.sources   # 검증 폴더 절대경로 채우기
pip install -e ".[test,db-postgres]"
python -m pytest tests/
```

## 구조

```
config/          판정 정의 (이미지 포함) · 운영 조정 초기값
src/api_module/  패키지 — common/ + 단계별 (collector/processor/interpolation/grading/evaluation)
docker/          이미지별 Dockerfile (5종)
contracts/       계약 — 큐·테이블·입력·설정 스키마·릴리스 알림
fixtures/        원문·가공·합성 픽스처
tests/           unit / replay / contract / pipeline / db
ci/              scan_keys.py · gate/expected.yaml
handoff/         인프라 인계물 (초기본)
docs/            plan/ · reports/ · SOURCES.md
```

## 계획서

`docs/plan/API모듈_제작계획서_20260927.md`
