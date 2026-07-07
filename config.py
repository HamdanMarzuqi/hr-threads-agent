"""
config.py — Konfigurasi terpusat untuk HR Threads Agent.
Membaca semua environment variables dari file .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ── AI Provider ──────────────────────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()  # "gemini" atau "claude"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")

# ── Web Search ───────────────────────────────────────────────────────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

# ── Threads (Meta) ───────────────────────────────────────────────────────────
THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "")

# ── Jadwal Upload ────────────────────────────────────────────────────────────
UPLOAD_TIME = os.getenv("UPLOAD_TIME", "00:00")  # Format HH:MM (UTC)

# ── Timeout Review (menit) ───────────────────────────────────────────────────
REVIEW_REMINDER_MINUTES = int(os.getenv("REVIEW_REMINDER_MINUTES", "120"))
REVIEW_SKIP_MINUTES = int(os.getenv("REVIEW_SKIP_MINUTES", "180"))

# ── Pengaturan Konten ────────────────────────────────────────────────────────
POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "1"))


def validate_config() -> list[str]:
    """
    Validasi semua konfigurasi wajib.
    Mengembalikan list error jika ada konfigurasi yang belum diisi.
    """
    errors = []

    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY belum diisi di .env")
    if AI_PROVIDER == "claude" and not CLAUDE_API_KEY:
        errors.append("CLAUDE_API_KEY belum diisi di .env")
    if not TAVILY_API_KEY:
        errors.append("TAVILY_API_KEY belum diisi di .env")
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN belum diisi di .env")
    if not TELEGRAM_CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID belum diisi di .env")
    if not THREADS_ACCESS_TOKEN:
        errors.append("THREADS_ACCESS_TOKEN belum diisi di .env")
    if not THREADS_USER_ID:
        errors.append("THREADS_USER_ID belum diisi di .env")

    return errors
