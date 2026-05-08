"""
Collects startup and VC ecosystem news from RSS feeds:
- TechCrunch: deal flow and funding news
- a16z: VC thesis content, where institutional money is moving
- YC Blog: what early-stage founders are building

Same pattern as tech_news.py: feedparser in executor, concurrent fetches.
"""

import asyncio

import feedparser

from utils.logger import get_logger
from utils.retry import async_retry

logger = get_logger(__name__)

RSS_FEEDS = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("a16z", "https://a16z.com/feed/"),
    ("Y Combinator", "https://www.ycombinator.com/blog/rss.xml"),
]

ITEMS_PER_FEED = 4


async def _parse_feed(source: str, url: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    feed = await loop.run_in_executor(None, feedparser.parse, url)

    items = []
    for entry in feed.entries[:ITEMS_PER_FEED]:
        summary = getattr(entry, "summary", "") or ""
        summary = summary[:200].strip()
        items.append({
            "title": entry.get("title", "Sin título"),
            "url": entry.get("link", ""),
            "summary": summary,
            "source": source,
        })
    return items


@async_retry(max_attempts=2, backoff_factor=2)
async def fetch() -> str:
    """Fetch startup / VC news from TechCrunch, a16z, YC. Returns formatted string."""
    tasks = [_parse_feed(name, url) for name, url in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    items = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Startups feed %s failed: %s", RSS_FEEDS[i][0], result)
        else:
            items.extend(result)

    if not items:
        return "[noticias de startups no disponibles]"

    lines = []
    for item in items[:8]:
        line = f"- **[{item['title']}]({item['url']})** ({item['source']})"
        if item["summary"]:
            line += f"\n  {item['summary']}"
        lines.append(line)

    logger.info("startups: %d items", len(items[:8]))
    return "\n\n".join(lines)
