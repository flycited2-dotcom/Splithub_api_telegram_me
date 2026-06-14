# Техническое задание: Интеграция Stock Bot с фотоген-агентом

**Проект:** SplitHub — автоматизация генерации карточек товаров для Telegram-канала  
**Дата составления:** 2026-06-14  
**Автор:** составлено по итогам технического анализа двух репозиториев  
**Статус:** готово к реализации

---

## 1. Контекст и цель

### 1.1 Что есть сейчас

У владельца работают **два отдельных инструмента**:

**Stock Bot** (`Splithub_api_telegram_me`)
- Интерактивный Telegram-бот для владельца магазина климатической техники SplitHub.ru
- Показывает остатки товаров по трём поставщикам (Бриз, Русклимат, Daichi) только по Крыму (Симферополь)
- Навигация: Поставщик → Бренд → Серия → Наценка → Список позиций с ценой и фото
- Данные: read-only из PostgreSQL сайта SplitHome
- Умеет извлекать технические характеристики из БД (`specs.py`)
- Работает на VPS, long-polling

**фотоген-агент** (`agent_convert_foto_rituailb2b2`)
- Telegram-бот, принимающий фото товара + характеристики
- Через Chrome/Playwright автоматически открывает ChatGPT-проект
- Загружает эталонные фото стиля + фото товара + промпт с характеристиками
- Генерирует (~2 мин) премиальную рекламную карточку
- Отправляет результат обратно в Telegram
- Режим `conditioner` (кондиционеры, стиль SplitHub) **уже существует и настроен**
- Архитектура: VPS (бот + SQLite очередь + HTTP API) + локальный ПК (Chrome + Playwright)

### 1.2 Текущая ручная цепочка (что хочется автоматизировать)

```
[Stock Bot] → пользователь видит товар
    ↓ (вручную копирует характеристики)
[фотоген-бот] → вводит характеристики
    ↓ (вручную отправляет фото)
[фотоген-бот] → ~2 мин → присылает карточку
    ↓ (вручную проверяет и решает публиковать ли)
[Telegram-канал] → публикация
```

### 1.3 Целевой результат

```
[Stock Bot] → пользователь нажимает «🎨 Создать карточку»
    ↓ (автоматически: фото + характеристики → фотоген API)
[фотоген-агент] → ~2 мин → карточка готова
    ↓ (автоматически: пользователю в фотоген-чат)
[Кнопки: ✅ Опубликовать / 🔄 Переделать / ❌ Отмена]
    ↓ (одно нажатие)
[Telegram-канал SplitHub]
```

---

## 2. Архитектура решения

