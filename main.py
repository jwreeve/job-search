from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import logging
import os
from typing import Optional, List

from models import Job, ScanLog, get_db, SessionLocal
from scraper import scrape_all_sites, SITES, make_job_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")
_scan_running = False
_scan_start_time: Optional[datetime] = None
_scan_progress: List[dict] = []
_scan_stop = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(run_scan, "interval", hours=6, id="periodic_scan", replace_existing=True)
    scheduler.start()
    logger.info("Healthcare Job Monitor started — auto-scan every 6 hours.")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Healthcare Job Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _commit_results(results: list) -> int:
    if not results:
        return 0
    db = SessionLocal()
    new_count = 0
    try:
        for site_result in results:
            jobs_new = 0
            jobs_duplicate = 0
            for jd in site_result["jobs"]:
                key = jd.get("job_key") or make_job_key(jd["title"], jd["source_url"])
                if db.query(Job).filter(Job.job_key == key).first():
                    jobs_duplicate += 1
                else:
                    db.add(Job(
                        job_key=key,
                        title=jd["title"],
                        url=jd["url"],
                        source_url=jd["source_url"],
                        source_name=site_result["source_name"],
                        matched_keywords=jd["matched_keywords"],
                        is_new=True,
                    ))
                    jobs_new += 1
            db.add(ScanLog(
                source_url=site_result["source_url"],
                source_name=site_result["source_name"],
                jobs_found=len(site_result["jobs"]),
                jobs_new=jobs_new,
                jobs_duplicate=jobs_duplicate,
                status=site_result["status"],
                error_message=site_result.get("error"),
            ))
            new_count += jobs_new
        db.commit()
    finally:
        db.close()
    return new_count


async def run_scan():
    global _scan_running, _scan_start_time, _scan_progress, _scan_stop
    if _scan_running:
        logger.info("Scan already running, skipping.")
        return

    _scan_running = True
    _scan_stop = False
    _scan_start_time = datetime.utcnow()
    _accumulated: list = []

    _scan_progress = [
        {"name": s["name"], "status": "pending", "jobs_found": None, "error": None}
        for s in SITES
    ]

    def on_start(name: str):
        for p in _scan_progress:
            if p["name"] == name:
                p["status"] = "running"
                break

    def on_done(result: dict):
        for p in _scan_progress:
            if p["name"] == result["source_name"]:
                p["status"] = result["status"]
                p["jobs_found"] = len(result["jobs"])
                p["error"] = result.get("error")
                break
        _accumulated.append(result)

    logger.info("Scan started across %d sites.", len(SITES))
    try:
        await scrape_all_sites(
            SITES,
            on_site_start=on_start,
            on_site_done=on_done,
            stop_check=lambda: _scan_stop,
        )
        n = _commit_results(_accumulated)
        logger.info("Scan complete — %d new job(s) found.", n)
    except Exception:
        logger.exception("Scan failed with an unhandled error.")
        _commit_results(_accumulated)
    finally:
        _scan_running = False


# ── API routes ──────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs(
    new_only: bool = False,
    keyword: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Job)
    if new_only:
        q = q.filter(Job.is_new == True)
    if keyword:
        q = q.filter(Job.matched_keywords.ilike(f"%{keyword}%"))
    if source:
        q = q.filter(Job.source_name.ilike(f"%{source}%"))
    return [_to_dict(j) for j in q.order_by(Job.is_new.desc(), Job.first_seen.desc()).all()]


