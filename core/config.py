"""
core/config.py
──────────────
Environment loading and feature-flag helpers.
All other modules import from here instead of calling load_dotenv() themselves.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY missing in .env")


def _env_flag(name: str, default: bool = False) -> bool:
    """Return a boolean value from an environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
