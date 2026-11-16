# -*- coding: utf-8 -*-
"""Конфигурация бота. Все секреты берутся из переменных окружения (.env)."""
import os

try:  # локальная разработка: читаем .env, если он есть
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


# --- Telegram -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# --- MAX (VK Teams / max.ru) ----------------------------------------------
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
# Базовый URL официального Bot API MAX (https://dev.max.ru/docs-api)
MAX_API_BASE = os.getenv("MAX_API_BASE", "https://platform-api.max.ru")
# Путь webhook'а для MAX на нашем домене
MAX_WEBHOOK_PATH = os.getenv("MAX_WEBHOOK_PATH", "/max/webhook")
# Секретная подпись (если включена в настройках webhook MAX)
MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET", "")
# Требовать секрет в webhook (MAX подписи не присылает — по умолчанию выкл.)
MAX_WEBHOOK_STRICT = _b("MAX_WEBHOOK_STRICT")

# --- Владелец (получатель заявок) ------------------------------------------
OWNER_MAX_USER_ID = os.getenv("OWNER_MAX_USER_ID", "")   # chat_id пользователя в MAX
OWNER_TELEGRAM_ID = os.getenv("OWNER_TELEGRAM_ID", "")   # дубль в Telegram (опционально)

# --- Google Таблица ---------------------------------------------------------
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")  # путь к json
GOOGLE_SHEETS_WORKSHEET = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Лист1")

# --- Веб-сервер --------------------------------------------------------------
# Поддомен бота на Sweb
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://bot.neurodelo.pro")
PORT = int(os.getenv("PORT", "8080"))
# Путь webhook'а Telegram берём из aiogram (см. main.py): /tg/webhook/<token>

# --- Прочее -------------------------------------------------------------------
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(24 * 3600)))  # 24 часа
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
DEBUG = _b("DEBUG")
