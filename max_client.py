# -*- coding: utf-8 -*-
"""Клиент официального Bot API MAX (https://dev.max.ru/docs-api).

Базовый URL:  https://platform-api.max.ru  (в доке рекомендуют platform-api2)
Авторизация:  заголовок `Authorization: <token>` БЕЗ префикса Bearer.
Webhook:      MAX присылает POST с объектом Update:
              {"update_type": "message_created"|"message_callback"|..., ...}
Отправка:     POST /messages?chat_id=...  {"text": ..., "attachments": [...]}
Клавиатура:   attachment type="inline_keyboard", кнопки типа "callback".
Ответ на клик кнопки: POST /answers?callback_id=...
"""
import json
import logging

import aiohttp

import config

log = logging.getLogger("max")


async def max_api(method: str, path: str, params=None, **kwargs):
    """Низкоуровневый запрос к API MAX. Возвращает dict/str или None при ошибке."""
    if not config.MAX_BOT_TOKEN:
        log.warning("MAX_BOT_TOKEN не задан — запрос к API MAX пропущен")
        return None
    url = f"{config.MAX_API_BASE}{path}"
    headers = {"Authorization": config.MAX_BOT_TOKEN,
               "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.request(method, url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=15),
                             **kwargs) as r:
            text = await r.text()
            if r.status >= 300:
                log.error("MAX API %s %s -> %s: %s", method, path, r.status, text)
                return None
            try:
                return json.loads(text)
            except Exception:  # noqa: BLE001
                return text


def build_keyboard(buttons):
    """Собирает inline_keyboard: по одной callback-кнопке в ряду.

    Формат по официальному API MAX (dev.max.ru/docs-api): кнопка содержит
    type=callback, text — подпись, payload — строка, которая вернётся в
    событии message_callback.
    """
    rows = []
    for label in buttons[:30]:
        rows.append([{
            "type": "callback",
            "text": label[:64],
            "payload": label[:255],
        }])
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


async def send_message(chat_id: str, text: str, buttons=None):
    """Отправка текста (опционально с inline-клавиатурой) в диалог/чат."""
    payload = {"text": text[:4000]}
    if buttons:
        payload["attachments"] = [build_keyboard(buttons)]
    res = await max_api("POST", "/messages", params={"chat_id": chat_id},
                        json=payload)
    if res is None and buttons:
        # запасной вариант — нумерованный список прямо в тексте
        lst = "\n".join(f"{i + 1}. {b}" for i, b in enumerate(buttons))
        res = await max_api("POST", "/messages", params={"chat_id": chat_id},
                            json={"text": f"{text}\n\n{lst}"})
    return res


async def answer_callback(callback_id: str, text: str, buttons=None):
    """Ответ на нажатие кнопки (заменяет сообщение под кнопками)."""
    payload = {"message": {"text": text[:4000]}}
    if buttons:
        payload["message"]["attachments"] = [build_keyboard(buttons)]
    return await max_api("POST", "/answers",
                         params={"callback_id": callback_id}, json=payload)


async def set_webhook(url: str):
    """Подписка на события через Webhook (POST /subscriptions)."""
    body = {
        "url": url,
        "update_types": ["message_created", "message_callback", "bot_started"],
    }
    return await max_api("POST", "/subscriptions", json=body)


async def delete_webhook(url: str):
    return await max_api("DELETE", "/subscriptions", params={"url": url})


async def get_me():
    return await max_api("GET", "/me")


def parse_update(body: dict):
    """Разбирает объект Update из webhook MAX.

    Возвращает dict:
      event      — 'message' | 'callback' | 'bot_started' | 'ignored'
      chat_id    — идентификатор диалога для ответа (числовой, строкой)
      user_id    — отправитель
      text       — текст сообщения или payload кнопки
      name       — имя пользователя
      callback_id— для ответа POST /answers
    либо None, если тело непонятное.
    """
    if not isinstance(body, dict):
        return None
    update_type = body.get("update_type") or ""

    # служебные события, которые нас не касаются
    if update_type in ("bot_stopped", "dialog_removed", "dialog_cleared",
                       "chat_title_changed", "dialog_muted", "dialog_unmuted",
                       "bot_added", "bot_removed", "user_added", "user_removed",
                       "message_edited", "message_removed"):
        return {"event": "ignored", "chat_id": None}

    if update_type == "bot_started":
        user = body.get("user") or {}
        chat_id = body.get("chat_id") or user.get("user_id")
        if chat_id is None:
            return None
        return {
            "event": "bot_started",
            "chat_id": str(chat_id),
            "user_id": str(user.get("user_id") or chat_id),
            "text": "/start",
            "name": " ".join(p for p in
                             (user.get("first_name"), user.get("last_name")) if p),
            "callback_id": None,
        }

    if update_type == "message_callback":
        cb = body.get("callback") or {}
        user = cb.get("user") or {}
        msg = body.get("message") or {}
        recipient = msg.get("recipient") or {}
        chat_id = recipient.get("chat_id") or body.get("chat_id") or \
            user.get("user_id")
        if chat_id is None:
            return None
        payload = cb.get("callback_payload") or cb.get("payload") or ""
        return {
            "event": "callback",
            "chat_id": str(chat_id),
            "user_id": str(user.get("user_id") or chat_id),
            "text": payload,
            "name": " ".join(p for p in
                             (user.get("first_name"), user.get("last_name")) if p),
            "callback_id": cb.get("callback_id"),
        }

    # message_created (у старых версий мог приходить как message)
    msg = body.get("message") or body.get("created") or {}
    if not isinstance(msg, dict) or not msg:
        return None
    sender = msg.get("sender") or {}
    if sender.get("is_bot"):
        return {"event": "ignored", "chat_id": None}
    recipient = msg.get("recipient") or {}
    chat_id = recipient.get("chat_id") or body.get("chat_id") or \
        sender.get("user_id")
    if chat_id is None:
        return None
    text = (msg.get("body") or msg.get("text") or "").strip()
    name = " ".join(p for p in (sender.get("first_name"),
                                sender.get("last_name")) if p)
    return {
        "event": "message",
        "chat_id": str(chat_id),
        "user_id": str(sender.get("user_id") or chat_id),
        "text": text,
        "name": name,
        "callback_id": None,
    }
