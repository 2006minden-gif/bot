# Публикация бота на Sweb — bot.neurodelo.pro

Готовый архив для загрузки: **deploy/bot-neurodelo.tar.gz**
(содержит весь код + боевой .env с токенами; без .git, логов и кэша)

## Шаг 1. Поддомен в панели Sweb
1. Панель управления Sweb → Домены / Субдомены → создать субдомен `bot.neurodelo.pro`
   (корень сайта, например `/home/<login>/bot.neurodelo.pro`).
2. Включить SSL (Let's Encrypt) для субдомена — webhook'ы Telegram/MAX работают только по https.

## Шаг 2. Загрузка файлов (FTP — самый быстрый путь)
Через FileZilla/WinSCP (данные FTP из панели Sweb):
1. Загрузить `deploy/bot-neurodelo.tar.gz` в корень субдомена.
2. В панели Sweb открыть Файловый менеджер или подключиться по SSH и выполнить:
   `cd ~/bot.neurodelo.pro && tar xzf bot-neurodelo.tar.gz && rm bot-neurodelo.tar.gz`
   Либо распаковать архив локально и закачать файлы в каталог субдомена напрямую.

Альтернатива через Git: заведите репозиторий проекта на GitHub/GitLab (из /workspace),
в панели Sweb «Git → Подключить репозиторий», деплой в каталог субдомена.
Файл `.env` в git не входит — его нужно один раз положить в каталог вручную (есть в архиве).

## Шаг 3. Python-приложение
В панели Sweb: Python приложения (WSGI/Passenger/uwsgi) → Создать приложение:
- Каталог: корень субдомена; Python 3.10+; виртуальное окружение — создать.
- Зависимости: `requirements.txt` (gunicorn включён; если панель ругается на uvicorn —
  удалите строку uvicorn из копии requirements на сервере).
- Точка входа: **`wsgi:application`** (файл wsgi.py — WSGI-мост над FastAPI,
  проверен локально под gunicorn: health-check и webhook MAX отвечают 200).
- Если панель поддерживает ASGI/uvicorn напрямую — можно `main:app`.

## Шаг 4. Проверка
Открыть в браузере `https://bot.neurodelo.pro/` — должно вернуть
`{"status":"ok","service":"neurodelo.pro lead bot"}`.

## Шаг 5. Webhook'ы
Если есть SSH в каталоге приложения: `python main.py --setup-webhooks`

Или вручную curl'ами (подставьте токен Telegram из .env):

    # удалить старый webhook (если был)
    curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"
    # установить новый
    curl -F "url=https://bot.neurodelo.pro/tg/webhook/<TOKEN>" \
         "https://api.telegram.org/bot<TOKEN>/setWebhook"

MAX: подписка на события —
    curl -X POST https://platform-api.max.ru/subscriptions \
         -H "Authorization: <MAX_BOT_TOKEN>" -H "Content-Type: application/json" \
         -d '{"url":"https://bot.neurodelo.pro/max/webhook","secret":"<MAX_WEBHOOK_SECRET из .env>"}'

## Шаг 6. Cron (добавить в панели Sweb)

    17 * * * * curl -s "https://bot.neurodelo.pro/admin/flush?secret=<MAX_WEBHOOK_SECRET из .env>" > /dev/null

Сбрасывает брошенные анкеты (клиент молчит >24 ч) в MAX и Google Таблицу.

## Шаг 7. Пусковое тестирование
1. Напишите боту в Telegram «старт» — должна начаться анкета.
2. Напишите тому же боту в MAX — в логах приложения появится строка
   `Новый чат в MAX: chat_id=NNNN...` — это ваш настоящий числовой ID.
   Скопируйте его в `.env` → `OWNER_MAX_USER_ID=NNNN...` и перезапустите приложение.
3. Пройдите анкету до конца → заявка придёт вам в MAX и продублируется в Google Таблицу.

## Осталось от владельца
- JSON-ключ сервисного аккаунта Google → файл `secrets/service_account.json` на сервере
  (иначе дубль в Google Таблицу будет писать ошибку в лог, MAX-рассылка продолжит работать).
