"""
Runs the briefing pipeline on a daily cron schedule.

Why AsyncIOScheduler over BackgroundScheduler?
AsyncIOScheduler runs jobs directly on the asyncio event loop, so our
async main() function can be scheduled without creating a new event loop
each time. BackgroundScheduler runs in a thread, which would require
asyncio.run(main()) inside the job — inefficient and potentially problematic
with async libraries that don't support multiple event loops.

Why `await asyncio.Event().wait()`?
This suspends the coroutine indefinitely without busy-waiting. It's the
standard pattern for "keep this async program alive forever." The Event
is never set, so it never resolves — but KeyboardInterrupt will break out.

To test without waiting until 8am, replace CronTrigger with:
    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime, timedelta
    trigger = DateTrigger(run_date=datetime.now() + timedelta(seconds=30))
"""

import asyncio
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

from main import main
from utils.logger import get_logger

logger = get_logger(__name__)


async def run_scheduler() -> None:
    hour = int(os.getenv("BRIEFING_HOUR", 8))
    minute = int(os.getenv("BRIEFING_MINUTE", 0))
    timezone = os.getenv("TIMEZONE", "Europe/Madrid")

    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        main,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id="daily_briefing",
        name="Daily Briefing",
        misfire_grace_time=300,  # run up to 5min late if the trigger was missed
    )
    scheduler.start()
    logger.info("Scheduler started — briefing at %02d:%02d (%s)", hour, minute, timezone)

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(run_scheduler())
