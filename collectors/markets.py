"""
Collects market data from two sources:

1. yfinance — portfolio price data (synchronous → run in executor)
2. Fear & Greed Index — crypto sentiment from api.alternative.me

Why run_in_executor for yfinance?
yfinance is a synchronous library that uses requests under the hood.
Calling it directly in an async function would block the event loop,
preventing other coroutines from running while we wait for Yahoo Finance.
run_in_executor moves the blocking call to a thread pool, freeing the
event loop to handle other work.
"""

import asyncio
import os

import httpx
import pandas as pd
import yfinance as yf

from utils.logger import get_logger
from utils.retry import async_retry

logger = get_logger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/"


def _build_tickers() -> list[str]:
    stocks = os.getenv("PORTFOLIO_STOCKS", "NVDA,MSFT,AAPL,AMZN").split(",")
    etfs = os.getenv("PORTFOLIO_ETFS", "SPY,QQQ").split(",")
    crypto = os.getenv("PORTFOLIO_CRYPTO", "BTC-USD,ETH-USD").split(",")
    return [t.strip() for t in stocks + etfs + crypto if t.strip()]


def _download_prices(tickers: list[str]) -> str:
    """Synchronous yfinance call — must run in executor."""
    try:
        data = yf.download(
            tickers,
            period="5d",   # 5 calendar days guarantees ≥2 trading days across timezones
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if data.empty or "Close" not in data.columns:
            return "[sin datos de precios]"

        close = data["Close"]

        # yfinance returns a Series when only one ticker succeeds — normalize to DataFrame
        if isinstance(close, pd.Series):
            close = close.to_frame(name=close.name or tickers[0])

        # Drop rows where ALL values are NaN (market not yet open today, weekends)
        close = close.dropna(how="all")

        if len(close) < 2:
            return "[datos de precios insuficientes — puede que el mercado aún no haya abierto]"

        rows = []
        for ticker in tickers:
            if ticker not in close.columns:
                continue
            prev = close[ticker].iloc[-2]
            curr = close[ticker].iloc[-1]
            if pd.isna(prev) or pd.isna(curr):
                continue
            pct = (curr - prev) / prev * 100
            sign = "+" if pct >= 0 else ""
            rows.append(f"{ticker:<12} | ${curr:>10.2f} | {sign}{pct:.2f}%")

        return "\n".join(rows) if rows else "[sin datos de precios]"
    except Exception as exc:
        logger.error("yfinance error: %s", exc)
        return f"[error al obtener precios: {exc}]"


async def _fetch_fear_greed(client: httpx.AsyncClient) -> tuple[str, str]:
    try:
        response = await client.get(FEAR_GREED_URL, timeout=10)
        response.raise_for_status()
        item = response.json()["data"][0]
        return item["value"], item["value_classification"]
    except Exception as exc:
        logger.warning("Fear & Greed fetch failed: %s", exc)
        return "N/A", "N/A"


@async_retry(max_attempts=2, backoff_factor=2)
async def fetch() -> dict[str, str]:
    """
    Returns a dict with keys: portfolio_data, fear_greed_value, fear_greed_label.

    Unlike other collectors, markets returns a dict because main.py
    needs to unpack the values into separate template slots.
    """
    tickers = _build_tickers()
    loop = asyncio.get_event_loop()

    async with httpx.AsyncClient() as client:
        portfolio_task = loop.run_in_executor(None, _download_prices, tickers)
        fear_greed_task = _fetch_fear_greed(client)

        portfolio_data, (fg_value, fg_label) = await asyncio.gather(
            portfolio_task, fear_greed_task
        )

    logger.info("markets: portfolio + fear&greed collected")
    return {
        "portfolio_data": portfolio_data,
        "fear_greed_value": fg_value,
        "fear_greed_label": fg_label,
    }
