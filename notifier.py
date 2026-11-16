# -*- coding: utf-8 -*-
"""Отправка заявок владельцу (через бота-оповещателя в MAX) и дубль в Google Таблицу."""
import asyncio
import logging
from datetime import datetime

import aiohttp

import config
from timezone_utils import now_str

log = logging.getLogger("notifier")


def format_request(session, interrupted: bool) -> str:
    """Собирает все ответы клиента в одно структурированное сообщение."""
    platform = "Telegram" if session.platform == "telegram" else "MAX"
    a = session.answers
    lines = [
        "📋 НОВАЯ ЗАЯВКА с сайта neurodelo.pro" + (" ⚠️ (диалог прерван)" if interrupted else ""),
        "",
        f"👤 Имя: {a.get('name') or '— (не успел указать)'}",
        f"📞 Контакт: {a.get('contact') or '— (не успел указать)'}",
        f"🧭 Направление: {a.get('direction') or '— (не выбрал)'}",
        f"💰 Бюджет: {a.get('budget') or '—'}",
        f"⏰ Сроки: {a.get('deadline') or '—'}",
        "",
        "📝 Детали задачи:",
        session.details(),
        "",
        f"🕒 Время заявки: {now_str()}",
        f"📨 Откуда пришёл клиент: {platform}",
    ]
    if interrupted:
        answered = len(a)
        total = len(session.steps)
        lines.append("")
        lines.append(f"⚠️ Клиент прервал диалог: отвечено {answered} из {total} вопросов.")
    return "\n".join(lines)


async def send_to_max_owner(text: str):
    """Отправляет сообщение владельцу через бота-оповещателя в MAX."""
    if not config.MAX_BOT_TOKEN or not config.OWNER_MAX_USER_ID:
        log.warning("MAX токен/ID владельца не заданы — заявка в MAX не отправлена")
        return False
    url = f"{config.MAX_API_BASE}/chats/{config.OWNER_MAX_USER_ID}/messages/send"
    headers = {"Authorization": f"Bearer {config.MAX_BOT_TOKEN}",
               "Content-Type": "application/json"}
    payload = {"text": text}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                body = await r.text()
                if r.status >= 300:
                    log.error("MAX send failed %s: %s", r.status, body)
                    return False
                return True
    except Exception as e:  # noqa: BLE001
        log.exception("MAX send error: %s", e)
        return False


async def send_to_telegram_owner(text: str):
    """Опциональный дубль заявки владельцу в Telegram."""
    if not config.TELEGRAM_BOT_TOKEN or not config.OWNER_TELEGRAM_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={
                "chat_id": config.OWNER_TELEGRAM_ID,
                "text": text,
            }, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return r.status == 200
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram owner dup failed: %s", e)
        return False


async def save_to_google_sheets(session, interrupted: bool):
    """Дублирует заявку в Google Таблицу (через gspread, сервисный аккаунт)."""
    if not config.GOOGLE_SHEETS_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        log.warning("Google Таблица не настроена — заявка не задублирована")
        return False
    try:
        import gspread
    except ImportError:
        log.error("gspread не установлен (pip install gspread google-auth)")
        return False

    a = session.answers
    row = [
        now_str(),                                        # время заявки
        "Telegram" if session.platform == "telegram" else "MAX",
        a.get("name", ""),
        a.get("contact", ""),
        a.get("direction", ""),
        a.get("budget", ""),
        a.get("deadline", ""),
        session.details().replace("\n", " / "),
        "ПРЕРВАНА" if interrupted else "Завершена",
        session.chat_id,
    ]

    def _write():
        gc = gspread.service_account(filename=config.GOOGLE_SERVICE_ACCOUNT_JSON)
        sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)
        try:
            ws = sh.worksheet(config.GOOGLE_SHEETS_WORKSHEET)
        except gspread.WorksheetNotFound:
            ws = sh.sheet1
        if ws.values_get("A1:A1").get("range") is None or not ws.get_all_values():
            ws.append_row(["Время заявки", "Платформа", "Имя", "Контакт",
                           "Направление", "Бюджет", "Сроки",
                           "Детали задачи", "Статус", "Chat ID"])
        ws.append_row(row)

    try:
        await asyncio.to_thread(_write)
        return True
    except Exception as e:  # noqa: BLE001
        log.exception("Google Sheets write failed: %s", e)
        return False


async def deliver_request(session, interrupted: bool):
    """Основной вход: собрать текст и разослать (MAX + таблицы + TG-дубль)."""
    text = format_request(session, interrupted)
    max_ok, sheets_ok, tg_ok = await asyncio.gather(
        send_to_max_owner(text),
        save_to_google_sheets(session, interrupted),
        send_to_telegram_owner(text),
    )
    log.info("Заявка доставлена: MAX=%s Sheets=%s TG=%s (interrupted=%s)",
             max_ok, sheets_ok, tg_ok, interrupted)
    if not max_ok:
        # страховка: если MAX недоступен, сохраняем текст локально
        try:
            from storage import _DB_DIR
            import os, json
            os.makedirs(_DB_DIR, exist_ok=True)
            with open(os.path.join(_DB_DIR, "unsent_requests.log"), "a",
                      encoding="utf-8") as f:
                f.write(json.dumps({"time": now_str(), "text": text},
                                   ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass
    return max_ok, sheets_ok
