import asyncio
import hashlib
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

_stealth = Stealth()

logger = logging.getLogger(__name__)

KEYWORDS = [
    "Psychiatric Mental Health Nurse Practitioner (PMHNP)",
    "PMHNP",
    "PMHNP-BC",
    "Psychiatric Nurse Practitioner",
    "Psych NP",
    "Behavioral Health Nurse Practitioner",
    "Mental Health Nurse Practitioner",
    "Nurse Practitioner – Behavioral Health",
    "Nurse Practitioner – Mental Health",
    "Nurse Practitioner – Psychiatry",
    "Psychiatric APRN",
    "Psychiatric Advanced Practice Nurse",
    "Advanced Psychiatric Nursing",
    "Advanced Practice Psychiatric Nurse",
    "Advanced Practice Registered Nurse (APRN)",
    "APRN",
    "Advanced Practice RN",
    "Advanced Practice Nurse",
    "Advanced Nurse Practitioner",
    "Advanced Practice Provider (APP)",
    "Advanced Practice Provider",
    "Advanced Practice Providers",
    "Advanced Practice Clinician (APC)",
    "Nurse Practitioner",
    "Child and Adolescent Psychiatric Nurse Practitioner",
    "Psychiatric Prescriber",
    "Medication Management Provider",
    "Outpatient Psychiatric NP",
    "Outpatient Psychiatry NP",
    "Adult Psychiatry NP",
    "Family Psychiatry NP",
    "Child & Adolescent PMHNP",
    "Youth Behavioral Health NP",
    "Geriatric Psychiatry NP",
    "Substance Use Disorder NP",
    "Addiction Medicine NP",
    "Dual Diagnosis NP",
    "Community Psychiatry NP",
    "Community Mental Health APRN",
    "Behavioral Health Clinician APRN",
    "Crisis Services NP",
]

CT_LOCATION_TERMS = ["connecticut", ", ct"]

SITES = [
    # CT-specific employer sites — all postings are inherently in Connecticut
    {"url": "https://www.bristolhealth.org/careers", "name": "Bristol Health", "ct_only": True},
    {"url": "https://jobs.ynhhs.org/jobs", "name": "Yale New Haven Health System", "ct_only": True},
    {"url": "https://www.jobapscloud.com/CT/#EmpDiv1", "name": "JobAps Connecticut", "ct_only": True},
    {"url": "https://www.connecticutchildrens.org/careers", "name": "Connecticut Children's", "ct_only": True},
    {
        "url": "https://recruiting.paylocity.com/Recruiting/Jobs/All/9d515094-2479-4c19-8e65-7c11c10e2d49/InterCommunity-Inc",
        "name": "InterCommunity Inc (Paylocity)",
        "ct_only": True,
    },
    {
        "url": "https://css-middlesex-prd.inforcloudsuite.com/hcm/Jobs/form/JobBoard%281,EXTERNAL%29.JobSearchCompositeForm?csk.JobBoard=EXTERNAL&csk.HROrganization=1&menu=JobsNavigationMenu.NewJobSearch",
        "name": "CSS Middlesex (Infor)",
        "ct_only": True,
    },
    {"url": "https://bridgesct.org/about/employment-opportunities/", "name": "Bridges CT", "ct_only": True},
    {
        "url": "https://www.paycomonline.net/v4/ats/web.php/portal/0598C020420D-D1B3BA21EBF9977F627A/career-page",
        "name": "Community Mental Health Affiliates (Paycom)",
        "ct_only": True,
    },
    {"url": "https://jobs.appone.com/CONTINUUMOFCAREINC", "name": "Continuum of Care (AppOne)", "ct_only": True},
    {"url": "https://hfsc.wd503.myworkdayjobs.com/Careers", "name": "Hartford HealthCare (Workday)", "ct_only": True},
    {
        "url": "https://jobs.dayforcehcm.com/wheeler/CANDIDATEPORTAL?searchText=Nurse",
        "name": "Wheeler Clinic (Dayforce)",
        "ct_only": True,
    },
    {
        "url": "https://www.paycomonline.net/v4/ats/web.php/portal/7C0C0E444892D176391CB4939C0EB63C/career-page",
        "name": "Perception Programs (Paycom)",
        "ct_only": True,
    },
    {"url": "https://careers.mwhs1.com/us/en", "name": "McCall Behavioral Health", "ct_only": True},
    {
        "url": "https://phx.us-west.paycomonline.net/v4/ats/web.php/portal/067D-CEED98BE460C97C30F01690FCC42/career-page",
        "name": "Rushford (Paycom)",
        "ct_only": True,
    },
    {"url": "https://www.theconnectioninc.org/careers/", "name": "The Connection Inc", "ct_only": True},
    {"url": "https://www.chc1.com/careers/", "name": "Community Health Center", "ct_only": True},
    {"url": "https://chc1.applicantpro.com/jobs/", "name": "CHC (ApplicantPro)", "ct_only": True},
    {"url": "https://www.trinityhealthofne.org/careers", "name": "Trinity Health of New England", "ct_only": True},
    {"url": "https://your.yale.edu/work-yale/careers", "name": "Yale University Careers", "ct_only": True},
    {"url": "https://www.va.gov/connecticut-health-care/work-with-us/", "name": "VA Connecticut", "ct_only": True},
    {"url": "https://bhcare.org/about-us/careers/", "name": "BHcare", "ct_only": True},
    {"url": "https://www.fcaweb.org/careers/", "name": "Family & Children's Agency", "ct_only": True},
    {"url": "https://www.griffinhealth.org/about/careers/", "name": "Griffin Health", "ct_only": True},
    {"url": "https://www.cgccentralct.org/careers/", "name": "CGC Central CT", "ct_only": True},
    {
        "url": "https://www.paycomonline.net/v4/ats/web.php/portal/0598C020420DD1B3BA21EBF9977F627A/career-page",
        "name": "CMHA (Paycom)",
        "ct_only": True,
    },
    # National boards — CT filtered by URL; jobs must also show CT in scraped text
    {
        "url": "https://careers.unitedhealthgroup.com/global/en/search-results?keywords=psychiatric+mental+health+Connecticut",
        "name": "UnitedHealth Group",
        "ct_only": False,
    },
    {"url": "https://jobs.trinity-health.org/newengland/search-results?keyword=psychiatric+nurse+practitioner&location=Connecticut", "name": "Trinity Health", "ct_only": False},
    {
        "url": "https://www.usajobs.gov/Search/Results?k=psychiatric+mental+health+nurse+practitioner&l=Connecticut",
        "name": "USAJobs (Federal)",
        "ct_only": False,
    },
    {
        "url": "https://wellpathcareers.com/search/?q=&location=Connecticut&radius=10&job_family=Advanced+Practice+Psychiatric+Providers+-+CPOM",
        "name": "Wellpath",
        "ct_only": False,
    },
]

