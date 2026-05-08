"""
Fetches recent AI/ML papers from ArXiv RSS feeds.

Three category feeds run concurrently. Papers are deduplicated by ArXiv ID
because the same paper often appears in multiple category feeds (e.g., a paper
on LLMs appears in both cs.AI and cs.CL).

We take the 4 most recent papers — ArXiv publishes in daily batches, so
"most recent" means today's submission batch.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser

from utils.logger import get_logger
from utils.retry import async_retry

logger = get_logger(__name__)

ARXIV_FEEDS = [
    ("cs.AI", "https://rss.arxiv.org/rss/cs.AI"),
    ("cs.LG", "https://rss.arxiv.org/rss/cs.LG"),
    ("cs.CL", "https://rss.arxiv.org/rss/cs.CL"),
]

PAPERS_TO_TAKE = 4
ABSTRACT_MAX_CHARS = 300


@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: str
    abstract: str
    url: str
    published: str


def _extract_arxiv_id(entry_id: str) -> str:
    """
    ArXiv entry IDs look like: http://arxiv.org/abs/2405.01234v1
    We strip the version suffix to use as a stable deduplication key.
    """
    match = re.search(r"abs/(\d{4}\.\d+)", entry_id)
    return match.group(1) if match else entry_id


def _parse_authors(entry) -> str:
    authors = getattr(entry, "authors", [])
    if authors:
        names = [a.get("name", "") for a in authors[:3]]
        suffix = " et al." if len(authors) > 3 else ""
        return ", ".join(n for n in names if n) + suffix
    return getattr(entry, "author", "N/A")


async def _fetch_feed(category: str, url: str) -> list[Paper]:
    loop = asyncio.get_event_loop()
    feed = await loop.run_in_executor(None, feedparser.parse, url)

    papers = []
    for entry in feed.entries:
        arxiv_id = _extract_arxiv_id(entry.get("id", ""))
        abstract = getattr(entry, "summary", "") or ""
        # ArXiv abstracts often start with "Abstract: " — clean that up
        abstract = re.sub(r"^Abstract:\s*", "", abstract).strip()
        abstract = abstract[:ABSTRACT_MAX_CHARS]

        papers.append(Paper(
            arxiv_id=arxiv_id,
            title=entry.get("title", "Sin título").replace("\n", " "),
            authors=_parse_authors(entry),
            abstract=abstract,
            url=entry.get("link", f"https://arxiv.org/abs/{arxiv_id}"),
            published=entry.get("published", ""),
        ))
    return papers


@async_retry(max_attempts=2, backoff_factor=2)
async def fetch() -> str:
    """Fetch and deduplicate ArXiv papers across cs.AI, cs.LG, cs.CL."""
    tasks = [_fetch_feed(cat, url) for cat, url in ARXIV_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen_ids: set[str] = set()
    papers: list[Paper] = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("ArXiv feed %s failed: %s", ARXIV_FEEDS[i][0], result)
            continue
        for paper in result:
            if paper.arxiv_id not in seen_ids:
                seen_ids.add(paper.arxiv_id)
                papers.append(paper)

    if not papers:
        return "[papers de ArXiv no disponibles]"

    # Take the first N papers (feeds return them newest-first)
    selected = papers[:PAPERS_TO_TAKE]
    lines = []
    for p in selected:
        lines.append(
            f"- **{p.title}** — {p.authors}\n"
            f"  {p.abstract}...\n"
            f"  [arxiv.org]({p.url})"
        )

    logger.info("arxiv_papers: %d papers", len(selected))
    return "\n\n".join(lines)
