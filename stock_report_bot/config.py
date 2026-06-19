"""Конфигурация сервиса. Читает .env рядом с проектом (python-decouple),
с fallback на переменные окружения."""
import os

from decouple import Config, RepositoryEnv, config as env_config

_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'
)
config = Config(RepositoryEnv(_ENV_PATH)) if os.path.exists(_ENV_PATH) else env_config

# БД сайта (read-only): те же значения, что в /opt/oasis/.env проекта сайта.
DB = {
    'host': config('DB_HOST', default='localhost'),
    'port': config('DB_PORT', default='5432'),
    'dbname': config('DB_NAME'),
    'user': config('DB_USER'),
    'password': config('DB_PASSWORD'),
}

TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_OWNER_CHAT_ID = config('TELEGRAM_OWNER_CHAT_ID', default='')
TELEGRAM_API_URL = config('TELEGRAM_API_URL', default='https://api.telegram.org')

# Бриз API — нужен ТОЛЬКО чтобы получить опт-цену (base) Бриза напрямую: в БД
# сайта у Бриза лежит розница, а опт Бриз отдаёт лишь в своём API. Ключ — тот же,
# что в /opt/oasis/.env сайта (BREEZ_AUTH_HEADER). Пусто → опт Бриза = цена из БД.
BREEZ_BASE_URL = config('BREEZ_BASE_URL', default='https://api.breez.ru/v1/')
BREEZ_AUTH_HEADER = config('BREEZ_AUTH_HEADER', default='')

# Фотоген-агент: URL API и токен. Stock Bot и фотоген — на одном VPS, поэтому URL —
# localhost. Токен = API_TOKEN из .env фотоген-агента. Пусто → кнопка «Создать
# карточку» вернёт ошибку «не задан» (см. fotogen_bridge.submit_card).
FOTOGEN_API_URL = config('FOTOGEN_API_URL', default='')
FOTOGEN_API_TOKEN = config('FOTOGEN_API_TOKEN', default='')

# JAC — 4-й поставщик без API. Путь к JSON, который пишет скрапер b2b-jac.com
# (проект osatakti_mdv_b2b, файл jac_stock_latest.json). Пусто → JAC не включается.
JAC_STOCK_JSON = config('JAC_STOCK_JSON', default='')
# ТТХ карточек JAC (jac_specs_latest.json, команда `specs` скрапера). Пусто →
# меню/отчёт работают без характеристик.
JAC_SPECS_JSON = config('JAC_SPECS_JSON', default='')
# УТП серий JAC (jac_utp_latest.json — отобранные владельцем преимущества по сериям).
# Пусто → меню работает без блока УТП.
JAC_UTP_JSON = config('JAC_UTP_JSON', default='')
# Фото серий JAC (jac_photos_latest.json: {бренд:{серия: URL|имя_файла}}). Локальные
# файлы (THAICON) — в подпапке photos/ рядом. Пусто → карточка JAC без фото.
JAC_PHOTOS_JSON = config('JAC_PHOTOS_JSON', default='')
