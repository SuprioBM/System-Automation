"""Standalone Discord gateway bot process: python -m app.services.discord_bot_runner
Long-running; receives button/message interactions and relays decisions to
POST /discord/approval on the API process (APP_BASE_URL)."""
from __future__ import annotations

from app.core.config import REQUIRED_FOR_DISCORD_BOT, settings, validate_settings
from app.services.discord_service import DiscordBot

if __name__ == "__main__":
    validate_settings(REQUIRED_FOR_DISCORD_BOT)
    DiscordBot(settings.DISCORD_BOT_TOKEN).start()
