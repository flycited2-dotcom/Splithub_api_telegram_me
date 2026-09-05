"""Read-only HTTP API климатического каталога для тендерного агента.

Сервис переиспользует уже настроенные источники Telegram-бота: PostgreSQL сайта
(Русклимат, Daichi, Бриз) и JSON JAC. Исходные ключи поставщиков наружу не
передаются. Endpoint умеет только искать и не содержит операций заказа/резерва.
"""
from __future__ import annotations

import hmac
import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from stock_report_bot.breez import fetch_breez_base_by_nc
from stock_report_bot.config import (
    TENDER_CLIMATE_API_HOST,
    TENDER_CLIMATE_API_PORT,
    TENDER_CLIMATE_API_TOKEN,
)
from stock_report_bot.db import fetch_stock_rows
from stock_report_bot.jac import load_jac_rows
from stock_report_bot.report import SUPPLIER_LABELS, _price_for


SEARCH_PATH = "/api/internal/tender-climate-products/search"
MAX_BODY_BYTES = 64 * 1024
MAX_LIMIT = 100
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_GENERIC_TOKENS = {
    "кондиционер", "кондиционеры", "сплит", "система", "системы",
    "климатический", "климатическая", "климатическое", "оборудование",
    "монтаж", "установка", "поставка", "шт", "квт", "кв", "м",
}


def load_catalog_rows() -> list[dict[str, object]]:
    """Собрать единый живой срез четырёх поставщиков, не меняя источники."""
    rows = [dict(row) for row in fetch_stock_rows()]
    rows.extend(dict(row) for row in load_jac_rows())
    try:
        breez_base = fetch_breez_base_by_nc()
    except Exception:
        # Потеря оптовой цены Бриза не должна обрывать остальные источники.
        breez_base = {}
    return [_normalize_row(row, breez_base) for row in rows]


