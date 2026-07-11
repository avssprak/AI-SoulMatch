"""Central configuration, loaded from .env / environment variables."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = PROJECT_ROOT / "uploads"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'soulmatch.db').as_posix()}")

# Signs the persistent-login token (see soulmatch.auth.mint_session_token). If unset,
# a random key is generated for this process only — logins won't survive a server
# restart until a fixed SECRET_KEY is set in .env.
_env_secret_key = os.getenv("SECRET_KEY", "")
SECRET_KEY = _env_secret_key or secrets.token_hex(32)
SECRET_KEY_IS_EPHEMERAL = not _env_secret_key

# Blended pricing used to estimate AI-action cost for the Admin usage tile
# (see soulmatch.billing) — defaults match docs/AI-SoulMatch_Unit_Economics.xlsx.
LLM_PRICE_IN_USD_PER_MTOK = float(os.getenv("LLM_PRICE_IN_USD_PER_MTOK", "0.30"))
LLM_PRICE_OUT_USD_PER_MTOK = float(os.getenv("LLM_PRICE_OUT_USD_PER_MTOK", "2.50"))
USD_INR = float(os.getenv("USD_INR", "86"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# "local" — any OpenAI-compatible chat-completions server (LM Studio, Ollama, etc.)
# running on the same machine/network, e.g. http://localhost:1234/v1/chat/completions
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:1234/v1/chat/completions")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "google/gemma-3-1B-it-QAT")

# First-run admin account, auto-created if the users table is empty.
# CHANGE THE PASSWORD after first login, or set these in .env before first run.
BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "changeme123")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
