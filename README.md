# Бот-анкета заявок neurodelo.pro (Telegram + MAX)

Бот собирает заявки клиентов с сайта **neurodelo.pro**: задаёт вопросы по скрипту,
собирает ответы и отправляет их владельцу в **MAX** (через бота-оповещателя),
а также дублирует каждую заявку в **Google Таблицу**. Работает в двух мессенджерах —
**Telegram** и **MAX** — по одному и тому же сценарию.

---

## 1. Сценарий диалога

1. **«Какое направление вас интересует?»** — кнопки: Разработка сайта / ИИ-агент / Маркетплейсы / Приложение / Другое.
2. Уточняющие вопросы по ветке:
   - **Сайт** → тип сайта (лендинг, корпоративный, магазин, сложный сервис) + есть ли дизайн/примеры сайтов.
   - **ИИ-агент** → задача ИИ (автоответы, автоматизация, анализ данных, другое) + с какими системами должен работать ИИ.
   - **Маркетплейсы** → площадка (Wildberries, Ozon, Яндекс Маркет, МегаМаркет) + какой процесс автоматизировать.
   - **Приложение** → тип (iOS, Android, кроссплатформенное, десктопное) + есть ли дизайн/примеры приложений.
   - **Другое** → свободное описание задачи.
3. **Бюджет**: до 50 тыс / 50–100 тыс / 100–300 тыс / более 300 тыс / нужна консультация.
4. **Сроки**: срочно (до 2 недель) / в течение месяца / не горит.
5. **Имя** и **контакт** (телефон или ник).
6. Благодарность: «специалист свяжется в течение 2 часов».

### Как добавить новый маркетплейс (или любой вариант)

Откройте `survey.py` и допишите строку в список `MARKETPLACES`:

```python
MARKETPLACES = [
    ("Wildberries",),
    ("Ozon",),
    ("Яндекс Маркет",),
    ("МегаМаркет",),
    ("AliExpress",),   # ← новая площадка, больше ничего менять не нужно
]
```

То же самое для типов сайтов (`SITE_TYPES`), задач ИИ (`AI_TASKS`),
типов приложений (`APP_TYPES`), бюджетов (`BUDGETS`) и сроков (`DEADLINES`).

### Брошенный диалог

Если клиент прервал диалог сам (`/cancel` в Telegram, «отмена»/`/cancel` в MAX)
или просто перестал отвечать (по умолчанию через 24 часа — настраивается
`SESSION_TTL_SECONDS`), бот отправляет владельцу в MAX и в Google Таблицу всё,
что успел собрать, с пометкой **«диалог прерван»** и статусом `ПРЕРВАНА` в таблице.
Проверка просроченных анкет выполняется фоновой задачей каждый час, а также
по cron-эндпоинту `GET /admin/flush?secret=<MAX_WEBHOOK_SECRET>`.

---

## 2. Структура проекта

| Файл | Назначение |
|---|---|
| `main.py` | FastAPI-приложение, webhook'и Telegram и MAX, запуск |
| `dialog.py` | Общая логика анкеты (не зависит от платформы) |
| `survey.py` | Вопросы, варианты ответов (расширяемые списки) |
| `storage.py` | Хранение состояния диалогов (JSON на диске) |
| `notifier.py` | Сборка заявки → MAX владельцу + Google Таблица |
| `max_client.py` | Клиент API MAX (dev.max.ru / platform.max.ru/api-v1) |
| `timezone_utils.py` | Время заявки (Europe/Moscow) |
| `config.py`, `.env.example` | Настройки через переменные окружения |
| `test_dialog.py` | Локальные тесты сценария без реальных API |

---

## 3. Что нужно получить от владельца

1. **TELEGRAM_BOT_TOKEN** — токен Telegram-бота (от @BotFather).
2. **MAX_BOT_TOKEN** — токен MAX-бота из кабинета разработчика <https://dev.max.ru>.
3. **OWNER_MAX_USER_ID** — chat_id владельца (его личный чат с ботом-оповещателем в MAX).
   Как узнать: владелец пишет боту любое сообщение, а мы берём `chat_id`
   из пришедшего webhook-события (логи) или через `GET /chats`.
4. **GOOGLE_SHEETS_ID** — id таблицы (строка из URL между `/d/` и `/edit`).
5. **secrets/service_account.json** — ключ сервисного аккаунта Google Cloud
   (проект → API «Google Sheets API» → сервисный аккаунт → ключ JSON),
   и этот аккаунт нужно **шарить таблицу** (Edit) на его email.

Все значения кладутся в файл `.env` (шаблон — `.env.example`).

---