# CSS selectors for job listing elements, tried in order
JOB_SELECTORS = [
    # Workday
    "[data-automation-id='jobItem']",
    "[data-automation-id='compositeJobDetail']",
    # iCIMS
    ".iCIMS_JobsTable tr[data-id]",
    ".iCIMS_Anchor",
    # Paylocity
    ".jss-job-list-item",
    "[class*='jss-job']",
    # AppOne
    ".job-listing-item",
    "div[class*='appone']",
    # Wellpath / generic cards
    ".careers-job-card",
    "[class*='job-card']",
    "[class*='job-listing']",
    "[class*='job-item']",
    "[class*='position-item']",
    "[class*='career-listing']",
    "[class*='job-result']",
    "[class*='posting-item']",
    # Infor CloudSuite
    ".Jobs_JobListItem",
    # Dayforce
    "[class*='dx-datagrid-row']",
    ".job-position",
    # Generic table rows
    "table[class*='job'] tbody tr",
    "table[class*='position'] tbody tr",
    # Generic list items
    "li[class*='job']",
    "li[class*='position']",
    "li[class*='career']",
    # Divs
    "div[class*='job-post']",
    "[class*='search-result-item']",
]


async def scrape_all_sites(
    sites: List[Dict],
    on_site_start=None,
    on_site_done=None,
    stop_check=None,
) -> List[Dict]:
    semaphore = asyncio.Semaphore(3)
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )

        async def _scrape(site):
            async with semaphore:
                if stop_check and stop_check():
                    result = {
                        "source_name": site["name"],
                        "source_url": site["url"],
                        "jobs": [],
                        "status": "stopped",
                        "error": None,
                    }
                    if on_site_done:
                        on_site_done(result)
                    return result
                if on_site_start:
                    on_site_start(site["name"])
                try:
                    result = await asyncio.wait_for(scrape_site(browser, site), timeout=90)
                except asyncio.TimeoutError:
                    result = {
                        "source_name": site["name"],
                        "source_url": site["url"],
                        "jobs": [],
                        "status": "error",
                        "error": "Site scrape timed out after 90s",
                    }
                    logger.warning("Hard timeout scraping %s", site["name"])
                if on_site_done:
                    on_site_done(result)
                return result

        tasks = [_scrape(site) for site in sites]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for site, outcome in zip(sites, outcomes):
            if isinstance(outcome, Exception):
                logger.error("Unhandled error scraping %s: %s", site["name"], outcome)
                err = {
                    "source_name": site["name"],
                    "source_url": site["url"],
                    "jobs": [],
                    "status": "error",
                    "error": str(outcome),
                }
                results.append(err)
                if on_site_done:
                    on_site_done(err)
            else:
                results.append(outcome)

        await browser.close()

    return results


