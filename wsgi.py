# -*- coding: utf-8 -*-
"""WSGI-адаптер для хостингов без поддержки ASGI (Sweb, только WSGI/Passenger).

Точка входа приложения на Sweb:  wsgi:application
Запуск локально для проверки:    gunicorn wsgi:application -b 0.0.0.0:8080
"""
import asyncio
import json
import os
import threading

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("PORT", "8080")

# Импортируем приложение ПОСЛЕ загрузки .env (config читает переменные окружения)
from main import app  # noqa: E402


class _LoopHolder:
    """Одна фоновая event-loop для всего процесса (запускается один раз)."""

    loop: asyncio.AbstractEventLoop | None = None
    started = False
    lock = threading.Lock()

    @classmethod
    def ensure(cls) -> asyncio.AbstractEventLoop:
        with cls.lock:
            if cls.loop is None:
                cls.loop = asyncio.new_event_loop()
            if not cls.started:
                t = threading.Thread(target=cls.loop.run_forever, daemon=True)
                t.start()
                cls.started = True
                # Запуск стартовых задач lifespan (long-polling и пр.)
                from main import app as _app
                from main import startup_tasks

                asyncio.run_coroutine_threadsafe(startup_tasks(_app), cls.loop)
        return cls.loop


_loop = _LoopHolder.ensure()


def application(environ, start_response):
    """Минимальный WSGI-мост над ASGI-приложением FastAPI."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/") or "/"
    query = environ.get("QUERY_STRING", "")

    headers_raw = environ.get("HTTP_HEADERS_RAW")
    if headers_raw:
        headers = json.loads(headers_raw)
    else:
        headers = []
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                name = key[5:].replace("_", "-").lower()
                headers.append([name.encode(), value.encode()])
        if environ.get("CONTENT_TYPE"):
            headers.append([b"content-type", environ["CONTENT_TYPE"].encode()])
        if environ.get("CONTENT_LENGTH"):
            headers.append([b"content-length", environ["CONTENT_LENGTH"].encode()])

    body_chunks = []
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > 0:
        stream = environ["wsgi.input"]
        remaining = length
        while remaining > 0:
            chunk = stream.read(min(remaining, 65536))
            if not chunk:
                break
            body_chunks.append(chunk)
            remaining -= len(chunk)
    body = b"".join(body_chunks)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": environ.get("SERVER_PROTOCOL", "HTTP/1.1").split("/")[-1],
        "method": method,
        "scheme": environ.get("wsgi.url_scheme", "https"),
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": headers,
        "client": (environ.get("REMOTE_ADDR", ""), int(environ.get("REMOTE_PORT", "0") or 0)),
        "server": (environ.get("SERVER_NAME", ""), int(environ.get("SERVER_PORT", "443") or 443)),
    }

    request = {"body": body}

    async def receive():
        if request["body"] is not None:
            b, request["body"] = request["body"], None
            return {"type": "http.request", "body": b, "more_body": False}
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    result = {"status": None, "headers": None, "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            result["headers"] = message.get("headers", [])
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    future = asyncio.run_coroutine_threadsafe(app(scope, receive, send), _loop)
    future.result(timeout=60)

    resp_headers = [(k.decode(), v.decode()) for k, v in (result["headers"] or [])]
    start_response(f"{result['status']} Reason", resp_headers)
    return [result["body"]]
