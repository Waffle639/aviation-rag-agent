"""Chat UI configuration."""

from __future__ import annotations

import os


APP_TITLE = os.getenv("CHAT_APP_TITLE", "Aviation Assistant")
APP_TAGLINE = os.getenv("CHAT_APP_TAGLINE", "Evidence-first copilot for manuals and accident records")
PAGE_ICON = os.getenv("CHAT_PAGE_ICON", "A")
DEFAULT_SESSION_LIMIT = int(os.getenv("CHAT_SESSION_LIMIT", "80"))
