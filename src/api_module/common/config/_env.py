"""
.env 로딩 (값은 출력하지 않는다)
키 값 접근은 get_key()로만 — 인증키를 읽어 출력하지 않는다
"""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class EnvConfig:
    dtrecent_url: str
    nifs_url: str
    # 변수명만 보관 — 값은 get_key()로 그때그때 읽는다
    dtrecent_key_var: str = "DTRECENT_KEY"
    nifs_key_bulletin_var: str = "NIFS_KEY_BULLETIN"
    nifs_key_line_var: str = "NIFS_KEY_LINE"
    nifs_key_fishery_sea_var: str = "NIFS_KEY_FISHERY_SEA"
    database_url_var: str = "DATABASE_URL"

    def get_key(self, var_name: str) -> str:
        value = os.environ.get(var_name)
        if not value:
            raise RuntimeError(f"필수 환경변수 미설정: {var_name}")
        return value


def load_env_config() -> EnvConfig:
    missing = []
    url = os.environ.get("DTRECENT_URL", "")
    nifs_url = os.environ.get("NIFS_URL", "")
    if not url:
        missing.append("DTRECENT_URL")
    if not nifs_url:
        missing.append("NIFS_URL")
    if missing:
        raise RuntimeError(f"필수 URL 환경변수 미설정: {', '.join(missing)}")
    return EnvConfig(dtrecent_url=url, nifs_url=nifs_url)
