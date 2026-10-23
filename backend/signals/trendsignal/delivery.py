"""Optional delivery of the brief to a Telegram chat (only when TELEGRAM_* env vars are set)."""

from __future__ import annotations

import logging
import re

import httpx

from trendsignal.config import Settings

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_CHUNK_CHARS = 4000  # Telegram's limit is 4096 characters per message


def to_plain_text(markdown: str) -> str:
    text = re.sub(r"\s*\[S\d+\]", "", markdown)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1: \2", text)
    text = re.sub(r"\*\*|__|\*", "", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _chunks(text: str, size: int) -> list[str]:
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph[:size]
    if current:
        chunks.append(current)
    return chunks


def send_telegram(settings: Settings, markdown: str, http: httpx.Client | None = None) -> tuple[bool, str | None]:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False, "Telegram not configured"
    client = http or httpx.Client(timeout=20.0)
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        for chunk in _chunks(to_plain_text(markdown), TELEGRAM_CHUNK_CHARS):
            response = client.post(url, json={"chat_id": settings.telegram_chat_id, "text": chunk,
                                              "disable_web_page_preview": True})
            if response.status_code != 200:
                return False, f"Telegram returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        log.warning("Telegram delivery failed: %s", exc.__class__.__name__)
        return False, f"Telegram delivery failed: {exc.__class__.__name__}"
    finally:
        if http is None:
            client.close()
    return True, None
