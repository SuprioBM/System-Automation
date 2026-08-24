"""Central configuration.

All environment variables are loaded once here via pydantic-settings. Nothing
is required at import time (importing app.core.config must never crash a
process that doesn't need every integration) -- instead, `require()` and
`validate_settings()` fail loudly and specifically at the point a process
actually needs a given value, per the "fail clearly, never run half-broken"
rule.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_BASE_URL: str = "http://localhost:8000"

    # GitHub App
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_CLIENT_ID: str | None = None
    GITHUB_APP_CLIENT_SECRET: str | None = None
    GITHUB_PRIVATE_KEY: str | None = None
    GITHUB_WEBHOOK_SECRET: str | None = None
    GITHUB_OWNER: str | None = None
    GITHUB_TOKEN: str | None = None  # legacy PAT fallback only

    # Groq
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "qwen/qwen3.6-27b"

    # Embeddings
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Supabase
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_DB_URL: str | None = None

    # Redis
    REDIS_URL: str | None = None

    # Discord
    DISCORD_BOT_TOKEN: str | None = None
    DISCORD_RESUME_CHANNEL_ID: str | None = None
    DISCORD_LINKEDIN_CHANNEL_ID: str | None = None
    DISCORD_ERROR_CHANNEL_ID: str | None = None
    DISCORD_CALLBACK_SHARED_SECRET: str | None = None
    # Comma-separated Discord user IDs allowed to Resume/Cancel a failed
    # workflow. If unset, resume/cancel is allowed for anyone who can see
    # the error channel (logged loudly as unrestricted -- see §15).
    DISCORD_AUTHORIZED_USER_IDS: str | None = None

    # Failure recovery (checkpoint-based)
    NODE_MAX_RETRIES: int = 3

    # LinkedIn
    LINKEDIN_CLIENT_ID: str | None = None
    LINKEDIN_CLIENT_SECRET: str | None = None
    LINKEDIN_REDIRECT_URI: str | None = None
    LINKEDIN_ACCESS_TOKEN: str | None = None
    LINKEDIN_PERSON_URN: str | None = None

    # Pollinations
    POLLINATIONS_BASE_URL: str = "https://image.pollinations.ai"
    POLLINATIONS_API_TOKEN: str | None = None

    # Remote LaTeX compiler
    LATEX_COMPILER_PROVIDER: str = "ytotech"
    LATEX_COMPILER_URL: str = "https://latex.ytotech.com/builds/sync"
    LATEX_COMPILER_API_TOKEN: str | None = None

    # Portfolio
    PORTFOLIO_REVALIDATE_URL: str | None = None
    REVALIDATE_SECRET: str | None = None

    @property
    def discord_resume_channel_id(self) -> int:
        return _as_int("DISCORD_RESUME_CHANNEL_ID", self.DISCORD_RESUME_CHANNEL_ID)

    @property
    def discord_linkedin_channel_id(self) -> int:
        return _as_int("DISCORD_LINKEDIN_CHANNEL_ID", self.DISCORD_LINKEDIN_CHANNEL_ID)

    @property
    def discord_error_channel_id(self) -> int:
        return _as_int("DISCORD_ERROR_CHANNEL_ID", self.DISCORD_ERROR_CHANNEL_ID)

    @property
    def discord_authorized_user_ids(self) -> set[str]:
        if not self.DISCORD_AUTHORIZED_USER_IDS:
            return set()
        return {x.strip() for x in self.DISCORD_AUTHORIZED_USER_IDS.split(",") if x.strip()}


def _as_int(name: str, value: str | None) -> int:
    if not value:
        raise ConfigurationError(f"{name} is not set")
    try:
        return int(value)
    except ValueError as e:
        raise ConfigurationError(f"{name}={value!r} is not a valid integer") from e


settings = Settings()

# Named requirement sets for each process entrypoint. validate_settings() is
# called explicitly at startup of each process (API, worker, discord bot) --
# never implicitly at import time.
REQUIRED_FOR_API = [
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_WEBHOOK_SECRET",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "REDIS_URL",
]

REQUIRED_FOR_WORKER = REQUIRED_FOR_API + [
    "GROQ_API_KEY",
    "SUPABASE_DB_URL",
    "DISCORD_BOT_TOKEN",       # worker sends approval + failure notifications directly via REST
    "DISCORD_ERROR_CHANNEL_ID",
]

REQUIRED_FOR_DISCORD_BOT = [
    "DISCORD_BOT_TOKEN",
    "DISCORD_RESUME_CHANNEL_ID",
    "DISCORD_LINKEDIN_CHANNEL_ID",
    "DISCORD_ERROR_CHANNEL_ID",
    "DISCORD_CALLBACK_SHARED_SECRET",
    "APP_BASE_URL",
]


def validate_settings(required: list[str]) -> None:
    missing = [name for name in required if not getattr(settings, name, None)]
    if missing:
        raise ConfigurationError(
            "Missing required configuration: " + ", ".join(missing) +
            ". Set these in .env (see .env.example)."
        )


def require(name: str) -> str:
    """Fetch a single setting, raising ConfigurationError with a clear
    message if it's unset. Use this in adapters at the point of use rather
    than trusting Optional[str] silently."""
    value = getattr(settings, name, None)
    if not value:
        raise ConfigurationError(f"{name} is not set. Add it to .env (see .env.example).")
    return value
