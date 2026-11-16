# -*- coding: utf-8 -*-
"""Локальный тест диалога без реальных API.

Запуск:  python test_dialog.py
Эмулирует полный проход анкеты в Telegram и ветку маркетплейсов в MAX,
а также прерывание диалога (клиент написал /cancel).
"""
import asyncio
import os
import shutil

# чистим данные перед тестом
HERE = os.path.dirname(os.path.abspath(__file__))
shutil.rmtree(os.path.join(HERE, "data"), ignore_errors=True)

import storage          # noqa: E402
import dialog           # noqa: E402
import notifier         # noqa: E402


class FakeOutbox:
    def __init__(self):
        self.messages = []

    def sender(self, chat_id):
        async def send(text, buttons=None, markdown=False):
            self.messages.append({"chat": chat_id, "text": text, "buttons": buttons})
        return send


async def patch_network():
    """Гасим реальные сетевые вызовы."""
    async def fake_max(text): return True
    async def fake_tg(text): return True
    async def fake_sheets(s, i): return True
    notifier.send_to_max_owner = fake_max
    notifier.send_to_telegram_owner = fake_tg
    notifier.save_to_google_sheets = fake_sheets


async def run_flow(out, platform, chat, answers):
    await dialog.start_dialog(out.sender(chat), platform, chat, "Тест")
    for a in answers:
        status = await dialog.handle_message(out.sender(chat), platform, chat, a)
        assert status in ("asked", "done"), status
    return status


def last_questions(out, n=1):
    return [m["text"] for m in out.messages[-n:]]


async def main():
    await patch_network()

    # --- 1. Полный цикл: Сайт ------------------------------------------------
    out = FakeOutbox()
    ans = ["Разработка сайта", "Лендинг", "Дизайна нет, вот пример: site.ru",
           "до 50 тысяч", "Срочно (до 2 недель)", "Иван", "+79001234567"]
    status = await run_flow(out, "telegram", "111", ans)
    assert status == "done"
    s = storage.get("telegram", "111")
    assert s is None  # удалена после завершения
    assert "Спасибо, Иван" in out.messages[-1]["text"]
    print("[OK] Полная анкета 'Сайт' завершена")
    print("--- последние сообщения клиенту ---")
    for m in out.messages[:4]:
        print(" *", m["text"].replace("\n", " ⏎ ")[:110], "| кнопки:", m["buttons"])

    # --- 2. ИИ-агент ----------------------------------------------------------
    out = FakeOutbox()
    await run_flow(out, "telegram", "222",
                   ["ИИ-агент", "Автоответы", "CRM Bitrix24 и Telegram",
                    "100–300 тысяч", "В течение месяца", "Пётр", "@petr"])
    print("[OK] Анкета 'ИИ-агент'")

    # --- 3. Маркетплейсы ------------------------------------------------------
    out = FakeOutbox()
    await run_flow(out, "max", "333",
                   ["Маркетплейсы", "Wildberries", "Автоматизация поставок и цен",
                    "более 300 тысяч", "Не горит", "ООО Ромашка", "romashka@mail.ru"])
    print("[OK] Анкета 'Маркетплейсы' (MAX)")

    # --- 4. Приложение --------------------------------------------------------
    out = FakeOutbox()
    await run_flow(out, "telegram", "444",
                   ["Приложение", "Кроссплатформенное", "Есть макеты в Figma",
                    "нужна консультация", "Не горит", "Сидор", "89990001122"])
    print("[OK] Анкета 'Приложение'")

    # --- 5. Другое ------------------------------------------------------------
    out = FakeOutbox()
    await run_flow(out, "telegram", "555",
                   ["Другое", "Нужен чат-бот для ресторана",
                    "50–100 тысяч", "В течение месяца", "Мария", "@maria"])
    print("[OK] Анкета 'Другое'")

    # --- 6. Прерванный диалог (/cancel) ---------------------------------------
    out = FakeOutbox()
    await dialog.start_dialog(out.sender("666"), "telegram", "666", "Брошеный")
    await dialog.handle_message(out.sender("666"), "telegram", "666", "Разработка сайта")
    await dialog.handle_message(out.sender("666"), "telegram", "666", "Интернет-магазин")
    ok = await dialog.abandon(out.sender("666"), "telegram", "666")
    assert ok and storage.get("telegram", "666") is None
    print("[OK] Прерванный диалог отправлен владельцу с пометкой")

    # проверка текста прерванной заявки
    import survey
    s = storage.Session({
        "id": "x", "platform": "telegram", "chat_id": "666",
        "steps": [dict(survey.full_flow()[0])] + dialog.build_steps_for("Разработка сайта"),
        "answers": {"direction": "Разработка сайта", "site_type": "Интернет-магазин"},
        "step_index": 2, "finished": False, "aborted": True,
        "created_at": 0, "updated_at": 0})
    txt = notifier.format_request(s, interrupted=True)
    assert "прервал диалог" in txt and "Интернет-магазин" in txt
    print("--- пример сообщения владельцу (прерванная заявка) ---")
    print(txt)

    # --- 7. TTL-сброс брошенных анкет -----------------------------------------
    out = FakeOutbox()
    await dialog.start_dialog(out.sender("777"), "max", "777", "Тильт")
    await dialog.handle_message(out.sender("777"), "max", "777", "Другое")
    # искусственно «старим» сессию
    db = storage._load()
    k = storage.key("max", "777")
    db[k]["updated_at"] -= storage.config.SESSION_TTL_SECONDS + 10
    storage._save(db)
    sent = await dialog.flush_expired()
    assert sent >= 1
    print("[OK] flush_expired отправил брошенную анкету")

    print("\n=== ВСЕ ТЕСТЫ ПРОЙДЕНЫ ===")


if __name__ == "__main__":
    asyncio.run(main())
