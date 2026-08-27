"""환경변수 + config.yaml 로딩. 앱 전역에서 settings / scoring_config 를 import 해 사용한다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/worker/core/config.py -> apps/worker
WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", WORKER_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 외부 API
    dart_api_key: str = ""
    ecos_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_is_mock: bool = False

    # 인프라
    database_url: str = ""
    redis_url: str = ""

    # LLM
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen2.5:1.5b-instruct"
    ollama_base_url: str = "http://localhost:11434"

    # 앱 정책
    max_watchlist_slots: int = 3
    snapshot_cache_ttl_seconds: int = 21600
    news_poll_interval_minutes: int = 10

    def missing_keys(self) -> list[str]:
        """비어 있는 필수 설정 목록. 헬스체크/기동 시 경고용."""
        required = {
            "DART_API_KEY": self.dart_api_key,
            "ECOS_API_KEY": self.ecos_api_key,
            "NAVER_CLIENT_ID": self.naver_client_id,
            "NAVER_CLIENT_SECRET": self.naver_client_secret,
            "KIS_APP_KEY": self.kis_app_key,
            "KIS_APP_SECRET": self.kis_app_secret,
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
        }
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_scoring_config() -> dict[str, Any]:
    with open(WORKER_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


settings = get_settings()