## 4. Установка и запуск локально

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить токены
# быстрая проверка сценария:
python test_dialog.py
# режим разработки (long polling Telegram):
python main.py --polling
# или сервер с webhook'ами:
python main.py         # uvicorn main:app :8080
```

---

## 5. Деплой на Sweb (bot.neurodelo.pro)

### 5.1 Создание поддомена

1. Панель Sweb → **Домены** → добавить субдомен `bot.neurodelo.pro`
   (отдельный каталог, например `/home/USERNAME/bot.neurodelo.pro`,
   чтобы не мешать основному сайту).
2. Включить **SSL (Let's Encrypt)** для поддомена — webhook'ы работают только по HTTPS.
   После этого проверьте, что `https://bot.neurodelo.pro/` отвечает `{"status":"ok"}`.

### 5.2 Загрузка файлов — Git (как основной сайт)

В панели Sweb: **Git → Подключить репозиторий** (GitHub/GitLab), путь
репозитория — каталог поддомена `bot.neurodelo.pro`, ветка `main`, включить
автоpull по webhook или нажимать «Pull» вручную после push:

```bash
git add . && git commit -m "Lead bot: Telegram + MAX" && git push origin main
```

### 5.3 Загрузка файлов — FTP (альтернатива)

Через FileZilla/WinSCP по данным из панели Sweb (хост, логин, порт 21):
загрузить содержимое проекта в `/bot.neurodelo.pro/`, кроме `.git/`.
Файлы `.env` и `secrets/service_account.json` загружать в последнюю очередь,
права на них — `600`. Каталогу `data/` дать права на запись,
в нём бот хранит активные анкеты.

### 5.4 Python-приложение на Sweb

В панели Sweb: **Python приложения (Phusion Passenger / uwsgi) → Создать приложение**:
- Путь к приложению: каталог поддомена `/bot.neurodelo.pro`
- Точка входа (ASGI app): `main:app`
- Python: 3.10+ (если доступен только WSGI — см. пункт 8 «Переход на WSGI»)
- В переменных окружения приложения продублировать значения из `.env`
  (либо просто положить `.env` в каталог — python-dotenv подхватит его сам).

Зависимости: если панель позволяет «pip install -r requirements.txt» — нажать её;
иначе через SSH: `cd ~/bot.neurodelo.pro && pip install -r requirements.txt --user`.

### 5.5 Настройка webhook'ов

После того как поддомен работает, выполнить один раз (локально с заполненным `.env`
или на сервере по SSH):

```bash
python main.py --setup-webhooks
```

Эта команда сама вызовет:

- **Telegram**: `POST https://api.telegram.org/bot<TOKEN>/setWebhook`
  с URL `https://bot.neurodelo.pro/tg/webhook/<TELEGRAM_BOT_TOKEN>`
  (проверить: `getWebhookInfo`).
- **MAX**: `POST https://platform.max.ru/api-v1/webhooks/setWebhook`
  с URL `https://bot.neurodelo.pro/max/webhook` (согласно документации dev.max.ru;
  если в кабинете MAX webhook задаётся вручную — указать этот URL там).

Вручную (без скрипта):

```bash
curl -F "url=https://bot.neurodelo.pro/tg/webhook/$TELEGRAM_BOT_TOKEN" \
     "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook"

curl -X POST "$MAX_API_BASE/webhooks/setWebhook" \
     -H "Authorization: Bearer $MAX_BOT_TOKEN" -H "Content-Type: application/json" \
     -d '{"url":"https://bot.neurodelo.pro/max/webhook"}'
```

### 5.6 Cron для брошенных анкет (опционально)

Фоновая задача в самом приложении уже сбрасывает просроченные анкеты каждый час.
Если хотите надёжности через cron Sweb:

```
0 * * * * curl -s "https://bot.neurodelo.pro/admin/flush?secret=$MAX_WEBHOOK_SECRET"
```

---

## 6. Проверка боевого запуска

1. Написать боту в Telegram `/start` → пройти весь опрос → убедиться, что:
   - бот поблагодарил и обещал связь в течение 2 часов;
   - владельцу в MAX пришло структурированное сообщение (имя, контакт,
     направление, бюджет, сроки, детали, время, платформа);
   - в Google Таблице появилась строка со статусом «Завершена».
2. То же самое повторить в MAX.
3. Начать анкету, ответить на 2 вопроса и написать `/cancel` → проверить
   заявку с пометкой «диалог прерван» в MAX и строку «ПРЕРВАНА» в таблице.

## 7. Безопасность

- Webhook Telegram защищён секретным путём `<token>` в URL.
- Webhook MAX проверяет заголовок `X-Max-Signature`/параметр `secret`,
  если задан `MAX_WEBHOOK_SECRET`.
- Эндпоинт `/admin/flush` закрыт тем же секретом.
- Если отправка в MAX недоступна, заявка сохраняется в `data/unsent_requests.log`
  (не теряется, можно переотправить вручную).

## 8. Если на Sweb доступен только WSGI (без ASGI)

Логика бота вынесена в модули, не зависящие от веб-фреймворка. Для WSGI-хостинга
можно поднять тот же код через адаптер: `pip install a2wsgi` и в `wsgi.py`:

```python
from a2wsgi import ASGIMiddleware
from main import app
application = ASGIMiddleware(app)
```

Точка входа приложения на Sweb: `wsgi:application`.
