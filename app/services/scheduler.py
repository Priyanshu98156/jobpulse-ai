import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.database import SessionLocal
from app.connectors.manager import connector_manager

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def scheduled_sync_job():
    logger.info("Executing scheduled job synchronization across all connectors...")
    db = SessionLocal()
    try:
        summary = await connector_manager.sync_all_jobs(db)
        logger.info(f"Scheduled sync complete: {summary}")
    except Exception as e:
        logger.error(f"Error during scheduled sync: {e}")
    finally:
        db.close()

def start_scheduler():
    if not settings.AUTO_SYNC_ENABLED:
        logger.info("Auto sync is disabled in settings. Scheduler will not start background job.")
        return

    if not scheduler.running:
        scheduler.add_job(
            scheduled_sync_job,
            "interval",
            minutes=settings.SYNC_INTERVAL_MINUTES,
            id="job_sync_worker",
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"Background Job Scheduler started. Sync interval: every {settings.SYNC_INTERVAL_MINUTES} minutes.")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background Job Scheduler stopped.")

