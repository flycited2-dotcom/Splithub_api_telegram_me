"""Separate rendering style from publishing destination in the existing photogen service.

Apply to the two saved source files only after checking the live server. This
does not queue generation or publish cards. Every replacement is version-checked.
"""
import ast

def replace(text, old, new, count=1):
    if text.count(old)!=count:
        raise ValueError('Photogen source changed; patch requires review')
    return text.replace(old,new)

def publication_mode(row):
    return (row['publish_mode'] if 'publish_mode' in row.keys() else None) or row['mode']

def patch_sources(api, bot):
    api=api.replace('\r\n','\n'); bot=bot.replace('\r\n','\n')
    api=replace(api,'"ALTER TABLE jobs ADD COLUMN request_hash TEXT"):',
        '"ALTER TABLE jobs ADD COLUMN request_hash TEXT",\n                "ALTER TABLE jobs ADD COLUMN publish_mode TEXT"):')
    api=replace(api,'    caption: str = Form(""),\n    assigned_account:',
        '    caption: str = Form(""),\n    publish_mode: str = Form(""),\n    assigned_account:')
    api=replace(api,'    _check_request_key(request_key)\n    photo_bytes = await photo.read()',
        '    if publish_mode not in ("", "conditioner"):\n        raise HTTPException(status_code=400, detail="Invalid publish_mode")\n    _check_request_key(request_key)\n    photo_bytes = await photo.read()')
    api=replace(api,'json.dumps(["card", mode, specs, brand.strip(), model.strip(), chat_id, caption],',
        'json.dumps(["card", mode, specs, brand.strip(), model.strip(), chat_id, caption] + ([publish_mode] if publish_mode else []),')
    api=replace(api,'"assigned_account, request_key, request_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
        '"assigned_account, request_key, request_hash, publish_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",')
    api=replace(api,'model or None, caption or None, account, request_key or None, request_hash),',
        'model or None, caption or None, account, request_key or None, request_hash, publish_mode or None),')
    bot=replace(bot,'"ALTER TABLE jobs ADD COLUMN caption TEXT",',
        '"ALTER TABLE jobs ADD COLUMN caption TEXT",\n            "ALTER TABLE jobs ADD COLUMN publish_mode TEXT",')
    marker='def _conditioner_result_markup(job_id: int, has_channel: bool) -> InlineKeyboardMarkup:'
    helper='def _publication_mode(row):\n    return (row["publish_mode"] if "publish_mode" in row.keys() else None) or row["mode"]\n\n\n'
    bot=replace(bot,marker,helper+marker)
    bot=replace(bot,'if action == "publish":\n        # Владелец подтвердил публикацию готовой карточки (режим подтверждения).\n        job_mode = row["mode"] if "mode" in row.keys() else DEFAULT_MODE',
        'if action == "publish":\n        # Preserve the explicitly selected publishing destination, regardless of render style.\n        job_mode = _publication_mode(row)')
    bot=replace(bot,'channel_id = MODES_CHANNELS.get(job_mode, "")\n\n                    if job_mode == "conditioner":',
        'channel_id = MODES_CHANNELS.get(_publication_mode(row), "")\n\n                    if _publication_mode(row) == "conditioner":')
    bot=replace(bot,'"INSERT INTO jobs (chat_id, input_filename, mode, specs, brand, model, caption) "\n                "VALUES (?, ?, ?, ?, ?, ?, ?)",',
        '"INSERT INTO jobs (chat_id, input_filename, mode, specs, brand, model, caption, publish_mode) "\n                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",',count=2)
    bot=replace(bot,'row["mode"], row["specs"], row["brand"], row["model"], row["caption"]),',
        'row["mode"], row["specs"], row["brand"], row["model"], row["caption"],\n                 row["publish_mode"] if "publish_mode" in row.keys() else None),',count=2)
    ast.parse(api); ast.parse(bot)
    return api,bot
