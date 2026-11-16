# -*- coding: utf-8 -*-
"""Хранилище сессий диалога.

Sweb — обычный shared-хостинг: процесс может перезапускаться, поэтому
состояние диалогов сохраняем на диск (JSON). При наличии Redis можно
заменить реализацию, интерфейс остаётся тем же.
"""
import json
import os
import time
import threading
import uuid

import config

_LOCK = threading.Lock()
_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_DB_FILE = os.path.join(_DB_DIR, "sessions.json")
OWNERS_FILE = "owners.json"


def _path(name: str) -> str:
    return name if os.path.isabs(name) else os.path.join(_DB_DIR, name)


def load_json(name: str, default):
    """Универсальная загрузка small-файлов (owners.json и т.п.)."""
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(name: str, data):
    os.makedirs(_DB_DIR, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(name))


def _load() -> dict:
    try:
        with open(_DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(db: dict):
    os.makedirs(_DB_DIR, exist_ok=True)
    tmp = _DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _DB_FILE)


def _cleanup(db: dict):
    now = time.time()
    expired = [k for k, v in db.items()
               if now - v.get("updated_at", 0) > config.SESSION_TTL_SECONDS]
    for k in expired:
        db.pop(k, None)


class Session:
    """Одна анкета клиента.

    Поля:
      platform   — 'telegram' | 'max'
      chat_id    — id чата на платформе
      step_index — индекс текущего шага в self.steps
      steps      — [{id, type, question, options?}]
      answers    — {step_id: answer}
      finished / aborted
    """

    def __init__(self, data: dict):
        self.__dict__.update(data)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        return d

    # --- работа с шагами -----------------------------------------------------

    def current_step(self):
        if 0 <= self.step_index < len(self.steps):
            return self.steps[self.step_index]
        return None

    def answer_current(self, text: str):
        step = self.current_step()
        if step:
            self.answers[step["id"]] = (text or "").strip()
        self.step_index += 1
        self.updated_at = time.time()

    def is_complete(self) -> bool:
        return self.step_index >= len(self.steps)

    @property
    def direction_label(self):
        return self.answers.get("direction", "")

    def details(self) -> str:
        """Все уточняющие ответы одной строкой 'вопрос: ответ'."""
        parts = []
        base_ids = {"direction", "budget", "deadline", "name", "contact"}
        for step in self.steps:
            sid = step["id"]
            if sid in base_ids:
                continue
            ans = self.answers.get(sid)
            if ans:
                parts.append(f"{step['question']} — {ans}")
        return "\n".join(parts) if parts else "—"

    def summary_line(self) -> str:
        return " | ".join(f"{k}: {v}" for k, v in self.answers.items())


# --- API хранилища -------------------------------------------------------------

def key(platform: str, chat_id) -> str:
    return f"{platform}:{chat_id}"


def get(platform: str, chat_id):
    with _LOCK:
        db = _load()
        _cleanup(db)
        raw = db.get(key(platform, chat_id))
        return Session(raw) if raw else None


def save(session: Session):
    session.updated_at = time.time()
    with _LOCK:
        db = _load()
        _cleanup(db)
        db[key(session.platform, session.chat_id)] = session.to_dict()
        _save(db)


def delete(platform: str, chat_id):
    with _LOCK:
        db = _load()
        db.pop(key(platform, chat_id), None)
        _save(db)


def new_session(platform: str, chat_id, steps: list) -> Session:
    s = Session({
        "id": uuid.uuid4().hex,
        "platform": platform,
        "chat_id": str(chat_id),
        "steps": steps,
        "answers": {},
        "step_index": 0,
        "finished": False,
        "aborted": False,
        "created_at": time.time(),
        "updated_at": time.time(),
    })
    save(s)
    return s


def pop_abandoned(platform: str, chat_id):
    """Забрать сессию при прерывании диалога (для отправки владельцу)."""
    s = get(platform, chat_id)
    if s:
        s.aborted = True
        delete(platform, chat_id)
    return s
