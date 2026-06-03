"""Точка входа: собрать отчёт об остатках из БД сайта и отправить владельцу
в Telegram. Запуск: `python -m stock_report_bot.main`. Расписание — cron/systemd
раз в сутки (примеры в README)."""
import logging
import sys
import time

from stock_report_bot.config import TELEGRAM_OWNER_CHAT_ID
from stock_report_bot.breez import fetch_breez_base_by_nc
from stock_report_bot.db import fetch_stock_rows
from stock_report_bot.report import build_report_chunks
from stock_report_bot.telegram import send_telegram

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('stock_report_bot')


def main():
    if not TELEGRAM_OWNER_CHAT_ID:
        logger.error('TELEGRAM_OWNER_CHAT_ID не задан — отправлять некому')
        return 1
    rows = fetch_stock_rows()
    breez_base = fetch_breez_base_by_nc()   # опт (base) Бриза напрямую из Бриз API
    chunks = build_report_chunks(rows, breez_base=breez_base)
    sent = 0
    for i, chunk in enumerate(chunks):
        if i:
            time.sleep(1.5)   # не слать залпом в один чат: лимит Telegram ~1 msg/с + щадим socat-прокси
        if send_telegram(chunk, TELEGRAM_OWNER_CHAT_ID):
            sent += 1
    logger.info('Отправлено %d/%d сообщений (позиций: %d)', sent, len(chunks), len(rows))
    return 0 if sent == len(chunks) else 2


if __name__ == '__main__':
    sys.exit(main())
