import asyncio
from datetime import datetime
from services.backup_service import run_backup
from core.settings import get_setting, set_setting

async def backup_scheduler_task():
    while True:
        try:
            frequency = get_setting("backup_frequency", "daily").strip().lower()
            if frequency != "off":
                last_run_str = get_setting("last_backup_run")
                
                # Determine interval in seconds
                if frequency == "every 6 hours":
                    interval = 6 * 3600
                elif frequency == "every 12 hours":
                    interval = 12 * 3600
                elif frequency == "daily":
                    interval = 24 * 3600
                elif frequency == "weekly":
                    interval = 7 * 24 * 3600
                else:
                    interval = 24 * 3600 # fallback to daily
                
                should_run = False
                now = datetime.now()
                
                if last_run_str:
                    try:
                        last_run = datetime.fromisoformat(last_run_str)
                        if (now - last_run).total_seconds() >= interval:
                            should_run = True
                    except ValueError:
                        should_run = True
                else:
                    should_run = True
                
                if should_run:
                    run_backup()
                    set_setting("last_backup_run", now.isoformat())
                    
        except Exception as e:
            print(f"Error in backup scheduler: {e}")
            
        await asyncio.sleep(3600) # Check every hour

# Global reference to prevent garbage collection
_scheduler_task = None

async def start_scheduler():
    global _scheduler_task
    _scheduler_task = asyncio.create_task(backup_scheduler_task())
