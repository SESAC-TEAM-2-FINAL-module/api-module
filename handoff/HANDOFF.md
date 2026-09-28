# HANDOFF.md — 인프라 인계 내역 (계획서 2.0.4절)

I-11 완료 후 작성. 현재 초판 자리 표시.

## 인계 항목 (I-11에서 채움)

- 워크로드 목록과 역할
- 필요한 환경변수와 비밀 (키 이름만)
- 외부 egress 대상
- 객체 저장소·큐·DB 접속 요구
- 양식장 좌표 읽기 권한
- 워크로드 설정 권장값과 근거
- 운영 조정 ConfigMap 소유·변경 절차·게이트 명령
- 기동 시 검사 항목
- 운영 지표 목록
- 이미지 목록과 이미지 알림 형식

## 워크로드 설정 권장값 (인계 전 채움)

| 워크로드 | 권장 주기 | 근거 |
|---|---|---|
| collector-tide | 10분 | 계획서 1.1절 |
| collector-bulletin | 1시간 (비시즌 6시간) | 계획서 1.1절 — 계절은 axis_coverage.season_months |
| collector-line | 1일 | 계획서 1.1절 |
| collector-fishery-watch | 주 1회 | 계획서 1.1절 |
| collector-completeness | 주 1회 | 계획서 2.1절 |
| evaluation-sweep | 10분 | 계획서 2.1절 *(제안)* |
| interpolation-error | 1일 | 계획서 2.1절 *(제안)* |
