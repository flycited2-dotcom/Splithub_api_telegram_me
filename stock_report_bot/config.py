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

# JAC — 4-й поставщик без API. Путь к JSON, который пишет скрапер b2b-jac.com
# (проект osatakti_mdv_b2b, файл jac_stock_latest.json). Пусто → JAC не включается.
JAC_STOCK_JSON = config('JAC_STOCK_JSON', default='')
