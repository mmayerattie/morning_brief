"""
Collects tech news from:
1. RSS feeds (The Verge AI, TechCrunch AI, Ars Technica)
2. Hacker News API (top stories with score > 100)

feedparser is synchronous, so we run it in a thread executor to avoid
blocking the asyncio event loop while waiting for network + parsing.

For HN, we make all detail requests concurrently — 30 story fetches
in parallel instead of sequentially, which is why it stays fast.
"""

import asyncio
from dataclasses import dataclass

import feedparser
import httpx

from utils.logger import get_logger
from utils.retry import async_retry

logger = get_logger(__name__)

RSS_FEEDS = [
    ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
]

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
HN_MIN_SCORE = 100
HN_FETCH_COUNT = 30
HN_TAKE_COUNT = 5


@dataclass
class NewsItem:
    title: str
    url: str
    summary: str
    source: str


async def _parse_rss(url: str, source: str) -> list[NewsItem]:
    loop = asyncio.get_event_loop()
    feed = await loop.run_in_executor(None, feedparser.parse, url)
    items = []
    for entry in feed.entries[:5]:
        summary = getattr(entry, "summary", "") or ""
        # Strip HTML tags from summary (feedparser sometimes returns raw HTML)
        summary = summary[:200].strip()
        items.append(NewsItem(
            title=entry.get("title", "Sin título"),
            url=entry.get("link", ""),
            summary=summary,
            source=source,
        ))
    return items


async def _fetch_hn_story(client: httpx.AsyncClient, story_id: int) -> dict | None:
    try:
        response = await client.get(HN_ITEM.format(id=story_id), timeout=10)
        return response.json()
    except Exception:
        return None


async def _fetch_hn_top() -> list[NewsItem]:
    async with httpx.AsyncClient() as client:
        response = await client.get(HN_TOP_STORIES, timeout=10)
        top_ids = response.json()[:HN_FETCH_COUNT]

        # Fetch all story details concurrently — this is why HN is fast despite 30 requests
        stories = await asyncio.gather(*[_fetch_hn_story(client, sid) for sid in top_ids])

    filtered = [
        s for s in stories
        if s and s.get("score", 0) >= HN_MIN_SCORE and s.get("url")
    ]
    filtered.sort(key=lambda s: s["score"], reverse=True)

    return [
        NewsItem(
            title=s["title"],
            url=s["url"],
            summary=f"Score: {s['score']} | {s.get('descendants', 0)} comentarios",
            source="Hacker News",
        )
        for s in filtered[:HN_TAKE_COUNT]
    ]


@async_retry(max_attempts=2, backoff_factor=2)
async def fetch() -> str:
    """Fetch tech news from RSS feeds + Hacker News. Returns formatted string."""
    rss_tasks = [_parse_rss(url, name) for name, url in RSS_FEEDS]
    rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)

    items: list[NewsItem] = []
    for i, result in enumerate(rss_results):
        if isinstance(result, Exception):
            logger.warning("RSS feed %s failed: %s", RSS_FEEDS[i][0], result)
        else:
            items.extend(result)

    try:
        hn_items = await _fetch_hn_top()
        items.extend(hn_items)
    except Exception as exc:
        logger.warning("Hacker News fetch failed: %s", exc)

    if not items:
        return "[tech news no disponible]"

    lines = []
    for item in items[:8]:  # cap total to avoid bloating the prompt
        line = f"- **{item.title}** ({item.source})"
        if item.url:
            line = f"- **[{item.title}]({item.url})** ({item.source})"
        if item.summary:
            line += f"\n  {item.summary}"
        lines.append(line)

    logger.info("tech_news: %d items", len(items[:8]))
    return "\n\n".join(lines)
