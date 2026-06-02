# SplitHome — Telegram-сервис ежедневных остатков

Самостоятельный сервис: раз в сутки собирает список товаров в наличии и шлёт его
владельцу в **личный** Telegram. Не зависит от деплоя сайта — только читает его БД.

Строка отчёта: `• Модель — опт-цена ₽ — кол-во шт.`, сгруппировано по поставщику,
несколькими сообщениями (лимит Telegram 4096 символов).

## Состав отчёта (бизнес-правило)

«**Крым для всех + Бриз со всех складов**»:
- Rusklimat / Daichi — только то, что есть в Крыму (склад «Симферополь»), количество = крымский остаток.
- Бриз — на любом складе (Крым + материк Шерризон/Ростов), количество = сумма по всем складам.

Материк Rusklimat/Daichi намеренно не включаем — иначе отчёт раздулся бы почти на
весь каталог (Краснодар 52k, Киржач 30k единиц).

## Зависимость от сайта

Данные (товары, остатки, цены) в БД готовит синхронизация сайта SplitHome. Сервис
их только читает. Важно: правильная **опт-цена Бриза** (`price_wholesale` = base/закупка)
обеспечивается 1-строчным фиксом в `sync_stock` сайта — он должен остаться в проекте сайта.

## Установка

```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # заполнить DB_PASSWORD и TELEGRAM_BOT_TOKEN из /opt/oasis/.env сайта
```

## Запуск

```bash
python -m stock_report_bot.main        # собрать и отправить отчёт один раз
```

## Расписание (раз в сутки, 09:00 МСК)

**cron** на сервере:
```cron
0 9 * * *  cd /opt/splithub_api_telegram && /opt/splithub_api_telegram/.venv/bin/python -m stock_report_bot.main >> /var/log/stock_report.log 2>&1
```

**systemd timer** (альтернатива): `stock-report.service` + `stock-report.timer`
с `OnCalendar=*-*-* 09:00:00` и `Persistent=true`.

> Подключение к БД: на сервере PostgreSQL — это docker-контейнер `db`. Либо
> опубликуйте порт (тогда `DB_HOST=localhost`), либо запустите сервис в той же
> docker-сети сайта с `DB_HOST=db`.

## Тесты

```bash
python -m unittest discover -s tests -v
```
Тесты `tests/test_report.py` проверяют группировку/количество/чанкинг на чистом
Python (без БД и сети).

## Структура

```
stock_report_bot/
  config.py     — чтение .env (БД + Telegram)
  db.py         — SQL-запрос остатков к БД сайта (read-only)
  report.py     — сборка текста (группировка/цена/чанкинг), чистые функции
  telegram.py   — отправка в Telegram (UTF-8 charset обязателен)
  main.py       — точка входа: собрать → отправить
tests/test_report.py
docs/PLAN.md
```
