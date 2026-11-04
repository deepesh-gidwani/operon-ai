"""Central configuration. Secrets come from backend env vars only."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # loads backend/.env when present; env vars always win


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


MODEL_API_KEY: str = _clean(os.getenv("MODEL_API_KEY"))
MODEL_API_URL: str = _clean(os.getenv("MODEL_API_URL")) or "https://api.meta.ai/v1"
MODEL_NAME: str = _clean(os.getenv("MODEL_NAME")) or "muse-spark-1.3"
CORS_ORIGINS: list[str] = [
    o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5173").split(",") if o.strip()
]
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB") or "25")
LLM_TIMEOUT_S: float = float(os.getenv("LLM_TIMEOUT_S") or "120")
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES") or "2")
LLM_RETRY_BACKOFF_S: float = float(os.getenv("LLM_RETRY_BACKOFF_S") or "1.0")


def require_api_key() -> str:
    if not MODEL_API_KEY:
        raise RuntimeError(
            "MODEL_API_KEY is not configured. Set it in backend/.env (see .env.example)."
        )
    return MODEL_API_KEY
