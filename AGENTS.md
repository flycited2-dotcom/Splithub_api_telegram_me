# Telegram bot deployment

- Active production is **212.116.115.150** (SSH alias `sprintbox-itp`), project
  `/opt/splithub_api_telegram`. Inspect the current server state before deploying.
- **213.109.202.45 is an obsolete installation.** Its menu bot and morning timer
  are disabled. Do not start them alongside the active server: both installations
  use the same Telegram token and competing getUpdates calls cause HTTP 409.
- Preserve existing server-specific `run_bot.py`, `run_bot.sh`, `run_report.py`,
  and `run_daily.sh` network wrappers. Do not copy wrappers between servers.
- Keep the previous series price list, stock list and photo generation accessible.
  New navigation is group → supplier → subcategory → product. Client cards contain
  the series photo and all matching models; TTX/UTP cards are a separate action.
- Keep back/home buttons on every interactive screen. Download and search are
  separate actions. Download uses Telegram's supported `style=primary`.
- Test actual callback processing after deployment, not only sendMessage delivery.
  Check sanitized logs for 409, and run the unittest suite.
- Never print Telegram request URLs in logs: they contain the bot token. Never
  commit .env, supplier data exports or database files.
- Morning report: 08:30 Europe/Moscow. Do not leave a duplicate 09:00 cron entry.

See `docs/CATALOG-DEPLOYMENT.md` for deployment verification and rollback records.