```
┌─────────────────────────────────────────────────────────┐
│  Stock Bot VPS                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  stock_report_bot/bot.py  (long-polling)         │   │
│  │  Пользователь нажимает «🎨 Создать карточку»    │   │
│  │         ↓                                        │   │
│  │  fotogen_bridge.submit_card(...)                 │   │
│  │    1. скачивает фото по image_url из БД          │   │
│  │    2. извлекает specs.build_specs_for_card(...)  │   │
│  │    3. POST /api/submit-job → фотоген VPS         │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────┘
                               │ HTTP POST (multipart)
                               ▼
┌─────────────────────────────────────────────────────────┐
│  фотоген VPS  213.109.202.45                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  vps_api.py  POST /api/submit-job  (НОВЫЙ)       │   │
│  │    → сохраняет фото в input/                     │   │
│  │    → INSERT INTO jobs (mode='conditioner', ...)  │   │
│  └──────────────────────────────────────────────────┘   │
│                    ↓ SQLite queue.db                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │  SSH-туннель → локальный ПК                      │   │
│  │  remote_agent.py → Chrome/Playwright → ChatGPT   │   │
│  │  Промпт: conditioner.txt + {{SPECS}} из запроса  │   │
│  │  Эталоны: reference/conditioner/etalon_*.png     │   │
│  │                 ~2 минуты                        │   │
│  └──────────────────────────────────────────────────┘   │
│                    ↓ result готов                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │  vps_bot.py  result_sender  (ИЗМЕНЁН)            │   │
│  │    → НЕ постит сразу в канал                     │   │
│  │    → шлёт пользователю с кнопками:               │   │
│  │      [✅ Опубликовать] [🔄 Переделать] [❌ Нет]  │   │
│  │    → callback publish:{job_id}                   │   │
│  │       → bot.send_photo(CHANNEL_ID, ...)          │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Репозитории

| Репозиторий | Назначение | Ветка разработки |
|-------------|-----------|-----------------|
| `flycited2-dotcom/Splithub_api_telegram_me` | Stock Bot | `claude/ac-agent-automation-pipeline-8psbi7` |
| `flycited2-dotcom/agent_convert_foto_rituailb2b2` | фотоген-агент | `main` (или создать feature-ветку) |

> **Важно:** фотоген-бот работает только в связке с **локальным ПК владельца** (Windows, Chrome на порту 9333, `remote_agent.py`). Переносить на отдельный VPS невозможно без переконфигурирования всей системы.

---

## 4. Пошаговый план реализации

### Этап 1: Подготовка (нулевой риск для работающих ботов)

**Шаг 1.1 — Новые переменные окружения в Stock Bot**

Файл: `Splithub_api_telegram_me/.env.example`

Добавить строки:
```env
# фотоген-агент: URL API и токен доступа
FOTOGEN_API_URL=http://213.109.202.45:8765
FOTOGEN_API_TOKEN=<тот же API_TOKEN что в фотоген .env>
```

Файл: `Splithub_api_telegram_me/.env` (на сервере) — добавить те же переменные с реальными значениями.

**Шаг 1.2 — Обновить `stock_report_bot/config.py`**

Добавить в конец файла:
```python
FOTOGEN_API_URL   = config('FOTOGEN_API_URL', default='')
FOTOGEN_API_TOKEN = config('FOTOGEN_API_TOKEN', default='')
```

---

### Этап 2: Stock Bot — извлечение характеристик для карточки

**Шаг 2.1 — Добавить функцию в `stock_report_bot/specs.py`**

Добавить в конец файла (после `build_specs_message`):

```python
def build_specs_for_card(tech_rows, brand, series, source, utp_raw=None, titles=None):
    """Список строк преимуществ для подстановки в {{SPECS}} промпта фотоген-агента.
    Plain text, без HTML-тегов — готов к отправке в ChatGPT.

    Возвращает список строк вида:
      ['⚡ Класс энергоэффективности A++', '❄️ Инверторная технология', ...]
    """
    t = _Tech(tech_rows, titles)
    lines = [ln for extract in _FEATURES if (ln := extract(t))]
    lines += _utp_extras(t, source, utp_raw)
    return lines
```

**Почему это безопасно:** новая функция, ничего не меняет в существующем коде.

---

### Этап 3: Stock Bot — HTTP-мост к фотоген API

**Шаг 3.1 — Создать `stock_report_bot/fotogen_bridge.py`**

Новый файл:
```python
"""Отправка задачи на генерацию карточки товара в фотоген-агент.

Вызывается из bot.py при нажатии «🎨 Создать карточку».
Скачивает фото товара по URL и отправляет multipart-запрос на /api/submit-job
фотоген-агента. Синхронный (stock-бот не использует asyncio).
"""
import io
import logging
import urllib.request

import requests

from stock_report_bot.config import FOTOGEN_API_URL, FOTOGEN_API_TOKEN

log = logging.getLogger('stock_report_bot.fotogen_bridge')

_TIMEOUT = 20   # сек на скачивание фото и отправку