@app.post("/api/jobs/{job_id}/toggle-save")
def toggle_save(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.is_saved = not job.is_saved
    db.commit()
    return {"ok": True, "is_saved": job.is_saved}


@app.post("/api/jobs/{job_id}/mark-seen")
def mark_seen(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.is_new = False
    db.commit()
    return {"ok": True}


@app.post("/api/jobs/mark-all-seen")
def mark_all_seen(db: Session = Depends(get_db)):
    db.query(Job).filter(Job.is_new == True).update({"is_new": False})
    db.commit()
    return {"ok": True}


@app.delete("/api/jobs")
def clear_jobs(db: Session = Depends(get_db)):
    deleted = db.query(Job).filter(Job.is_saved == False).delete()
    db.commit()
    return {"ok": True, "deleted": deleted}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"ok": True}


@app.post("/api/scan")
async def trigger_scan():
    if _scan_running:
        return {"status": "already_running", "message": "A scan is already in progress."}
    asyncio.create_task(run_scan())
    return {"status": "started", "message": "Scan started in the background."}


@app.post("/api/scan/stop")
async def stop_scan():
    global _scan_stop
    if not _scan_running:
        return {"status": "not_running"}
    _scan_stop = True
    return {"status": "stopping"}


@app.get("/api/scan/progress")
def get_scan_progress():
    elapsed = None
    if _scan_start_time:
        elapsed = (datetime.utcnow() - _scan_start_time).total_seconds()
    return {
        "in_progress": _scan_running,
        "elapsed_seconds": elapsed,
        "sites": _scan_progress,
    }


@app.get("/api/scan/logs")
def scan_logs(db: Session = Depends(get_db)):
    logs = db.query(ScanLog).order_by(ScanLog.scanned_at.desc()).limit(300).all()
    return [
        {
            "id": l.id,
            "scanned_at": l.scanned_at.isoformat() if l.scanned_at else None,
            "source_name": l.source_name,
            "source_url": l.source_url,
            "jobs_found": l.jobs_found,
            "jobs_new": l.jobs_new,
            "jobs_duplicate": l.jobs_duplicate,
            "status": l.status,
            "error_message": l.error_message,
        }
        for l in logs
    ]


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    total = db.query(Job).count()
    new_count = db.query(Job).filter(Job.is_new == True).count()
    last_log = db.query(ScanLog).order_by(ScanLog.scanned_at.desc()).first()
    return {
        "total_jobs": total,
        "new_jobs": new_count,
        "last_scan": last_log.scanned_at.isoformat() if last_log and last_log.scanned_at else None,
        "scan_in_progress": _scan_running,
        "sites_count": len(SITES),
    }


def _to_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "title": j.title,
        "url": j.url,
        "source_url": j.source_url,
        "source_name": j.source_name,
        "matched_keywords": j.matched_keywords,
        "first_seen": j.first_seen.isoformat() if j.first_seen else None,
        "is_new": j.is_new,
        "is_saved": j.is_saved or False,
    }


# ── Local-scraper ingest ─────────────────────────────────────────────────────

@app.post("/api/ingest")
def ingest_jobs(payload: dict, db: Session = Depends(get_db)):
    secret = os.getenv("INGEST_SECRET")
    if secret and payload.get("secret") != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    jobs_by_source: dict = {}
    for jd in payload.get("jobs", []):
        jobs_by_source.setdefault(jd["source_url"], []).append(jd)

    new_count = 0
    for log in payload.get("logs", []):
        jobs_new = 0
        jobs_duplicate = 0
        for jd in jobs_by_source.get(log["source_url"], []):
            key = jd.get("job_key") or make_job_key(jd["title"], jd["source_url"])
            if db.query(Job).filter(Job.job_key == key).first():
                jobs_duplicate += 1
            else:
                db.add(Job(
                    job_key=key,
                    title=jd["title"],
                    url=jd["url"],
                    source_url=jd["source_url"],
                    source_name=jd["source_name"],
                    matched_keywords=jd["matched_keywords"],
                    is_new=True,
                ))
                jobs_new += 1
        db.add(ScanLog(
            source_url=log["source_url"],
            source_name=log["source_name"],
            jobs_found=log["jobs_found"],
            jobs_new=jobs_new,
            jobs_duplicate=jobs_duplicate,
            status=log["status"],
            error_message=log.get("error"),
        ))
        new_count += jobs_new

    db.commit()
    logger.info("Ingest complete — %d new job(s) added.", new_count)
    return {"ok": True, "new_jobs": new_count}


# ── Static frontend ──────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")
