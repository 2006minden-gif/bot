# -*- coding: utf-8 -*-
"""Клиент API MAX (максимум.ру / VK Teams public API).

Документация: https://dev.max.ru/docs-api  (platform.max.ru/api-v1)
Webhook: MAX присылает onUpdate с полем message_created.
Отправка: POST /chats/{chat_id}/messages/send, Bearer токен бота.
"""
import logging

import aiohttp

import config

log = logging.getLogger("max")


async def max_api(method: str, path: str, **kwargs):
    if not config.MAX_BOT_TOKEN:
        log.warning("MAX_BOT_TOKEN не задан — запрос к API MAX пропущен")
        return None
    url = f"{config.MAX_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {config.MAX_BOT_TOKEN}",
               "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.request(method, url, headers=headers,
                             timeout=aiohttp.ClientTimeout(total=15),
                             **kwargs) as r:
            text = await r.text()
            if r.status >= 300:
                log.error("MAX API %s %s -> %s: %s", method, path, r.status, text)
                return None
            try:
                import json
                return json.loads(text)
            except Exception:  # noqa: BLE001
                return text


async def send_message(chat_id: str, text: str, buttons=None):
    """Отправка текста в чат MAX.

    Кнопки (inline quick-replies) поддерживаются через attachments type=6
    (callback button). Если платформа не примет — отправим только текст.
    """
    payload = {"text": text}
    if buttons:
        attachments = []
        for i, label in enumerate(buttons[:12]):
            attachments.append({
                "type": 6,  # callback button
                "payload": {
                    "buttons": [{
                        "action": {"type": 2, "payload": f"btn:{label}"},
                        "label": label[:60],
                    }]
                },
            })
        payload["attachments"] = attachments
    res = await max_api("POST", f"/chats/{chat_id}/messages/send", json=payload)
    if res is None and buttons:
        # запасной вариант — списком в тексте
        lst = "\n".join(f"{i+1}. {b}" for i, b in enumerate(buttons))
        res = await max_api("POST", f"/chats/{chat_id}/messages/send",
                            json={"text": f"{text}\n\n{lst}"})
    return res


def parse_update(body: dict):
    """Достаёт из webhook-события MAX: chat_id, текст, имя, тип события.

    Возвращает dict или None, если событие нас не касается.
    """
    if not isinstance(body, dict):
        return None
    update = body.get("update", body)
    mc = update.get("message_created") or update.get("message_callback") 
    msg = body.get("message") or (mc if isinstance(mc, dict) else None)
    if msg is None:
        # иногда приходит сразу message_created на верхнем уровне
        msg = update.get("message")
    if not isinstance(msg, dict):
        return None

    chat = msg.get("chat_info") or msg.get("chat") or {}
    chat_id = chat.get("chat_id") or msg.get("chat_id") or \
        (chat.get("recipient") or {}).get("user_chat_id")
    sender = msg.get("sender") or chat.get("user") or {}
    sender_id = sender.get("user_id")
    # в личных чатах MAX chat_id совпадает с user_id собеседника
    if chat_id is None and sender_id is not None:
        chat_id = sender_id
    if chat_id is None:
        return None
    # игнорируем собственные сообщения бота
    if sender.get("is_bot") or sender_id == "me":
        return None

    text = (msg.get("body") or msg.get("text") or "").strip()
    name_parts = [sender.get("first_name"), sender.get("second_name")]
    name = " ".join(p for p in name_parts if p)

    is_callback = bool(update.get("message_callback") or msg.get("callback"))
    if is_callback:
        cb = msg.get("callback") or {}
        payload = cb.get("payload") or ""
        if payload.startswith("btn:"):
            text = payload[4:]

    return {
        "chat_id": str(chat_id),
        "text": text,
        "name": name,
        "user_id": str(sender_id) if sender_id is not None else str(chat_id),
        "is_callback": is_callback,
        "callback_id": (msg.get("callback") or {}).get("callback_id"),
    }