def submit_card(
    photo_url: str,
    brand: str,
    model: str,
    specs_lines: list,
    chat_id: int,
) -> tuple[bool, str]:
    """Отправить задачу генерации карточки в фотоген-агент.

    Args:
        photo_url:   URL фото товара из БД сайта (catalog_productimage.url)
        brand:       Бренд (напр. «Samsung»)
        model:       Серия/модель (напр. «WindFree Comfort»)
        specs_lines: Список строк преимуществ для {{SPECS}} промпта
        chat_id:     Telegram chat_id владельца — куда фотоген отправит результат

    Returns:
        (True, 'ok') при успехе; (False, 'текст ошибки') при сбое.
    """
    if not FOTOGEN_API_URL or not FOTOGEN_API_TOKEN:
        return False, "FOTOGEN_API_URL или FOTOGEN_API_TOKEN не задан в .env"

    # Скачиваем фото товара
    try:
        req = urllib.request.Request(
            photo_url,
            headers={'User-Agent': 'SplithubStockBot/1.0'},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            photo_bytes = resp.read()
    except Exception as exc:
        log.warning('submit_card: не удалось скачать фото %s: %s', photo_url, exc)
        return False, f"Не удалось скачать фото товара: {exc}"

    specs_text = '\n'.join(specs_lines) if specs_lines else ''

    try:
        resp = requests.post(
            f"{FOTOGEN_API_URL.rstrip('/')}/api/submit-job",
            headers={'x-agent-token': FOTOGEN_API_TOKEN},
            data={
                'mode':    'conditioner',
                'specs':   specs_text,
                'brand':   brand or '',
                'model':   model or '',
                'chat_id': str(chat_id),
            },
            files={
                'photo': (f"{brand}_{model}.jpg".replace(' ', '_'), io.BytesIO(photo_bytes), 'image/jpeg'),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        log.info('submit_card OK: %s %s → job queued', brand, model)
        return True, 'ok'
    except Exception as exc:
        log.warning('submit_card: ошибка запроса к фотоген API: %s', exc)
        return False, f"Ошибка отправки в фотоген: {exc}"
```

**Зависимость:** нужна библиотека `requests`. Добавить в `requirements.txt`:
```
requests>=2.31
```
(проверить, не стоит ли уже — если стоит, не дублировать)

---

### Этап 4: Stock Bot — кнопка «🎨 Создать карточку»

**Шаг 4.1 — Добавить callback-код и кнопку в `stock_report_bot/menu.py`**

В функцию `kb_markup(source, brand_idx, series_idx)` добавить одну кнопку в конце:

```python
def kb_markup(source, brand_idx, series_idx):
    code = SRC_CODE[source]
    disc = [_pct_btn(code, brand_idx, series_idx, p) for p in DISCOUNT_PCTS]
    row1 = [_pct_btn(code, brand_idx, series_idx, p) for p in MARKUP_PCTS[:5]]
    row2 = [_pct_btn(code, brand_idx, series_idx, p) for p in MARKUP_PCTS[5:]]
    card = [_btn('🎨 Создать карточку для канала', cb_pack('c', code, brand_idx, series_idx))]  # НОВОЕ
    back = [_btn('⬅ Назад', cb_pack('s', code, brand_idx, 0))]
    return _kb([disc, row1, row2, card, back])  # card добавлен
```

**Шаг 4.2 — Добавить обработчик в `stock_report_bot/bot.py`**

Добавить импорт вверху файла:
```python
from stock_report_bot import menu, specs, fotogen_bridge  # добавить fotogen_bridge
```

В функции `_handle_callback`, в блок `try`, после обработки `elif action in ('gp', 'gs'):` добавить:

```python
elif action == 'c':                       # c|code|bidx|sidx — создать карточку
    code, bidx, sidx = parts[1], int(parts[2]), int(parts[3])
    source, brand, series = _resolve(rows, code, bidx, sidx)

    positions = menu.positions_for(rows, source, brand, series)
    nc_codes = [r.get('nc_code') for r in positions if r.get('nc_code')]
    titles = [r.get('title') for r in positions]

    utp_raw = None
    if source == 'breeze':
        utp_map = _breez_utp()
        utp_raw = next((utp_map.get(nc) for nc in nc_codes if utp_map.get(nc)), None)

    spec_lines = specs.build_specs_for_card(
        fetch_tech_values(nc_codes),
        brand,
        menu.short_series(series),
        source,
        utp_raw=utp_raw,
        titles=titles,
    )
    photo_url = menu.series_image(rows, source, brand, series)

    if not photo_url:
        edit_message_text(chat_id, message_id,
            '⚠️ Фото товара не найдено в базе. Загрузи фото вручную в фотоген-боте.',
            None)
    else:
        ok, err = fotogen_bridge.submit_card(
            photo_url=photo_url,
            brand=brand,
            model=menu.short_series(series),
            specs_lines=spec_lines,
            chat_id=chat_id,
        )
        if ok:
            edit_message_text(chat_id, message_id,
                f'⏳ <b>{brand} {menu.short_series(series)}</b>\n'
                'Карточка отправлена в фотоген-агент. Готовая карточка придёт '
                'через ~2 мин в чат фотоген-бота с кнопками подтверждения.',
                None)
        else:
            edit_message_text(chat_id, message_id,
                f'❌ Не удалось отправить задачу: {err}', None)
```

---

### Этап 5: фотоген-агент — новый endpoint приёма задачи

**Файл:** `agent_convert_foto_rituailb2b2/vps/vps_api.py`

Добавить новый endpoint после существующего `@app.post("/api/fail/{job_id}")`:

```python
@app.post("/api/submit-job")
async def submit_job(
    x_agent_token: str = Header(...),
    mode: str = Form("conditioner"),
    specs: str = Form(""),
    brand: str = Form(""),
    model: str = Form(""),
    chat_id: int = Form(...),
    photo: UploadFile = File(...),
):
    """Внешний клиент (Stock Bot) ставит задачу в очередь напрямую через API.

    Принимает фото товара + характеристики, создаёт job в queue.db.
    Результат будет отправлен боту в чат chat_id через result_sender.
    """
    _auth(x_agent_token)

    if mode not in ("conditioner", "mcp", "kbt", "ritual", "wreath"):
        raise HTTPException(status_code=400, detail=f"Неизвестный режим: {mode}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    ext = Path(photo.filename or "input.jpg").suffix.lower() or ".jpg"
    filename = f"ext_{ts}{ext}"
    target = INPUT_DIR / filename
    target.write_bytes(await photo.read())

    log.info("submit-job: mode=%s brand=%s model=%s chat_id=%s file=%s",
             mode, brand, model, chat_id, filename)

    with db_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (chat_id, input_filename, mode, specs, brand, model) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, filename, mode, specs or None, brand or None, model or None),
        )
        conn.commit()

    return {"ok": True, "queued": filename}
```

**После добавления** — перезапустить `ritualb2b-api.service` на VPS:
```bash
systemctl restart ritualb2b-api
journalctl -u ritualb2b-api --since="1 minute ago" --no-pager
```

---

### Этап 6: фотоген-агент — режим подтверждения перед публикацией

Это единственное изменение, затрагивающее **существующее поведение** фотоген-бота.

**Что изменится:** для режима `conditioner`, когда `CONDITIONER_TELEGRAM_CHANNEL_ID` задан, бот **больше не будет постить напрямую в канал**. Вместо этого пришлёт карточку владельцу с кнопками.

**Файл:** `agent_convert_foto_rituailb2b2/vps/vps_bot.py`

**Шаг 6.1 — Добавить новый callback-код `publish`**

В функции `on_callback`, в блок обработки actions, добавить перед `if action == "redo":`:

```python
if action == "publish":
    # Пользователь нажал «✅ Опубликовать в канал»
    job_mode = row["mode"] if "mode" in row.keys() else DEFAULT_MODE
    channel_id = MODES_CHANNELS.get(job_mode, "")
    if not channel_id:
        await q.message.reply_text(
            f"⚠️ Канал для режима «{MODES_LABELS.get(job_mode, job_mode)}» не настроен.\n"
            "Добавьте в .env: <MODE>_TELEGRAM_CHANNEL_ID",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    out_path = OUTPUT_DIR / row["output_filename"]
    if not out_path.exists():
        await q.message.reply_text(
            f"⚠️ Файл результата не найден: {row['output_filename']}",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    try:
        with open(out_path, "rb") as f:
            await q.message.bot.send_document(
                chat_id=int(channel_id),
                document=InputFile(f, filename=row["output_filename"]),
                caption=row["output_filename"],
                read_timeout=120, write_timeout=120, connect_timeout=30,
            )
        await q.message.reply_text(
            f"✅ Опубликовано в канал!\n{row['output_filename']}",
            reply_markup=MAIN_KEYBOARD,
        )
        log.info("publish: канал %s ← %s", channel_id, row["output_filename"])
    except Exception as e:
        await q.message.reply_text(
            f"❌ Ошибка публикации: {e}", reply_markup=MAIN_KEYBOARD,
        )
    return
```

**Шаг 6.2 — Изменить `result_sender` для режима conditioner**

В функции `result_sender`, в блоке `for row in done_rows:`, найти участок:

```python
# БЫЛО:
if channel_id:
    try:
        with open(out_path, "rb") as f:
            await app.bot.send_document(
                chat_id=int(channel_id),
                ...
            )
        ...
    except Exception as e:
        ...
        continue
else:
    # Канал не настроен — fallback в личный чат
    ...
```

Заменить на:

```python
# СТАЛО: всегда показываем пользователю с кнопками (независимо от наличия канала)
keyboard_btns = [
    [InlineKeyboardButton("🔄 Перегенерировать", callback_data=f"redo:{row['id']}")],
    [InlineKeyboardButton("🗑 Удалить (плохой)", callback_data=f"bad:{row['id']}")],
]
if channel_id:
    # Канал есть → показываем кнопку публикации первой
    keyboard_btns.insert(0, [InlineKeyboardButton(
        "✅ Опубликовать в канал", callback_data=f"publish:{row['id']}"
    )])

pending_now = _pending_count()
caption = (
    f"✅ Готово ({mode_label}): {row['output_filename']}\n"
    f"В очереди: {pending_now}"
)
with open(out_path, "rb") as f:
    await app.bot.send_document(
        chat_id=row["chat_id"],
        document=InputFile(f, filename=row["output_filename"]),
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard_btns),
        read_timeout=120, write_timeout=120, connect_timeout=30,
    )
log.info("Карточка → владелец: %s", row["output_filename"])
```

**После изменений** — перезапустить `ritualb2b-bot.service`:
```bash
systemctl restart ritualb2b-bot
journalctl -u ritualb2b-bot --since="1 minute ago" --no-pager
```

---

### Этап 7: Добавить переменную окружения в фотоген

Файл: `agent_convert_foto_rituailb2b2/vps/.env` (на VPS `/root/ritualb2b/.env`)

Убедиться что задано:
```env
CONDITIONER_TELEGRAM_CHANNEL_ID=-100XXXXXXXXXX   # ID Telegram-канала SplitHub
```

Если не задано — результаты будут приходить в личный чат (это тоже работает, кнопка «✅ Опубликовать» всё равно появится, но будет недоступна с пояснением).

---

## 5. Порядок деплоя (не нарушающий работающие боты)

```
Шаг 1  →  Stock Bot: config.py + .env (новые переменные)
           Риск: нулевой. Просто добавляем переменные.

Шаг 2  →  Stock Bot: specs.py (новая функция build_specs_for_card)
           Риск: нулевой. Новая функция, ничего не меняем.

Шаг 3  →  Stock Bot: fotogen_bridge.py (новый файл)
           Риск: нулевой. Новый файл, не импортируется нигде пока.

Шаг 4  →  Stock Bot: menu.py (новая кнопка) + bot.py (новый elif)
           Риск: минимальный. Добавляем кнопку и блок кода.
           Тестируем: открываем меню, видим новую кнопку, нажимаем —
           должно вернуть «❌ Ошибка» (фотоген API ещё не добавлен).
           Это нормально. Старые кнопки наценок работают как прежде.

Шаг 5  →  фотоген VPS API: vps_api.py (новый endpoint)
           Деплой: через paramiko base64-чанками (SFTP ненадёжен).
           Перезапуск: systemctl restart ritualb2b-api
           Тестируем: curl -X POST http://localhost:8765/api/submit-job ...
           Теперь кнопка «🎨 Создать карточку» должна работать,
           фото и specs попадают в очередь агента.

Шаг 6  →  фотоген VPS BOT: vps_bot.py (approval mode)
           Это последнее и единственное изменение поведения существующего бота.
           Деплой + перезапуск: systemctl restart ritualb2b-bot
           Тестируем: создать задачу через кнопку в stock bot,
           убедиться что через ~2 мин приходит карточка с кнопками [✅ 🔄 ❌].
           Нажать ✅ — убедиться что публикуется в канал.
```

---

## 6. Структура изменений по файлам

### `Splithub_api_telegram_me` (Stock Bot)

| Файл | Тип изменения | Описание |
|------|--------------|----------|
| `.env.example` | Добавить 2 строки | `FOTOGEN_API_URL`, `FOTOGEN_API_TOKEN` |
| `.env` (сервер) | Добавить 2 строки | Те же, с реальными значениями |
| `requirements.txt` | Добавить 1 строку | `requests>=2.31` (если нет) |
| `stock_report_bot/config.py` | Добавить 2 строки | Читать новые env-переменные |
| `stock_report_bot/specs.py` | Добавить функцию ~8 строк | `build_specs_for_card()` |
| `stock_report_bot/fotogen_bridge.py` | Новый файл ~60 строк | HTTP-клиент к фотоген API |
| `stock_report_bot/menu.py` | Изменить 2 строки | Кнопка в `kb_markup()` |
| `stock_report_bot/bot.py` | Добавить elif ~30 строк | Обработка callback `'c'` |

### `agent_convert_foto_rituailb2b2` (фотоген-агент)

| Файл | Тип изменения | Описание |
|------|--------------|----------|
| `vps/.env` (сервер) | Проверить/добавить | `CONDITIONER_TELEGRAM_CHANNEL_ID` |
| `vps/vps_api.py` | Добавить endpoint ~30 строк | `POST /api/submit-job` |
| `vps/vps_bot.py` | Изменить result_sender ~30 строк | Approval mode вместо прямой публикации |

**Итого:** ~170 строк нового/изменённого кода в 10 файлах двух репозиториев.

---

## 7. Переменные окружения

### Stock Bot (`.env`)

```env
# Уже существуют (не трогать):
DB_HOST=...
DB_PORT=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_OWNER_CHAT_ID=1264067528
BREEZ_AUTH_HEADER=...

# ДОБАВИТЬ:
FOTOGEN_API_URL=http://213.109.202.45:8765
FOTOGEN_API_TOKEN=<значение API_TOKEN из /root/ritualb2b/.env фотоген-VPS>
```

### фотоген VPS (`/root/ritualb2b/.env`)

```env
# Уже существуют (не трогать):
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...
API_TOKEN=...
...

# ПРОВЕРИТЬ/ДОБАВИТЬ:
CONDITIONER_TELEGRAM_CHANNEL_ID=-100XXXXXXXXXX
```

---

## 8. Тестирование

### 8.1 Smoke test после каждого этапа

**После Шага 4 (кнопка + bridge):**
```
Открыть stock bot → выбрать любой кондиционер
→ нажать «🎨 Создать карточку»
→ ожидаемо: сообщение об ошибке (API недоступен) — это нормально
→ НЕЛЬЗЯ: упасть без ответа, поломать существующие кнопки наценок
```

**После Шага 5 (API endpoint):**
```
Нажать «🎨 Создать карточку»
→ ожидаемо: «⏳ Карточка отправлена в фотоген-агент. Придёт через ~2 мин»
→ Проверить на VPS: sqlite3 /root/ritualb2b/queue.db "SELECT * FROM jobs ORDER BY id DESC LIMIT 1"
→ Статус должен быть pending или processing
```

**После Шага 6 (approval mode):**
```
Через ~2 мин в фотоген-боте должна появиться карточка с тремя кнопками
→ Нажать «✅ Опубликовать в канал»
→ Карточка должна появиться в Telegram-канале
→ Нажать «🔄 Перегенерировать» — должна появиться новая задача в очереди
→ Нажать «❌ Не публиковать» — ничего не должно происходить
```

### 8.2 Регрессионное тестирование (не трогать!)

После каждого этапа проверить, что работает как раньше:
- Ежедневный отчёт `python -m stock_report_bot.main` — отправляет без изменений
- Меню stock bot: кнопки наценок +1%..+10%, скидок −1%..−7% — работают
- фотоген-бот: режимы `ritual`, `wreath`, `mcp`, `kbt` — работают без изменений
- Генерация кондиционера вручную (отправить фото в фотоген-бот) — работает

---

## 9. Важные технические замечания

### Деплой файлов на фотоген VPS
SFTP на VPS ненадёжен (`EOF during negotiation`). Использовать **base64-чанки через SSH**:
```python
import paramiko, base64, math
# Читаем файл → кодируем base64 → заливаем кусками по SSH
# Затем: python3 -c "import base64,pathlib; pathlib.Path('/root/ritualb2b/vps_api.py').write_bytes(base64.b64decode('...'))"
```
После деплоя обязательно:
```bash
python3 -c "import py_compile; py_compile.compile('/root/ritualb2b/vps_api.py')"
systemctl restart ritualb2b-api ritualb2b-bot
```

### Порт фотоген API закрыт снаружи
`FOTOGEN_API_URL=http://213.109.202.45:8765` — порт 8765 закрыт firewall (`INPUT DROP`).
**Stock Bot и фотоген должны быть на одном VPS**, или порт нужно открыть только для IP Stock Bot:
```bash
ufw allow from <IP_STOCK_BOT_VPS> to any port 8765
```
Альтернатива: настроить VPN между VPS или использовать reverse proxy (nginx) с auth-заголовком.

> **Уточнить у владельца:** на каком VPS работает Stock Bot? Если это тот же `213.109.202.45` — порт уже доступен через localhost, URL менять на `http://127.0.0.1:8765`.

### Telegram chat_id между ботами
Результат от фотоген-бота приходит в **чат фотоген-бота** (другой бот, другой чат).
Это нормально — у владельца два Telegram-чата:
- Чат со stock bot (остатки, меню)
- Чат с фотоген-ботом (карточки, публикация)

`chat_id` владельца один и тот же (`1264067543`) — он уже писал обоим ботам.

### Формат `{{SPECS}}` в промпте
Промпт `conditioner.txt` содержит `{{SPECS}}` — он заменяется на текст характеристик.
`build_specs_for_card()` возвращает список строк вида:
```
⚡ Класс энергоэффективности A++
❄️ Инверторная технология
🌡 Работа на обогрев до −25 °C
🔇 Уровень шума от 19 дБ
📶 Wi-Fi управление
```
Каждая строка станет отдельной плашкой на карточке.

---

## 10. Будущие этапы (за рамками этого ТЗ)

### Этап 2 (следующий): Supervisor-агент
После того как базовый пайплайн работает — добавить автоматическую проверку результата перед показом владельцу:
- Вызов Claude API (vision) после генерации: читаемость текста, соответствие бренда, нет ли артефактов
- Если проверка провалена → автоматическая перегенерация (без участия владельца)
- Если ОК → показать владельцу с кнопками

### Этап 3 (перспектива): Массовая генерация
- Выбрать нескольких товаров → поставить их все в очередь одной кнопкой
- Приоритизация очереди (ручные задания vs автоматические)

---

## 11. Контакты и доступы

| Ресурс | Значение |
|--------|---------|
| фотоген VPS | `213.109.202.45` |
| Пользователь VPS | `root` |
| SSH-ключ (деплой) | `~/.ssh/id_ritualb2b_admin` (локальный ПК) |
| Путь проекта фотоген | `/root/ritualb2b/` |
| Systemd-сервисы | `ritualb2b-bot`, `ritualb2b-api` |
| БД фотоген | `/root/ritualb2b/queue.db` |
| Telegram владелец | `@flycited`, chat_id `1264067528` |
| Google аккаунт | `flycited2@gmail.com` |
| Stock Bot репо | `github.com/flycited2-dotcom/Splithub_api_telegram_me` |
| фотоген репо | `github.com/flycited2-dotcom/agent_convert_foto_rituailb2b2` |

---

*Документ составлен на основе анализа обоих репозиториев и технического обсуждения с владельцем 2026-06-14.*
