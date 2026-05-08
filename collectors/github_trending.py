"""
Scrapes GitHub Trending (monthly) and avoids repeating repos across days.

Seen repos are persisted in storage/seen_repos.json. Each run:
  1. Load previously shown repos
  2. Scrape the monthly trending list (larger pool than daily)
  3. Filter out already-seen repos
  4. Take the top 5 unseen ones
  5. Save them so tomorrow's run skips them

Why monthly instead of daily?
Monthly trending = a larger, more stable pool with proven repos.
Daily trending can be noisy (a repo spikes for one day then disappears).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from utils.logger import get_logger
from utils.retry import async_retry

logger = get_logger(__name__)

TRENDING_URL = "https://github.com/trending?since=monthly&spoken_language_code="
REPOS_TO_SHOW = 5
SEEN_REPOS_FILE = Path(__file__).parent.parent / "storage" / "seen_repos.json"
SEEN_REPOS_MAX = 60  # keep rolling window so repos can resurface after ~2 months
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class TrendingRepo:
    name: str
    url: str
    description: str
    stars_today: str
    language: str


def _load_seen() -> set[str]:
    try:
        with open(SEEN_REPOS_FILE) as f:
            return set(json.load(f).get("repos", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_seen(seen: set[str]) -> None:
    # Keep a rolling window to prevent unbounded growth
    recent = list(seen)[-SEEN_REPOS_MAX:]
    SEEN_REPOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_REPOS_FILE, "w") as f:
        json.dump({"repos": recent}, f, indent=2)


def _parse_repos(html: str) -> list[TrendingRepo]:
    soup = BeautifulSoup(html, "lxml")
    repos = []

    for article in soup.select("article.Box-row"):
        name_el = article.select_one("h2.h3 a")
        if not name_el:
            continue
        repo_path = name_el["href"].strip()
        name = repo_path.lstrip("/")
        url = f"https://github.com{repo_path}"

        desc_el = article.select_one("p.col-9")
        description = desc_el.text.strip() if desc_el else "Sin descripción"

        stars_el = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = stars_el.text.strip() if stars_el else "N/A"

        lang_el = article.select_one("span[itemprop='programmingLanguage']")
        language = lang_el.text.strip() if lang_el else "N/A"

        repos.append(TrendingRepo(
            name=name, url=url, description=description,
            stars_today=stars_today, language=language,
        ))

    return repos


@async_retry(max_attempts=2, backoff_factor=2)
async def fetch() -> str:
    """Scrape GitHub monthly trending, skip already-seen repos, return top 5 new ones."""
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get(TRENDING_URL, timeout=15, follow_redirects=True)
        response.raise_for_status()

    all_repos = _parse_repos(response.text)

    if not all_repos:
        return "[GitHub Trending no disponible — posible cambio en el HTML]"

    seen = _load_seen()
    new_repos = [r for r in all_repos if r.name not in seen]

    # If everything has been seen (unlikely), reset and use all
    if not new_repos:
        logger.info("github_trending: all repos seen before, resetting history")
        seen = set()
        new_repos = all_repos

    selected = new_repos[:REPOS_TO_SHOW]

    # Persist the shown repos
    seen.update(r.name for r in selected)
    _save_seen(seen)

    lines = []
    for repo in selected:
        lines.append(
            f"- **[{repo.name}]({repo.url})** ⭐ {repo.stars_today} — {repo.language}\n"
            f"  {repo.description}"
        )

    logger.info("github_trending: %d new repos (pool: %d, seen: %d)",
                len(selected), len(all_repos), len(seen))
    return "\n\n".join(lines)
