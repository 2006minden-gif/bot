# -*- coding: utf-8 -*-
"""Вопросник (скрипт) сбора заявок.

Логика диалога описана декларативно: состояние -> следующий шаг.
Шаги бывают двух типов:
  * choice — варианты на кнопки (ReplyKeyboard)
  * input  — свободный текстовый ответ

Чтобы добавить новый маркетплейс (или любой другой вариант),
достаточно дописать строку в соответствующий список ниже.
"""

# --- Варианты ответа ---------------------------------------------------------

DIRECTIONS = [
    ("site", "Разработка сайта"),
    ("ai", "ИИ-агент"),
    ("marketplace", "Маркетплейсы"),
    ("app", "Приложение"),
    ("other", "Другое"),
]

SITE_TYPES = [
    ("Лендинг",),
    ("Корпоративный сайт",),
    ("Интернет-магазин",),
    ("Сложный сервис",),
]

AI_TASKS = [
    ("Автоответы",),
    ("Автоматизация процессов",),
    ("Анализ данных",),
    ("Другое",),
]

# Список площадок расширяемый: просто добавьте новую строку сюда.
MARKETPLACES = [
    ("Wildberries",),
    ("Ozon",),
    ("Яндекс Маркет",),
    ("МегаМаркет",),
    # ("AliExpress",),   <- пример: расскомментируйте или добавьте свою площадку
]

APP_TYPES = [
    ("Мобильное iOS",),
    ("Мобильное Android",),
    ("Кроссплатформенное",),
    ("Десктопное",),
]

BUDGETS = [
    ("до 50 тысяч",),
    ("50–100 тысяч",),
    ("100–300 тысяч",),
    ("более 300 тысяч",),
    ("нужна консультация",),
]

DEADLINES = [
    ("Срочно (до 2 недель)",),
    ("В течение месяца",),
    ("Не горит",),
]

OTHER_CHOICES = ["Другое", "Свой вариант"]

# --- Тексты вопросов ----------------------------------------------------------

Q_DIRECTION = "Какое направление вас интересует? 👇"
Q_SITE_TYPE = "Какой тип сайта вам нужен?"
Q_SITE_DESIGN = ("Расскажите, есть ли у вас уже дизайн или примеры сайтов, "
                 "которые нравятся? Можете прислать ссылки или описать словами.")
Q_AI_TASK = "Какую задачу должен решать ИИ-агент?"
Q_AI_SYSTEMS = ("Опишите, пожалуйста, с какими системами должен работать ИИ "
                "(CRM, мессенджеры, базы данных, 1С и т.д.).")
Q_MARKETPLACE = "На какой площадке работаете / планируете работать?"
Q_MP_PROCESS = "Какой процесс нужно автоматизировать? Опишите своими словами."
Q_APP_TYPE = "Какой тип приложения вам нужен?"
Q_APP_DESIGN = ("Есть ли у вас уже дизайн или примеры приложений, "
                "которые нравятся? Пришлите ссылки или опишите словами.")
Q_OTHER = "Опишите, пожалуйста, вашу задачу."
Q_BUDGET = "Какой бюджет вы закладываете на проект?"
Q_DEADLINE = "Какие сроки реализации?"
Q_NAME = "Как вас зовут? 🙂"
Q_CONTACT = ("Отлично! Оставьте контакт для связи — телефон или ник в мессенджере "
             "(например: +7 900 000-00-00 или @username).")

DONE_TEXT = ("🎉 Спасибо, {name}! Ваша заявка принята.\n\n"
             "Наш специалист свяжется с вами в течение 2 часов по контакту: {contact}")

ABORT_TEXT = ("Похоже, вы прервали диалог. Если захотите продолжить — просто "
              "напишите мне ещё раз. Хорошего дня! 👋")


def _choices(items):
    return [i[0] for i in items]


def build_flow(direction_key: str):
    """Возвращает список уточняющих шагов для выбранного направления."""
    if direction_key == "site":
        return [
            {"id": "site_type", "type": "choice", "question": Q_SITE_TYPE,
             "options": _choices(SITE_TYPES)},
            {"id": "site_design", "type": "input", "question": Q_SITE_DESIGN},
        ]
    if direction_key == "ai":
        return [
            {"id": "ai_task", "type": "choice", "question": Q_AI_TASK,
             "options": _choices(AI_TASKS)},
            {"id": "ai_systems", "type": "input", "question": Q_AI_SYSTEMS},
        ]
    if direction_key == "marketplace":
        return [
            {"id": "marketplace", "type": "choice", "question": Q_MARKETPLACE,
             "options": _choices(MARKETPLACES)},
            {"id": "mp_process", "type": "input", "question": Q_MP_PROCESS},
        ]
    if direction_key == "app":
        return [
            {"id": "app_type", "type": "choice", "question": Q_APP_TYPE,
             "options": _choices(APP_TYPES)},
            {"id": "app_design", "type": "input", "question": Q_APP_DESIGN},
        ]
    # other
    return [
        {"id": "other_task", "type": "input", "question": Q_OTHER},
    ]


# Общие финальные шаги (для всех направлений)
FINAL_STEPS = [
    {"id": "budget", "type": "choice", "question": Q_BUDGET,
     "options": _choices(BUDGETS)},
    {"id": "deadline", "type": "choice", "question": Q_DEADLINE,
     "options": _choices(DEADLINES)},
    {"id": "name", "type": "input", "question": Q_NAME},
    {"id": "contact", "type": "input", "question": Q_CONTACT},
]


def full_flow():
    """Полный скрипт: сначала выбор направления, затем ветка, затем финал."""
    return [{"id": "direction", "type": "choice", "question": Q_DIRECTION,
             "options": [label for _, label in DIRECTIONS]}]


def direction_by_label(label: str):
    for key, lbl in DIRECTIONS:
        if lbl.lower() == (label or "").strip().lower():
            return key
    return None
