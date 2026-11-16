# -*- coding: utf-8 -*-
"""Единая логика диалога-анкеты. Работает одинаково для Telegram и MAX."""
import logging

import survey
from storage import Session, get, save, delete, new_session, pop_abandoned

log = logging.getLogger("dialog")


def build_steps_for(direction_label: str) -> list:
    """Собирает полный список шагов после выбора направления."""
    key = survey.direction_by_label(direction_label)
    branch = survey.build_flow(key or "other")
    return branch + survey.FINAL_STEPS


async def start_dialog(send_text, platform: str, chat_id, user_name: str = "") -> bool:
    """Начать анкету заново. send_text(text, buttons|None, markdown=False) — корутина."""
    existing = get(platform, chat_id)
    if existing and not existing.is_complete():
        await _send_step(send_text, existing)
        return False
    steps = [dict(survey.full_flow()[0])]  # шаг "direction"
    s = new_session(platform, chat_id, steps)
    greeting = ""
    if user_name:
        greeting = f"Здравствуйте, {user_name}! "
    await send_text(
        greeting + "Я помогу оставить заявку на нашем сайте neurodelo.pro. "
                   "Ответьте, пожалуйста, на несколько вопросов — это займёт пару минут.\n\n"
                   + s.current_step()["question"],
        buttons=s.current_step()["options"],
    )
    return True


async def handle_message(send_text, platform: str, chat_id, text: str) -> str:
    """Обработка входящего текста. Возвращает статус:
    'asked'      — задали следующий вопрос / повторили текущий
    'done'       — анкета завершена
    'no-session' — активной анкеты нет (нужно стартовать)
    """
    s = get(platform, chat_id)
    if s is None:
        return "no-session"
    if s.is_complete():
        delete(platform, chat_id)
        return "no-session"

    step = s.current_step()

    # Валидация для шагов с кнопками: в MAX кнопок может не быть —
    # принимаем и свободный текст, если он похож на вариант или пользователь
    # пишет "Другое"/свой вариант. Для строгих списков подсказываем.
    if step["type"] == "choice" and step.get("strict", False):
        opts = [o.lower() for o in step["options"]]
        if text.strip().lower() not in opts:
            await send_text(
                "Пожалуйста, выберите один из вариантов 👇",
                buttons=step["options"])
            return "asked"

    s.answer_current(text)

    # После выбора направления достраиваем ветку вопросов
    if step["id"] == "direction":
        s.steps = [step] + build_steps_for(text)

    save(s)

    nxt = s.current_step()
    if nxt is None:
        # анкета завершена
        from notifier import deliver_request
        delete(platform, chat_id)
        s.finished = True
        await deliver_request(s, interrupted=False)
        await send_text(survey.DONE_TEXT.format(
            name=s.answers.get("name", "друг"),
            contact=s.answers.get("contact", "—")))
        return "done"

    await _send_step(send_text, s)
    return "asked"


async def abandon(send_text, platform: str, chat_id) -> bool:
    """Клиент сам прервал диалог (/cancel или аналог). Отправляем собранное."""
    s = pop_abandoned(platform, chat_id)
    if s is None:
        return False
    from notifier import deliver_request
    await deliver_request(s, interrupted=True)
    await send_text(survey.ABORT_TEXT)
    return True


async def flush_expired():
    """Присылает владельцу все сессии, у которых истёк TTL (клиент бросил диалог).

    Вызывается периодически (cron/фоновая задача).
    """
    from storage import _load, key
    from notifier import deliver_request
    import time, config as cfg

    sent = 0
    for k, raw in list(_load().items()):
        if time.time() - raw.get("updated_at", 0) > cfg.SESSION_TTL_SECONDS:
            s = Session(raw)
            if not s.answers:  # ничего не успел ответить — не шлём
                delete(s.platform, s.chat_id)
                continue
            s.aborted = True
            delete(s.platform, s.chat_id)
            await deliver_request(s, interrupted=True)
            sent += 1
    log.info("flush_expired: отправлено прерванных заявок: %s", sent)
    return sent


async def _send_step(send_text, s: Session):
    step = s.current_step()
    if step is None:
        return
    await send_text(step["question"],
                    buttons=step.get("options") if step["type"] == "choice" else None)
