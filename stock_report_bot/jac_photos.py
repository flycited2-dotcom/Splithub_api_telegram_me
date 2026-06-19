"""Фото серий JAC из jac_photos_latest.json (готовит скрапер `osatakti_mdv_b2b`).

Формат: {бренд: {СЕРИЯ_В_ВЕРХНЕМ_РЕГИСТРЕ: ref}}, где ref —
  • URL вендора (MDV/MHI/EUROKLIMAT) — фотоген скачает напрямую; или
  • имя локального файла (THAICON, фото лежат рядом, в подпапке photos/) — отдаём байтами.

Связка по бренду + нормализованной серии (как jac_utp). Файла нет/серии нет → None,
кнопка «Создать карточку» скажет «фото не найдено» (не падаем).
"""
import json
import logging
import os

logger = logging.getLogger('stock_report_bot.jac_photos')


def _configured_path():
    try:
        from stock_report_bot.config import JAC_PHOTOS_JSON
        return JAC_PHOTOS_JSON
    except Exception:
        return ''


def normalize_series(s):
    return ' '.join((s or '').upper().split())


def load_photos(path=None):
    """{бренд:{СЕРИЯ: ref}}; путь пуст/файла нет/битый → {}."""
    path = path if path is not None else _configured_path()
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning('фото JAC недоступны (%s) — без фото карточек', e)
        return {}


def photo_ref(photos, brand, series):
    """Сырая ссылка на фото серии (URL или имя локального файла); нет → None."""
    return (photos.get(brand) or {}).get(normalize_series(series)) or None


def resolve_photo(ref, json_path=None):
    """ref → то, что отдаём в submit_card: URL как есть, либо АБСОЛЮТНЫЙ путь к
    локальному файлу (в подпапке `photos/` рядом с jac_photos_latest.json)."""
    if not ref:
        return None
    if ref.startswith('http://') or ref.startswith('https://'):
        return ref
    base = os.path.dirname(json_path if json_path is not None else _configured_path())
    return os.path.join(base, 'photos', ref)
