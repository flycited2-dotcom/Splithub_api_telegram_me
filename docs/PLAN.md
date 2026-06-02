# План: отдельный Telegram-сервис ежедневных остатков

## Контекст

Изначально фича разрабатывалась внутри проекта сайта (`B2B_split_breeze_v2`) как
Celery-задача. По решению владельца вынесена в **отдельный проект**
(`Splithub_api_telegram_me`), который читает общую БД сайта и шлёт отчёт
независимо от деплоя сайта.

## Что в сайте остаётся (НЕ откатывать)

Фикс опт-цены Бриза в `apps/sync/tasks.py::sync_stock`: `base` (закупка) из
stock-эндпоинта пишется в `price_wholesale` всегда (без гейта). Без него в БД у
Бриза опт-цена = розничной, и сервис показал бы неправильную цену. Покрыт тестом
`apps/sync/tests/test_sync_stock_price.py`. Остальные правки фичи из папки сайта
откатаны.

## Архитектура сервиса

- `config.py` — `.env` (DB + Telegram), python-decouple.
- `db.py` — один SQL к БД сайта (таблицы `catalog_product`, `stock_stock`,
  `stock_warehousestock`), read-only.
- `report.py` — чистая сборка текста: `build_report_chunks(rows, today, max_len)`.
- `telegram.py` — `send_telegram(text, chat_id)` с `charset=utf-8`.
- `main.py` — `fetch_stock_rows()` → `build_report_chunks()` → `send_telegram()`.

## Бизнес-правила

- Состав: Крым для всех + Бриз со всех складов. Количество: Бриз — сумма складов,
  остальные — крымский остаток. Реализовано в SQL (`s.warehouse='Симферополь' OR
  source='breeze'`, `total_qty>0`) и `report._qty_for`.
- Наименование = `Product.title` как есть. Опт-цена = `price_wholesale`.
- Группировка по поставщику, чанкинг ~3900 символов, несколько сообщений.

## Проверка

1. `python -m unittest discover -s tests` — логика отчёта (без БД).
2. Заполнить `.env` (DB + токен), `python -m stock_report_bot.main` — сообщения
   приходят в личку владельца (chat_id 1264067528).
3. На сервере: cron/systemd-timer на 09:00 МСК; БД-контейнер `db` доступен сервису.

## Деплой

Отдельно от сайта: venv + cron, либо отдельный docker-контейнер в сети сайта.
См. README.
