"""
Logs each briefing run to Supabase.

Create this table in your Supabase SQL editor before first use:

    create table briefings (
        id          uuid primary key default gen_random_uuid(),
        created_at  timestamptz default now(),
        date        date not null,
        raw_content text,
        sent        boolean default false,
        error       text
    );

Why always log, even on failure?
The log_briefing call lives in main.py's `finally` block — it runs whether
the pipeline succeeded or failed. This gives you a complete audit trail.
If you wake up and the bot is silent, check Supabase: sent=false + error
tells you exactly what broke. If raw_content is populated but sent=false,
Claude worked but Telegram delivery failed.

Supabase's Python client is synchronous, so we run it in an executor.
"""

import asyncio
import os
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def _get_client():
    from supabase import create_client
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY"),
    )


async def log_briefing(
    date: str,
    content: Optional[str],
    sent: bool,
    error: Optional[str] = None,
) -> None:
    """Insert a briefing log row. Never raises — logging failures are swallowed."""
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        logger.warning("Supabase not configured — skipping log")
        return

    try:
        loop = asyncio.get_event_loop()
        client = _get_client()
        await loop.run_in_executor(
            None,
            lambda: client.table("briefings").insert({
                "date": date,
                "raw_content": content,
                "sent": sent,
                "error": error,
            }).execute(),
        )
        logger.info("Briefing logged to Supabase (sent=%s)", sent)
    except Exception as exc:
        # Don't let logging failure propagate — the briefing may have been delivered
        logger.error("Failed to log to Supabase: %s", exc)