def search_catalog(
    rows: list[dict[str, object]], query: str, *, limit: int = 50
) -> list[dict[str, object]]:
    """Ранжировать каталог по модели/бренду/серии без искусственных дублей."""
    normalized_query = _normalize(query)
    tokens = [token for token in _tokens(normalized_query) if token not in _GENERIC_TOKENS]
    ranked: list[tuple[int, float, str, dict[str, object]]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        source = str(row.get("source") or "")
        sku = str(row.get("sku") or row.get("model") or row.get("name") or "")
        identity = (source.casefold(), sku.casefold())
        if identity in seen:
            continue
        haystack = _normalize(
            " ".join(
                str(row.get(field) or "")
                for field in ("supplier_name", "brand", "series", "model", "sku", "name")
            )
        )
        if tokens:
            matched = sum(token in haystack for token in tokens)
            if matched == 0:
                continue
            score = matched * 10
            if all(token in haystack for token in tokens):
                score += 25
        else:
            score = 1
        if normalized_query and normalized_query in haystack:
            score += 50
        price = row.get("price_gross")
        price_rank = float(price) if price is not None else float("inf")
        ranked.append((-score, price_rank, haystack, row))
        seen.add(identity)
    ranked.sort(key=lambda value: (value[0], value[1], value[2]))
    return [value[3] for value in ranked[: max(1, min(int(limit), MAX_LIMIT))]]


def build_response(payload: dict[str, object], rows: list[dict[str, object]]) -> dict[str, object]:
    query = " ".join(str(payload.get("query") or "").split()).strip()
    if not query:
        raise ValueError("query is required")
    try:
        limit = int(payload.get("limit") or 50)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer") from None
    products = search_catalog(rows, query, limit=limit)
    return {
        "ok": True,
        "query": query,
        "total": len(products),
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "products": [_api_product(row) for row in products],
        "sources": sorted({str(row.get("source") or "") for row in products}),
    }


def _normalize_row(row: dict[str, object], breez_base: dict[str, float]) -> dict[str, object]:
    source = str(row.get("source") or "")
    brand = str(row.get("brand") or "").strip()
    series = str(row.get("series") or "").strip()
    title = str(row.get("title") or "").strip()
    sku = str(row.get("nc_code") or title).strip()
    model = title
    price = _price_for(row, breez_base)
    quantity = _safe_int(row.get("crimea_qty"))
    return {
        "source": source,
        "supplier_name": SUPPLIER_LABELS.get(source, source or "Климатический хаб"),
        "sku": sku,
        "brand": brand,
        "series": series,
        "model": model,
        "name": " ".join(part for part in (brand, series if source == "jac" else "", title) if part),
        "price_gross": float(price) if price is not None else None,
        "stock_quantity": quantity,
        "stock_label": "в наличии" if quantity > 0 else "нет в наличии",
        "warehouse": "Симферополь",
        "delivery_days": None,
        "category": str(row.get("category_id") or "климатическая техника"),
        "product_url": "",
        "specs": {
            "cooling_capacity_hint": row.get("btu_calc"),
            "series": series,
            "category_id": row.get("category_id"),
        },
    }


def _api_product(row: dict[str, object]) -> dict[str, object]:
    quantity = _safe_int(row.get("stock_quantity"))
    source = str(row.get("source") or "")
    supplier = str(row.get("supplier_name") or source)
    specifications = row.get("specs") if isinstance(row.get("specs"), dict) else {}
    attributes = [
        {"label": "Поставщик", "key": "supplier", "value": supplier},
        {"label": "Источник", "key": "source", "value": source},
        {"label": "Склад", "key": "warehouse", "value": str(row.get("warehouse") or "")},
        {"label": "Количество", "key": "stock_quantity", "value": quantity, "numericValue": quantity},
    ]
    attributes.extend(
        {"label": str(key), "key": str(key), "value": value}
        for key, value in specifications.items()
        if value not in (None, "")
    )
    return {
        "source": source,
        "supplierName": supplier,
        "sku": str(row.get("sku") or ""),
        "name": str(row.get("name") or ""),
        "purchasePriceGross": row.get("price_gross"),
        "stockStatus": "available" if quantity > 0 else "out",
        "isAvailable": quantity > 0,
        "stockQuantity": quantity,
        "warehouse": str(row.get("warehouse") or ""),
        "deliveryDays": row.get("delivery_days"),
        "vendor": str(row.get("brand") or ""),
        "part": str(row.get("model") or row.get("sku") or ""),
        "category": str(row.get("category") or "климатическая техника"),
        "description": f"{supplier}; склад {row.get('warehouse') or 'не указан'}; остаток {quantity}",
        "productUrl": str(row.get("product_url") or ""),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "attributes": attributes,
        "specifications": specifications,
    }


def _normalize(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold().replace("ё", "е")))


def _tokens(value: str) -> list[str]:
    return [token for token in value.split() if len(token) >= 2]


def _safe_int(value: object) -> int:
    try:
        return max(0, int(float(str(value or 0))))
    except (TypeError, ValueError):
        return 0


class TenderClimateHandler(BaseHTTPRequestHandler):
    server_version = "TLTClimateTenderAPI/1.0"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != SEARCH_PATH:
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if not _authorized(self.headers.get("Authorization", "")):
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"ok": False, "error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(413, {"ok": False, "error": "invalid_body_size"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            response = build_response(payload, load_catalog_rows())
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        except Exception:
            self._json(503, {"ok": False, "error": "catalog_temporarily_unavailable"})
            return
        self._json(200, response)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "tender-climate-products"})
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        # Не писать bearer token или тело запроса в стандартный access log.
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _authorized(header: str) -> bool:
    expected = TENDER_CLIMATE_API_TOKEN.strip()
    if len(expected) < 32 or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip(), expected)


def main() -> None:
    if len(TENDER_CLIMATE_API_TOKEN.strip()) < 32:
        raise SystemExit("TENDER_CLIMATE_API_TOKEN must contain at least 32 characters")
    server = ThreadingHTTPServer((TENDER_CLIMATE_API_HOST, TENDER_CLIMATE_API_PORT), TenderClimateHandler)
    print(f"Tender climate API listening on {TENDER_CLIMATE_API_HOST}:{TENDER_CLIMATE_API_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
