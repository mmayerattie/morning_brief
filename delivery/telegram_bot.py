"""
Sends briefing messages to a Telegram chat via the Bot API.

We use plain httpx rather than the python-telegram-bot library because
this is a send-only use case — the library's overhead (polling, handlers,
webhook management) is unnecessary here.

The bot must be started first: talk to @BotFather on Telegram to create one.
Get your chat_id by talking to @userinfobot — it replies with your user ID.
"""

import asyncio
import os
import re

import httpx

from utils.logger import get_logger

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _strip_html(text: str) -> str:
    """Remove all HTML tags — used as fallback when Telegram rejects the HTML."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text


async def _send_chunk(client: httpx.AsyncClient, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = TELEGRAM_API.format(token=token)

    # Try with HTML formatting first; fall back to plain text if Telegram rejects it
    for parse_mode in ("HTML", None):
        payload: dict = {"chat_id": chat_id, "text": text}
        if parse_mode == "HTML":
            payload["parse_mode"] = "HTML"
        else:
            payload["text"] = _strip_html(text)
            logger.warning("HTML rejected by Telegram, retrying as plain text")

        response = await client.post(url, json=payload, timeout=30)

        if response.status_code == 400:
            logger.error("Telegram 400 — response body: %s", response.text)
            if parse_mode == "HTML":
                continue  # retry as plain text
            raise httpx.HTTPStatusError(
                response.text, request=response.request, response=response
            )

        response.raise_for_status()
        logger.info("Chunk sent (%d chars, mode=%s)", len(payload["text"]), parse_mode or "plain")
        return


async def send_briefing(chunks: list[str]) -> None:
    """Send all message chunks to the Telegram chat, with a short delay between them."""
    async with httpx.AsyncClient() as client:
        for i, chunk in enumerate(chunks):
            await _send_chunk(client, chunk)
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)  # respect Telegram's rate limits
    logger.info("Briefing delivered (%d chunk(s))", len(chunks))
