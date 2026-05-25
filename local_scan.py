#!/usr/bin/env python3
"""
Run this locally on a cron to scrape from your home IP and push results
to the hosted app. Avoids datacenter IP blocks that affect Fly.io.

Usage:
    python3 local_scan.py
    python3 local_scan.py --url https://jobs.jonathanreeve.com

Cron (every 6 hours):
    0 */6 * * * /path/to/job-monitor/.venv/bin/python /path/to/job-monitor/local_scan.py >> /path/to/job-monitor/scan.log 2>&1
"""
import asyncio
import json
import sys
import urllib.request
from scraper import scrape_all_sites, SITES

HOST = "https://jobs.jonathanreeve.com"
SECRET = "24858000338965"  # set INGEST_SECRET on the server and paste it here

for arg in sys.argv[1:]:
    if arg.startswith("--url="):
        HOST = arg.split("=", 1)[1]
    elif arg == "--url" and sys.argv.index(arg) + 1 < len(sys.argv):
        HOST = sys.argv[sys.argv.index(arg) + 1]


async def main():
    print("Scraping all sites…")
    results = await scrape_all_sites(SITES)

    jobs = []
    logs = []
    for r in results:
        logs.append({
            "source_url": r["source_url"],
            "source_name": r["source_name"],
            "jobs_found": len(r["jobs"]),
            "status": r["status"],
            "error": r.get("error"),
        })
        for j in r["jobs"]:
            j["source_name"] = r["source_name"]
            jobs.append(j)

    print(f"Scrape done — {len(jobs)} jobs across {len(results)} sites. Uploading…")

    payload = json.dumps({"jobs": jobs, "logs": logs, "secret": SECRET}).encode()
    req = urllib.request.Request(
        f"{HOST}/api/ingest",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    print(f"Done — {result['new_jobs']} new job(s) added to {HOST}")


asyncio.run(main())
