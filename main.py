# -*- coding: utf-8 -*-
"""Бот-анкета neurodelo.pro (Telegram + MAX).

Запуск на Sweb (FastAPI/uvicorn, webhook-режим):
    uvicorn main:app --host 0.0.0.0 --port 8080

Webhook'и:
    Telegram: https://bot.neurodelo.pro/tg/webhook/<TELEGRAM_BOT_TOKEN>
    MAX:      https://bot.neurodelo.pro/max/webhook

Локальная разработка (long polling вместо webhook):
    python main.py --polling
"""
import asyncio
import logging
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import config
import dialog
import max_client
import storage
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("main")

# ============================== TELEGRAM (aiogram) ==========================
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove

router = Router()
tg_bot: Bot | None = None


def tg_keyboard(options) -> ReplyKeyboardMarkup | None:
    if not options:
        return None
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=o)] for o in options],
        resize_keyboard=True, one_time_keyboard=True, input_field_placeholder="Выберите вариант или напишите ответ")
    return kb


def make_tg_sender(chat_id: int):
    async def send_text(text: str, buttons=None, markdown: bool = False):
        await tg_bot.send_message(chat_id, text,
                                  reply_markup=tg_keyboard(buttons))
    return send_text


@router.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or ""
    await dialog.start_dialog(make_tg_sender(message.chat.id),
                              "telegram", message.chat.id, name)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    done = await dialog.abandon(make_tg_sender(message.chat.id),
                                "telegram", message.chat.id)
    if not done:
        await message.answer("Активной анкеты нет. Напишите /start, чтобы оставить заявку.")


@router.message(F.text)
async def any_text(message: Message):
    status = await dialog.handle_message(make_tg_sender(message.chat.id),
                                         "telegram", message.chat.id,
                                         message.text)
    if status == "no-session":
        await cmd_start(message)


# ================================ WEB APP ===================================

_flush_task = None


async def _flush_loop():
    """Раз в час проверяем брошенные диалоги и отправляем собранное владельцу."""
    while True:
        try:
            await asyncio.sleep(3600)
            await dialog.flush_expired()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("flush loop error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_bot, _flush_task
    if config.TELEGRAM_BOT_TOKEN:
        tg_bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)
        app.state.dp = dp
    _flush_task = asyncio.create_task(_flush_loop())
    log.info("Bot app started")
    yield
    _flush_task.cancel()
    if tg_bot:
        await tg_bot.session.close()


app = FastAPI(title="neurodelo bot", lifespan=lifespan)


@app.get("/")
async def health():
    return {"status": "ok", "service": "neurodelo.pro lead bot"}


@app.post("/tg/webhook/{token}")
async def tg_webhook(request: Request, token: str):
    if not config.TELEGRAM_BOT_TOKEN or token != config.TELEGRAM_BOT_TOKEN:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await request.json()
    dp: Dispatcher = request.app.state.dp
    await dp.feed_update(tg_bot, body)
    return {"ok": True}


# ================================ MAX WEBHOOK ================================

@app.post(config.MAX_WEBHOOK_PATH)
async def max_webhook(request: Request):
    # проверка секрета, если задан
    if config.MAX_WEBHOOK_SECRET:
        sig = request.headers.get("X-Max-Signature") or \
            request.query_params.get("secret")
        if sig != config.MAX_WEBHOOK_SECRET:
            return JSONResponse({"error": "forbidden"}, status_code=403)

    body = await request.json()
    upd = max_client.parse_update(body)
    if upd is None:
        return {"sync_id": body.get("sync_id")}

    chat_id = upd["chat_id"]
    text = upd["text"]

    async def send_max(t, buttons=None, markdown: bool = False):
        try:
            await max_client.send_message(chat_id, t, buttons=buttons)
        except Exception as e:  # noqa: BLE001
            log.exception("MAX send error: %s", e)

    low = text.lower()
    if low in ("/start", "старт", "начать", "заявка", "/cancel"):
        if low == "/cancel":
            ok = await dialog.abandon(send_max, "max", chat_id)
            if not ok:
                await send_max("Активной анкеты нет. Напишите «заявка», чтобы начать.")
        else:
            await dialog.start_dialog(send_max, "max", chat_id, upd["name"])
        return {"sync_id": body.get("sync_id")}

    status = await dialog.handle_message(send_max, "max", chat_id, text)
    if status == "no-session":
        await dialog.start_dialog(send_max, "max", chat_id, upd["name"])
    return {"sync_id": body.get("sync_id")}


# Служебный эндпоинт для cron на Sweb: сброс просроченных (брошенных) анкет
@app.get("/admin/flush")
async def admin_flush(secret: str = ""):
    if config.MAX_WEBHOOK_SECRET and secret != config.MAX_WEBHOOK_SECRET:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    sent = await dialog.flush_expired()
    return {"flushed": sent}


# ============================ НАСТРОЙКА WEBHOOK'ОВ ===========================

async def setup_telegram_webhook():
    url = f"{config.WEBHOOK_BASE_URL}/tg/webhook/{config.TELEGRAM_BOT_TOKEN}"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": url,
                  "allowed_updates": ["message"],
                  "drop_pending_updates": False}) as r:
            log.info("Telegram setWebhook: %s", await r.text())


async def setup_max_webhook():
    url = f"{config.WEBHOOK_BASE_URL}{config.MAX_WEBHOOK_PATH}"
    res = await max_client.max_api("POST", "/webhooks/setWebhook",
                                   json={"url": url})
    log.info("MAX setWebhook: %s", res)


# ================================ ЗАПУСК ====================================

def run_polling():
    """Локальная разработка: long polling для Telegram."""
    from aiogram.types import BotCommand
    async def _run():
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать заявку"),
            BotCommand(command="cancel", description="Отменить заявку"),
        ])
        await dp.start_polling(bot)
    asyncio.run(_run())


if __name__ == "__main__":
    if "--polling" in sys.argv:
        run_polling()
    elif "--setup-webhooks" in sys.argv:
        async def _s():
            if config.TELEGRAM_BOT_TOKEN:
                await setup_telegram_webhook()
            if config.MAX_BOT_TOKEN:
                await setup_max_webhook()
        asyncio.run(_s())
    else:
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=config.PORT)
