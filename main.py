"""
Entry point for the briefing pipeline.

Data flow:
  asyncio.gather() → 5 collectors run in parallel
      ↓
  summarizer  → Claude Sonnet API
      ↓
  formatter   → Markdown to Telegram HTML
      ↓
  telegram_bot → send to chat
      ↓ (always, in finally)
  supabase_client → log the run

Why return_exceptions=True in gather()?
Without it, one collector raising an exception cancels all others and the
briefing fails entirely. With it, exceptions are returned as values — we
handle them gracefully as "[source unavailable]" sections and still generate
a partial briefing. A degraded briefing beats no briefing.

Why try/except/finally?
The finally block guarantees Supabase logging happens regardless of what
failed. You always want an audit trail — sent=false + error tells you what broke.
"""

import asyncio
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from agent import formatter, summarizer
from collectors import arxiv_papers, github_trending, markets, startups, tech_news
from delivery import telegram_bot
from storage import supabase_client
from utils.logger import get_logger

logger = get_logger(__name__)

COLLECTOR_NAMES = ["tech_news", "arxiv_papers", "github_trending", "markets", "startups"]


def _process_results(results: list) -> dict[str, str]:
    """
    Unpack asyncio.gather() results into the sections dict for the prompt template.
    Exceptions become graceful "[source unavailable]" strings.

    markets.fetch() returns a dict (4 keys) instead of a plain string because
    the prompt template needs its values in separate slots.
    """
    sections: dict[str, str] = {}
    defaults = {
        "tech_news": "[noticias tech no disponibles]",
        "arxiv_papers": "[papers no disponibles]",
        "github_repos": "[GitHub trending no disponible]",
        "startup_news": "[noticias de startups no disponibles]",
        "portfolio_data": "[datos de portafolio no disponibles]",
        "fear_greed_value": "N/A",
        "fear_greed_label": "N/A",
    }
    sections.update(defaults)

    for name, result in zip(COLLECTOR_NAMES, results):
        if isinstance(result, Exception):
            logger.warning("Collector '%s' failed: %s", name, result)
            continue

        if name == "markets":
            # markets.fetch() returns a dict with 4 keys
            if isinstance(result, dict):
                sections.update(result)
        elif name == "startups":
            sections["startup_news"] = result
        elif name == "github_trending":
            sections["github_repos"] = result
        elif name == "arxiv_papers":
            sections["arxiv_papers"] = result
        elif name == "tech_news":
            sections["tech_news"] = result

    return sections


async def main() -> None:
    today = date.today().isoformat()
    raw_content: str | None = None
    sent = False
    error_msg: str | None = None

    try:
        logger.info("=== Iniciando pipeline de briefing (%s) ===", today)

        # ── Collect — all 5 sources fire simultaneously ───────────────────
        results = await asyncio.gather(
            tech_news.fetch(),
            arxiv_papers.fetch(),
            github_trending.fetch(),
            markets.fetch(),
            startups.fetch(),
            return_exceptions=True,
        )

        sections = _process_results(results)
        logger.info("Recolección completada")

        # ── Synthesize ────────────────────────────────────────────────────
        raw_content = await summarizer.create_briefing(sections)

        # ── Format + deliver ──────────────────────────────────────────────
        chunks = formatter.format_for_telegram(raw_content)
        await telegram_bot.send_briefing(chunks)
        sent = True
        logger.info("=== Briefing enviado exitosamente ===")

    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        error_msg = str(exc)

    finally:
        await supabase_client.log_briefing(
            date=today,
            content=raw_content,
            sent=sent,
            error=error_msg,
        )


if __name__ == "__main__":
    asyncio.run(main())
