# API 인증키 안전 처리 — 원문 저장 패턴

작성 2026-09-23 · IDW 파이프라인 프로젝트 경험 기반

---

## 발견 경위

정선관측(sooList) 재수집 과정에서 `save_raw_response()`가
파싱된 records 목록을 저장하고 있었음을 확인.
저장 파일에 `header`가 없고 요청 URL에 `sdate`·`edate`·`key` 파라미터가 없어
**쿼리를 재현할 수 없는 상태**였음.

---

## 문제 — 구 패턴

```python
# ❌ 구 시그니처: url과 text를 문자열로 직접 받음
def save_raw_response(out_dir, tag, url: str, text: str) -> Path:
    content = {
        "url": url,       # NIFS_BASE만 — 쿼리 파라미터 없음
        "raw": text,      # json.dumps(records) — 파싱 결과, 원문 아님
    }
    fname.write_text(json.dumps(content, ...), ...)
    # 검증 없음

# 호출부
save_raw_response(RAW_DIR, tag, config.NIFS_BASE, json.dumps(records))
```

**결과물 파일**
```json
{
  "url": "https://nifs.go.kr/openapi/...",   ← sdate·edate·key 없음
  "raw": [{"gru_nam": "남해", ...}, ...]     ← header 없음, 재직렬화됨
}
```

**문제점 3가지**
| # | 문제 | 영향 |
|---|---|---|
| 1 | URL에 쿼리 파라미터 없음 | 어떤 기간·키로 호출했는지 재현 불가 |
| 2 | `resp.text` 대신 `json.dumps(records)` 저장 | 원문 아님, `header.resultCode` 없음 |
| 3 | 키 마스킹 로직 없음 | 문자열로 URL 전달 시 키 노출 위험 |

---

## 해결 — 신 패턴

### 1. 키 보관: `.env` + `.gitignore`

```
# .env (공유 금지)
NIFS_LINE_KEY=실제키값
NIFS_FISHERY_KEY=실제키값
KHOA_KEY=실제키값
```

```
# .gitignore
.env
```

```python
# 진입점 최상단
from dotenv import load_dotenv
load_dotenv()
```

### 2. URL 마스킹 함수

```python
def _mask_key(url: str) -> str:
    for k in [config.NIFS_FISHERY_KEY, config.NIFS_LINE_KEY, config.KHOA_KEY]:
        if k:
            url = url.replace(k, "***")
    return url
```

### 3. 신 `save_raw_response()` — resp 객체 직접 수신

```python
def save_raw_response(out_dir: Path, tag: str,
                      resp: requests.Response, params: dict) -> Path:
    # 파라미터 딕셔너리에서 키 마스킹
    safe_params = {
        k: ("***" if k in ("key", "serviceKey") else str(v))
        for k, v in params.items()
    }
    content = {
        "url":        _mask_key(resp.request.url),   # 전체 URL, 키 마스킹
        "params":     safe_params,                    # 키 마스킹된 파라미터
        "http_status": resp.status_code,
        "final_url":  _mask_key(str(resp.url)),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "body":       resp.text,   # ← 절단·재직렬화 금지. 원문 그대로
    }
    fname.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    # 저장 후 검증: header.resultCode 없으면 즉시 중단
    parsed_body = json.loads(content["body"])
    if "resultCode" not in parsed_body.get("header", {}):
        raise RuntimeError(f"원문 검증 실패: header.resultCode 없음 [{fname.name}]")
    return fname
```

### 4. 호출부 — `_get()`으로 resp 먼저 획득

```python
# ✅ 신 패턴
resp = _get(config.NIFS_BASE, params)                   # resp 객체 획득
if resp is not None:
    save_raw_response(RAW_DIR, tag, resp, params)        # 저장·검증
    records, status = _parse_nifs(resp, "line", "p1")   # 파싱은 그 다음
```

**결과물 파일**
```json
{
  "url": "https://nifs.go.kr/openapi/...&sdate=20250923&edate=20260923&key=***",
  "params": {"id": "sooList", "sdate": "20250923", "edate": "20260923", "key": "***"},
  "http_status": 200,
  "final_url": "...",
  "fetched_at": "2026-09-23T11:46:51",
  "body": "{\"header\":{\"resultCode\":\"00\",...},\"body\":{...}}"
}
```

---

## 신규 프로세스 적용 체크리스트

- [ ] 인증키는 `.env`에만, 코드에 하드코딩 없음
- [ ] `.env`가 `.gitignore`에 포함됨
- [ ] URL·로그에 `_mask_key()` 적용
- [ ] params dict 저장 시 `key`/`serviceKey` 필드 `***` 치환
- [ ] `save_raw_response()`가 `resp.text`를 그대로 저장 (`json.loads` 후 `dumps` 금지)
- [ ] 저장 후 `header.resultCode` 검증, 없으면 RuntimeError
- [ ] `_get()` → `save_raw_response()` → `_parse_nifs()` 순서 준수