async def scrape_site(browser, site: Dict) -> Dict:
    url = site["url"]
    name = site["name"]
    jobs = []
    error = None

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        java_script_enabled=True,
    )
    page = await context.new_page()
    await _stealth.apply_stealth_async(page)
    page.set_default_timeout(45000)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeout:
            pass

        # Extra wait for heavy SPAs (Workday, Paycom, etc.)
        await page.wait_for_timeout(4000)

        ct_filter = not site.get("ct_only", True)
        jobs = await extract_jobs(page, url, ct_filter=ct_filter)
        logger.info("%-40s  %d matching jobs", name, len(jobs))

    except Exception as exc:
        error = str(exc)[:500]
        logger.warning("Error scraping %s: %s", name, error)
    finally:
        await context.close()

    return {
        "source_name": name,
        "source_url": url,
        "jobs": jobs,
        "status": "error" if error else "success",
        "error": error,
    }


async def extract_jobs(page: Page, source_url: str, ct_filter: bool = False) -> List[Dict]:
    jobs: List[Dict] = []

    # Strategy 1: known job-card selectors
    for selector in JOB_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            if not elements:
                continue

            for el in elements:
                try:
                    text = (await el.inner_text()).strip()
                    if not text or len(text) > 600:
                        continue

                    matched = _find_matches(text)
                    if not matched:
                        continue

                    if ct_filter and not _is_ct_location(text):
                        continue

                    # Grab link
                    href = await el.get_attribute("href")
                    if not href:
                        a = await el.query_selector("a")
                        if a:
                            href = await a.get_attribute("href")

                    title = _first_line(text)
                    jobs.append(
                        {
                            "title": title,
                            "url": _abs(href, source_url),
                            "source_url": source_url,
                            "matched_keywords": ", ".join(matched),
                        }
                    )
                except Exception:
                    continue

            if jobs:
                return _dedup(jobs, source_url)
        except Exception:
            continue

    # Strategy 2: scan all anchor text for keyword matches
    try:
        anchors = await page.query_selector_all("a")
        for a in anchors:
            try:
                text = (await a.inner_text()).strip()
                if not text or len(text) > 300 or len(text) < 6:
                    continue
                if text.lower() in {"apply", "back", "next", "previous", "home", "careers", "jobs"}:
                    continue

                matched = _find_matches(text)
                if not matched:
                    continue

                if ct_filter and not _is_ct_location(text):
                    continue

                href = await a.get_attribute("href")
                jobs.append(
                    {
                        "title": text[:200],
                        "url": _abs(href, source_url),
                        "source_url": source_url,
                        "matched_keywords": ", ".join(matched),
                    }
                )
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Anchor scan failed for %s: %s", source_url, exc)

    # Strategy 3: scan heading elements
    if not jobs:
        try:
            headings = await page.query_selector_all("h1, h2, h3, h4")
            for h in headings:
                try:
                    text = (await h.inner_text()).strip()
                    if not text or len(text) > 200:
                        continue
                    matched = _find_matches(text)
                    if not matched:
                        continue
                    if ct_filter and not _is_ct_location(text):
                        continue
                    # Try to find a nearby link
                    parent = await h.evaluate_handle("el => el.closest('a') || el.parentElement?.querySelector('a')")
                    href = None
                    try:
                        href = await parent.get_attribute("href")
                    except Exception:
                        pass
                    jobs.append(
                        {
                            "title": text[:200],
                            "url": _abs(href, source_url),
                            "source_url": source_url,
                            "matched_keywords": ", ".join(matched),
                        }
                    )
                except Exception:
                    continue
        except Exception:
            pass

    # Strategy 4: full rendered-page text scan — catches SPAs where selectors miss
    if not jobs:
        try:
            full_text = await page.evaluate("() => document.body?.innerText || ''")
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            for line in lines:
                if len(line) > 250 or len(line) < 5:
                    continue
                matched = _find_matches(line)
                if not matched:
                    continue
                if ct_filter and not _is_ct_location(line):
                    continue
                jobs.append(
                    {
                        "title": line[:200],
                        "url": source_url,
                        "source_url": source_url,
                        "matched_keywords": ", ".join(matched),
                    }
                )
        except Exception as exc:
            logger.debug("Full-page text scan failed for %s: %s", source_url, exc)

    return _dedup(jobs, source_url)


def _is_ct_location(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in CT_LOCATION_TERMS)


def _find_matches(text: str) -> List[str]:
    text_lower = text.lower()
    seen = set()
    matched = []
    for kw in KEYWORDS:
        if kw.lower() in text_lower and kw not in seen:
            seen.add(kw)
            matched.append(kw)
    return matched


def _first_line(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[0][:200] if lines else text[:200]


def _abs(href: Optional[str], base: str) -> str:
    if not href:
        return base
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def make_job_key(title: str, source_url: str) -> str:
    raw = f"{title.lower().strip()}|{source_url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _dedup(jobs: List[Dict], source_url: str) -> List[Dict]:
    seen: set = set()
    unique = []
    for j in jobs:
        key = make_job_key(j["title"], source_url)
        if key not in seen:
            seen.add(key)
            j["job_key"] = key
            unique.append(j)
    return unique
