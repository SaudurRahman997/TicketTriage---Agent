"""Environment configuration. Every limit here is enforced in agent.py / api.py."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Approximate USD per 1M tokens (input, output). ESTIMATES - verify against provider pricing pages.
PRICES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore", protected_namespaces=("settings_",))
    host: str = "127.0.0.1"
    port: int = 8000
    model_provider: str = "unconfigured"      # anthropic | gemini | unconfigured
    model_name: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    available_models: str = "anthropic:claude-haiku-4-5-20251001,gemini:gemini-2.5-flash,openai:gpt-4o-mini"
    max_steps: int = 6                         # default when a request gives none
    hard_max_steps: int = 12                   # ceiling even if a request asks for more
    max_tool_retries: int = 2                  # tool retries AND contract-repair attempts
    max_output_tokens: int = 512
    run_timeout_seconds: int = 40
    max_task_chars: int = 6000
    max_external_chars: int = 8000
    history_turns: int = 6
    history_chars: int = 24000
    max_sessions: int = 100
    max_response_bytes: int = 50000
    rate_limit_per_minute: int = 30
    max_concurrent_runs: int = 4
    max_daily_model_calls: int = 1500


settings = Settings()


def key_for(provider: str) -> str:
    return {"anthropic": settings.anthropic_api_key, "gemini": settings.gemini_api_key, "openai": settings.openai_api_key}.get(provider, "")


def model_options() -> list[dict]:
    out = []
    for item in settings.available_models.split(","):
        item = item.strip()
        if ":" not in item:
            continue
        provider, name = item.split(":", 1)
        out.append({"id": item, "provider": provider, "model": name, "configured": bool(key_for(provider))})
    return out


def default_model_id() -> str | None:
    if settings.model_provider != "unconfigured" and settings.model_name:
        return f"{settings.model_provider}:{settings.model_name}"
    for o in model_options():
        if o["configured"]:
            return o["id"]
    return None
