"""Local dev scheduler: runs the scraper on a recurring interval."""

from apscheduler.schedulers.blocking import BlockingScheduler

from scraper.google_maps_scraper import run

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(run, "interval", weeks=1, next_run_time=None)
    print("Scheduler started. Running scraper now, then weekly.")
    run()
    scheduler.start()
