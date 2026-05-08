import os
from datetime import date
from groq import Groq

from agent.prompts import BRIEFING_SYSTEM_PROMPT, BRIEFING_USER_TEMPLATE
from utils.logger import get_logger
from utils.retry import async_retry

logger = get_logger(__name__)

# Synchronous client is fine here: the API call happens after all async
# collection is done, so we don't block any concurrent work.
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


@async_retry(max_attempts=3, backoff_factor=2)
async def create_briefing(sections: dict[str, str]) -> str:
    """
    Sends collected section data to Groq and returns the generated briefing text.

    sections keys: tech_news, arxiv_papers, github_repos,
                   portfolio_data, fear_greed_value,
                   fear_greed_label, startup_news
    """
    user_prompt = BRIEFING_USER_TEMPLATE.format(
        date=date.today().strftime("%A, %d de %B de %Y"),
        tech_news=sections.get("tech_news", "[sin datos]"),
        arxiv_papers=sections.get("arxiv_papers", "[sin datos]"),
        github_repos=sections.get("github_repos", "[sin datos]"),
        portfolio_data=sections.get("portfolio_data", "[sin datos]"),
        fear_greed_value=sections.get("fear_greed_value", "N/A"),
        fear_greed_label=sections.get("fear_greed_label", "N/A"),
        startup_news=sections.get("startup_news", "[sin datos]"),
    )

    response = _client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1500,
        messages=[
            {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content