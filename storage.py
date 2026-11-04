"""Хранение конфигурации бота.

На GitHub Actions файловая система эфемерна, поэтому конфигурация
(config.json) хранится прямо в репозитории: изменения коммитятся через
GITHUB_TOKEN, который Actions даёт воркфлоу автоматически.

Локально (без GITHUB_TOKEN) конфиг пишется в обычный config.json рядом с ботом.
"""
from __future__ import annotations

import base64
import json
import logging
import os

import aiohttp

log = logging.getLogger("bot.storage")

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
REPO = "NewFluger/discord-bot"
BRANCH = "main"
API_URL = "https://api.github.com"
CONFIG_PATH_IN_REPO = "config.json"


def load_local() -> dict:
    """Читает локальный config.json (на Actions это копия из свежего checkout)."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        log.exception("Не удалось прочитать %s", CONFIG_PATH)
        return {}


async def save(config: dict) -> None:
    """Сохраняет конфигурацию: коммитом в репозиторий или локальным файлом."""
    text = json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if not GITHUB_TOKEN:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            fh.write(text)
        log.info("Конфиг сохранён локально: %s", CONFIG_PATH)
        return

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "discord-bot",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{API_URL}/repos/{REPO}/contents/{CONFIG_PATH_IN_REPO}"

    async with aiohttp.ClientSession(headers=headers) as session:
        sha = None
        async with session.get(url) as resp:
            if resp.status == 200:
                sha = (await resp.json()).get("sha")
            elif resp.status != 404:
                body = await resp.text()
                raise RuntimeError(f"GitHub GET config.json -> {resp.status}: {body[:200]}")

        payload = {
            "message": "chore(config): обновление конфигурации бота",
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha

        async with session.put(url, json=payload) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(f"GitHub PUT config.json -> {resp.status}: {body[:200]}")

    log.info("Конфиг сохранён в репозиторий %s", REPO)
