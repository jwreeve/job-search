#!/usr/bin/env python3
"""
Diagnose whether job sites are blocking the scraper.
Visits each site and reports:
  - page title (Cloudflare/challenge pages have telltale titles)
  - any bot-detection signals in the page content
  - number of jobs the scraper found
  - relevant page excerpt so you can judge manually
"""
import asyncio
import sys
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from scraper import SITES, extract_jobs

BOT_SIGNALS = [
    "just a moment",
    "checking your browser",
    "cloudflare",
    "access denied",
    "403 forbidden",
    "captcha",
    "please verify",
    "are you a robot",
    "enable javascript",
    "ddos protection",
    "ray id",
    "unusual traffic",
    "automated access",
    "bot detected",
    "security check",
    "please wait",
    "verifying you are human",
]


async def diagnose_site(browser, site):
    url = site["url"]
    name = site["name"]

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    page = await context.new_page()
    page.set_default_timeout(45000)

    result = {
        "name": name,
        "url": url,
        "status": "unknown",
        "title": None,
        "bot_signals": [],
        "jobs_found": 0,
        "page_excerpt": "",
        "error": None,
    }

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeout:
            pass
        await page.wait_for_timeout(4000)

        title = await page.title()
        result["title"] = title

        body_text = await page.evaluate("() => document.body?.innerText || ''")
        body_lower = body_text.lower()[:3000]

        signals = [s for s in BOT_SIGNALS if s in body_lower]
        result["bot_signals"] = signals

        # First 400 chars of visible text as a sanity check
        result["page_excerpt"] = body_text[:400].replace("\n", " ").strip()

        ct_filter = not site.get("ct_only", True)
        jobs = await extract_jobs(page, url, ct_filter=ct_filter)
        result["jobs_found"] = len(jobs)
        result["status"] = "blocked" if signals else ("ok" if True else "empty")
        if signals:
            result["status"] = "blocked"
        elif len(body_text.strip()) < 200:
            result["status"] = "empty_page"
        else:
            result["status"] = "ok"

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)[:300]
    finally:
        await context.close()

    return result


async def main():
    sites = SITES
    if "--site" in sys.argv:
        idx = sys.argv.index("--site")
        name_filter = sys.argv[idx + 1].lower()
        sites = [s for s in SITES if name_filter in s["name"].lower()]

    print(f"Diagnosing {len(sites)} sites...\n")

    semaphore = asyncio.Semaphore(3)
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )

        async def _run(site):
            async with semaphore:
                r = await diagnose_site(browser, site)
                # Print inline as each completes
                icon = "✓" if r["status"] == "ok" else ("⚠" if r["status"] == "blocked" else "✗")
                print(f"  {icon}  {r['name']:<45} status={r['status']:<12} jobs={r['jobs_found']}")
                if r["bot_signals"]:
                    print(f"       BOT SIGNALS: {r['bot_signals']}")
                if r["error"]:
                    print(f"       ERROR: {r['error'][:120]}")
                if r["title"]:
                    print(f"       Title: {r['title'][:80]}")
                return r

        tasks = [_run(s) for s in sites]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    # Summary
    ok = sum(1 for r in results if isinstance(r, dict) and r["status"] == "ok")
    blocked = sum(1 for r in results if isinstance(r, dict) and r["status"] == "blocked")
    errors = sum(1 for r in results if isinstance(r, dict) and r["status"] == "error")
    empty = sum(1 for r in results if isinstance(r, dict) and r["status"] == "empty_page")
    total_jobs = sum(r["jobs_found"] for r in results if isinstance(r, dict))

    print(f"\n{'='*60}")
    print(f"Summary: {ok} ok | {blocked} blocked | {empty} empty | {errors} errors")
    print(f"Total jobs found: {total_jobs}")

    if blocked:
        print("\nBlocked sites:")
        for r in results:
            if isinstance(r, dict) and r["status"] == "blocked":
                print(f"  - {r['name']}: {r['bot_signals']}")

    print("\nPage excerpts for sites with 0 jobs (non-error):")
    for r in results:
        if isinstance(r, dict) and r["status"] == "ok" and r["jobs_found"] == 0:
            print(f"\n  {r['name']} [{r['title']}]")
            print(f"  {r['page_excerpt'][:200]}")


asyncio.run(main())
