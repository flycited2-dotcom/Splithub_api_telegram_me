r"""Разовая отправка ТЕСТА JAC себе в Telegram (остатки + меню наценки с ТТХ).

Запуск (из папки проекта бота):
    .\.venv\Scripts\python send_jac_test.py

Берёт TELEGRAM_BOT_TOKEN и TELEGRAM_OWNER_CHAT_ID из .env (можно переопределить
--token/--chat). БД НЕ требуется. Данные скрапера — по умолчанию из соседнего
проекта osatakti_mdv_b2b\data (или --data ПУТЬ).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent


def read_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main():
    env = read_env(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=env.get("TELEGRAM_BOT_TOKEN", ""))
    ap.add_argument("--chat", default=env.get("TELEGRAM_OWNER_CHAT_ID", ""))
    ap.add_argument("--data", default=str(ROOT.parent / "osatakti_mdv_b2b" / "data"))
    ap.add_argument("--brands", default="MDV,EUROKLIMAT,THAICON")
    ap.add_argument("--markup", type=int, default=7, help="процент наценки для примера меню")
    a = ap.parse_args()
    if not a.token or not a.chat:
        sys.exit("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_CHAT_ID в .env (или --token/--chat).")

    sys.path.insert(0, str(ROOT))
    from stock_report_bot.jac import load_jac_rows
    from stock_report_bot.jac_specs import load_specs, spec_lines_for
    from stock_report_bot.report import build_report_chunks
    from stock_report_bot import menu

    os.environ["NO_PROXY"] = "*"             # мимо системного SOCKS-прокси
    sess = requests.Session()
    sess.trust_env = False

    def send(text: str) -> bool:
        r = sess.post(
            f"https://api.telegram.org/bot{a.token}/sendMessage",
            data=json.dumps({"chat_id": a.chat, "text": text, "parse_mode": "HTML",
                             "disable_web_page_preview": True}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30,
        ).json()
        if not r.get("ok"):
            print("  ! Telegram:", r.get("description"))
        return bool(r.get("ok"))

    me = sess.get(f"https://api.telegram.org/bot{a.token}/getMe", timeout=20).json()
    if not me.get("ok"):
        sys.exit(f"Токен невалиден: {me.get('description')}")
    print("Бот:", me["result"].get("username"), "| чат:", a.chat)

    data = Path(a.data)
    rows = load_jac_rows(str(data / "jac_stock_latest.json"))
    specs = load_specs(str(data / "jac_specs_latest.json"))
    brands = {b.strip() for b in a.brands.split(",") if b.strip()}

    # A) остатки по выбранным брендам
    rr = [r for r in rows if r["brand"] in brands]
    print(f"Остатки: {len(rr)} позиций по {', '.join(sorted(brands))}")
    chunks = build_report_chunks(rr)
    for i, ch in enumerate(chunks):
        head = f"🧪 <b>ТЕСТ JAC</b> — остатки {', '.join(sorted(brands))}\n\n"
        print("  A", i + 1, send((head + ch) if i == 0 else ch))
        time.sleep(1.3)

    # B) пример меню наценки с ТТХ (THAICON, первая серия — если есть)
    if "THAICON" in brands and menu.series_for(rows, "jac", "THAICON"):
        s0 = menu.series_for(rows, "jac", "THAICON")[0]
        items = menu.positions_for(rows, "jac", "THAICON", s0)
        sl = spec_lines_for(specs, [r["title"] for r in items])
        for ch in menu.build_priced_message(rows, "jac", "THAICON", s0, a.markup, None, spec_lines=sl):
            head = f"🧪 <b>ТЕСТ</b> — меню наценки +{a.markup}% с характеристиками\n\n"
            print("  B", send(head + ch))
            time.sleep(1.3)
    print("Готово.")


if __name__ == "__main__":
    main()
